from __future__ import annotations

import json
import subprocess
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from app.services.data_service import CRIME_TYPE_ORDER


CLIENT = TestClient(app)
ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "app" / "static"


def trend_state_scenario() -> dict:
    script = r"""
const fs = require("fs");
const vm = require("vm");
const charts={innerHTML:""};
const status={hidden:false,textContent:"載入趨勢資料中…",className:"trend-status loading"};
const context={
  CrimeSelectionState:require(process.argv[1]),
  DistrictSelectionState:require(process.argv[2]),
  DashboardLayoutState:{create:()=>({verticalRatio:.54,horizontalRatio:.62,verticalMode:null,horizontalMode:null})},
  MapNavigation:{},MapProjection:{},Intl,URLSearchParams,console,innerWidth:1400,innerHeight:900,
  document:{getElementById:id=>id==="crimeTrendCharts"?charts:id==="trendStatus"?status:{},addEventListener:()=>{},querySelectorAll:()=>[]},
};
context.globalThis=context;
vm.createContext(context);
vm.runInContext(fs.readFileSync(process.argv[3],"utf8"),context);
const initial=JSON.parse(vm.runInContext('JSON.stringify({trendState:state.trendState,status:document.getElementById("trendStatus")})',context));
vm.runInContext(`state.map={districts:[
  {county:"臺中市",district:"無資料區",incident_count:null},
  {county:"臺中市",district:"北屯區",incident_count:5}
]};state.hoveredDistrict=null;state.selectedDistrict=null;state.isDistrictPinned=false;globalThis.defaultRow=ensureDisplayedDistrict();`,context);
const defaultDistrict=JSON.parse(vm.runInContext('JSON.stringify({row:globalThis.defaultRow,hovered:state.hoveredDistrict})',context));
const values=Array.from({length:10},(_,index)=>({year:2016+index,incident_count:index,population:100000,rate:index,district_data_quality:"complete"}));
context.readyData={aggregate:{title:"全部案類（8 類合計）",values},crime_types:[{crime_type:"住宅竊盜",values}]};
vm.runInContext('state.crimeTypes=["住宅竊盜"];renderCrimeTypeTrends(readyData)',context);
const ready=JSON.parse(vm.runInContext('JSON.stringify({trendState:state.trendState,status:document.getElementById("trendStatus"),html:document.getElementById("crimeTrendCharts").innerHTML})',context));
const prior=charts.innerHTML;
vm.runInContext('setTrendState("loading","載入趨勢資料中…",{preserveCharts:true})',context);
const refresh=JSON.parse(vm.runInContext('JSON.stringify({trendState:state.trendState,status:document.getElementById("trendStatus"),html:document.getElementById("crimeTrendCharts").innerHTML})',context));
context.emptyData={aggregate:null,crime_types:[{crime_type:"住宅竊盜",values:values.map(row=>({...row,incident_count:null,rate:null,district_data_quality:"unavailable"}))}]};
vm.runInContext('renderCrimeTypeTrends(emptyData)',context);
const empty=JSON.parse(vm.runInContext('JSON.stringify({trendState:state.trendState,status:document.getElementById("trendStatus"),html:document.getElementById("crimeTrendCharts").innerHTML})',context));
vm.runInContext('setTrendState("error","趨勢資料載入失敗，請重新整理或重新選擇條件")',context);
const error=JSON.parse(vm.runInContext('JSON.stringify({trendState:state.trendState,status:document.getElementById("trendStatus"),html:document.getElementById("crimeTrendCharts").innerHTML})',context));
process.stdout.write(JSON.stringify({initial,defaultDistrict,ready,refresh,refreshPreserved:refresh.html===prior,empty,error}));
"""
    completed = subprocess.run(
        [
            "node",
            "-e",
            script,
            str(STATIC / "crime_selection.js"),
            str(STATIC / "selection_state.js"),
            str(STATIC / "app.js"),
        ],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return json.loads(completed.stdout)


def test_initial_html_and_state_render_visible_loading_instead_of_empty_collection():
    html = CLIENT.get("/").text
    source = (STATIC / "app.js").read_text(encoding="utf-8")
    assert 'id="trendStatus" class="trend-status loading"' in html
    assert "載入趨勢資料中…" in html
    assert 'trendState:"loading"' in source
    result = trend_state_scenario()
    assert result["initial"]["trendState"] == "loading"
    assert result["initial"]["status"]["hidden"] is False
    assert result["initial"]["status"]["textContent"] == "載入趨勢資料中…"


def test_default_scope_and_valid_default_district_are_established_without_hover():
    meta = CLIENT.get("/api/meta").json()["default_filters"]
    assert meta["county"] == "臺中市" and meta["year"] == 2025
    assert meta["months"] == list(range(1, 13))
    assert meta["crime_types"] == list(CRIME_TYPE_ORDER)
    result = trend_state_scenario()["defaultDistrict"]
    assert result["row"]["district"] == "北屯區"
    assert result["hovered"] == {"county": "臺中市", "district": "北屯區"}


def test_ready_state_atomically_replaces_loading_with_chart_data():
    ready = trend_state_scenario()["ready"]
    assert ready["trendState"] == "ready"
    assert ready["status"]["hidden"] is True
    assert "crime-trend-card" in ready["html"]
    assert "trend-value-label" in ready["html"]


def test_empty_and_error_states_are_visible_and_never_leave_partial_blank_dom():
    result = trend_state_scenario()
    assert result["empty"]["trendState"] == "empty"
    assert result["empty"]["status"]["hidden"] is False
    assert result["empty"]["status"]["textContent"] == "此行政區在目前條件下無可顯示的趨勢資料"
    assert result["empty"]["html"] == ""
    assert result["error"]["trendState"] == "error"
    assert result["error"]["status"]["textContent"] == "趨勢資料載入失敗，請重新整理或重新選擇條件"
    assert result["error"]["html"] == ""


def test_filter_refresh_preserves_previous_charts_with_loading_overlay():
    refresh = trend_state_scenario()["refresh"]
    assert refresh["trendState"] == "loading"
    assert refresh["status"]["hidden"] is False
    assert "overlay" in refresh["status"]["className"]
    assert "crime-trend-card" in refresh["html"]
    assert trend_state_scenario()["refreshPreserved"] is True


def test_initial_default_response_renders_aggregate_first_plus_eight_individuals():
    body = CLIENT.get(
        "/api/county/臺中市/district/北屯區/trends",
        params={"crime_types": ",".join(CRIME_TYPE_ORDER)},
    ).json()
    assert body["aggregate"]["title"] == "全部案類（8 類合計）"
    assert len(body["crime_types"]) == 8


def test_async_guards_remain_before_trend_application_and_errors():
    source = (STATIC / "app.js").read_text(encoding="utf-8")
    load_start = source.index("async function loadDistrictExtras")
    load_end = source.index("async function renderOfficial", load_start)
    block = source[load_start:load_end]
    assert "owner.requestId!==state.trendRequestId" in block
    assert "beginTrendRequest()" in block
    assert "validateTrendResponse(trends)" in block
    assert block.index("if(owner.requestId!==state.trendRequestId") < block.index("renderCrimeTypeTrends(trends)")


def test_trend_status_styles_cover_loading_empty_error_and_overlay_states():
    css = (STATIC / "styles.css").read_text(encoding="utf-8")
    assert ".trend-status{" in css
    assert ".trend-status.loading{" in css
    assert ".trend-status.empty{" in css
    assert ".trend-status.error{" in css
    assert ".trend-status.overlay{" in css
