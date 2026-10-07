from __future__ import annotations

import copy
import json
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.data.major_events_2016_2025 import MAJOR_EVENTS_2016_2025
from app.services.context_service import ContextService, detect_anomalies
from app.services.data_service import CRIME_TYPE_ORDER, service


CLIENT = TestClient(app)
ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "app" / "static"


def test_anomaly_detection_is_metadata_only_and_does_not_modify_source_values():
    trend = service.county_trend("臺中市", "北屯區", "住宅竊盜")
    original = copy.deepcopy(trend["values"])
    anomalies = detect_anomalies(trend["values"], "臺中市", "北屯區", "住宅竊盜")
    assert trend["values"] == original
    assert len(anomalies) == len(original) == 10
    assert all(item["metadata_only"] is True for item in anomalies)
    response = CLIENT.get(
        "/api/county/臺中市/district/北屯區/trends",
        params={"crime_types": "住宅竊盜"},
    ).json()
    assert response["crime_types"][0]["values"] == original
    assert response["crime_types"][0]["anomalies"] != original
    assert response["interpretation_policy"]["raw_values_modified"] is False


def test_zero_baseline_is_safe_and_never_produces_infinite_percentage():
    values = [
        {
            "year": 2016 + index,
            "incident_count": count,
            "district_data_quality": "complete",
        }
        for index, count in enumerate([0, 0, 0, 5, 5, 5, 5, 5, 5, 5])
    ]
    results = detect_anomalies(values, "臺中市", "測試區", "毒品")
    assert results[3]["previous_year_count"] == 0
    assert results[3]["yoy_change_percent"] is None
    assert "前一年為零" in results[3]["anomaly_reason"]
    assert results[3]["anomaly_level"] == "insufficient_data"
    assert all(item["yoy_change_percent"] is None or abs(item["yoy_change_percent"]) < float("inf") for item in results)


@pytest.mark.parametrize("quality", ["partial_source", "unavailable", "incomplete_assignment", "no_district_assignment"])
def test_unreliable_years_are_not_presented_as_ordinary_anomalies(quality: str):
    values = [
        {"year": 2016 + index, "incident_count": 10, "district_data_quality": "complete"}
        for index in range(10)
    ]
    values[5] = {"year": 2021, "incident_count": 999, "district_data_quality": quality}
    result = detect_anomalies(values, "臺中市", "測試區", "毒品")[5]
    assert result["anomaly_level"] == "insufficient_data"
    assert result["data_quality_warning"]
    assert "資料品質" in result["data_quality_warning"] or "不進行" in result["data_quality_warning"]


def test_event_dataset_requires_complete_source_metadata(monkeypatch):
    with monkeypatch.context() as patch:
        patch.setitem(MAJOR_EVENTS_2016_2025[2016], "global", [{"id": "unsourced"}])
        with pytest.raises(ValueError, match="source metadata"):
            ContextService()
    events = CLIENT.get("/api/context/events", params={"county": "臺中市", "year": 2021}).json()["events"]
    assert events
    assert all(event["source_title"] and event["source_url"] and event["source_agency"] for event in events)


def test_2021_covid_context_is_official_source_backed_and_noncausal():
    body = CLIENT.get("/api/context/events", params={"county": "臺中市", "year": 2021}).json()
    event = next(item for item in body["events"] if item["id"] == "tw-covid-level-3-2021")
    assert event["start_date"] == "2021-05-19" and event["end_date"] == "2021-07-26"
    assert event["confidence"] == "official" and event["status"] == "public_health_measure"
    assert event["source_agency"].startswith("衛生福利部疾病管制署")
    assert event["causality_established"] is False
    assert "不代表" in event["context_disclaimer"]
    assert "造成犯罪" not in event["summary"] or "不能" in event["summary"]


def test_anomaly_endpoint_exposes_reasons_quality_and_unchanged_counts():
    body = CLIENT.get(
        "/api/county/臺中市/district/北屯區/anomalies",
        params={"crime_types": ",".join(CRIME_TYPE_ORDER)},
    ).json()
    assert body["raw_values_modified"] is False
    assert len(body["series"]) == 9
    assert all(len(series["anomalies"]) == 10 for series in body["series"])
    assert all(
        anomaly["anomaly_reason"] and anomaly["anomaly_level"] in {"normal", "notable", "high", "insufficient_data"}
        for series in body["series"]
        for anomaly in series["anomalies"]
    )


def test_chart_markers_toggles_and_explanation_panel_render_from_real_response():
    data = CLIENT.get(
        "/api/county/臺中市/district/北屯區/trends",
        params={"crime_types": ",".join(CRIME_TYPE_ORDER)},
    ).json()
    script = r"""
const fs=require("fs"),vm=require("vm");
const elements=new Proxy({}, {get:(target,key)=>target[key]||(target[key]={innerHTML:"",handlers:{},addEventListener(type,handler){this.handlers[type]=handler}})});
const context={
  CrimeSelectionState:require(process.argv[1]),DistrictSelectionState:require(process.argv[2]),
  DashboardLayoutState:{create:()=>({verticalRatio:.54,horizontalRatio:.62,verticalMode:null,horizontalMode:null})},
  MapNavigation:{},MapProjection:{},Intl,URLSearchParams,console,innerWidth:1400,innerHeight:900,
  document:{getElementById:id=>elements[id]||{},addEventListener:()=>{},querySelectorAll:()=>[]},
};
context.globalThis=context;vm.createContext(context);vm.runInContext(fs.readFileSync(process.argv[3],"utf8"),context);
context.payload=JSON.parse(fs.readFileSync(0,"utf8"));
vm.runInContext("renderCrimeTypeTrends(payload)",context);
const markerHtml=elements.crimeTrendCharts.innerHTML;
vm.runInContext('renderContextExplanation("組織犯罪防制條例",2018)',context);
const panel=elements.anomalyExplanation.innerHTML;
vm.runInContext('bindControls()',context);
const marker={dataset:{crimeType:"汽車竊盜",contextYear:"2021"}};
elements.crimeTrendCharts.handlers.click({target:{closest:()=>marker}});
const eventPanel=elements.anomalyExplanation.innerHTML;
elements.anomalyMarkersToggle.handlers.change({target:{checked:false}});
const anomaliesOff=elements.crimeTrendCharts.innerHTML;
elements.eventMarkersToggle.handlers.change({target:{checked:false}});
const allOff=elements.crimeTrendCharts.innerHTML;
vm.runInContext('setTrendState("loading","loading",{preserveCharts:true})',context);
const loading=elements.crimeTrendCharts.innerHTML;
elements.eventMarkersToggle.handlers.change({target:{checked:true}});
const stillLoading=vm.runInContext('state.trendState==="loading"&&state.currentTrendData===null',context)&&loading===elements.crimeTrendCharts.innerHTML;
vm.runInContext('renderCrimeTypeTrends(payload)',context);
let keyboardPrevented=false;
elements.crimeTrendCharts.handlers.keydown({key:"Enter",target:{closest:()=>marker},preventDefault:()=>keyboardPrevented=true});
const keyboardPanel=elements.anomalyExplanation.innerHTML;
const grouped=vm.runInContext('crimeTrendSvg("毒品",payload.crime_types[0].values,[],[...payload.events,...payload.events])',context);
process.stdout.write(JSON.stringify({markerHtml,panel,eventPanel,anomaliesOff,allOff,stillLoading,keyboardPrevented,keyboardPanel,grouped}));
"""
    completed = subprocess.run(
        ["node", "-e", script, str(STATIC / "crime_selection.js"), str(STATIC / "selection_state.js"), str(STATIC / "app.js")],
        input=json.dumps(data, ensure_ascii=False),
        capture_output=True,
        check=True,
        text=True,
        encoding="utf-8",
    )
    result = json.loads(completed.stdout)
    assert 'class="event-marker"' in result["markerHtml"]
    assert 'class="anomaly-marker ' in result["markerHtml"]
    assert "data-context-year=\"2021\"" in result["markerHtml"]
    assert "資料品質優先" in result["panel"]
    assert result["panel"].index("資料品質優先") < result["panel"].index("已記錄背景事件")
    assert "事件時間重疊僅供背景解讀，不代表該事件造成犯罪數據變化" in result["panel"]
    assert 'class="anomaly-marker ' not in result["anomaliesOff"]
    assert 'class="event-marker"' in result["anomaliesOff"]
    assert 'class="event-marker"' not in result["allOff"]
    assert result["stillLoading"] is True
    assert result["keyboardPrevented"] is True
    assert "2021" in result["keyboardPanel"] and "cdc.gov.tw" in result["keyboardPanel"]
    assert result["grouped"].count('class="event-marker"') == 10
    assert result["grouped"].count('text-anchor="middle">6</text>') == 10
    assert "臺中市 北屯區" in result["eventPanel"]
    assert "縣市初步／正式統計檢核" in result["eventPanel"]
    assert "aiGegg4ncYmMP9dTx4W_Zw" in result["eventPanel"]
    html = CLIENT.get("/").text
    assert 'id="eventMarkersToggle"' in html and "重大事件標記" in html
    assert 'id="anomalyMarkersToggle"' in html and "異常波動標記" in html


def test_interpretation_copy_never_claims_proven_causation():
    source = (STATIC / "app.js").read_text(encoding="utf-8")
    event_text = (ROOT / "app" / "data" / "major_events_2016_2025.py").read_text(encoding="utf-8")
    assert "不能推論其造成案件數變化" in source
    assert "不代表該事件造成犯罪數據變化" in source
    for prohibited in ("因此造成", "證明是", "犯罪危機"):
        assert prohibited not in source
        assert prohibited not in event_text


def test_detector_thresholds_mad_and_previous_quality_are_explainable():
    def series(counts):
        return [{"year": 2016 + i, "incident_count": count, "district_data_quality": "complete"} for i, count in enumerate(counts)]

    spike = detect_anomalies(series([100, 101, 99, 250]), "臺中市", "測試區", "毒品")[-1]
    assert spike["anomaly_level"] == "high"
    assert spike["recent_median"] == 100 and spike["median_absolute_deviation"] == 1
    assert spike["robust_score"] == pytest.approx(101.175)
    assert spike["baseline_years"] == [2016, 2017, 2018]
    assert "門檻" in spike["anomaly_reason"]
    fallback = detect_anomalies(series([10, 10, 10, 15]), "臺中市", "測試區", "毒品")[-1]
    assert fallback["anomaly_level"] == "notable" and fallback["robust_score"] is None
    assert fallback["median_change_percent"] == 50
    prior_bad = series([10, 10, 10, 500, 1000])
    prior_bad[-2]["district_data_quality"] = "partial_source"
    result = detect_anomalies(prior_bad, "臺中市", "測試區", "毒品")[-1]
    assert result["anomaly_level"] == "insufficient_data"
    assert result["yoy_change_percent"] is None and result["data_quality_warning"]


def test_official_comparison_is_checked_before_context_without_changing_observations():
    data = service.county_all_crime_trends("臺中市", "北屯區", "all")
    for category in data["crime_types"]:
        original = service.county_trend("臺中市", "北屯區", category["crime_type"])["values"]
        assert category["values"] == original
        for annotation, row in zip(category["anomalies"], original):
            assert annotation["incident_count"] == row["incident_count"]
            comparison = annotation["official_comparisons"][0]
            source = service.national_comparison.get((row["year"], "臺中市", category["crime_type"]), {})
            assert comparison["comparison_status"] == source.get("comparison_status", "category_not_comparable")
            if source.get("comparison_status") != "comparable" or comparison["absolute_difference"]:
                assert annotation["data_quality_warning"]
            assert annotation["district_assignment_rate"] == row["district_assignment_rate"]


def test_fixed_catalog_is_county_independent_copy_safe_and_rejects_bad_sources(monkeypatch):
    context = ContextService()
    assert len(context.events()) == 60
    assert context.events(county="臺北市") == context.events(county="臺中市")
    assert context.events(year=2015) == []
    returned = context.events(year=2021)
    covid = next(event for event in returned if event["id"] == "tw-covid-level-3-2021")
    covid["sources"][0]["url"] = "bad"
    assert next(event for event in context.events() if event["id"] == covid["id"])["sources"][0]["url"].startswith("https://")
    with monkeypatch.context() as patch:
        patch.setitem(MAJOR_EVENTS_2016_2025[2016]["global"][0], "source_url", "javascript:alert(1)")
        with pytest.raises(ValueError, match="HTTPS"):
            ContextService()
    with monkeypatch.context() as patch:
        patch.setitem(MAJOR_EVENTS_2016_2025[2016]["global"][0], "status", "draft")
        with pytest.raises(ValueError, match="status"):
            ContextService()
