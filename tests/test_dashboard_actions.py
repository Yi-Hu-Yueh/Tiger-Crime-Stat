"""Dashboard command regressions. Provider boundary is always mocked."""
import asyncio
import copy
import json
import subprocess
from pathlib import Path

import httpx
import pytest

from app.services.dashboard_actions import UpdateView, validate_actions, view_actions
from app.services.chat_answers import crime_label
from app.services.chat_router import THEFT_CRIME_TYPES, route_message
from app.services.dashboard_router import route_dashboard_message
from app.services.data_service import service
from app.services.llm_service import ChatError, ChatRequest, LLMService, contains_model_protocol
from app.services.llm_tools import execute_tool
from app.services.scope_delta import extract_dashboard_actions, extract_scope_delta

SCOPE = {"selected_counties": ["臺中市"], "selected_years": [2025], "selected_months": list(range(1, 13)),
         "selected_crime_types": ["毒品"], "metric": "rate", "current_district": {"county": "臺中市", "district": "中區"}}
ALL_SCOPE = {**SCOPE, "selected_crime_types": list(service.crime_types), "metric": "count"}
YEAR_SCOPE = {**ALL_SCOPE, "selected_months": [2, 4, 6], "metric": "rate"}
THEFT_SCOPE = {"selected_counties": ["臺中市"], "selected_years": [2024, 2025], "selected_months": list(range(1, 13)),
               "selected_crime_types": ["機車竊盜"], "metric": "rate", "current_district": {"county": "臺中市", "district": "北屯區"}}
DELTA_SCOPE = {"selected_counties": ["臺中市"], "selected_years": [2023], "selected_months": list(range(1, 13)),
               "selected_crime_types": list(service.crime_types), "metric": "rate",
               "current_district": {"county": "臺中市", "district": "東勢區"}}
A = "幫我看 2025 年臺中市北屯區住宅竊盜"
COMMANDS = [A, "改成 2024 年", "看 2024 跟 2025", "改看機車竊盜", "看北屯區住宅竊盜十年趨勢", "比較臺中市跟彰化縣 2025 年毒品"]


@pytest.mark.parametrize(("message", "district", "years", "crimes"), [
    ("北區", "北區", [2023], list(service.crime_types)),
    ("2022", "東勢區", [2022], list(service.crime_types)),
    ("住宅竊盜", "東勢區", [2023], ["住宅竊盜"]),
    ("竊盜", "東勢區", [2023], THEFT_CRIME_TYPES),
    ("2024 跟 2025", "東勢區", [2024, 2025], list(service.crime_types)),
    ("北區 2022 住宅竊盜", "北區", [2022], ["住宅竊盜"]),
])
def test_generic_scope_delta_matrix(message, district, years, crimes):
    delta = extract_scope_delta(message, DELTA_SCOPE)
    assert delta is not None
    action = delta.actions[0]
    assert action["counties"] == ["臺中市"] and action["districts"] == [district]
    assert action["years"] == years and action["crime_types"] == crimes
    assert action["months"] == list(range(1, 13)) and action["metric"] == "rate"
    assert delta.actions[1] == {"type": "select_district", "county": "臺中市", "district": district}
    plan = route_dashboard_message(message, DELTA_SCOPE, delta=delta)
    assert plan is not None and plan.dashboard_actions == delta.actions


def test_scope_delta_supports_county_and_metric_without_prefixes():
    county = extract_scope_delta("臺中市", DELTA_SCOPE).actions[0]
    metric = extract_scope_delta("案件數", DELTA_SCOPE).actions[0]
    assert county["counties"] == ["臺中市"] and county["districts"] == ["東勢區"]
    assert metric["metric"] == "count" and metric["districts"] == ["東勢區"]


def test_explicit_open_map_phrase_emits_map_panel_action():
    actions = extract_dashboard_actions("打開地圖", DELTA_SCOPE)
    assert actions[-1] == {"type": "open_panel", "panel": "map"}


@pytest.mark.parametrize("message", ["2008", "你好", "為什麼會增加？", "這個資料可靠嗎？", "不存在區"])
def test_invalid_or_non_scope_messages_emit_no_structural_action(message):
    assert extract_dashboard_actions(message, DELTA_SCOPE) == ()


def test_ambiguous_district_without_safe_county_is_not_guessed():
    ambiguous = {**DELTA_SCOPE, "selected_counties": ["臺中市", "臺南市"], "current_district": None}
    assert extract_dashboard_actions("北區", ambiguous) == ()
    assert route_dashboard_message("北區", ambiguous) is None


@pytest.mark.parametrize("message", [
    "2025 年臺中市北屯區住宅竊盜有幾件？",
    "幫我看 2025 年臺中市北屯區住宅竊盜",
    "查 2025 北屯區住宅竊盜",
])
def test_clear_statistical_queries_share_the_same_dashboard_scope(message):
    plan = route_dashboard_message(message, ALL_SCOPE)
    assert plan is not None
    assert plan.dashboard_actions[0] == {
        "type": "set_dashboard_scope", "counties": ["臺中市"], "districts": ["北屯區"],
        "years": [2025], "months": list(range(1, 13)), "crime_types": ["住宅竊盜"], "metric": "count",
    }
    assert plan.dashboard_actions[1] == {"type": "select_district", "county": "臺中市", "district": "北屯區"}


def test_bare_supported_year_preserves_dashboard_context():
    plan = route_dashboard_message("2022", YEAR_SCOPE)
    assert plan is not None
    assert plan.dashboard_actions[0] == {
        "type": "set_dashboard_scope", "counties": ["臺中市"], "districts": ["中區"],
        "years": [2022], "months": [2, 4, 6], "crime_types": list(service.crime_types), "metric": "rate",
    }
    assert plan.dashboard_actions[1] == {"type": "select_district", "county": "臺中市", "district": "中區"}


@pytest.mark.parametrize("message", ["2024 跟 2025", "2024、2025", "看 2024 跟 2025"])
def test_standalone_multi_year_forms_preserve_context(message):
    action = route_dashboard_message(message, YEAR_SCOPE).dashboard_actions[0]
    assert action["years"] == [2024, 2025]
    assert action["counties"] == ["臺中市"] and action["districts"] == ["中區"]
    assert action["crime_types"] == list(service.crime_types) and action["months"] == [2, 4, 6] and action["metric"] == "rate"


def test_out_of_range_bare_year_never_creates_dashboard_action_or_model_call(monkeypatch):
    monkeypatch.delenv("NVIDIA_API_KEY", raising=False)
    called = False
    def handle(request):
        nonlocal called
        called = True
        return httpx.Response(500)
    async def run():
        async with LLMService(httpx.MockTransport(handle)) as client:
            return await client.chat(ChatRequest(message="2008", current_dashboard_scope=YEAR_SCOPE))
    result = asyncio.run(run())
    assert result["dashboard_actions"] == [] and result["llm_call_count"] == 0 and called is False
    assert "2016–2025" in result["answer"] and route_dashboard_message("2008", YEAR_SCOPE) is None


def test_six_commands_with_stale_dashboard_and_context_priority():
    history, views = [], []
    for message in COMMANDS:
        plan = route_dashboard_message(message, SCOPE, history)
        assert plan is not None
        views.append(plan.dashboard_actions[0])
        history.extend([{"role": "user", "content": message}, {"role": "assistant", "content": "臺北市中正區不是查詢範圍"}])
    assert views[0] == {"type": "set_dashboard_scope", "counties": ["臺中市"], "districts": ["北屯區"], "years": [2025],
                        "months": list(range(1, 13)), "crime_types": ["住宅竊盜"], "metric": "count"}
    assert views[1]["districts"] == ["北屯區"] and views[1]["crime_types"] == ["住宅竊盜"] and views[1]["years"] == [2024]
    assert views[2]["years"] == [2024, 2025]
    assert views[3]["years"] == [2024, 2025] and views[3]["crime_types"] == ["機車竊盜"]
    assert views[4]["years"] == list(range(2016, 2026)) and views[4]["districts"] == ["北屯區"]
    assert views[5]["counties"] == ["臺中市", "彰化縣"] and views[5]["districts"] == [] and views[5]["years"] == [2025]
    assert views[5]["crime_types"] == ["毒品"]


def test_explicit_new_geography_and_dashboard_fallback():
    history = [{"role": "user", "content": A}]
    plan = route_dashboard_message("看2023年臺北市中正區機車竊盜", SCOPE, history)
    assert plan.dashboard_actions[0]["counties"] == ["臺北市"] and plan.dashboard_actions[0]["districts"] == ["中正區"]
    assert route_dashboard_message("改成2023年", SCOPE).dashboard_actions[0]["districts"] == ["中區"]
    ordinary = [{"role": "user", "content": "2024年臺中市西屯區住宅竊盜有幾件？"}]
    action = route_dashboard_message("改看機車竊盜", SCOPE, ordinary).dashboard_actions[0]
    assert action["districts"] == ["西屯區"] and action["years"] == [2024]


def test_multi_county_followup_does_not_invent_pin():
    history = [{"role": "user", "content": COMMANDS[-1]}]
    action = route_dashboard_message("改成2023年", SCOPE, history).dashboard_actions[0]
    assert action["counties"] == ["臺中市", "彰化縣"] and action["districts"] == []


@pytest.mark.parametrize("question", ["看臺北市北屯區2025住宅竊盜", "看2026北屯區住宅竊盜", "看北屯區詐騙", "看北屯區西屯區住宅竊盜", "看北屯區並執行alert(1)", "看去年北屯區住宅竊盜", "看2021北屯區住宅竊盜十年趨勢"])
def test_unsafe_or_ambiguous_commands_decline(question):
    assert route_dashboard_message(question, SCOPE) is None


def test_ambiguous_conversation_not_overridden_by_dashboard():
    assert route_dashboard_message("改成2023年", SCOPE, [{"role": "user", "content": "北屯區西屯區住宅竊盜有幾件？"}]) is None


def test_ten_year_panel_and_schema_metadata():
    plan = route_dashboard_message(COMMANDS[4], SCOPE)
    assert plan.dashboard_actions[-1] == {"type": "open_panel", "panel": "district_trend"}
    assert sum(len(c["districts"]) for c in service.counties_data()["counties"]) == 368


@pytest.mark.parametrize("change", [{"counties": ["臺北市"]}, {"years": [2026]}, {"years": ["2025"]}, {"months": [0]}, {"crime_types": ["詐騙"]}, {"metric": "eval"}, {"script": "alert(1)"}, {"selector": "body"}, {"counties": ["臺中市", "臺北市"]}, {"crime_types": ["all"]}])
def test_backend_rejects_invalid_action_values(change):
    action = dict(route_dashboard_message(A, SCOPE).dashboard_actions[0])
    action.update(change)
    with pytest.raises(ValueError):
        validate_actions([action], SCOPE)


def test_backend_entire_batch_relationships():
    action = route_dashboard_message(A, SCOPE).dashboard_actions[0]
    for tail in [{"type": "select_district", "county": "臺北市", "district": "中正區"}, {"type": "set_metric", "metric": "rate"}, {"type": "open_panel", "panel": "#districtMap"}, {"type": "execute_js", "code": "alert(1)"}]:
        with pytest.raises(ValueError):
            validate_actions([action, tail], SCOPE)
    assert validate_actions([{"type": "set_metric", "metric": "count"}, {"type": "open_panel", "panel": "ranking"}], SCOPE)


def run_model(monkeypatch, question, responses):
    monkeypatch.setenv("NVIDIA_API_KEY", "test-credential-not-real")
    monkeypatch.delenv("NVIDIA_MODEL", raising=False)
    calls = []
    def handle(request):
        calls.append(json.loads(request.content))
        reply = responses[min(len(calls) - 1, len(responses) - 1)]
        if isinstance(reply, Exception):
            raise reply
        return httpx.Response(200, json=reply)
    async def run():
        async with LLMService(httpx.MockTransport(handle)) as client:
            return await client.chat(ChatRequest(message=question, current_dashboard_scope=SCOPE))
    return asyncio.run(run()), calls


def final_answer(text):
    return {"choices": [{"finish_reason": "stop", "message": {"role": "assistant", "content": text}}]}


@pytest.mark.parametrize("model_name", ["z-ai/glm-5.3-flash", "z-ai/glm-5.3"])
def test_bare_year_action_survives_api_key_and_runtime_model_paths(monkeypatch, model_name):
    monkeypatch.setenv("NVIDIA_API_KEY", "environment-key")
    monkeypatch.setenv("NVIDIA_MODEL", "z-ai/glm-5.3-flash")
    captured = []
    def handle(request):
        captured.append({"authorization": request.headers["authorization"], "model": json.loads(request.content)["model"]})
        return httpx.Response(200, json=final_answer("已切換至 2022 年。"))
    async def run():
        async with LLMService(httpx.MockTransport(handle)) as client:
            return await client.chat(ChatRequest(message="2022", current_dashboard_scope=YEAR_SCOPE),
                                     api_key="request-key", model_name=model_name)
    result = asyncio.run(run())
    action = result["dashboard_actions"][0]
    assert action["years"] == [2022] and action["districts"] == ["中區"]
    assert action["crime_types"] == list(service.crime_types) and action["months"] == [2, 4, 6] and action["metric"] == "rate"
    assert result["routing_mode"] == "deterministic_fast_path" and result["llm_call_count"] == 1
    assert captured == [{"authorization": "Bearer request-key", "model": model_name}]


@pytest.mark.parametrize("model_name", ["z-ai/glm-5.3-flash", "z-ai/glm-5.3"])
def test_district_only_delta_survives_api_key_and_model_paths_without_extra_routing_call(monkeypatch, model_name):
    monkeypatch.setenv("NVIDIA_API_KEY", "environment-key")
    captured = []
    def handle(request):
        captured.append({"authorization": request.headers["authorization"], "model": json.loads(request.content)["model"]})
        return httpx.Response(200, json=final_answer("2023 年臺中市北區統計已查證。"))
    async def run():
        async with LLMService(httpx.MockTransport(handle)) as client:
            return await client.chat(ChatRequest(message="北區", current_dashboard_scope=DELTA_SCOPE),
                                     api_key="request-key", model_name=model_name)
    result = asyncio.run(run())
    action = result["dashboard_actions"][0]
    assert action["counties"] == ["臺中市"] and action["districts"] == ["北區"]
    assert action["years"] == [2023] and action["crime_types"] == list(service.crime_types)
    assert result["routing_mode"] == "deterministic_fast_path"
    assert result["llm_call_count"] == len(captured) == 1
    assert captured == [{"authorization": "Bearer request-key", "model": model_name}]


def test_scope_actions_are_combined_even_when_answer_uses_general_llm_branch(monkeypatch):
    monkeypatch.setenv("NVIDIA_API_KEY", "environment-key")
    monkeypatch.delenv("NVIDIA_MODEL", raising=False)
    calls = []
    def handle(request):
        calls.append(json.loads(request.content))
        return httpx.Response(200, json=final_answer("資料可靠性需依來源與完整度判讀。"))
    async def run():
        async with LLMService(httpx.MockTransport(handle)) as client:
            return await client.chat(ChatRequest(message="北區的資料可靠嗎？", current_dashboard_scope=DELTA_SCOPE))
    result = asyncio.run(run())
    assert route_dashboard_message("北區的資料可靠嗎？", DELTA_SCOPE) is None
    assert result["routing_mode"] == "llm_tool_calling" and result["llm_call_count"] == len(calls) == 1
    assert result["dashboard_actions"][0]["districts"] == ["北區"]


@pytest.mark.parametrize("request_key,expected_key", [(None, "environment-key"), ("request-key", "request-key")])
def test_statistical_question_keeps_dashboard_actions_with_api_key_and_model_headers(monkeypatch, request_key, expected_key):
    monkeypatch.setenv("NVIDIA_API_KEY", "environment-key")
    monkeypatch.delenv("NVIDIA_MODEL", raising=False)
    authorizations, models = [], []
    def handle(request):
        authorizations.append(request.headers["authorization"])
        models.append(json.loads(request.content)["model"])
        return httpx.Response(200, json=final_answer("北屯區住宅竊盜為 83 件。"))
    async def run():
        async with LLMService(httpx.MockTransport(handle)) as client:
            return await client.chat(ChatRequest(
                message="2025 年臺中市北屯區住宅竊盜有幾件？",
                current_dashboard_scope=ALL_SCOPE,
            ), api_key=request_key, model_name="z-ai/glm-5.3")
    result = asyncio.run(run())
    scope = result["dashboard_actions"][0]
    assert scope["counties"] == ["臺中市"] and scope["districts"] == ["北屯區"]
    assert scope["years"] == [2025] and scope["crime_types"] == ["住宅竊盜"]
    assert result["dashboard_actions"][1] == {"type": "select_district", "county": "臺中市", "district": "北屯區"}
    assert "83 件" in result["answer"] and authorizations == [f"Bearer {expected_key}"]
    assert models == ["z-ai/glm-5.3"] and result["model"] == "z-ai/glm-5.3"


@pytest.mark.parametrize("message", COMMANDS)
def test_fast_path_one_call_and_timeout_still_returns_validated_actions(monkeypatch, message):
    result, calls = run_model(monkeypatch, message, [httpx.ReadTimeout("offline")])
    assert result["routing_mode"] == "deterministic_fast_path" and result["llm_call_count"] == len(calls) == 1
    assert result["answer_mode"] == "deterministic_fallback"
    assert validate_actions(result["dashboard_actions"], SCOPE) == result["dashboard_actions"]
    if message == A:
        assert "83 件" in result["answer"]


def test_model_function_schema_actions_validated_and_statistics_grounded(monkeypatch):
    view = dict(route_dashboard_message(A, SCOPE).dashboard_actions[0]);view.pop("type")
    tool = {"choices": [{"finish_reason": "tool_calls", "message": {"role": "assistant", "content": None,
             "tool_calls": [{"id": "view-1", "type": "function", "function": {"name": "update_dashboard_view", "arguments": json.dumps(view)}}]}}]}
    result, calls = run_model(monkeypatch, "請幫忙整理並同步合適的檢視", [tool, final_answer("查證住宅竊盜為83件。")])
    assert len(calls) == 1 and result["dashboard_actions"][0]["districts"] == ["北屯區"]
    assert not contains_model_protocol(result["answer"])
    assert result["tool_results"][0]["result"]["statistics"]["rows"][0]["incident_count"] == 83
    tool["choices"][0]["message"]["tool_calls"][0]["function"]["arguments"] = json.dumps({**view, "counties": ["臺北市"]})
    with pytest.raises(ChatError):
        run_model(monkeypatch, "請幫忙整理並同步合適的檢視", [tool])


@pytest.mark.parametrize("markup", [
    '<tool_call>update_dashboard_view<arg_key>years</arg_key><arg_value>[2024]</arg_value></tool_call>',
    '<tool_call>{"name":"update_dashboard_view"}',
    '&lt;tool_call&gt;update_dashboard_view&lt;/tool_call&gt;',
    '<arg_key>years</arg_key><arg_value>2024',
])
def test_fast_path_protocol_markup_never_reaches_frontend(monkeypatch, markup):
    result, calls = run_model(monkeypatch, "改成 2024 年", [final_answer(markup)])
    # Explicit dashboard action still validates and the rejected model text is
    # replaced locally without a recovery request.
    assert len(calls) == result["llm_call_count"] == 1
    assert result["answer_mode"] == "deterministic_fallback"
    assert result["dashboard_actions"][0]["years"] == [2024]
    assert not contains_model_protocol(result["answer"])
    assert "<tool_call" not in result["answer"] and "arg_key" not in result["answer"]


def test_fast_path_structured_tool_call_only_is_consumed_without_retry(monkeypatch):
    structured = {"choices": [{"finish_reason": "tool_calls", "message": {"role": "assistant", "content": None,
                  "tool_calls": [{"id": "unexpected-1", "type": "function", "function": {
                      "name": "update_dashboard_view", "arguments": '{"years":[2024]}'}}]}}]}
    result, calls = run_model(monkeypatch, "改成 2024 年", [structured])
    assert len(calls) == result["llm_call_count"] == 1
    assert result["answer_mode"] == "deterministic_fallback"
    assert result["dashboard_actions"][0]["years"] == [2024]
    assert "tool_call" not in result["answer"]


def test_normal_fast_path_answer_is_unchanged(monkeypatch):
    result, calls = run_model(monkeypatch, A, [final_answer("北屯區住宅竊盜為 83 件。")])
    assert len(calls) == 1 and result["answer"] == "北屯區住宅竊盜為 83 件。"


def test_frontend_protocol_guard_and_normal_text():
    root = Path(__file__).resolve().parents[1]
    script = r'''
const fs=require('fs'),vm=require('vm');
const context={Intl,URLSearchParams,DashboardLayoutState:{create:()=>({})},CrimeSelectionState:{},document:{addEventListener(){},getElementById(){return{}},querySelectorAll(){return[]}}};
vm.createContext(context);vm.runInContext(fs.readFileSync(process.argv[1],'utf8'),context);
const values=[
 context.chatAssistantText('<tool_call>update_dashboard_view</tool_call>'),
 context.chatAssistantText('<arg_key>years</arg_key><arg_value>2024'),
 context.chatAssistantText('&lt;tool_call&gt;broken'),
 context.chatAssistantText('北屯區住宅竊盜為 83 件。')
];
process.stdout.write(JSON.stringify(values));
'''
    result = subprocess.run(["node", "-e", script, str(root / "app/static/app.js")], capture_output=True, text=True, encoding="utf-8", check=True)
    assert json.loads(result.stdout) == ["", "", "", "北屯區住宅竊盜為 83 件。"]


@pytest.mark.parametrize("message", ["改看竊盜", "看竊盜", "竊盜案件", "竊盜趨勢"])
def test_generic_theft_selects_exactly_three_canonical_categories(message):
    plan = route_dashboard_message(message, THEFT_SCOPE)
    assert plan is not None
    action = plan.dashboard_actions[0]
    assert action["crime_types"] == THEFT_CRIME_TYPES
    assert "竊盜" not in action["crime_types"]
    assert set(action["crime_types"]) <= set(service.crime_types)
    if "趨勢" in message:
        assert action["years"] == list(range(2016, 2026))
        assert plan.dashboard_actions[-1] == {"type": "open_panel", "panel": "district_trend"}


@pytest.mark.parametrize("crime_type", THEFT_CRIME_TYPES)
def test_explicit_theft_category_keeps_single_category(crime_type):
    action = route_dashboard_message(f"改看{crime_type}", THEFT_SCOPE).dashboard_actions[0]
    assert action["crime_types"] == [crime_type]


def test_grouped_theft_preserves_dashboard_context_and_statistic_router():
    action = route_dashboard_message("改看竊盜", THEFT_SCOPE).dashboard_actions[0]
    assert action == {"type": "set_dashboard_scope", "counties": ["臺中市"], "districts": ["北屯區"],
                      "years": [2024, 2025], "months": list(range(1, 13)),
                      "crime_types": THEFT_CRIME_TYPES, "metric": "rate"}
    plan = route_message("竊盜案件", THEFT_SCOPE)
    assert plan is not None and plan.tools[0].arguments["crime_types"] == THEFT_CRIME_TYPES


def test_grouped_theft_quality_and_language_remain_honest():
    result = execute_tool("get_crime_trend", {"county": "臺中市", "district": "北屯區", "crime_types": THEFT_CRIME_TYPES})
    aggregate = {row["year"]: row for row in result["aggregate"]["values"]}
    motorcycle = next(item for item in result["crime_types"] if item["crime_type"] == "機車竊盜")
    incomplete_years = [row["year"] for row in motorcycle["values"] if row["district_data_quality"] == "incomplete_assignment"]
    assert incomplete_years
    assert all(aggregate[year]["district_data_quality"] != "complete" for year in incomplete_years)
    label = crime_label(THEFT_CRIME_TYPES)
    assert "三類竊盜合計" in label and "非官方獨立案類" in label
    assert all(crime_type in label for crime_type in THEFT_CRIME_TYPES)
    assert "竊盜" not in service.crime_types


def test_frontend_transaction_and_refresh_without_chat_loop():
    root = Path(__file__).resolve().parents[1]
    actions = list(route_dashboard_message(A, SCOPE).dashboard_actions)
    script = r'''
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const nodes=new Proxy({},{get:(o,k)=>o[k]||(o[k]={value:'',checked:false})});
const context={Intl,URLSearchParams,DashboardActions:require(process.argv[1]),DashboardLayoutState:{create:()=>({verticalRatio:.54,horizontalRatio:.62})},CrimeSelectionState:{summary:values=>values.join('、')},document:{addEventListener(){},getElementById:id=>nodes[id],querySelectorAll:()=>[]}};
vm.createContext(context);vm.runInContext(fs.readFileSync(process.argv[2],'utf8'),context);
const run=s=>vm.runInContext(s,context),actions=JSON.parse(process.argv[3]),metadata=JSON.parse(process.argv[4]);
context.actions=actions;context.metadata=metadata;
run(`state.meta={years:[2016,2017,2018,2019,2020,2021,2022,2023,2024,2025],crime_types:metadata.crime_types};state.countiesMeta=metadata;state.navigation.zoom=2;state.hoveredDistrict={county:'臺中市',district:'中區'};`);
run(`var refreshes=0,resets=0,panels=[],mode='success',snapshots=[];updatePickerSummaries=()=>{};updateCrimeTiles=()=>{};updatePinIndicator=()=>{};invalidateTrendRequest=()=>{};resetMapNavigation=()=>{resets++};openDashboardPanel=p=>panels.push(p);refreshAll=async()=>{refreshes++;snapshots.push(JSON.stringify({c:state.counties,d:state.selectedDistrict,y:state.years}));return mode!=='failure'};`);
(async()=>{
 const initial=run('JSON.stringify(state)');
 try{await run(`applyDashboardActions([...actions,{type:'execute_js',code:'alert(1)'}])`);throw Error('accepted invalid')}catch(e){assert(!e.message.includes('accepted invalid'))}
 assert.equal(run('JSON.stringify(state)'),initial);assert.equal(run('refreshes'),0);
 const status=await run('applyDashboardActions(actions)');assert(status.includes('已同步 Dashboard'));
 assert.equal(run('state.selectedDistrict.district'),'北屯區');assert.equal(run('state.isDistrictPinned'),true);assert.equal(run('state.metric'),'count');
 assert.equal(run('state.navigation.zoom'),2);assert.equal(run('state.layout.horizontalRatio'),.62);assert.equal(run('resets'),0);assert.equal(run('refreshes'),1);assert.equal(run('chatState.history.length'),0);
 assert.equal(run('panels.length'),0);
 for(const bad of [{type:'open_panel',panel:'body'},{type:'select_district',county:'臺北市',district:'北屯區'},{type:'set_metric',metric:'script'}]){
  context.bad=bad;const before=run('JSON.stringify(state)');try{await run('applyDashboardActions([bad])');throw Error('accepted invalid')}catch(e){assert(!e.message.includes('accepted invalid'))}assert.equal(run('JSON.stringify(state)'),before);
 }
 context.multi=[{...actions[0],counties:['臺中市','彰化縣'],districts:[]}];await run('applyDashboardActions(multi)');assert.equal(run('state.selectedDistrict'),null);assert.equal(run('state.isDistrictPinned'),false);assert.equal(run('resets'),1);
 const prior=run('JSON.stringify([state.counties,state.years,state.crimeTypes,state.selectedDistrict])');run("mode='failure'");try{await run('applyDashboardActions(actions)')}catch(e){assert(e.message.includes('保留先前'))}
 assert.equal(run('JSON.stringify([state.counties,state.years,state.crimeTypes,state.selectedDistrict])'),prior);
 process.stdout.write('passed');
})().catch(e=>{process.stderr.write(e.stack);process.exitCode=1});
'''
    meta = {**service.counties_data(), "crime_types": list(service.crime_types)}
    result = subprocess.run(["node", "-e", script, str(root / "app/static/dashboard_actions.js"), str(root / "app/static/app.js"), json.dumps(actions), json.dumps(meta)], capture_output=True, text=True, encoding="utf-8")
    assert result.returncode == 0, result.stderr
    assert result.stdout == "passed"


def test_chat_response_applies_actions_replaces_scope_and_shows_sync_message():
    root = Path(__file__).resolve().parents[1]
    actions = list(route_dashboard_message("2025 年臺中市北屯區住宅竊盜有幾件？", ALL_SCOPE).dashboard_actions)
    script = r'''
const fs=require('fs'),vm=require('vm'),assert=require('assert');
class Node{
 constructor(id=''){this.id=id;this.attrs={};this.handlers={};this.children=[];this.dataset={};this.hidden=false;this.value='';this.textContent='';this.scrollTop=0;this.scrollHeight=500;this.type='';}
 addEventListener(t,f){this.handlers[t]=f} setAttribute(k,v){this.attrs[k]=v} getAttribute(k){return this.attrs[k]}
 appendChild(n){n.parent=this;this.children.push(n)} querySelectorAll(s){return s==='.chat-message'?this.children.filter(n=>n.className==='chat-message'):[]}
 focus(){} remove(){if(this.parent)this.parent.children=this.parent.children.filter(n=>n!==this)}
}
const nodes=new Proxy({},{get:(o,k)=>o[k]||(o[k]=new Node(k))});
const actions=JSON.parse(process.argv[3]),metadata=JSON.parse(process.argv[4]);let request;
const context={Intl,URLSearchParams,AbortController,setTimeout,clearTimeout,
 DashboardActions:require(process.argv[1]),DashboardLayoutState:{create:()=>({verticalRatio:.54,horizontalRatio:.62})},CrimeSelectionState:{summary:v=>v.join('、')},DistrictSelectionState:{displayedIdentity:(hovered,selected,pinned)=>pinned?selected:(hovered||selected)},
 document:{addEventListener(){},getElementById:id=>nodes[id],createElement:()=>new Node(),querySelectorAll:()=>[]},
 fetch:async(url,options)=>{request={url,headers:{...options.headers},body:JSON.parse(options.body)};return{ok:true,json:async()=>({answer:'北屯區住宅竊盜為 83 件。',dashboard_actions:actions})}}
};
vm.createContext(context);vm.runInContext(fs.readFileSync(process.argv[2],'utf8'),context);
const run=s=>vm.runInContext(s,context);context.metadata=metadata;
run(`state.meta={years:[2016,2017,2018,2019,2020,2021,2022,2023,2024,2025],crime_types:metadata.crime_types};state.countiesMeta=metadata;state.counties=['臺中市'];state.years=[2025];state.months=[1,2,3,4,5,6,7,8,9,10,11,12];state.crimeTypes=[...metadata.crime_types];state.metric='count';state.selectedDistrict={county:'臺中市',district:'中區'};state.isDistrictPinned=true;state.hoveredDistrict=null;`);
run(`updatePickerSummaries=()=>{};updateCrimeTiles=()=>{};updatePinIndicator=()=>{};invalidateTrendRequest=()=>{};resetMapNavigation=()=>{};openDashboardPanel=()=>{};refreshAll=async()=>true;`);
nodes.nvidiaApiKey.value='request-key';nodes.nvidiaApiKey.type='password';nodes.chatInput.value='2025 年臺中市北屯區住宅竊盜有幾件？';nodes.chatEmpty.hidden=false;
(async()=>{
 await run('sendChat()');
 const messages=nodes.chatHistory.children.filter(n=>n.className==='chat-message').map(n=>({label:n.children[0].textContent,text:n.children[1].textContent}));
 assert.deepEqual(run('[...state.counties]'),['臺中市']);assert.deepEqual(run('[...state.years]'),[2025]);assert.deepEqual(run('[...state.crimeTypes]'),['住宅竊盜']);
 assert.equal(run('state.selectedDistrict.district'),'北屯區');assert.equal(run('state.isDistrictPinned'),true);
 assert(messages.some(m=>m.label==='系統'&&m.text.includes('已同步 Dashboard')));assert(messages.some(m=>m.label==='AI 助理'&&m.text.includes('83 件')));
 assert.equal(request.headers['X-NVIDIA-API-Key'],'request-key');assert.equal(request.headers['X-NVIDIA-Model'],'z-ai/glm-5.3-flash');assert.equal(request.body.current_dashboard_scope.current_district.district,'中區');
 process.stdout.write('passed');
})().catch(e=>{process.stderr.write(e.stack);process.exitCode=1});
'''
    meta = {**service.counties_data(), "crime_types": list(service.crime_types)}
    result = subprocess.run(["node", "-e", script, str(root / "app/static/dashboard_actions.js"), str(root / "app/static/app.js"),
                             json.dumps(actions), json.dumps(meta)], capture_output=True, text=True, encoding="utf-8")
    assert result.returncode == 0, result.stderr
    assert result.stdout == "passed"


def test_bare_year_chat_applies_action_preserves_scope_and_shows_sync_message():
    root = Path(__file__).resolve().parents[1]
    actions = list(route_dashboard_message("2022", YEAR_SCOPE).dashboard_actions)
    script = r'''
const fs=require('fs'),vm=require('vm'),assert=require('assert');
class Node{
 constructor(id=''){this.id=id;this.attrs={};this.handlers={};this.children=[];this.dataset={};this.hidden=false;this.value='';this.textContent='';this.scrollTop=0;this.scrollHeight=500;this.type='';}
 addEventListener(t,f){this.handlers[t]=f} setAttribute(k,v){this.attrs[k]=v} getAttribute(k){return this.attrs[k]}
 appendChild(n){n.parent=this;this.children.push(n)} querySelectorAll(s){return s==='.chat-message'?this.children.filter(n=>n.className==='chat-message'):[]}
 focus(){} remove(){if(this.parent)this.parent.children=this.parent.children.filter(n=>n!==this)}
}
const nodes=new Proxy({},{get:(o,k)=>o[k]||(o[k]=new Node(k))});
const actions=JSON.parse(process.argv[3]),metadata=JSON.parse(process.argv[4]);let request;
const context={Intl,URLSearchParams,AbortController,setTimeout,clearTimeout,
 DashboardActions:require(process.argv[1]),DashboardLayoutState:{create:()=>({verticalRatio:.54,horizontalRatio:.62})},CrimeSelectionState:{summary:v=>v.join('、')},DistrictSelectionState:{displayedIdentity:(hovered,selected,pinned)=>pinned?selected:(hovered||selected)},
 document:{addEventListener(){},getElementById:id=>nodes[id],createElement:()=>new Node(),querySelectorAll:()=>[]},
 fetch:async(url,options)=>{request={url,headers:{...options.headers},body:JSON.parse(options.body)};return{ok:true,json:async()=>({answer:'已切換至 2022 年。',dashboard_actions:actions})}}
};
vm.createContext(context);vm.runInContext(fs.readFileSync(process.argv[2],'utf8'),context);
const run=s=>vm.runInContext(s,context);context.metadata=metadata;
run(`state.meta={years:[2016,2017,2018,2019,2020,2021,2022,2023,2024,2025],crime_types:metadata.crime_types};state.countiesMeta=metadata;state.counties=['臺中市'];state.years=[2025];state.months=[2,4,6];state.crimeTypes=[...metadata.crime_types];state.metric='rate';state.selectedDistrict={county:'臺中市',district:'中區'};state.isDistrictPinned=true;state.hoveredDistrict=null;`);
run(`updatePickerSummaries=()=>{};updateCrimeTiles=()=>{};updatePinIndicator=()=>{};invalidateTrendRequest=()=>{};resetMapNavigation=()=>{};openDashboardPanel=()=>{};refreshAll=async()=>true;`);
nodes.nvidiaApiKey.value='request-key';nodes.nvidiaModel.value='z-ai/glm-5.3';nodes.chatInput.value='2022';nodes.chatEmpty.hidden=false;
(async()=>{
 await run('sendChat()');
 const messages=nodes.chatHistory.children.filter(n=>n.className==='chat-message').map(n=>({label:n.children[0].textContent,text:n.children[1].textContent}));
 assert.deepEqual(run('[...state.counties]'),['臺中市']);assert.deepEqual(run('[...state.years]'),[2022]);assert.deepEqual(run('[...state.months]'),[2,4,6]);
 assert.deepEqual(run('[...state.crimeTypes]'),metadata.crime_types);assert.equal(run('state.metric'),'rate');
 assert.equal(run('state.selectedDistrict.district'),'中區');assert.equal(run('state.isDistrictPinned'),true);
 assert(messages.some(m=>m.label==='系統'&&m.text.includes('已同步 Dashboard')));
 assert.equal(request.headers['X-NVIDIA-API-Key'],'request-key');assert.equal(request.headers['X-NVIDIA-Model'],'z-ai/glm-5.3');
 assert.deepEqual(request.body.current_dashboard_scope.selected_years,[2025]);assert.equal(request.body.current_dashboard_scope.current_district.district,'中區');
 process.stdout.write('passed');
})().catch(e=>{process.stderr.write(e.stack);process.exitCode=1});
'''
    meta = {**service.counties_data(), "crime_types": list(service.crime_types)}
    result = subprocess.run(["node", "-e", script, str(root / "app/static/dashboard_actions.js"), str(root / "app/static/app.js"),
                             json.dumps(actions), json.dumps(meta)], capture_output=True, text=True, encoding="utf-8")
    assert result.returncode == 0, result.stderr
    assert result.stdout == "passed"
