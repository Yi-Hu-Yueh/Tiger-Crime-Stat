import json
import re
import subprocess
from pathlib import Path

from app.data.major_events_2016_2025 import MAJOR_EVENTS_2016_2025
from app.services.chat_router import THEFT_CRIME_TYPES
from app.services.dashboard_router import route_dashboard_message
from app.services.data_service import service


ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "app" / "static"
ALL_MONTHS = list(range(1, 13))


def node_chart_snapshot() -> dict:
    script = r'''
const fs=require("fs"),vm=require("vm");
const context={DashboardLayoutState:{create:()=>({})},DistrictSelectionState:{},MapNavigation:{},MapProjection:{},Intl,URLSearchParams,console,document:{addEventListener(){},getElementById(){return{}},querySelectorAll(){return[]}}};
context.globalThis=context;vm.createContext(context);vm.runInContext(fs.readFileSync(process.argv[1],"utf8"),context);
const values=Array.from({length:10},(_,index)=>({year:2016+index,incident_count:[2,4,6,8,10,12,14,16,13,83][index],population:300000+index,rate:[.67,1.33,2,2.67,3.33,4,4.67,5.33,4.18,26.17][index],district_data_quality:"complete"}));
const events=Array.from({length:6},(_,index)=>({id:"event-"+index,start_date:"2021-01-01",end_date:"2021-12-31",scope:index<3?"global":"taiwan",title:"事件 "+index}));
const anomalies=[{year:2025,anomaly_level:"high",anomaly_reason:"測試異常"}];
vm.runInContext('state.years=[2024,2025];state.metric="count"',context);context.values=values;context.events=events;context.anomalies=anomalies;
const count=vm.runInContext('crimeTrendSvg("住宅竊盜",values,anomalies,events)',context);
vm.runInContext('state.metric="rate"',context);
const rate=vm.runInContext('crimeTrendSvg("住宅竊盜",values,anomalies,events)',context);
process.stdout.write(JSON.stringify({count,rate}));
'''
    result = subprocess.run(["node", "-e", script, str(STATIC / "app.js")], check=True, capture_output=True, text=True, encoding="utf-8")
    return json.loads(result.stdout)


def test_chart_axes_use_integer_counts_decimal_rates_and_full_years():
    charts = node_chart_snapshot()
    count_ticks = re.findall(r'class="axis-text y-axis-label"[^>]*>([^<]+)', charts["count"])
    rate_ticks = re.findall(r'class="axis-text y-axis-label"[^>]*>([^<]+)', charts["rate"])
    assert count_ticks and all(re.fullmatch(r"\d+", tick.replace(",", "")) for tick in count_ticks)
    assert rate_ticks and any("." in tick for tick in rate_ticks)
    year_labels = re.findall(r'class="axis-text x-axis-label"[^>]*>([^<]+)', charts["count"])
    assert year_labels == [str(year) for year in range(2016, 2026)]
    assert charts["count"].count('class="trend-selected"') == 2
    assert ">13<title>2024 案件數：13" in charts["count"]
    assert ">83<title>2025 案件數：83" in charts["count"]


def test_event_lane_is_separate_explicit_and_anomalies_remain_point_bound():
    chart = node_chart_snapshot()["count"]
    assert 'class="event-lane"' in chart
    assert "重大事件帶（每年收錄件數）" in chart
    assert "6 件事件" in chart and "2021 年收錄 6 件重大事件" in chart
    assert '<circle class="anomaly-marker high"' in chart
    assert chart.index('class="event-lane"') < chart.index('class="trend-selected"')
    assert '<line x1=' not in chart[chart.index('class="event-marker"'):chart.index('class="event-marker"') + 500]


def test_event_catalog_audit_and_sources_remain_explicit():
    for year in range(2016, 2026):
        active = MAJOR_EVENTS_2016_2025[year]["global"] + MAJOR_EVENTS_2016_2025[year]["taiwan"]
        assert len(active) == 6
        assert all((event.get("sources") or [{"url": event["source_url"]}])[0]["url"].startswith("https://") for event in active)
    source = (STATIC / "app.js").read_text(encoding="utf-8")
    assert "適用範圍：" in source and "sourceLinks(event)" in source
    assert "時間重疊不代表因果關係" in source


def test_collapsed_crime_picker_reuses_selection_and_grouped_theft_still_routes():
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    js = (STATIC / "app.js").read_text(encoding="utf-8")
    assert 'id="crimeTiles"' in html and 'hidden' in html.split('id="crimeTiles"', 1)[1].split(">", 1)[0]
    assert 'id="crimePickerToggle"' in html and "aria-expanded=\"false\"" in html
    assert "tiles.hidden=!open" in js and "state.crimeTypes=state.crimeTypes.filter" in js
    scope = {"selected_counties": ["臺中市"], "selected_years": [2024, 2025], "selected_months": ALL_MONTHS,
             "selected_crime_types": ["機車竊盜"], "metric": "count", "current_district": {"county": "臺中市", "district": "北屯區"}}
    action = route_dashboard_message("改看竊盜", scope).dashboard_actions[0]
    assert action["crime_types"] == THEFT_CRIME_TYPES


def test_dataset_code_moved_to_source_description():
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    js = (STATIC / "app.js").read_text(encoding="utf-8")
    assert "資料集代碼：14200" in html and "資料集代碼：14200" in js
    assert 'note:"Dataset 14200"' not in js
    crime_section = html.split('<section class="crime-section">', 1)[1].split("</section>", 1)[0]
    assert "14200" not in crime_section


def test_primary_cards_summary_and_population_formula_use_runtime_values():
    scope = service.scope_map_data("臺中市", "2024,2025", ",".join(map(str, ALL_MONTHS)), "住宅竊盜", "count")
    row = next(item for item in scope["districts"] if item["district"] == "北屯區")
    trends = service.county_all_crime_trends("臺中市", "北屯區", "住宅竊盜")
    assert row["incident_count"] == 96 and row["population"] == 628147
    assert row["rate"] == row["incident_count"] / row["population"] * 100_000
    selected = [item for item in trends["crime_types"][0]["values"] if item["year"] in (2024, 2025)]
    assert [item["population"] for item in selected] == [310965, 317182]
    assert sum(item["population"] for item in selected) == row["population"]

    script = r'''
const fs=require("fs"),vm=require("vm"),selection=require(process.argv[1]);
const nodes=new Proxy({}, {get:(o,k)=>o[k]||(o[k]={textContent:"",innerHTML:"",className:""})});
const context={CrimeSelectionState:selection,DashboardLayoutState:{create:()=>({})},DistrictSelectionState:{},MapNavigation:{},MapProjection:{},Intl,URLSearchParams,console,document:{addEventListener(){},getElementById:id=>nodes[id],querySelectorAll(){return[]}}};
context.globalThis=context;vm.createContext(context);vm.runInContext(fs.readFileSync(process.argv[2],"utf8"),context);
context.row=JSON.parse(process.argv[3]);context.trends=JSON.parse(process.argv[4]);
vm.runInContext('state.countiesMeta={county_count:22};state.meta={years:[2016,2017,2018,2019,2020,2021,2022,2023,2024,2025]};state.counties=["臺中市"];state.years=[2024,2025];state.months=[1,2,3,4,5,6,7,8,9,10,11,12];state.crimeTypes=["住宅竊盜"];state.metric="count";state.map={rate_label:"每十萬人口加權案件數"};state.currentTrendData=trends;renderDetail(row)',context);
process.stdout.write(JSON.stringify({count:nodes.detailCount.textContent,rate:nodes.detailRate.textContent,countRank:nodes.countRank.textContent,rateRank:nodes.rateRank.textContent,summary:nodes.statisticalSummary.textContent,period:nodes.summaryPeriod.textContent,calculation:nodes.calculationBreakdown.innerHTML,quality:nodes.qualityStatus.innerHTML,warning:nodes.detailWarning.textContent}));
'''
    trend_payload = {"county": trends["county"], "district": trends["district"], "aggregate": None,
                     "crime_types": [{"crime_type": "住宅竊盜", "values": trends["crime_types"][0]["values"]}]}
    result = subprocess.run(["node", "-e", script, str(STATIC / "crime_selection.js"), str(STATIC / "app.js"), json.dumps(row, ensure_ascii=False), json.dumps(trend_payload, ensure_ascii=False)], check=True, capture_output=True, text=True, encoding="utf-8")
    rendered = json.loads(result.stdout)
    assert rendered["count"] == "96" and rendered["rate"] == "15.28"
    assert "案件數排名 1／29" in rendered["countRank"] and "同指標排名 13／29" in rendered["rateRank"]
    assert "選取期間住宅竊盜共 96 件" in rendered["summary"]
    assert all(term not in rendered["summary"] for term in ("最危險", "最安全", "治安最好", "治安最差"))
    assert rendered["period"] == "摘要統計：2024–2025（2 年）"
    assert "2024：310,965；2025：317,182" in rendered["calculation"]
    assert "96 件" in rendered["calculation"] and "628,147 人" in rendered["calculation"] and "100,000" in rendered["calculation"]
    assert "15.28" in rendered["calculation"]
    assert "行政區資料為警政署季度初步案件資料" in rendered["warning"]


def test_quality_period_chart_height_and_responsive_splitters_remain_visible():
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    css = (STATIC / "styles.css").read_text(encoding="utf-8")
    js = (STATIC / "app.js").read_text(encoding="utf-8")
    assert "資料品質：" in html and "可分配率：" in html and "來源涵蓋：" in html
    assert 'id="detailWarning" class="warning"' in html
    assert "摘要統計：" in html and "長期趨勢：2016–2025" in html
    assert ".crime-trend-chart{height:320px;min-height:280px}" in css
    assert ".crime-trend-chart svg{width:100%;height:100%" in css
    assert "scheduleMapRefit()" in js and 'window.addEventListener("resize"' in js
    assert "layout-vertical-left" in css and "layout-horizontal-down" in css
