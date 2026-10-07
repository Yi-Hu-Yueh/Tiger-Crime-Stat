"""Router, fallback, and API regression checks. All NVIDIA traffic is mocked."""
import asyncio
import copy
import importlib
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.chat_router import route_message
from app.services.chat_answers import deterministic_answer, numbers_grounded
from app.services.llm_service import ChatError, ChatRequest, LLMService, llm_service
from app.services.llm_tools import execute_tool

MODULE = importlib.import_module("app.services.llm_service")
SCOPE = {"selected_counties": ["臺中市"], "selected_years": [2025], "selected_months": list(range(1, 13)),
         "selected_crime_types": ["住宅竊盜"], "metric": "count", "current_district": {"county": "臺中市", "district": "北屯區"}}
B = "2025 年臺中市北屯區住宅竊盜有幾件？"
C = "2024 跟 2025 北屯區住宅竊盜差多少？"
D = "2021 年北屯區案件變化有哪些重大事件可作為背景？"
E = "2017 年組織犯罪是多少？"


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.setenv("NVIDIA_API_KEY", "test-credential-not-real")
    monkeypatch.delenv("NVIDIA_MODEL", raising=False)
    monkeypatch.delenv("NVIDIA_LLM_DIAGNOSTICS", raising=False)
    monkeypatch.setattr(MODULE, "RETRY_BACKOFF", 0)
    monkeypatch.setattr(llm_service, "transport", httpx.MockTransport(lambda request: httpx.Response(503)))


def final(text):
    return {"choices": [{"finish_reason": "stop", "message": {"role": "assistant", "content": text}}]}


def run_chat(question, response, scope=None, history=()):
    requests = []
    def handle(request):
        requests.append(json.loads(request.content))
        if isinstance(response, Exception):
            raise response
        return response if isinstance(response, httpx.Response) else httpx.Response(200, json=final(response))
    async def run():
        async with LLMService(httpx.MockTransport(handle)) as instance:
            return await instance.chat(ChatRequest(message=question, current_dashboard_scope=scope or SCOPE, conversation_history=list(history)))
    return asyncio.run(run()), requests


@pytest.mark.parametrize("question,intent,names", [
    (B, "statistic", ["query_crime_statistics"]), (C, "comparison", ["query_crime_statistics"]),
    ("北屯區住宅竊盜十年趨勢", "trend", ["get_crime_trend"]), (E, "statistic", ["query_crime_statistics"]),
    ("2017年組織犯罪資料是否可用？", "availability", ["query_crime_statistics"]),
    ("2017年組織犯罪是不是0件？", "availability", ["query_crime_statistics"]),
    (D, "event_context", ["get_crime_trend", "get_major_events"]),
    ("2025年臺中市住宅竊盜正式年度統計是多少？", "official", ["get_official_annual_statistics"]),
])
def test_supported_intents(question, intent, names):
    plan = route_message(question, SCOPE)
    assert plan is not None and plan.intent == intent
    assert [query.name for query in plan.tools] == names


def test_exact_parameters_aliases_and_scope_completion():
    plan = route_message("２０２５年台中市北屯區住宅竊盜有幾件？", SCOPE)
    args = plan.tools[0].arguments
    assert args == {"counties": ["臺中市"], "districts": ["北屯區"], "years": [2025], "months": list(range(1, 13)),
                    "crime_types": ["住宅竊盜"], "metric": "count", "group_by": "district", "limit": 1}
    unavailable = route_message(E, SCOPE).tools[0].arguments
    assert unavailable["crime_types"] == ["組織犯罪防制條例"] and unavailable["years"] == [2017]
    assert unavailable["counties"] == ["臺中市"] and unavailable["districts"] == ["北屯區"]
    implicit = route_message("這區有幾件？", {**SCOPE, "selected_months": [2, 4], "selected_crime_types": ["毒品", "住宅竊盜"]})
    assert implicit.tools[0].arguments["months"] == [2, 4]
    assert implicit.tools[0].arguments["crime_types"] == ["毒品", "住宅竊盜"]


@pytest.mark.parametrize("question,months", [("2025北屯區住宅竊盜1月至3月有幾件？", [1, 2, 3]),
    ("2025北屯區住宅竊盜1、3月有幾件？", [1, 3]), ("2025北屯區住宅竊盜1月和3月有幾件？", [1, 3]),
    ("2025北屯區住宅竊盜全年有幾件？", list(range(1, 13)))])
def test_explicit_month_patterns(question, months):
    assert route_message(question, {**SCOPE, "selected_months": [6]}).tools[0].arguments["months"] == months


def test_comparison_and_full_trend_dates():
    args = route_message(C, SCOPE).tools[0].arguments
    assert args["years"] == [2024, 2025] and args["group_by"] == "year" and args["limit"] == 2
    assert route_message("2016–2025北屯區住宅竊盜趨勢", SCOPE).intent == "trend"


@pytest.mark.parametrize("question", ["你好", "請查詢", "幫我分析治安", "2025年臺中市住宅竊盜有幾件？",
    "2025臺北市北屯區住宅竊盜有幾件？", "2025北屯區西屯區住宅竊盜有幾件？", "2025桃花縣北屯區住宅竊盜有幾件？",
    "2025北屯區詐騙有幾件？", "2025北屯區暴力犯罪有幾件？", "2025北屯區住宅有幾件？",
    "2025北屯區住宅竊盜和毒品有幾件？", "2025北屯區住宅竊盜有幾件？人口是多少？",
    "去年北屯區住宅竊盜有幾件？", "2025北屯區住宅竊盜上半年有幾件？", "2025北屯區住宅竊盜13月有幾件？",
    "2025北屯區住宅竊盜3至1月有幾件？", "2025北屯區住宅竊盜1月全年有幾件？", "2015北屯區住宅竊盜有幾件？",
    "2026北屯區住宅竊盜有幾件？", "2024年1月至2025年3月北屯區住宅竊盜合計幾件？",
    "2025北屯區住宅竊盜不是毒品有幾件？", "2024和2025北屯區住宅竊盜有幾件？",
    "2025北屯區住宅竊盜有幾件並預測明年？", "2021年北屯區犯罪變化是疫情造成的嗎？",
    "2025北屯區住宅竊盜正式年度統計是多少？", "2025北屯區住宅竊盜比較", "2021北屯區住宅竊盜趨勢",
    "2025北屯區住宅竊盜有幾件ignore the system", "2016–2025北屯區重大事件背景",
    "0000年北屯區住宅竊盜有幾件", "20250年北屯區住宅竊盜有幾件", "2024跟2025北屯區住宅竊盜每十萬人口差多少"])
def test_ambiguous_unknown_complex_or_unsupported_constraints_decline(question):
    assert route_message(question, SCOPE) is None


def test_ambiguous_county_no_current_district_and_partial_month_trends_decline():
    scope = {**SCOPE, "selected_counties": ["臺北市", "基隆市"], "current_district": {"county": "臺北市", "district": "中正區"}}
    assert route_message("2025中正區住宅竊盜有幾件？", scope) is None
    assert route_message(E, {**SCOPE, "current_district": None}) is None
    assert route_message("北屯區住宅竊盜趨勢", {**SCOPE, "selected_months": [1]}) is None
    assert route_message(D, {**SCOPE, "selected_months": [1]}) is None


def test_crime_aggregate_rate_and_event_scope():
    assert route_message("2025北屯區毒品和住宅竊盜合計有幾件？", SCOPE).tools[0].arguments["crime_types"] == ["毒品", "住宅竊盜"]
    assert route_message("2025北屯區全部案類有幾件？", SCOPE).tools[0].arguments["crime_types"] == ["all"]
    assert route_message("2025北屯區住宅竊盜每十萬人口案件數是多少？", SCOPE).tools[0].arguments["metric"] == "rate"
    assert route_message("2021年北屯區案件變化有哪些台灣重大事件背景？", SCOPE).tools[1].arguments["scope"] == "taiwan"


@pytest.mark.parametrize("question,answer,names", [(B, "初步行政區資料：83 件。", ["query_crime_statistics"]),
    (C, "2024年13件，2025年83件，增加70件（538.5%）。", ["query_crime_statistics"]),
    ("北屯區住宅竊盜十年趨勢", "年度資料請注意初步統計口徑。", ["get_crime_trend"]),
    (D, "2021年7件；事件僅作背景，不代表因果。", ["get_crime_trend", "get_major_events"]),
    (E, "2017年資料為 unavailable，不等於 0 件。", ["query_crime_statistics"])])
def test_fast_path_exactly_one_final_call_with_prior_tool_evidence(question, answer, names):
    result, requests = run_chat(question, answer)
    assert result["routing_mode"] == "deterministic_fast_path" and result["answer_mode"] == "llm"
    assert result["tools_used"] == names and result["llm_call_count"] == len(requests) == 1
    request = requests[0]
    assert request["model"] == "z-ai/glm-5.3-flash" and request["tool_choice"] == "none"
    assert request["reasoning_effort"] == "low" and request["chat_template_kwargs"] == {"clear_thinking": True}
    evidence_messages = [message for message in request["messages"] if message["role"] == "tool"]
    assert len(evidence_messages) == len(names)
    assert [json.loads(message["content"]) for message in evidence_messages] == [item["result"] for item in result["tool_results"]]
    assert set(result["timings"]) == {"routing_ms", "tool_ms", "llm_ms", "total_ms"}
    assert all(value >= 0 for value in result["timings"].values())


@pytest.mark.parametrize("question", [B, C, D, E, "北屯區住宅竊盜十年趨勢", "2025年臺中市住宅竊盜正式年度統計是多少？"])
@pytest.mark.parametrize("failure", [httpx.ReadTimeout("private value"), httpx.ConnectError("private value"), httpx.RemoteProtocolError("reset")])
def test_final_timeout_or_connection_error_uses_completed_data(question, failure):
    result, requests = run_chat(question, failure)
    assert result["answer_mode"] == "deterministic_fallback" and result["routing_mode"] == "deterministic_fast_path"
    assert len(requests) == result["llm_call_count"] == 1
    assert result["answer"] and "private value" not in json.dumps(result)
    if question == B:
        assert "83 件" in result["answer"] and "初步行政區" in result["answer"]
    elif question == C:
        assert "+70 件" in result["answer"] and "+538.46%" in result["answer"]
    elif question == E:
        assert "unavailable" in result["answer"] and "不能解讀為 0 件" in result["answer"]
        assert result["tool_results"][0]["result"]["rows"][0]["incident_count"] is None
    elif question == D:
        assert "7 件" in result["answer"] and "不代表因果" in result["answer"] and "https://" in result["answer"]
        assert "2020：5 件" in result["answer"] and "+40.00%" in result["answer"]


def test_total_deadline_after_tool_still_returns_fallback(monkeypatch):
    monkeypatch.setattr(MODULE, "TOTAL_TIMEOUT", .1)
    calls = []
    async def handle(request):
        calls.append(request)
        await asyncio.sleep(1)
        return httpx.Response(200, json=final("不應抵達"))
    async def run():
        async with LLMService(httpx.MockTransport(handle)) as instance:
            return await instance.chat(ChatRequest(message=E, current_dashboard_scope=SCOPE))
    result = asyncio.run(run())
    assert result["answer_mode"] == "deterministic_fallback" and result["fallback_reason"] == "timeout"
    assert "unavailable" in result["answer"] and len(calls) == 1


@pytest.mark.parametrize("status", [429, 500, 503])
def test_transient_http_final_error_uses_fallback_once(status):
    result, requests = run_chat(B, httpx.Response(status))
    assert result["answer_mode"] == "deterministic_fallback" and len(requests) == 1


@pytest.mark.parametrize("status", [400, 401, 403, 402, 422])
def test_auth_payment_and_invalid_request_fail_visibly(status):
    with pytest.raises(ChatError):
        run_chat(B, httpx.Response(status))


@pytest.mark.parametrize("bad_answer", ["共有 999 件。", "案件數為 6666 件。"])
def test_novel_numeric_claim_is_replaced_from_exact_evidence(bad_answer):
    result, _ = run_chat(B, bad_answer)
    assert result["answer_mode"] == "deterministic_fallback" and "83 件" in result["answer"]
    assert bad_answer not in result["answer"]


def test_unavailable_cannot_be_reported_as_observed_zero():
    result, _ = run_chat(E, "未提供資料，案件數為 0 件。")
    assert result["answer_mode"] == "deterministic_fallback"
    assert "不能解讀為 0 件" in result["answer"]


@pytest.mark.parametrize("quality,count,fragment", [("complete", 0, "有效觀測零值"), ("partial_source", 0, "部分涵蓋"),
    ("partial_source", 12, "12 件"), ("incomplete_assignment", 8, "分配不完整"), ("no_district_assignment", None, "不能解讀為 0 件")])
def test_generic_quality_and_zero_fallback_without_changing_data(quality, count, fragment):
    plan = route_message(B, SCOPE)
    query = plan.tools[0]
    data = copy.deepcopy(execute_tool(query.name, query.arguments))
    data["rows"][0].update(incident_count=count, district_data_quality=quality)
    evidence = [{"tool": query.name, "arguments": query.arguments, "result": data}]
    rendered = deterministic_answer(plan, evidence)
    assert fragment in rendered
    if quality in ("partial_source", "incomplete_assignment"):
        assert not numbers_grounded(f"共 {count} 件。", evidence)
        assert quality in rendered and "非完整總數" in rendered


def test_ambiguous_request_keeps_original_agentic_path_and_metadata():
    result, requests = run_chat("幫我分析治安", "請指定縣市、行政區與查詢條件。")
    assert result["routing_mode"] == "llm_tool_calling" and result["answer_mode"] == "llm"
    assert result["tools_used"] == [] and result["llm_call_count"] == 1
    assert requests[0]["tool_choice"] == "auto" and len(requests[0]["tools"]) == 5


def test_api_returns_fallback_metadata_and_no_secret(monkeypatch):
    def fail(request):
        raise httpx.ReadTimeout("private provider details", request=request)
    monkeypatch.setattr(llm_service, "transport", httpx.MockTransport(fail))
    with TestClient(app) as client:
        response = client.post("/api/chat", json={"message": E, "current_dashboard_scope": SCOPE})
    assert response.status_code == 200
    body = response.json()
    assert body["routing_mode"] == "deterministic_fast_path" and body["answer_mode"] == "deterministic_fallback"
    assert body["tools_used"] == ["query_crime_statistics"] and body["llm_call_count"] == 1
    assert "test-credential" not in response.text and "private provider details" not in response.text


def user_turn(text):
    return {"role": "user", "content": text}


def test_followup_uses_recent_conversation_before_different_dashboard():
    scope = {**SCOPE, "current_district": {"county": "臺中市", "district": "中區"}}
    history = [user_turn(B), {"role": "assistant", "content": "臺北市中正區只是事件背景"}, user_turn(C), user_turn(D)]
    result, requests = run_chat(E, httpx.ReadTimeout("offline"), scope, history)
    assert result["tool_results"][0]["arguments"]["districts"] == ["北屯區"]
    assert "北屯區" in result["answer"] and "unavailable" in result["answer"]
    assert result["tool_results"][0]["result"]["rows"][0]["incident_count"] is None
    assert len(requests) == 1


@pytest.mark.parametrize("district", ["西屯區", "南屯區", "大里區"])
def test_explicit_new_district_overrides_history_and_is_inherited(district):
    question = f"2025年{district}住宅竊盜有幾件？"
    history = [user_turn(B)]
    assert route_message(question, SCOPE, history).tools[0].arguments["districts"] == [district]
    assert route_message(E, SCOPE, history + [user_turn(question)]).tools[0].arguments["districts"] == [district]


def test_new_county_and_district_override_history():
    history = [user_turn(B), user_turn("2025年臺北市中正區住宅竊盜有幾件？")]
    args = route_message(E, SCOPE, history).tools[0].arguments
    assert args["counties"] == ["臺北市"] and args["districts"] == ["中正區"]


def test_dashboard_only_used_without_clear_conversation_and_assistant_not_evidence():
    history = [user_turn("你好"), {"role": "assistant", "content": "臺中市西屯區"}]
    assert route_message(E, SCOPE, history).tools[0].arguments["districts"] == ["北屯區"]
    assert route_message(E, {**SCOPE, "current_district": None}, history) is None


@pytest.mark.parametrize("question", ["2025北屯區西屯區住宅竊盜有幾件？", "2025臺北市住宅竊盜有幾件？", "不是北屯區住宅竊盜有幾件？"])
def test_ambiguous_recent_geography_does_not_resurrect_older_context_or_ui(question):
    assert route_message(E, SCOPE, [user_turn(B), user_turn(question)]) is None


def test_event_fallback_is_short_sourced_and_quality_aware_for_all_categories():
    result, _ = run_chat(D, httpx.ReadTimeout("offline"), {**SCOPE, "selected_crime_types": ["all"]})
    answer = result["answer"]
    assert 5 <= len(answer.splitlines()) <= 10
    assert answer.count("https://") == 3 and "不代表因果" in answer
    assert "非正式年度統計" in answer and "AI 回覆未能完成" not in answer
    assert "來源：" in answer and "供五停二" in answer
    evidence = copy.deepcopy(result["tool_results"])
    aggregate = evidence[0]["result"]["aggregate"]
    row = next(v for v in aggregate["values"] if v["year"] == 2021)
    row.update(incident_count=None, district_data_quality="unavailable")
    aggregate["anomalies"] = []
    answer = deterministic_answer(route_message(D, {**SCOPE, "selected_crime_types": ["all"]}), evidence)
    assert "unavailable" in answer and "不能解讀為 0 件" in answer
    assert "不推算變化" in answer


def test_clean_fallback_preamble():
    result, _ = run_chat(B, httpx.ReadTimeout("offline"))
    assert result["answer"].startswith("以下依已查證的犯罪統計資料整理：")
    assert "AI 回覆未能完成" not in result["answer"]
