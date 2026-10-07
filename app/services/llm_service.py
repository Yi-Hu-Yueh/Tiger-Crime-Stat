"""NVIDIA non-streaming chat. Credentials are never included in prompts/errors.

Verified 2026-10-05:
https://docs.api.nvidia.com/nim/reference/z-ai-glm-5-3-flash
https://docs.api.nvidia.com/nim/reference/z-ai-glm-5-3-flash-infer
NVIDIA-linked serving recipe: https://recipes.vllm.ai/zai-org/GLM-5.3
httpx sends chat_template_kwargs directly in JSON (not an extra_body wrapper).
"""
from __future__ import annotations

import asyncio
import html
import json
import os
import re
import time
import unicodedata
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Annotated, Literal

import httpx
from pydantic import Field, ValidationError, model_validator
from starlette.concurrency import run_in_threadpool

from app.services.chat_router import ALL_YEARS, route_message
from app.services.chat_answers import deterministic_answer, numbers_grounded
from app.services.dashboard_actions import ACTION_TOOL, UpdateView, validate_actions, view_actions
from app.services.dashboard_router import conversation_scope, route_dashboard_message
from app.services.scope_delta import extract_scope_delta
from app.services.llm_tools import Counties, Crimes, Filters, Months, Name, StrictModel, TOOL_REGISTRY, TOOLS, Years, execute_tool

MODEL = "z-ai/glm-5.3-flash"
SUPPORTED_MODELS = (MODEL, "z-ai/glm-5.3")
BASE_URL = "https://integrate.api.nvidia.com/v1"
MAX_MODEL_ROUNDS = 3
MAX_ATTEMPTS = 2
MAX_TOKENS = 1024
TOTAL_TIMEOUT = 90
HTTP_TIMEOUT = httpx.Timeout(connect=5, read=35, write=10, pool=5)
RETRY_BACKOFF = 0.5
MAX_RETRY_DELAY = 2.0
TRANSIENT_CONNECTION_ERRORS = (httpx.ConnectError, httpx.ReadError, httpx.WriteError, httpx.RemoteProtocolError, httpx.ConnectTimeout)
SYSTEM_PROMPT = """你是犯罪統計助理，用繁體中文簡潔回答，不輸出推理。
泛稱「竊盜」僅指住宅竊盜、汽車竊盜、機車竊盜三類合計，不是官方獨立案類。
使用純文字，不使用 Markdown 粗體、標題或連結語法；條列用「•」，來源直接附網址。
事件背景回答限約5至10行，只選少數相關事件，保留資料品質限制及時間重疊不代表因果的提醒。
數字、排名、差異及趨勢只用本輪工具；不得自行計算或臆造。兩年比較用 query_crime_statistics 的 group_by=year、districts，引用 comparisons。
條件優先順序：本次明示、最近明確對話、儀表板範圍。條件不足或地理歧義先問，不可猜測。歷史回答不是統計證據。
使用者要求看、改看或同步儀表板時，可用 update_dashboard_view 提出結構化動作；一般問答不更改儀表板。工具僅回傳待套用動作，不可聲稱已套用；瀏覽器會在成功後顯示同步狀態。不可輸出 JavaScript 或 DOM 選擇器。
區分初步行政區與正式縣市年度值，不得分攤正式總數。unavailable/null/無行政區分配不等於零；披露 partial_source/incomplete_assignment 的涵蓋與分配限制。全部案類僅8類，不製造暴力犯罪彙總。
事件只用固定目錄並引用來源；時間重疊不代表因果。問變化與背景時一起查趨勢及事件工具，可在同輪呼叫；資料不足明說。"""

PROTOCOL_TOKEN = re.compile(
    r"<\s*/?\s*(?:tool(?:_call|_response)?|function(?:_call)?|arg(?:_key|_value))\b"
    r"|(?:tool_call|tool_response|function_call|arg_key|arg_value)\s*>", re.IGNORECASE)
YEAR_TOKEN = re.compile(r"(?<!\d)((?:19|20)\d{2})(?!\d)")


def contains_model_protocol(content: str) -> bool:
    """Reject complete or truncated internal protocol markup as one opaque unit."""
    return bool(PROTOCOL_TOKEN.search(html.unescape(content)))


def dashboard_action_answer(actions: list[dict]) -> str:
    scope = next((item for item in actions if item.get("type") == "set_dashboard_scope"), None)
    if scope and len(scope["years"]) == 1:
        return f"已準備將 Dashboard 切換至 {scope['years'][0]} 年。"
    return "已準備同步 Dashboard。"


def _compact_number_scope(values: list[int], suffix: str) -> str:
    ordered = sorted(set(values))
    if len(ordered) == 1:
        return f"{ordered[0]}{suffix}"
    contiguous = all(value == ordered[index - 1] + 1 for index, value in enumerate(ordered[1:], 1))
    if contiguous:
        return f"{ordered[0]}–{ordered[-1]}{suffix}"
    return "、".join(map(str, ordered)) + suffix


def dashboard_scope_text(scope: dict) -> str:
    """Describe the validated browser scope without inventing omitted context."""
    current = scope.get("current_district")
    if current:
        geography = f"{current['county']} › {current['district']}"
    else:
        geography = "、".join(scope["selected_counties"])
    years = _compact_number_scope(scope["selected_years"], " 年")
    months = "全年" if sorted(scope["selected_months"]) == list(range(1, 13)) else _compact_number_scope(scope["selected_months"], " 月")
    crimes = "、".join(scope["selected_crime_types"])
    return f"{geography}｜{years}｜{months}｜{crimes}"


def unsupported_year_answer(message: str, scope: dict) -> str | None:
    years = sorted({int(value) for value in YEAR_TOKEN.findall(unicodedata.normalize("NFKC", message))})
    unsupported = [year for year in years if year not in ALL_YEARS]
    if not unsupported:
        return None
    label = "、".join(map(str, unsupported))
    return (f"{label} 年不在目前資料範圍內，可查詢年份為 {ALL_YEARS[0]}–{ALL_YEARS[-1]}。\n"
            f"目前仍顯示 {dashboard_scope_text(scope)} 資料，篩選條件未變更。")


class DistrictScope(StrictModel):
    county: Name
    district: Name


class DashboardScope(StrictModel):
    selected_counties: Counties
    selected_years: Years
    selected_months: Months
    selected_crime_types: Crimes
    metric: Literal["count", "rate"]
    current_district: DistrictScope | None = None

    @model_validator(mode="after")
    def validate_scope(self):
        Filters(counties=self.selected_counties, years=self.selected_years,
                months=self.selected_months, crime_types=self.selected_crime_types)
        if self.current_district:
            from app.services.data_service import service
            district = self.current_district
            if district.county not in self.selected_counties or district.district not in service.county_districts[district.county]:
                raise ValueError("目前行政區不在所選縣市範圍")
        return self


class HistoryMessage(StrictModel):
    role: Literal["user", "assistant"]
    content: Annotated[str, Field(min_length=1, max_length=10000)]


class ChatRequest(StrictModel):
    message: Annotated[str, Field(min_length=1, max_length=4000)]
    conversation_history: Annotated[list[HistoryMessage], Field(max_length=20)] = Field(default_factory=list)
    current_dashboard_scope: DashboardScope

    @model_validator(mode="after")
    def validate_message(self):
        if not self.message.strip() or sum(len(item.content) for item in self.conversation_history) > 50000:
            raise ValueError("訊息空白或對話紀錄過長")
        return self


class ChatError(Exception):
    def __init__(self, message: str, status: int = 502, transient: bool = False):
        super().__init__(message)
        self.status = status
        self.diagnostics = None
        self.transient = transient


class LLMService:
    def __init__(self, transport=None):
        self.transport = transport
        self._client = None

    @property
    def model(self):
        model = os.environ.get("NVIDIA_MODEL", "").strip() or MODEL
        if model not in SUPPORTED_MODELS:
            raise ChatError("NVIDIA_MODEL 請設定為 z-ai/glm-5.3-flash 或 z-ai/glm-5.3。", 503)
        return model

    @staticmethod
    def request_model(model_name: str | None):
        if model_name is None:
            return None
        if len(model_name) > 64:
            raise ChatError("不支援的 NVIDIA 模型。請選擇 GLM-5.3-Flash 或 GLM-5.3。", 400)
        model = model_name.strip()
        if model not in SUPPORTED_MODELS:
            raise ChatError("不支援的 NVIDIA 模型。請選擇 GLM-5.3-Flash 或 GLM-5.3。", 400)
        return model

    def model_metadata(self):
        # An invalid optional AI setting must not break dashboard/data readiness.
        try:
            return {"model": self.model}
        except ChatError as exc:
            return {"model": None, "configuration_error": str(exc)}

    async def __aenter__(self):
        if self._client is not None and not self._client.is_closed:
            raise RuntimeError("LLM client lifecycle already started")
        self._client = httpx.AsyncClient(transport=self.transport, timeout=HTTP_TIMEOUT,
            limits=httpx.Limits(max_connections=8, max_keepalive_connections=8, keepalive_expiry=30), follow_redirects=False)
        return self

    async def __aexit__(self, *exc):
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def chat(self, request: ChatRequest, api_key: str | None = None, model_name: str | None = None):
        started = time.perf_counter()
        timings = {"model": None, "model_rounds": 0, "tool_rounds": 0, "retries": 0, "llm_requests": [], "tools": []}
        error, plan, fallback_reason = None, None, None
        evidence = []
        routing_ms = 0.0
        scope = request.current_dashboard_scope.model_dump()
        history = [turn.model_dump() for turn in request.conversation_history]
        dashboard_delta = extract_scope_delta(request.message, scope, history)
        dashboard_actions = dashboard_delta.actions if dashboard_delta else ()
        if api_key is not None and len(api_key) > 512:
            raise ChatError("NVIDIA API Key 格式無效。", 400)
        request_api_key = api_key.strip() if api_key is not None else None
        if api_key is not None and not request_api_key:
            raise ChatError("NVIDIA API Key 不可為空。", 400)
        request_model = self.request_model(model_name)
        range_answer = unsupported_year_answer(request.message, scope)
        if range_answer:
            total_ms = round((time.perf_counter() - started) * 1000, 2)
            return {"answer": range_answer, "model": None, "tool_results": [], "dashboard_actions": [],
                    "routing_mode": "deterministic_range_guard", "answer_mode": "deterministic",
                    "tools_used": [], "llm_call_count": 0,
                    "timings": {"routing_ms": total_ms, "tool_ms": 0.0, "llm_ms": 0.0, "total_ms": total_ms}}
        try:
            model = request_model or self.model
            timings["model"] = model
            key = request_api_key or os.environ.get("NVIDIA_API_KEY", "").strip()
            if not key:
                raise ChatError("尚未設定 NVIDIA API Key，請在對話區輸入或設定後端環境變數。", 503)
            if self._client is None or self._client.is_closed:
                raise ChatError("AI 連線服務尚未啟動，請重新啟動後端。", 503)
            async with asyncio.timeout(TOTAL_TIMEOUT):
                routing_started = time.perf_counter()
                plan = route_dashboard_message(request.message, scope, history, dashboard_delta) or route_message(request.message, scope, history)
                routing_ms = round((time.perf_counter() - routing_started) * 1000, 2)
                if plan:
                    for query in plan.tools:
                        tool_started = time.perf_counter()
                        record = {"round": 0, "tool": query.name}
                        timings["tools"].append(record)
                        try:
                            tool_result = await run_in_threadpool(execute_tool, query.name, query.arguments)
                        finally:
                            record["duration_ms"] = round((time.perf_counter() - tool_started) * 1000, 2)
                        evidence.append({"tool": query.name, "arguments": query.arguments, "result": tool_result})
                    timings["tool_rounds"] = 1
                    result = await self._fast_answer(self._client, key, model, request, evidence, timings)
                    if result.get("protocol_only") or contains_model_protocol(result["answer"]):
                        fallback_reason = "protocol_content"
                    elif not numbers_grounded(result["answer"], evidence):
                        fallback_reason = "unverified_answer"
                else:
                    result = await self._loop(self._client, key, model, request, timings)
        except (TimeoutError, httpx.TimeoutException):
            error = ChatError("AI 分析逾時，請縮小查詢範圍後重試。", 504)
            fallback_reason = "timeout"
        except httpx.RequestError:
            error = ChatError("無法連線至 NVIDIA，請稍後再試。", 502)
            fallback_reason = "connection_error"
        except ChatError as exc:
            error = exc
            if exc.transient:
                fallback_reason = "provider_unavailable"
        # A total deadline can cancel the final network call. Completed local
        # evidence lives outside that timeout scope so it is still returnable.
        if fallback_reason and plan and len(evidence) == len(plan.tools):
            result = {"answer": deterministic_answer(plan, evidence), "model": model, "tool_results": evidence,
                      "answer_mode": "deterministic_fallback", "fallback_reason": fallback_reason}
            error = None
        timings["total_ms"] = round((time.perf_counter() - started) * 1000, 2)
        diagnostics_enabled = os.environ.get("NVIDIA_LLM_DIAGNOSTICS", "0") == "1"
        if error:
            if diagnostics_enabled:
                error.diagnostics = timings
            raise error
        if diagnostics_enabled:
            result["diagnostics"] = timings
        if dashboard_actions:
            result["dashboard_actions"] = validate_actions(list(dashboard_actions), request.current_dashboard_scope.model_dump())
        elif plan and plan.dashboard_actions:
            result["dashboard_actions"] = validate_actions(list(plan.dashboard_actions), request.current_dashboard_scope.model_dump())
        result.update({"routing_mode": "deterministic_fast_path" if plan else "llm_tool_calling",
                       "answer_mode": result.get("answer_mode", "llm"),
                       "tools_used": list(dict.fromkeys(item["tool"] for item in result["tool_results"])),
                       "llm_call_count": len(timings["llm_requests"]),
                       "timings": {"routing_ms": routing_ms,
                                   "tool_ms": round(sum(item["duration_ms"] for item in timings["tools"]), 2),
                                   "llm_ms": round(sum(item["duration_ms"] for item in timings["llm_requests"]), 2),
                                   "total_ms": timings["total_ms"]}})
        return result

    @staticmethod
    def _check_status(response):
        status = response.status_code
        if status in (401, 403):
            raise ChatError("NVIDIA API Key 驗證失敗，請確認輸入的 Key 是否有效。", 503)
        if status == 402:
            raise ChatError("NVIDIA 試用額度或付款條件未滿足，請檢查供應商帳戶。", 503)
        if status == 429:
            raise ChatError("NVIDIA 請求過於頻繁或額度受限，請稍後再試。", 429, transient=True)
        if status >= 500:
            raise ChatError("NVIDIA 服務暫時異常，請稍後再試。", transient=True)
        if status != 200:
            raise ChatError("NVIDIA 無法接受此請求，請檢查模型設定或稍後重試。")

    async def _fast_answer(self, client, key, model, request, evidence, timings):
        messages = [{"role": "system", "content": SYSTEM_PROMPT + "\n本次工具已由確定性路由器完成。只解釋已附結果，不再查詢；用最多3個重點回答，保留資料品質限制。"},
                    {"role": "user", "content": request.message}]
        calls = [{"id": f"local-{index}", "type": "function", "function": {"name": item["tool"], "arguments": json.dumps(item["arguments"], ensure_ascii=False)}}
                 for index, item in enumerate(evidence)]
        messages.append({"role": "assistant", "content": None, "tool_calls": calls})
        messages.extend({"role": "tool", "tool_call_id": call["id"], "content": json.dumps(item["result"], ensure_ascii=False, allow_nan=False)}
                        for call, item in zip(calls, evidence))
        timings["model_rounds"] = 1
        response = await self._model_request(client, key, {
            "model": model, "messages": messages,
            "tools": [tool for tool in TOOLS if tool["function"]["name"] in {item["tool"] for item in evidence}],
            "tool_choice": "none", "reasoning_effort": "low", "chat_template_kwargs": {"clear_thinking": True},
            "max_tokens": MAX_TOKENS, "temperature": 0.5, "stream": False,
        }, timings, 1, max_attempts=1)
        self._check_status(response)
        try:
            choice = response.json()["choices"][0]
            message = choice["message"]
            content = message.get("content")
            if message.get("role") != "assistant":
                raise ValueError()
            # The deterministic path already executed its allowlisted tools.
            # A provider-emitted structured call is protocol-only output: do
            # not execute it and do not expose it; local evidence will answer.
            if message.get("tool_calls"):
                if choice.get("finish_reason") != "tool_calls" or not isinstance(message["tool_calls"], list):
                    raise ValueError()
                return {"answer": "", "model": model, "tool_results": evidence, "protocol_only": True}
            if choice.get("finish_reason") != "stop" or not isinstance(content, str) or not content.strip() or len(content) > 10000:
                raise ValueError()
        except (KeyError, IndexError, TypeError, ValueError, AttributeError) as exc:
            raise ChatError("NVIDIA 回覆格式不完整，請稍後重試。") from exc
        return {"answer": content, "model": model, "tool_results": evidence}

    @staticmethod
    def _retry_delay(response, attempt):
        value = response.headers.get("retry-after") if response is not None else None
        delay = RETRY_BACKOFF * (2 ** attempt)
        if value:
            try:
                delay = max(0, float(value))
            except ValueError:
                try:
                    delay = max(0, (parsedate_to_datetime(value) - datetime.now(timezone.utc)).total_seconds())
                except (TypeError, ValueError, OverflowError):
                    pass
        # Do not retry earlier than a long server-requested cooldown.
        return delay if delay <= MAX_RETRY_DELAY else None

    async def _model_request(self, client, key, body, timings, round_number, max_attempts=MAX_ATTEMPTS):
        for attempt in range(max_attempts):
            started = time.perf_counter()
            record = {"round": round_number, "attempt": attempt + 1}
            timings["llm_requests"].append(record)
            response = None
            try:
                response = await client.post(BASE_URL + "/chat/completions", headers={"Authorization": "Bearer " + key}, json=body)
                record["status"] = response.status_code
                if response.status_code != 429 and response.status_code < 500:
                    return response
                if attempt + 1 == max_attempts:
                    return response
            except TRANSIENT_CONNECTION_ERRORS as exc:
                record["error"] = type(exc).__name__
                if attempt + 1 == max_attempts:
                    raise
            except (httpx.RequestError, asyncio.CancelledError) as exc:
                record["error"] = type(exc).__name__
                raise
            finally:
                record["duration_ms"] = round((time.perf_counter() - started) * 1000, 2)
            delay = self._retry_delay(response, attempt)
            if delay is None:
                return response
            # Retrying a model request never re-executes an already-run local tool.
            await asyncio.sleep(delay)
            timings["retries"] += 1

    async def _loop(self, client, key, model, request, timings):
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        messages.extend(item.model_dump() for item in request.conversation_history)
        messages.append({"role": "user", "content": "目前儀表板範圍（僅供查詢，不是統計證據）：\n" + json.dumps(request.current_dashboard_scope.model_dump(), ensure_ascii=False) + "\n使用者問題：\n" + request.message})
        resolved = conversation_scope([turn.model_dump() for turn in request.conversation_history], request.current_dashboard_scope.model_dump())
        messages[-1]["content"] += "\n最近明確對話與儀表板補足的條件（本次明示仍優先；_ambiguous_geography 表示需詢問地理）：\n" + json.dumps(resolved, ensure_ascii=False)
        evidence = []
        pending_actions = []
        used_ids = set()
        for round_index in range(MAX_MODEL_ROUNDS):
            timings["model_rounds"] = round_index + 1
            response = await self._model_request(client, key, {
                "model": model, "messages": messages, "tools": [*TOOLS, ACTION_TOOL], "tool_choice": "auto",
                "reasoning_effort": "low", "chat_template_kwargs": {"clear_thinking": True},
                "max_tokens": MAX_TOKENS, "temperature": 0.5, "stream": False,
            }, timings, round_index + 1)
            self._check_status(response)
            try:
                payload = response.json()
                choice = payload["choices"][0]
                message = choice["message"]
                if message.get("role") != "assistant":
                    raise ValueError()
                calls = message.get("tool_calls")
                if not calls:
                    content = message.get("content")
                    if choice.get("finish_reason") != "stop" or not isinstance(content, str) or not content.strip() or len(content) > 10000:
                        raise ValueError()
                    if not evidence and re.search(r"\d[\d,.]*\s*(?:件|%|％|名)", content):
                        raise ChatError("模型未查證統計來源，已停止顯示數字；請重新提問。")
                    if contains_model_protocol(content):
                        if pending_actions:
                            content = dashboard_action_answer(pending_actions)
                        else:
                            raise ChatError("AI 回覆包含無法安全顯示的內部協定內容，請重新提問。")
                    # Only public answer/evidence leave the backend; reasoning is private.
                    result = {"answer": content, "model": model, "tool_results": evidence}
                    if pending_actions:
                        result["dashboard_actions"] = validate_actions(pending_actions, request.current_dashboard_scope.model_dump())
                    return result
                if choice.get("finish_reason") != "tool_calls" or not isinstance(calls, list) or not 1 <= len(calls) <= 4:
                    raise ValueError()
                if round_index + 1 >= MAX_MODEL_ROUNDS:
                    raise ChatError("已達工具查詢次數上限，請縮小問題範圍後重試。")
                validated = []
                for call in calls:
                    identifier, function = call["id"], call["function"]
                    if call.get("type") != "function" or not isinstance(identifier, str) or not identifier or identifier in used_ids:
                        raise ValueError()
                    arguments = function["arguments"]
                    if not isinstance(arguments, str) or len(arguments) > 12000:
                        raise ValueError()
                    try:
                        parsed = json.loads(arguments)
                        if not isinstance(parsed, dict):
                            raise ValueError()
                        tool_started = time.perf_counter()
                        tool_record = {"round": round_index + 1, "tool": function["name"]}
                        # Names are recorded only after allowlist validation below.
                        if function["name"] not in TOOL_REGISTRY and function["name"] != "update_dashboard_view":
                            raise ValueError()
                        timings["tools"].append(tool_record)
                        timings["tool_rounds"] = len({item["round"] for item in timings["tools"]})
                        try:
                            if function["name"] == "update_dashboard_view":
                                if pending_actions:
                                    raise ValueError("每輪對話僅接受一組儀表板範圍")
                                view = UpdateView.model_validate(parsed)
                                pending_actions = view_actions(view, request.current_dashboard_scope.model_dump())
                                statistics = await run_in_threadpool(execute_tool, "query_crime_statistics", {
                                    **view.model_dump(exclude={"panel"}), "limit": 1 if view.districts else 5})
                                result = {"dashboard_actions": pending_actions, "status": "validated_pending_browser_apply", "statistics": statistics}
                            else:
                                result = await run_in_threadpool(execute_tool, function["name"], parsed)
                        finally:
                            tool_record["duration_ms"] = round((time.perf_counter() - tool_started) * 1000, 2)
                    except (KeyError, ValueError, TypeError, ValidationError) as exc:
                        raise ChatError("模型要求無效的工具或查詢條件，請明確指定縣市、行政區、年份與案類後重試。") from exc
                    used_ids.add(identifier)
                    validated.append((call, result, parsed))
                assistant_message = {"role": "assistant", "content": message.get("content"), "tool_calls": calls}
                if isinstance(message.get("reasoning_content"), str):
                    assistant_message["reasoning_content"] = message["reasoning_content"]
                messages.append(assistant_message)
                for call, result, parsed in validated:
                    messages.append({"role": "tool", "tool_call_id": call["id"], "content": json.dumps(result, ensure_ascii=False, allow_nan=False)})
                    evidence.append({"tool": call["function"]["name"], "arguments": parsed, "result": result})
                # A structured dashboard-only call is complete once it validates;
                # the browser owns application and its existing sync message.
                if all(call["function"]["name"] == "update_dashboard_view" for call, _, _ in validated):
                    return {"answer": dashboard_action_answer(pending_actions), "model": model,
                            "tool_results": evidence,
                            "dashboard_actions": validate_actions(pending_actions, request.current_dashboard_scope.model_dump())}
            except (KeyError, IndexError, TypeError, ValueError, AttributeError) as exc:
                raise ChatError("NVIDIA 回覆格式不完整，請稍後重試。") from exc
        raise ChatError("已達工具查詢次數上限。")


llm_service = LLMService()
