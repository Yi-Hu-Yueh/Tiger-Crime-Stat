from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app


STATIC = Path(__file__).resolve().parents[1] / "app" / "static"


@pytest.fixture(scope="module")
def scenario():
    payload = TestClient(app).get("/api/county/臺中市/district/北屯區/trends?crime_types=all").json()
    script = r'''
const fs=require("fs"),vm=require("vm");
const nodes=new Proxy({}, {get:(target,key)=>target[key]||(target[key]={innerHTML:"",handlers:{},addEventListener(type,fn){this.handlers[type]=fn}})});
const pending=[],errors=[];
const summary={previous_year_comparison:{previous_year:2020,previous_count:10,current_year:2021,current_count:20,percent_change:100,comparable:true}};
const response=data=>({ok:true,json:async()=>data});
const context={
 CrimeSelectionState:require(process.argv[1]),DistrictSelectionState:require(process.argv[2]),
 DashboardLayoutState:{create:()=>({})},MapNavigation:{},MapProjection:{},Intl,URLSearchParams,AbortController,setTimeout,clearTimeout,
 console:{error:(...args)=>errors.push(args.map(String).join(" "))},
 document:{getElementById:id=>nodes[id],addEventListener:()=>{},querySelectorAll:()=>[]},
 fetch:url=>url.includes("/summary?")?Promise.resolve(response(summary)):new Promise(resolve=>pending.push(data=>resolve(response(data))))
};
context.globalThis=context;vm.createContext(context);
vm.runInContext(fs.readFileSync(process.argv[3],"utf8"),context);
context.payload=JSON.parse(fs.readFileSync(0,"utf8"));
// Force the original failure: a strong later individual anomaly outside the selected year.
context.payload.crime_types[0].anomalies.find(item=>item.year===2024).anomaly_level="high";
const run=code=>vm.runInContext(code,context);
const snapshot=()=>({html:nodes.anomalyExplanation.innerHTML,selection:JSON.parse(run('JSON.stringify(state.selectedAnnotation)'))});
const click=(crimeType,year)=>nodes.crimeTrendCharts.handlers.click({target:{closest:()=>({dataset:{crimeType,contextYear:String(year)}})}});
run('state.years=[2021];bindControls();renderCrimeTypeTrends(payload)');
const initial=snapshot();
click("毒品",2024);
const explicit=snapshot();
nodes.eventMarkersToggle.handlers.change({target:{checked:false}});
const toggled=snapshot();
// Start a real filter refresh: reset is synchronous even before a response arrives.
run('state.years=[2021];invalidateTrendRequest()');
const resetting=snapshot();
run('renderCrimeTypeTrends(payload)');
const reset=snapshot();
click("毒品",2024);
run('state.crimeTypes=["住宅竊盜"];invalidateTrendRequest();renderCrimeTypeTrends({...payload,aggregate:null,crime_types:payload.crime_types.filter(item=>item.crime_type==="住宅竊盜")})');
const crimeChanged=snapshot();
run('state.crimeTypes=[...CRIME_TYPE_ORDER];state.years=[2021,2022,2023];invalidateTrendRequest();renderCrimeTypeTrends(payload)');
const multi=snapshot();
click("毒品",2024);
run('renderCrimeTypeTrends({...payload,district:"西屯區"})');
const districtChanged=snapshot();
click("毒品",2024);
run('state.counties=["臺北市"];invalidateTrendRequest();renderCrimeTypeTrends({...payload,county:"臺北市",district:"中正區"})');
const countyChanged=snapshot();
run('state.counties=["臺中市"];state.years=[2021];invalidateTrendRequest();renderCrimeTypeTrends({...payload,aggregate:null})');
const noAggregate=snapshot();
run('renderCrimeTypeTrends({...payload,aggregate:{...payload.aggregate,values:payload.aggregate.values.map(row=>({...row,incident_count:null,rate:null}))},crime_types:payload.crime_types.map(item=>({...item,values:item.values.map(row=>({...row,incident_count:null,rate:null}))}))})');
const empty=snapshot();
(async()=>{
 run('districtCrimeTrendCache.clear();state.years=[2024];state.crimeTypes=["毒品"]');
 const old=run('loadDistrictExtras({county:"臺中市",district:"北屯區"})');
 run('state.years=[2021];state.crimeTypes=[...CRIME_TYPE_ORDER];invalidateTrendRequest()');
 const current=run('loadDistrictExtras({county:"臺中市",district:"北屯區"})');
 pending[1](context.payload);
 await current;
 const fresh=snapshot();
 // Ignore AbortController on purpose: a response already in flight can still arrive.
 pending[0]({...context.payload,aggregate:null,crime_types:[context.payload.crime_types[0]]});
 await old;
 const late=snapshot();
 process.stdout.write(JSON.stringify({initial,explicit,toggled,resetting,reset,crimeChanged,multi,districtChanged,countyChanged,noAggregate,empty,fresh,late,errors}));
})().catch(error=>{process.stderr.write(error.stack);process.exit(1)});
'''
    result = subprocess.run(
        ["node", "-e", script, str(STATIC / "crime_selection.js"), str(STATIC / "selection_state.js"), str(STATIC / "app.js")],
        input=json.dumps(payload, ensure_ascii=False), text=True, encoding="utf-8", capture_output=True, check=True,
    )
    return json.loads(result.stdout)


def test_2021_defaults_to_selected_year_and_all_crime_aggregate(scenario):
    html = scenario["initial"]["html"]
    assert "全部案類（8 類合計）｜2021" in html
    assert "毒品｜2024" not in html and "2024" not in html
    assert "目前篩選範圍" in html and scenario["initial"]["selection"] is None


def test_click_is_explicit_drill_down_and_marker_toggle_preserves_it(scenario):
    for key in ("explicit", "toggled"):
        assert "毒品｜2024" in scenario[key]["html"]
        assert "圖表註解（明確選取）" in scenario[key]["html"]
        assert scenario[key]["selection"]["year"] == 2024


def test_year_filter_resets_immediately_then_renders_2021_scope(scenario):
    assert scenario["resetting"]["selection"] is None
    assert "所選年度：2021" in scenario["resetting"]["html"]
    assert "2024" not in scenario["resetting"]["html"]
    assert "全部案類（8 類合計）｜2021" in scenario["reset"]["html"]


def test_crime_county_and_district_changes_clear_old_annotation(scenario):
    assert "住宅竊盜｜2021" in scenario["crimeChanged"]["html"]
    assert "西屯區" in scenario["districtChanged"]["html"]
    assert "臺北市 中正區" in scenario["countyChanged"]["html"]
    for key in ("crimeChanged", "districtChanged", "countyChanged"):
        assert scenario[key]["selection"] is None
        assert "毒品｜2024" not in scenario[key]["html"]


def test_multi_year_summary_uses_only_selected_years(scenario):
    html = scenario["multi"]["html"]
    assert "所選年度：2021、2022、2023" in html
    assert "全部案類（8）" in html
    for year in (2021, 2022, 2023):
        assert f"<b>{year}</b>" in html
    assert "2024" not in html and "2025" not in html
    assert scenario["multi"]["selection"] is None


def test_source_backed_2021_event_and_quality_precedence(scenario):
    for key in ("initial", "multi", "empty"):
        html = scenario[key]["html"]
        assert "COVID-19" in html and "cdc.gov.tw" in html
        assert "不代表該事件造成犯罪數據變化" in html
        assert html.index("資料品質優先") < html.index("觀測事實") < html.index("已記錄背景事件")


def test_missing_aggregate_is_neutral_instead_of_arbitrary_category(scenario):
    html = scenario["noAggregate"]["html"]
    assert "全部案類（8）｜所選年度：2021" in html
    assert "不指定個別案類代替" in html and "毒品｜" not in html


def test_late_response_cannot_replace_new_scope_even_when_abort_is_ignored(scenario):
    assert scenario["fresh"] == scenario["late"]
    assert "全部案類（8 類合計）｜2021" in scenario["late"]["html"]
    assert scenario["errors"] == []
