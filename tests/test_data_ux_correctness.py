from __future__ import annotations

import asyncio
import json
import subprocess
from datetime import date
from pathlib import Path

import httpx

from app.data.major_events_2016_2025 import MAJOR_EVENTS_2016_2025
from app.services.llm_service import ChatRequest, LLMService, dashboard_scope_text


ROOT = Path(__file__).resolve().parents[1]
ALL_MONTHS = list(range(1, 13))
SCOPE = {
    "selected_counties": ["臺中市"],
    "selected_years": [2025],
    "selected_months": ALL_MONTHS,
    "selected_crime_types": ["住宅竊盜"],
    "metric": "count",
    "current_district": {"county": "臺中市", "district": "北屯區"},
}


def test_every_catalog_event_overlaps_only_its_displayed_year_and_has_unique_sourced_identity():
    seen_ids = set()
    seen_entries = set()
    for year, scopes in MAJOR_EVENTS_2016_2025.items():
        calendar_start, calendar_end = date(year, 1, 1), date(year, 12, 31)
        for scope, events in scopes.items():
            for event in events:
                start, end = date.fromisoformat(event["start_date"]), date.fromisoformat(event["end_date"])
                assert start <= calendar_end and end >= calendar_start
                assert event["year"] == year and event["scope"] == scope
                assert event["id"] not in seen_ids
                seen_ids.add(event["id"])
                identity = (event["title"], event["start_date"], event["end_date"], event["scope"])
                assert identity not in seen_entries
                seen_entries.add(identity)
                assert event["source_title"] and event["source_agency"]
                assert event["source_url"].startswith("https://")
    assert len(seen_ids) == len(seen_entries) == 60


def test_scope_text_reports_actual_validated_dashboard_state():
    assert dashboard_scope_text(SCOPE) == "臺中市 › 北屯區｜2025 年｜全年｜住宅竊盜"
    changed = {
        **SCOPE,
        "selected_years": [2024, 2025],
        "selected_months": [1, 3],
        "selected_crime_types": ["住宅竊盜", "汽車竊盜", "機車竊盜"],
    }
    assert dashboard_scope_text(changed) == "臺中市 › 北屯區｜2024–2025 年｜1、3 月｜住宅竊盜、汽車竊盜、機車竊盜"


def test_unsupported_year_is_local_state_preserving_and_uses_no_provider_or_tool():
    provider_requests = []

    def provider(request):
        provider_requests.append(request)
        return httpx.Response(500)

    async def run():
        async with LLMService(httpx.MockTransport(provider)) as instance:
            return await instance.chat(ChatRequest(message="2008", current_dashboard_scope=SCOPE))

    result = asyncio.run(run())
    assert "2008 年不在目前資料範圍內" in result["answer"]
    assert "2016–2025" in result["answer"]
    assert "臺中市 › 北屯區｜2025 年｜全年｜住宅竊盜" in result["answer"]
    assert "篩選條件未變更" in result["answer"]
    assert result["dashboard_actions"] == []
    assert result["tool_results"] == [] and result["tools_used"] == []
    assert result["llm_call_count"] == 0 and provider_requests == []


def test_unsupported_year_response_changes_with_actual_scope_not_example_constants():
    scope = {
        **SCOPE,
        "selected_counties": ["彰化縣"],
        "selected_years": [2022, 2023],
        "selected_months": [5],
        "selected_crime_types": ["毒品"],
        "current_district": {"county": "彰化縣", "district": "員林市"},
    }

    async def run():
        return await LLMService().chat(ChatRequest(message="請看２００８年", current_dashboard_scope=scope))

    result = asyncio.run(run())
    assert "彰化縣 › 員林市｜2022–2023 年｜5 月｜毒品" in result["answer"]
    assert "2025 年臺中市北屯區住宅竊盜" not in result["answer"]
    assert result["dashboard_actions"] == [] and result["llm_call_count"] == 0


def test_scope_header_tracks_filter_state_and_validated_dashboard_action():
    script = r'''
const fs=require('fs'),vm=require('vm');
const elements={detailScopeHeader:{textContent:''}};
const context={
  CrimeSelectionState:require(process.argv[1]),DistrictSelectionState:require(process.argv[2]),
  DashboardActions:require(process.argv[3]),DashboardLayoutState:{create:()=>({})},MapNavigation:{},MapProjection:{},
  Intl,URLSearchParams,document:{addEventListener:()=>{},getElementById:id=>elements[id]||null}
};
vm.createContext(context);vm.runInContext(fs.readFileSync(process.argv[4],'utf8'),context);
const meta={years:[2016,2017,2018,2019,2020,2021,2022,2023,2024,2025],crime_types:['毒品','強盜','搶奪','住宅竊盜','汽車竊盜','機車竊盜','強制性交','組織犯罪防制條例'],counties:[{county:'臺中市',districts:['北屯區']}]};
vm.runInContext(`state.meta=${JSON.stringify(meta)};state.countiesMeta={county_count:22};state.counties=['臺中市'];state.years=[2025];state.months=[1,2,3,4,5,6,7,8,9,10,11,12];state.crimeTypes=['住宅竊盜'];state.selectedDistrict={county:'臺中市',district:'北屯區'};state.isDistrictPinned=true;updateScopeHeader()`,context);
const first=elements.detailScopeHeader.textContent;
context.action=[{type:'set_dashboard_scope',counties:['臺中市'],districts:['北屯區'],years:[2024,2025],months:[1,2,3,4,5,6,7,8,9,10,11,12],crime_types:['住宅竊盜','汽車竊盜','機車竊盜'],metric:'count'}];
vm.runInContext(`Object.assign(state,DashboardActions.prepare(action,state,state.meta).state);updateScopeHeader(state.selectedDistrict)`,context);
process.stdout.write(JSON.stringify({first,changed:elements.detailScopeHeader.textContent}));
'''
    files = [ROOT / "app/static" / name for name in ("crime_selection.js", "selection_state.js", "dashboard_actions.js", "app.js")]
    result = subprocess.run(["node", "-e", script, *(str(path) for path in files)], capture_output=True, text=True, encoding="utf-8")
    assert result.returncode == 0, result.stderr
    rendered = json.loads(result.stdout)
    assert rendered["first"] == "臺中市 › 北屯區｜2025｜全年｜住宅竊盜"
    assert rendered["changed"] == "臺中市 › 北屯區｜2024–2025｜全年｜住宅竊盜、汽車竊盜、機車竊盜"


def test_scope_header_is_sticky_and_shared_by_map_and_llm_workspace():
    html = (ROOT / "app/static/index.html").read_text(encoding="utf-8")
    css = (ROOT / "app/static/styles.css").read_text(encoding="utf-8")
    js = (ROOT / "app/static/app.js").read_text(encoding="utf-8")
    assert html.count('id="detailScopeHeader"') == 1
    assert html.index('id="detailScopeHeader"') > html.index('class="detail-panel panel"')
    assert "position:sticky" in css[css.index(".detail-scope-header"):]
    assert "updateScopeHeader()" in js and "updateScopeHeader(row)" in js
    assert 'if(body.dashboard_actions?.length)' in js


def test_nvidia_smoke_marker_is_not_injected_by_application_logic():
    application_sources = [*ROOT.glob("app/**/*.py"), *ROOT.glob("app/static/*.js"), *ROOT.glob("app/static/*.html")]
    marker = "NVIDIA" + "_LIVE_OK"
    assert all(marker not in path.read_text(encoding="utf-8") for path in application_sources)
