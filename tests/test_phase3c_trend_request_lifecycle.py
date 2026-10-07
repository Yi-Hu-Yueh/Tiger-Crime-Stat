from __future__ import annotations

import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "app" / "static"


def run_lifecycle_scenario(mode: str) -> dict:
    script = r"""
const fs=require("fs");
const vm=require("vm");
const mode=process.argv[1];
const realSetTimeout=setTimeout;
const urls=[];
const errors=[];
const types=["毒品","強盜","搶奪","住宅竊盜","汽車竊盜","機車竊盜","強制性交","組織犯罪防制條例"];
const values=(empty=false)=>Array.from({length:10},(_,index)=>({
  year:2016+index,incident_count:empty?null:index+1,population:100000,rate:empty?null:index+1,
  district_data_quality:empty?"unavailable":"complete",source_coverage_status:empty?"unavailable":"complete",
  district_assignment_rate:empty?null:1,observation_status:empty?"unavailable":"observed_positive",display_warning:""
}));
const trendData=(district="中區",empty=false)=>({
  county:"臺中市",district,years:Array.from({length:10},(_,index)=>2016+index),full_year_only:true,
  selected_crime_types:types,
  aggregate:{title:`${district}｜全部案類（8 類合計）`,crime_types:types,values:values(empty)},
  crime_types:types.map(crime_type=>({crime_type,values:values(empty)})),
});
const summary={previous_year_comparison:{previous_year:2024,previous_count:1,current_year:2025,current_count:2,percent_change:100,comparable:true,display_message:""}};
const mapData={all_months_selected:true,district_count:1,source_coverage_status:"complete",district_assignment_rate:1,preliminary_county_source_total:10,rate_label:"每十萬人口案件數",population_basis:"年底戶籍人口",districts:[{county:"臺中市",district:"中區",incident_count:2,rate:2,population:100000,value:2,district_data_quality:"complete",source_coverage_status:"complete",district_assignment_rate:1,count_rank_within_county:1,rate_rank_within_county:1,rank_denominator:1,display_warning:"",year_scope:"2025",month_scope:"全年",crime_type:"all"}]};
const response=(data,ok=true,status=200)=>({ok,status,json:async()=>data});
const abortError=()=>{const error=new Error("aborted");error.name="AbortError";return error};
const delayed=(data,delay,signal)=>new Promise((resolve,reject)=>{const timer=realSetTimeout(()=>resolve(response(data)),delay);if(signal)signal.addEventListener("abort",()=>{clearTimeout(timer);reject(abortError())},{once:true})});
async function fetchMock(url,options={}){
  urls.push(url);
  const decoded=decodeURIComponent(url);
  if(url.includes("/api/scope/map"))return response(mapData);
  if(url.includes("/summary?")){
    if(mode==="timeout")return new Promise((_,reject)=>options.signal.addEventListener("abort",()=>reject(abortError()),{once:true}));
    if(mode==="stale"&&decoded.includes("甲區"))return delayed(summary,40,options.signal);
    if(mode==="pointerleave")return delayed(summary,20,options.signal);
    return response(summary);
  }
  if(url.includes("/trends?")){
    if(mode==="network-error")return response({detail:"boom"},false,500);
    if(mode==="malformed")return response({aggregate:null,bad:true});
    if(mode==="empty")return response(trendData("中區",true));
    if(mode==="timeout")return new Promise((_,reject)=>options.signal.addEventListener("abort",()=>reject(abortError()),{once:true}));
    if(mode==="stale"&&decoded.includes("甲區"))return delayed(trendData("甲區"),40,options.signal);
    if(mode==="stale"&&decoded.includes("乙區"))return response(trendData("乙區"));
    if(mode==="pointerleave")return delayed(trendData("中區"),20,options.signal);
    return response(trendData("中區"));
  }
  throw new Error(`unexpected URL ${url}`);
}
const charts={innerHTML:""};
const status={hidden:false,textContent:"載入趨勢資料中…",className:"trend-status loading"};
const nodes=new Proxy({}, {get:(target,key)=>target[key]||(target[key]={innerHTML:"",textContent:"",hidden:false,className:"",style:{},classList:{toggle:()=>{},add:()=>{},remove:()=>{}},setAttribute:()=>{},querySelectorAll:()=>[],querySelector:()=>null})});
nodes.crimeTrendCharts=charts;nodes.trendStatus=status;
const context={
  CrimeSelectionState:require(process.argv[2]),DistrictSelectionState:require(process.argv[3]),
  DashboardLayoutState:{create:()=>({verticalRatio:.54,horizontalRatio:.62,verticalMode:null,horizontalMode:null})},
  MapNavigation:{},MapProjection:{},Intl,URLSearchParams,AbortController,fetch:fetchMock,
  setTimeout:mode==="timeout"?((callback,ms)=>ms===12000?realSetTimeout(callback,0):realSetTimeout(callback,ms)):setTimeout,
  clearTimeout,innerWidth:1400,innerHeight:900,
  console:{log:()=>{},warn:()=>{},error:(...args)=>errors.push(args.map(String).join(" "))},
  document:{getElementById:id=>nodes[id],addEventListener:()=>{},querySelectorAll:()=>[],querySelector:()=>null,elementFromPoint:()=>null},
};
context.globalThis=context;
vm.createContext(context);
vm.runInContext(fs.readFileSync(process.argv[4],"utf8"),context);
vm.runInContext(`
  updateCrimeTiles=()=>{};updatePickerSummaries=()=>{};updatePinIndicator=()=>{};
  renderMap=()=>{};renderDetail=()=>{};renderTable=()=>{};hideError=()=>{};showError=()=>{};
  renderOfficial=async()=>{};renderDistrictTrends=async()=>{};
  state.meta={years:[2016,2017,2018,2019,2020,2021,2022,2023,2024,2025],crime_types:${JSON.stringify(types)}};
  state.countiesMeta={county_count:22};state.counties=["臺中市"];state.years=[2025];state.months=[1,2,3,4,5,6,7,8,9,10,11,12];state.crimeTypes=${JSON.stringify(types)};state.metric="rate";
`,context);
if(mode==="render-error")vm.runInContext('crimeTrendSvg=()=>{throw new Error("render boom")}',context);

(async()=>{
  if(mode==="stale"){
    const first={county:"臺中市",district:"甲區"},second={county:"臺中市",district:"乙區"};
    const oldRequest=vm.runInContext('loadDistrictExtras(globalThis.first)',Object.assign(context,{first}));
    await new Promise(resolve=>realSetTimeout(resolve,1));
    const currentRequest=vm.runInContext('loadDistrictExtras(globalThis.second)',Object.assign(context,{second}));
    await Promise.all([oldRequest,currentRequest]);
  }else if(mode==="pointerleave"){
    context.pointerRow={county:"臺中市",district:"中區"};
    vm.runInContext('state.map={districts:[globalThis.pointerRow]};state.hoveredDistrict=identity("臺中市","中區")',context);
    const request=vm.runInContext('loadDistrictExtras(globalThis.pointerRow)',context);
    vm.runInContext('handleMapPointerLeave()',context);
    await request;
  }else{
    await vm.runInContext('refreshData()',context);
  }
  const result=JSON.parse(vm.runInContext('JSON.stringify({trendState:state.trendState,trendRequestId:state.trendRequestId,controllerActive:Boolean(state.trendController),district:state.hoveredDistrict})',context));
  result.status={hidden:status.hidden,textContent:status.textContent,className:status.className};
  result.html=charts.innerHTML;
  result.chartCount=(charts.innerHTML.match(/class="crime-trend-card/g)||[]).length;
  result.urls=urls;
  result.errors=errors;
  process.stdout.write(JSON.stringify(result));
})().catch(error=>{process.stderr.write(error.stack);process.exit(1)});
"""
    completed = subprocess.run(
        [
            "node",
            "-e",
            script,
            mode,
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


def test_realistic_default_initialization_path_reaches_ready_with_nine_charts():
    result = run_lifecycle_scenario("success")
    assert result["trendState"] == "ready"
    assert result["status"]["hidden"] is True
    assert result["chartCount"] == 9
    assert result["district"] == {"county": "臺中市", "district": "中區"}
    assert any("/api/scope/map?" in url for url in result["urls"])
    assert any("/district/%E4%B8%AD%E5%8D%80/trends?crime_types=" in url for url in result["urls"])
    assert any("/scope/district/" in url and "/summary?" in url for url in result["urls"])


def test_aborted_stale_request_cannot_strand_or_overwrite_current_request():
    result = run_lifecycle_scenario("stale")
    assert result["trendState"] == "ready"
    assert result["status"]["hidden"] is True
    assert "乙區｜全部案類" in result["html"]
    assert "甲區｜全部案類" not in result["html"]
    assert result["controllerActive"] is False


def test_pointerleave_during_initial_request_no_longer_self_invalidates_loading():
    result = run_lifecycle_scenario("pointerleave")
    assert result["trendState"] == "ready"
    assert result["status"]["hidden"] is True
    assert result["chartCount"] == 9
    assert result["controllerActive"] is False


def test_network_error_terminates_loading_in_error_state():
    result = run_lifecycle_scenario("network-error")
    assert result["trendState"] == "error"
    assert result["status"]["hidden"] is False
    assert result["status"]["textContent"] == "趨勢資料載入失敗，請重新整理或重新選擇條件"
    assert result["errors"]


def test_structurally_valid_no_data_response_terminates_in_empty_state():
    result = run_lifecycle_scenario("empty")
    assert result["trendState"] == "empty"
    assert result["status"]["textContent"] == "此行政區在目前條件下無可顯示的趨勢資料"


def test_malformed_response_terminates_loading_in_error_state():
    result = run_lifecycle_scenario("malformed")
    assert result["trendState"] == "error"
    assert result["status"]["hidden"] is False


def test_render_exception_terminates_loading_in_error_state():
    result = run_lifecycle_scenario("render-error")
    assert result["trendState"] == "error"
    assert result["status"]["hidden"] is False
    assert result["errors"]


def test_timeout_aborts_authoritative_request_and_terminates_in_error_state():
    result = run_lifecycle_scenario("timeout")
    assert result["trendState"] == "error"
    assert result["status"]["hidden"] is False
    assert result["controllerActive"] is False
    assert result["errors"]


def test_lifecycle_uses_dedicated_generation_abort_timeout_and_validation():
    source = (STATIC / "app.js").read_text(encoding="utf-8")
    assert "trendRequestId:0,trendController:null" in source
    assert "const TREND_TIMEOUT_MS=12000" in source
    assert "owner.requestId!==state.trendRequestId" in source
    assert "owner.controller.abort()" in source
    assert "validateTrendResponse(trends)" in source
    assert 'setTrendState("error","趨勢資料載入失敗，請重新整理或重新選擇條件")' in source
