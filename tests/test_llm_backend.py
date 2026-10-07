"""Offline only: every model request uses MockTransport, never real API quota."""
import asyncio
import json
import importlib
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.data_service import service
from app.services.llm_service import ChatError, ChatRequest, LLMService, MODEL, SYSTEM_PROMPT, llm_service
from app.services.llm_tools import TOOLS, execute_tool

LLM_MODULE = importlib.import_module("app.services.llm_service")

SCOPE = {"selected_counties": ["臺中市"], "selected_years": [2025], "selected_months": list(range(1, 13)),
         "selected_crime_types": ["住宅竊盜"], "metric": "count", "current_district": {"county": "臺中市", "district": "北屯區"}}
STATS = {"counties": ["臺中市"], "districts": ["北屯區"], "years": [2025], "crime_types": ["住宅竊盜"]}


@pytest.fixture(autouse=True)
def offline_key(monkeypatch):
    monkeypatch.setenv("NVIDIA_API_KEY", "test-credential-not-real")
    monkeypatch.delenv("NVIDIA_MODEL", raising=False)
    monkeypatch.delenv("NVIDIA_LLM_DIAGNOSTICS", raising=False)
    monkeypatch.setattr(LLM_MODULE, "RETRY_BACKOFF", 0)
    # Even unexpected test paths cannot reach NVIDIA.
    monkeypatch.setattr(llm_service, "transport", httpx.MockTransport(lambda request: httpx.Response(503)))


def answer(text="您好，請指定查詢範圍。", finish="stop"):
    return {"choices": [{"finish_reason": finish, "message": {"role": "assistant", "content": text, "reasoning_content": "private reasoning"}}]}


def call(name="query_crime_statistics", arguments=None, identifier="call-1"):
    return {"choices": [{"finish_reason": "tool_calls", "message": {"role": "assistant", "content": None,
            "tool_calls": [{"id": identifier, "type": "function", "function": {"name": name, "arguments": json.dumps(STATS if arguments is None else arguments)}}]}}]}


def run_responses(responses):
    requests = []
    def handle(request):
        requests.append(json.loads(request.content))
        value = responses[min(len(requests) - 1, len(responses) - 1)]
        if isinstance(value, Exception):
            raise value
        return value if isinstance(value, httpx.Response) else httpx.Response(200, json=value)
    result = asyncio.run(chat_once(httpx.MockTransport(handle)))
    return result, requests


async def chat_once(transport, api_key=None, model_name=None):
    async with LLMService(transport) as client:
        return await client.chat(ChatRequest(message="請查詢", current_dashboard_scope=SCOPE), api_key=api_key, model_name=model_name)


def test_missing_key(monkeypatch):
    monkeypatch.delenv("NVIDIA_API_KEY")
    with TestClient(app) as client:
        response = client.post("/api/chat", json={"message": "您好", "current_dashboard_scope": SCOPE})
    assert response.status_code == 503 and "尚未設定" in response.json()["detail"]


def test_request_key_overrides_environment_and_never_enters_payload_response_metadata_or_logs(monkeypatch, caplog):
    monkeypatch.setenv("NVIDIA_API_KEY", "environment-test-key")
    monkeypatch.setenv("NVIDIA_LLM_DIAGNOSTICS", "1")
    seen = {}
    def handle(request):
        seen["authorization"] = request.headers.get("authorization")
        seen["body"] = request.content.decode()
        return httpx.Response(200, json=answer())
    result = asyncio.run(chat_once(httpx.MockTransport(handle), "  request-test-key  "))
    assert seen["authorization"] == "Bearer request-test-key"
    assert "request-test-key" not in seen["body"]
    assert "request-test-key" not in json.dumps(result)
    assert "diagnostics" in result and "request-test-key" not in caplog.text
    assert "environment-test-key" not in seen["authorization"]


def test_environment_key_remains_fallback_when_header_is_absent(monkeypatch):
    monkeypatch.setenv("NVIDIA_API_KEY", "environment-fallback-key")
    seen = {}
    def handle(request):
        seen["authorization"] = request.headers.get("authorization")
        return httpx.Response(200, json=answer())
    asyncio.run(chat_once(httpx.MockTransport(handle)))
    assert seen["authorization"] == "Bearer environment-fallback-key"


def test_request_model_overrides_environment_model(monkeypatch):
    monkeypatch.setenv("NVIDIA_MODEL", "z-ai/glm-5.3-flash")
    seen = {}
    def handle(request):
        seen["model"] = json.loads(request.content)["model"]
        return httpx.Response(200, json=answer())
    result = asyncio.run(chat_once(httpx.MockTransport(handle), model_name="  z-ai/glm-5.3  "))
    assert seen["model"] == result["model"] == "z-ai/glm-5.3"


def test_missing_request_model_uses_environment_then_builtin_default(monkeypatch):
    seen = []
    def handle(request):
        seen.append(json.loads(request.content)["model"])
        return httpx.Response(200, json=answer())
    monkeypatch.setenv("NVIDIA_MODEL", "z-ai/glm-5.3")
    asyncio.run(chat_once(httpx.MockTransport(handle)))
    monkeypatch.delenv("NVIDIA_MODEL", raising=False)
    asyncio.run(chat_once(httpx.MockTransport(handle)))
    assert seen == ["z-ai/glm-5.3", "z-ai/glm-5.3-flash"]


def test_model_switch_takes_effect_on_next_request_without_restart(monkeypatch):
    monkeypatch.delenv("NVIDIA_MODEL", raising=False)
    seen = []
    def handle(request):
        seen.append(json.loads(request.content)["model"])
        return httpx.Response(200, json=answer())
    async def run():
        async with LLMService(httpx.MockTransport(handle)) as client:
            request = ChatRequest(message="請查詢", current_dashboard_scope=SCOPE)
            await client.chat(request, model_name="z-ai/glm-5.3")
            await client.chat(request, model_name="z-ai/glm-5.3-flash")
    asyncio.run(run())
    assert seen == ["z-ai/glm-5.3", "z-ai/glm-5.3-flash"]


def test_unsupported_request_model_is_rejected_without_provider_call_or_echo():
    called = False
    def handle(request):
        nonlocal called
        called = True
        return httpx.Response(200, json=answer())
    unsupported = "arbitrary/private-model"
    with pytest.raises(ChatError, match="不支援的 NVIDIA 模型") as caught:
        asyncio.run(chat_once(httpx.MockTransport(handle), model_name=unsupported))
    assert caught.value.status == 400 and called is False and unsupported not in str(caught.value)


def test_endpoint_rejects_unsupported_model_safely():
    unsupported = "arbitrary/private-model"
    with TestClient(app) as client:
        response = client.post("/api/chat", headers={"X-NVIDIA-Model": unsupported},
                               json={"message": "您好", "current_dashboard_scope": SCOPE})
    assert response.status_code == 400 and "不支援的 NVIDIA 模型" in response.json()["detail"]
    assert unsupported not in response.text


def test_blank_request_key_is_rejected_before_provider_call():
    called = False
    def handle(request):
        nonlocal called
        called = True
        return httpx.Response(200, json=answer())
    with pytest.raises(ChatError, match="不可為空") as caught:
        asyncio.run(chat_once(httpx.MockTransport(handle), "   "))
    assert caught.value.status == 400 and called is False


def test_oversized_request_key_is_rejected_without_echoing_it():
    oversized = "sensitive-test-key-" + "x" * 512
    with TestClient(app) as client:
        response = client.post("/api/chat", headers={"X-NVIDIA-API-Key": oversized},
                               json={"message": "您好", "current_dashboard_scope": SCOPE})
    assert response.status_code == 400 and response.json() == {"detail": "NVIDIA API Key 格式無效。"}
    assert oversized not in response.text


def test_endpoint_forwards_request_key_and_sanitizes_auth_failure(monkeypatch):
    seen = {}
    def handle(request):
        seen["authorization"] = request.headers.get("authorization")
        return httpx.Response(401, text="private provider credential detail")
    monkeypatch.setattr(llm_service, "transport", httpx.MockTransport(handle))
    with TestClient(app) as client:
        response = client.post("/api/chat", headers={"X-NVIDIA-API-Key": "endpoint-test-key"},
                               json={"message": "您好", "current_dashboard_scope": SCOPE})
    assert response.status_code == 503
    assert seen["authorization"] == "Bearer endpoint-test-key"
    assert response.json() == {"detail": "NVIDIA API Key 驗證失敗，請確認輸入的 Key 是否有效。"}
    assert "endpoint-test-key" not in response.text and "private provider" not in response.text


def test_direct_answer_config_context_and_private_reasoning():
    result, requests = run_responses([answer()])
    assert result["answer"] == "您好，請指定查詢範圍。"
    assert "private reasoning" not in json.dumps(result)
    sent = requests[0]
    assert sent["model"] == MODEL and sent["stream"] is False
    assert sent["max_tokens"] == 1024 and MODEL == "z-ai/glm-5.3-flash"
    assert sent["reasoning_effort"] == "low" and sent["chat_template_kwargs"] == {"clear_thinking": True}
    assert "extra_body" not in sent and len(sent["tools"]) == 5
    assert "北屯區" in sent["messages"][-1]["content"]
    assert "test-credential" not in json.dumps(sent)


def test_one_tool_uses_exact_validated_statistics():
    result, requests = run_responses([call(), answer("初步資料為 83 件。")])
    row = result["tool_results"][0]["result"]["rows"][0]
    expected = next(row for row in service.scope_map_data("臺中市", "2025", None, "住宅竊盜", "count")["districts"] if row["district"] == "北屯區")
    assert row == expected and row["incident_count"] == 83
    assert requests[1]["messages"][-1]["role"] == "tool"
    assert json.loads(requests[1]["messages"][-1]["content"])["rows"][0] == expected


def test_sequential_tools_and_endpoint(monkeypatch):
    sequence = [call(), call("get_major_events", {"years": [2021]}, "call-2"), answer("時間重疊不代表因果。")]
    captured = []
    def handle(request):
        captured.append(json.loads(request.content))
        return httpx.Response(200, json=sequence.pop(0))
    monkeypatch.setattr(llm_service, "transport", httpx.MockTransport(handle))
    with TestClient(app) as client:
        response = client.post("/api/chat", json={"message": "這區", "current_dashboard_scope": SCOPE,
                    "conversation_history": [{"role": "user", "content": "之前的問題"}, {"role": "assistant", "content": "之前的回答"}]})
    assert response.status_code == 200 and len(response.json()["tool_results"]) == 2
    assert captured[0]["messages"][1]["content"] == "之前的問題"
    assert len(captured) == 3


def test_loop_is_bounded():
    with pytest.raises(ChatError, match="次數上限"):
        run_responses([call("get_major_events", {"years": [2021]}, str(index)) for index in range(6)])


@pytest.mark.parametrize("name,args", [("execute_shell", {}), ("query_crime_statistics", {**STATS, "years": [2030]}),
    ("query_crime_statistics", {**STATS, "limit": 101}), ("query_crime_statistics", {**STATS, "extra": "ignored?"}),
    ("query_crime_statistics", {**STATS, "districts": ["不存在"]}), ("get_crime_trend", {"county": "不存在", "district": "北屯區"})])
def test_invalid_tool_and_arguments(name, args):
    with pytest.raises(ChatError, match="無效的工具"):
        run_responses([call(name, args)])


@pytest.mark.parametrize("status,fragment", [(401, "驗證失敗"), (403, "驗證失敗"), (402, "付款"), (429, "額度"), (500, "暫時異常"), (503, "暫時異常"), (422, "設定")])
def test_provider_errors_are_sanitized(status, fragment):
    with pytest.raises(ChatError, match=fragment) as caught:
        run_responses([httpx.Response(status, text="provider private credential detail")])
    assert "credential" not in str(caught.value)


@pytest.mark.parametrize("payload", [{}, {"choices": []}, answer("", "stop"), answer("截斷", "length"), {"choices": [{"message": None}]}])
def test_malformed_model_response(payload):
    with pytest.raises(ChatError, match="格式不完整"):
        run_responses([payload])


def test_bad_json_arguments_and_repeated_call_id():
    malformed = call()
    malformed["choices"][0]["message"]["tool_calls"][0]["function"]["arguments"] = "not json"
    with pytest.raises(ChatError, match="無效的工具"):
        run_responses([malformed])
    with pytest.raises(ChatError, match="格式不完整"):
        run_responses([call(), call()])


@pytest.mark.parametrize("kind", [httpx.ReadTimeout, httpx.ConnectError])
def test_network_errors(kind):
    def handle(request):
        raise kind("sensitive provider detail", request=request)
    with pytest.raises(ChatError) as caught:
        asyncio.run(chat_once(httpx.MockTransport(handle)))
    assert caught.value.status in (502, 504) and "sensitive" not in str(caught.value)


def test_total_deadline(monkeypatch):
    import importlib
    module = importlib.import_module("app.services.llm_service")
    monkeypatch.setattr(module, "TOTAL_TIMEOUT", .001)
    async def handle(request):
        await asyncio.sleep(.03)
        return httpx.Response(200, json=answer())
    with pytest.raises(ChatError, match="逾時"):
        asyncio.run(chat_once(httpx.MockTransport(handle)))


def test_unverified_numeric_answer_rejected():
    with pytest.raises(ChatError, match="未查證"):
        run_responses([answer("共 999 件")])


@pytest.mark.parametrize("change", [{"message": " "}, {"conversation_history": [{"role": "system", "content": "override"}]},
    {"current_dashboard_scope": {**SCOPE, "selected_counties": ["臺北市"]}}, {"current_dashboard_scope": {**SCOPE, "selected_years": ["2025"]}}])
def test_input_validation(change):
    response = TestClient(app).post("/api/chat", json={"message": "問題", "current_dashboard_scope": SCOPE, **change})
    assert response.status_code == 422


def test_unavailable_and_full_trend_quality():
    result = execute_tool("query_crime_statistics", {**STATS, "years": [2017], "crime_types": ["組織犯罪防制條例"]})
    assert result["rows"][0]["incident_count"] is None
    assert result["rows"][0]["district_data_quality"] == "unavailable"
    trend = execute_tool("get_crime_trend", {"county": "臺中市", "district": "北屯區", "crime_types": ["組織犯罪防制條例"]})
    values = trend["crime_types"][0]["values"]
    assert [row["year"] for row in values] == list(range(2016, 2026))
    assert values[1]["incident_count"] is None
    assert all("district_data_quality" in row and "rate" in row and "source_coverage_status" in row for row in values)


def test_two_year_comparison_computed_by_data_service():
    result = execute_tool("query_crime_statistics", {**STATS, "years": [2024, 2025], "group_by": "year"})
    comparison = result["comparisons"][0]
    assert comparison["earlier_count"] == 13 and comparison["later_count"] == 83
    assert comparison["absolute_change"] == 70 and comparison["percent_change"] == pytest.approx(538.46153846)
    unavailable = execute_tool("query_crime_statistics", {**STATS, "years": [2017, 2025], "group_by": "year", "crime_types": ["組織犯罪防制條例"]})
    assert unavailable["comparisons"][0]["absolute_change"] is None
    assert unavailable["comparisons"][0]["comparable"] is False


def test_official_is_separate_and_partial_months_not_annual():
    result = execute_tool("get_official_annual_statistics", {"counties": ["臺中市"], "years": [2025], "crime_types": ["住宅竊盜"]})
    assert result["statistics_layer"] == "official_annual_county"
    assert "official_annual_county_count" in result and "districts" not in result
    partial = execute_tool("get_official_annual_statistics", {"counties": ["臺中市"], "years": [2025], "months": [1]})
    assert partial["official_annual_county_count"] is None


def test_fixed_event_catalog_sources_and_causality():
    result = execute_tool("get_major_events", {"years": [2021], "scope": "taiwan"})
    expected = [event for event in service.context.events(year=2021) if event["scope"] == "taiwan"]
    assert result["events"] == expected and result["causality_established"] is False
    assert all(event["source_url"] and event["title"] and event["summary"] and event["start_date"] for event in expected)


def test_prompt_and_environment_template():
    for term in ("繁體中文", "不得自行計算", "unavailable", "partial_source", "正式", "因果", "暴力犯罪"):
        assert term in SYSTEM_PROMPT
    root = Path(__file__).resolve().parents[1]
    assert (root / ".env.example").read_text().splitlines() == ["NVIDIA_API_KEY=", "NVIDIA_MODEL=z-ai/glm-5.3-flash", "NVIDIA_LLM_DIAGNOSTICS=0"]
    assert ".env" in (root / ".gitignore").read_text()


def test_model_schema_exposes_exact_county_and_crime_names():
    schema = TOOLS[0]["function"]["parameters"]["properties"]
    assert "臺中市" in schema["counties"]["items"]["enum"]
    assert "組織犯罪防制條例" in schema["crime_types"]["items"]["enum"]


@pytest.mark.parametrize("prior,current,quality,delta,percent", [(0, 0, "complete", 0, 0), (0, 3, "complete", 3, None),
    (4, 2, "partial_source", None, None), (4, None, "no_district_assignment", None, None)])
def test_comparison_zero_and_quality_guards(monkeypatch, prior, current, quality, delta, percent):
    def data(county, year, months, crimes, metric):
        return {"districts": [{"district": "北屯區", "incident_count": prior if year == "2024" else current,
                              "district_data_quality": "complete" if year == "2024" else quality}]}
    monkeypatch.setattr(service, "scope_map_data", data)
    result = service.compare_district_years("臺中市", "北屯區", [2024, 2025], "1", "住宅竊盜")
    assert result["absolute_change"] == delta and result["percent_change"] == percent


def test_scoped_months_crimes_rank_sort_limit_match_data_service():
    args = {"counties": ["臺中市", "臺北市"], "years": [2024, 2025], "months": [1, 3], "crime_types": ["毒品", "住宅竊盜"], "metric": "rate", "sort": "rate_desc", "limit": 3}
    result = execute_tool("query_crime_statistics", args)
    expected = service.scope_map_data("臺中市,臺北市", "2024,2025", "1,3", "毒品,住宅竊盜", "rate")
    ranked = sorted(expected["districts"], key=lambda row: (row["rate"] is None, -row["rate"] if row["rate"] is not None else 0, row["county"], row["district"], row["years"]))
    assert result["rows"] == ranked[:3]
    assert result["truncated"] and result["matching_rows"] == len(ranked)


def test_model_override_health_and_response_metadata(monkeypatch):
    assert TestClient(app).get("/health").json()["llm"]["model"] == MODEL
    monkeypatch.setenv("NVIDIA_MODEL", "z-ai/glm-5.3")
    result, requests = run_responses([answer()])
    assert result["model"] == requests[0]["model"] == "z-ai/glm-5.3"
    assert TestClient(app).get("/health").json()["llm"]["model"] == "z-ai/glm-5.3"


def test_explicit_timeouts_and_shared_lifecycle():
    requests = []
    def handle(request):
        requests.append(request)
        return httpx.Response(200, json=answer())
    async def check():
        instance = LLMService(httpx.MockTransport(handle))
        assert instance._client is None
        async with instance:
            shared = instance._client
            assert shared.timeout == httpx.Timeout(connect=5, read=35, write=10, pool=5)
            for _ in range(2):
                await instance.chat(ChatRequest(message="您好", current_dashboard_scope=SCOPE))
                assert instance._client is shared and not shared.is_closed
        assert shared.is_closed and instance._client is None
    asyncio.run(check())
    assert len(requests) == 2


def test_fastapi_manages_shared_client_lifespan(monkeypatch):
    monkeypatch.setattr(llm_service, "transport", httpx.MockTransport(lambda request: httpx.Response(200, json=answer())))
    assert llm_service._client is None
    with TestClient(app) as client:
        shared = llm_service._client
        for _ in range(2):
            assert client.post("/api/chat", json={"message": "您好", "current_dashboard_scope": SCOPE}).status_code == 200
            assert llm_service._client is shared
    assert shared.is_closed and llm_service._client is None


@pytest.mark.parametrize("failure", [httpx.ConnectError("private"), httpx.ReadError("private"), httpx.RemoteProtocolError("reset"),
    httpx.ConnectTimeout("private"), httpx.Response(429), httpx.Response(500), httpx.Response(503)])
def test_transient_failures_retry_once_then_succeed(monkeypatch, failure):
    monkeypatch.setenv("NVIDIA_LLM_DIAGNOSTICS", "1")
    result, requests = run_responses([failure, answer()])
    assert len(requests) == 2 and requests[0] == requests[1]
    assert result["diagnostics"]["retries"] == 1 and result["diagnostics"]["model_rounds"] == 1
    assert "private" not in json.dumps(result)


@pytest.mark.parametrize("status", [401, 403, 402, 400, 404, 422])
def test_nontransient_status_never_retried(monkeypatch, status):
    monkeypatch.setenv("NVIDIA_LLM_DIAGNOSTICS", "1")
    with pytest.raises(ChatError) as caught:
        run_responses([httpx.Response(status)])
    assert len(caught.value.diagnostics["llm_requests"]) == 1
    assert caught.value.diagnostics["retries"] == 0


@pytest.mark.parametrize("failure", [httpx.ConnectError("reset"), httpx.Response(429), httpx.Response(503)])
def test_retries_are_bounded(monkeypatch, failure):
    monkeypatch.setenv("NVIDIA_LLM_DIAGNOSTICS", "1")
    with pytest.raises(ChatError) as caught:
        run_responses([failure])
    assert len(caught.value.diagnostics["llm_requests"]) == 2
    assert caught.value.diagnostics["retries"] == 1


def test_long_retry_after_fails_without_early_retry(monkeypatch):
    monkeypatch.setenv("NVIDIA_LLM_DIAGNOSTICS", "1")
    with pytest.raises(ChatError) as caught:
        run_responses([httpx.Response(429, headers={"Retry-After": "60"})])
    assert caught.value.status == 429 and caught.value.diagnostics["retries"] == 0
    assert len(caught.value.diagnostics["llm_requests"]) == 1


def test_retry_delay_parsing():
    assert LLMService._retry_delay(httpx.Response(503, headers={"Retry-After": "1"}), 0) == 1
    assert LLMService._retry_delay(httpx.Response(503, headers={"Retry-After": "Wed, 01 Jan 2020 00:00:00 GMT"}), 0) == 0


def test_three_model_rounds_maximum_and_no_unnecessary_last_tool(monkeypatch):
    monkeypatch.setenv("NVIDIA_LLM_DIAGNOSTICS", "1")
    with pytest.raises(ChatError, match="次數上限") as caught:
        run_responses([call("get_major_events", {"years": [2021]}, str(index)) for index in range(5)])
    diag = caught.value.diagnostics
    assert diag["model_rounds"] == 3 and len(diag["llm_requests"]) == 3
    assert diag["tool_rounds"] == 2 and len(diag["tools"]) == 2


def test_diagnostics_opt_in_timings_and_retry_does_not_repeat_tool(monkeypatch):
    assert "diagnostics" not in run_responses([answer()])[0]
    monkeypatch.setenv("NVIDIA_LLM_DIAGNOSTICS", "1")
    result, requests = run_responses([call(), httpx.Response(503), answer("初步資料 83 件。")])
    diag = result["diagnostics"]
    assert diag["model_rounds"] == 2 and diag["tool_rounds"] == 1 and diag["retries"] == 1
    assert len(diag["tools"]) == 1 and len(diag["llm_requests"]) == 3
    assert all(item["duration_ms"] >= 0 for item in diag["tools"] + diag["llm_requests"])
    assert diag["total_ms"] >= sum(item["duration_ms"] for item in diag["llm_requests"])
    assert requests[1] == requests[2] and "test-credential" not in json.dumps(diag)


def test_diagnostics_error_response_is_sanitized(monkeypatch):
    monkeypatch.setenv("NVIDIA_LLM_DIAGNOSTICS", "1")
    monkeypatch.setattr(llm_service, "transport", httpx.MockTransport(lambda request: httpx.Response(401, text="private token")))
    with TestClient(app) as client:
        response = client.post("/api/chat", json={"message": "secret question", "current_dashboard_scope": SCOPE})
    assert response.status_code == 503
    assert response.json()["diagnostics"]["llm_requests"][0]["status"] == 401
    assert "private" not in response.text and "secret question" not in response.text and "test-credential" not in response.text


def test_invalid_optional_model_does_not_break_dashboard_health(monkeypatch):
    monkeypatch.setenv("NVIDIA_MODEL", "unsupported-model-private-value")
    with TestClient(app) as client:
        health = client.get("/health")
        response = client.post("/api/chat", json={"message": "您好", "current_dashboard_scope": SCOPE})
    assert health.status_code == 200 and health.json()["ready"] is True
    assert health.json()["llm"]["model"] is None and "configuration_error" in health.json()["llm"]
    assert response.status_code == 503 and "NVIDIA_MODEL" in response.json()["detail"]
    assert "unsupported-model-private-value" not in response.text + health.text
