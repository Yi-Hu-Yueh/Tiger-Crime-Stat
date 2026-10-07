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
ALL_MONTHS = "1,2,3,4,5,6,7,8,9,10,11,12"


def scope_map(crime_types: str, *, year: str = "2025", metric: str = "count") -> dict:
    response = CLIENT.get(
        "/api/scope/map",
        params={
            "counties": "臺中市",
            "years": year,
            "months": ALL_MONTHS,
            "crime_types": crime_types,
            "metric": metric,
        },
    )
    assert response.status_code == 200
    return response.json()


def test_default_crime_selection_contains_all_eight_types():
    meta = CLIENT.get("/api/meta").json()
    assert meta["default_filters"]["crime_types"] == list(CRIME_TYPE_ORDER)
    assert meta["default_filters"]["crime_type"] == "all"
    source = (STATIC / "app.js").read_text(encoding="utf-8")
    assert "crimeTypes:[...CRIME_TYPE_ORDER]" in source
    assert "state.crimeTypes=[...state.meta.default_filters.crime_types]" in source


def test_crime_selection_state_toggles_multiple_prevents_empty_and_restores_all():
    script = r"""
const selection = require(process.argv[1]);
const order = ["毒品","強盜","搶奪","住宅竊盜","汽車竊盜","機車竊盜","強制性交","組織犯罪防制條例"];
let selected = selection.selectAll(order);
const initial = {selected:[...selected], all:selection.isAll(selected,order), summary:selection.summary(selected,order)};
selected = selection.toggle(selected,"毒品",order);
selected = selection.toggle(selected,"強盜",order);
selected = selection.toggle(selected,"搶奪",order);
const remaining = {selected:[...selected], all:selection.isAll(selected,order), summary:selection.summary(selected,order)};
let one = ["住宅竊盜"];
one = selection.toggle(one,"住宅竊盜",order);
const preventedEmpty = [...one];
const restored = selection.selectAll(order);
process.stdout.write(JSON.stringify({initial,remaining,preventedEmpty,restored}));
"""
    completed = subprocess.run(
        ["node", "-e", script, str(STATIC / "crime_selection.js")],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    result = json.loads(completed.stdout)
    assert len(result["initial"]["selected"]) == 8 and result["initial"]["all"] is True
    assert result["initial"]["summary"] == "全部案類（8）"
    assert len(result["remaining"]["selected"]) == 5 and result["remaining"]["all"] is False
    assert result["preventedEmpty"] == ["住宅竊盜"]
    assert result["restored"] == list(CRIME_TYPE_ORDER)


def test_crime_tiles_are_checkbox_toggles_with_all_master_and_summary():
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    source = (STATIC / "app.js").read_text(encoding="utf-8")
    assert 'id="crimeSummary"' in html and "全部案類（8）" in html
    assert 'id="crimeTiles" class="crime-tiles" role="group"' in html
    assert 'button.setAttribute("role","checkbox")' in source
    assert 'item.value==="all"?CrimeSelectionState.selectAll' in source
    assert "CrimeSelectionState.toggle" in source
    assert 'master&&!allSelected?"mixed"' in source


def test_two_selected_types_aggregate_raw_counts_for_map_detail_and_table_rows():
    residential = scope_map("住宅竊盜")
    automobile = scope_map("汽車竊盜")
    combined = scope_map("住宅竊盜,汽車竊盜")
    assert combined["crime_selection"] == "multiple"
    assert combined["crime_types"] == ["住宅竊盜", "汽車竊盜"]
    expected = {
        row["district"]: row["incident_count"]
        + next(item["incident_count"] for item in automobile["districts"] if item["district"] == row["district"])
        for row in residential["districts"]
    }
    assert {row["district"]: row["incident_count"] for row in combined["districts"]} == expected
    assert combined["preliminary_county_source_total"] == residential["preliminary_county_source_total"] + automobile["preliminary_county_source_total"]


def test_multi_type_rate_is_aggregate_count_over_population_not_sum_of_rates():
    combined = scope_map("住宅竊盜,汽車竊盜", metric="rate")
    row = next(item for item in combined["districts"] if item["district"] == "北屯區")
    expected = row["incident_count"] / row["population"] * 100_000
    assert abs(row["rate"] - expected) < 1e-12
    assert row["rate"] == row["value"]
    service_source = (ROOT / "app" / "services" / "data_service.py").read_text(encoding="utf-8")
    assert "rate = None if count is None or scope_quality" in service_source
    assert "else count / population * 100_000" in service_source


def test_rankings_are_computed_from_multi_type_aggregate_values():
    body = scope_map("住宅竊盜,汽車竊盜", metric="rate")
    rows = body["districts"]
    for value_key, rank_key in (("incident_count", "count_rank_within_county"), ("rate", "rate_rank_within_county")):
        ordered = sorted((row[value_key] for row in rows), reverse=True)
        assert all(row[rank_key] == ordered.index(row[value_key]) + 1 for row in rows)
    assert {row["rank_denominator"] for row in rows} == {29}


def test_partial_or_unavailable_selected_type_propagates_without_zero_fabrication():
    body = scope_map("住宅竊盜,組織犯罪防制條例", year="2017", metric="rate")
    assert body["source_coverage_status"] == "partial"
    assert body["district_data_quality"] == "partial_source"
    assert all(row["rate"] is None and row["value"] is None for row in body["districts"])
    assert all(row["count_rank_within_county"] is None for row in body["districts"])
    assert any(row["incident_count"] and row["incident_count"] > 0 for row in body["districts"])


def test_assignment_rate_uses_summed_raw_assigned_and_attributable_records():
    residential = scope_map("住宅竊盜", year="2024")
    motorcycle = scope_map("機車竊盜", year="2024")
    combined = scope_map("住宅竊盜,機車竊盜", year="2024")
    assigned = residential["district_assigned_records"] + motorcycle["district_assigned_records"]
    total = residential["preliminary_county_source_total"] + motorcycle["preliminary_county_source_total"]
    assert combined["district_assigned_records"] == assigned
    assert combined["preliminary_county_source_total"] == total
    assert abs(combined["district_assignment_rate"] - assigned / total) < 1e-15
    assert combined["district_assignment_rate"] != (residential["district_assignment_rate"] + motorcycle["district_assignment_rate"]) / 2


def test_official_multi_type_sum_requires_all_selected_categories_to_be_comparable():
    params = {"counties": "臺中市", "years": "2025", "months": ALL_MONTHS}
    comparable = CLIENT.get(
        "/api/scope/official",
        params={**params, "crime_types": "住宅竊盜,汽車竊盜"},
    ).json()
    residential = CLIENT.get("/api/scope/official", params={**params, "crime_types": "住宅竊盜"}).json()
    automobile = CLIENT.get("/api/scope/official", params={**params, "crime_types": "汽車竊盜"}).json()
    assert comparable["comparison_status"] == "comparable"
    assert comparable["official_aggregate_label"] == "所選案類年度正式統計合計"
    assert comparable["official_annual_county_count"] == residential["official_annual_county_count"] + automobile["official_annual_county_count"]
    blocked = CLIENT.get(
        "/api/scope/official",
        params={**params, "crime_types": "住宅竊盜,組織犯罪防制條例"},
    ).json()
    assert blocked["comparison_status"] == "category_not_comparable"
    assert blocked["official_annual_county_count"] is None


def test_trend_endpoints_and_main_chart_renderer_follow_selected_types():
    body = CLIENT.get(
        "/api/scope/trends",
        params={"counties": "臺中市", "crime_types": "住宅竊盜,汽車竊盜"},
    ).json()
    assert body["crime_types"] == ["住宅竊盜", "汽車竊盜"]
    assert body["crime_selection"] == "multiple" and len(body["districts"]) == 29
    source = (STATIC / "app.js").read_text(encoding="utf-8")
    assert "data.crime_types.filter(item=>state.crimeTypes.includes(item.crime_type))" in source
    assert "crime_types:state.crimeTypes.join" in source
    assert "crime_types=${encodeURIComponent(state.crimeTypes.join" in source


def test_main_trend_renderer_outputs_nine_charts_for_all_and_one_for_single_selection():
    script = r"""
const fs = require("fs");
const vm = require("vm");
const target = {innerHTML:""};
const context = {
  CrimeSelectionState: require(process.argv[1]),
  DashboardLayoutState: {create:()=>({verticalRatio:.54,horizontalRatio:.62,verticalMode:null,horizontalMode:null})},
  DistrictSelectionState: {}, MapNavigation: {}, MapProjection: {}, Intl, URLSearchParams, console,
  innerWidth:1400, innerHeight:900,
  document:{getElementById:id=>id==="crimeTrendCharts"?target:{},addEventListener:()=>{},querySelectorAll:()=>[]},
};
context.globalThis=context;
vm.createContext(context);
vm.runInContext(fs.readFileSync(process.argv[2],"utf8"),context);
const types=["毒品","強盜","搶奪","住宅竊盜","汽車竊盜","機車竊盜","強制性交","組織犯罪防制條例"];
const values=Array.from({length:10},(_,index)=>({year:2016+index,incident_count:index,population:100000,rate:index,district_data_quality:"complete"}));
const data={aggregate:{title:"全部案類（8 類合計）",values},crime_types:types.map(crime_type=>({crime_type,values}))};
vm.runInContext(`state.crimeTypes=${JSON.stringify(types)}`,context);
context.data=data;
vm.runInContext("renderCrimeTypeTrends(data)",context);
const all=(target.innerHTML.match(/class="crime-trend-card/g)||[]).length;
vm.runInContext('state.crimeTypes=["住宅竊盜"]',context);
context.data={aggregate:null,crime_types:data.crime_types.filter(item=>item.crime_type==="住宅竊盜")};
vm.runInContext("renderCrimeTypeTrends(data)",context);
const one=(target.innerHTML.match(/class="crime-trend-card/g)||[]).length;
process.stdout.write(JSON.stringify({all,one,html:target.innerHTML}));
"""
    completed = subprocess.run(
        ["node", "-e", script, str(STATIC / "crime_selection.js"), str(STATIC / "app.js")],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    result = json.loads(completed.stdout)
    assert result["all"] == 9
    assert result["one"] == 1
    assert 'data-crime-type="住宅竊盜"' in result["html"]


def test_all_selected_current_district_trends_start_with_all_eight_aggregate():
    body = CLIENT.get(
        "/api/county/臺中市/district/北屯區/trends",
        params={"crime_types": ",".join(CRIME_TYPE_ORDER)},
    ).json()
    assert body["crime_selection"] == "all"
    assert body["aggregate"]["title"] == "全部案類（8 類合計）"
    assert body["aggregate"]["crime_types"] == list(CRIME_TYPE_ORDER)
    assert [item["crime_type"] for item in body["crime_types"]] == list(CRIME_TYPE_ORDER)
    assert len(body["crime_types"]) + 1 == 9


def test_aggregate_yearly_count_and_rate_use_raw_counts_and_year_population():
    body = CLIENT.get(
        "/api/county/臺中市/district/北屯區/trends",
        params={"crime_types": ",".join(CRIME_TYPE_ORDER)},
    ).json()
    aggregate_by_year = {row["year"]: row for row in body["aggregate"]["values"]}
    individuals = {
        item["crime_type"]: {row["year"]: row for row in item["values"]}
        for item in body["crime_types"]
    }
    for year, aggregate in aggregate_by_year.items():
        individual_rows = [individuals[crime_type][year] for crime_type in CRIME_TYPE_ORDER]
        if all(row["incident_count"] is not None for row in individual_rows):
            assert aggregate["incident_count"] == sum(row["incident_count"] for row in individual_rows)
        if aggregate["district_data_quality"] in {"complete", "incomplete_assignment"}:
            assert abs(aggregate["rate"] - aggregate["incident_count"] / aggregate["population"] * 100_000) < 1e-12


def test_three_selected_types_return_aggregate_first_then_canonical_individual_order():
    selected = ["住宅竊盜", "汽車竊盜", "機車竊盜"]
    body = CLIENT.get(
        "/api/county/臺中市/district/北屯區/trends",
        params={"crime_types": ",".join(reversed(selected))},
    ).json()
    assert body["aggregate"]["title"] == "所選案類合計（3 類）"
    assert body["aggregate"]["crime_types"] == selected
    assert [item["crime_type"] for item in body["crime_types"]] == selected
    assert len(body["crime_types"]) + 1 == 4
    for index, aggregate in enumerate(body["aggregate"]["values"]):
        visible = [item["values"][index]["incident_count"] for item in body["crime_types"]]
        if all(value is not None for value in visible):
            assert aggregate["incident_count"] == sum(visible)


def test_one_selected_type_avoids_duplicate_aggregate_chart():
    body = CLIENT.get(
        "/api/county/臺中市/district/北屯區/trends",
        params={"crime_types": "住宅竊盜"},
    ).json()
    assert body["aggregate"] is None
    assert [item["crime_type"] for item in body["crime_types"]] == ["住宅竊盜"]


def test_current_district_aggregate_propagates_partial_and_unavailable_quality():
    body = CLIENT.get(
        "/api/county/臺中市/district/中區/trends",
        params={"crime_types": "住宅竊盜,組織犯罪防制條例"},
    ).json()
    by_year = {row["year"]: row for row in body["aggregate"]["values"]}
    assert by_year[2017]["district_data_quality"] == "partial_source"
    assert by_year[2017]["rate"] is None
    assert by_year[2017]["incident_count"] is not None
    assert by_year[2018]["district_data_quality"] == "partial_source"
    assert by_year[2018]["rate"] is None


def test_aggregate_chart_is_prepended_and_keeps_in_chart_labels_without_count_boxes():
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    source = (STATIC / "app.js").read_text(encoding="utf-8")
    assert "items=data.aggregate?[{crime_type:data.aggregate.title" in source
    assert "...selected]:selected" in source
    assert 'class="trend-value-label ${quality}"' in source
    assert 'id="trendYearCounts"' not in html


def test_single_crime_new_query_is_backward_compatible_with_legacy_query():
    common = {"counties": "臺中市", "years": "2025", "months": ALL_MONTHS, "metric": "count"}
    legacy = CLIENT.get("/api/scope/map", params={**common, "crime_type": "住宅竊盜"}).json()
    current = CLIENT.get("/api/scope/map", params={**common, "crime_types": "住宅竊盜"}).json()
    assert current == legacy
    assert current["crime_selection"] == "single"


def test_empty_or_duplicate_crime_selection_is_rejected():
    common = {"counties": "臺中市", "years": "2025", "months": ALL_MONTHS, "metric": "count"}
    assert CLIENT.get("/api/scope/map", params={**common, "crime_types": ""}).status_code == 404
    assert CLIENT.get("/api/scope/map", params={**common, "crime_types": "住宅竊盜,住宅竊盜"}).status_code == 404
