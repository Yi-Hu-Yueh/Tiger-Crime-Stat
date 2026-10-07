from __future__ import annotations

import re
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from app.services.data_service import CRIME_TYPE_ORDER


CLIENT = TestClient(app)
ROOT = Path(__file__).resolve().parents[1]
ALL_MONTHS = "1,2,3,4,5,6,7,8,9,10,11,12"


def all_map(county="臺中市", year=2025, months=ALL_MONTHS, metric="count"):
    response = CLIENT.get(
        f"/api/county/{county}/map",
        params={"year": year, "months": months, "crime_type": "all", "metric": metric},
    )
    assert response.status_code == 200
    return response.json()


def test_readable_typography_scale_and_fixed_layout_are_declared():
    css = (ROOT / "app" / "static" / "styles.css").read_text(encoding="utf-8")
    required = {
        ".app-header h1": "30px", ".app-header p": "18px", ".filter-bar>label": "16px",
        ".filter-bar select": "16px", ".month-menu label": "15px", ".crime-tile": "16px",
        ".detail-section .panel-title h2": "26px", ".stats strong": "30px",
        ".ranks strong": "19px", "table": "15px", "th": "16px", ".warning": "14px",
        ".tooltip": "15px", ".axis-text": "14px",
    }
    readable_block = css.split("Phase 3C readable type scale", 1)[1]
    for selector, size in required.items():
        assert re.search(re.escape(selector) + r"\{[^}]*font-size:" + re.escape(size), readable_block)
    assert "height:100vh" in css and "overflow-y:auto" in readable_block


def test_frontend_contains_obvious_all_categories_tile_and_methodology_note():
    js = (ROOT / "app" / "static" / "app.js").read_text(encoding="utf-8")
    html = CLIENT.get("/").text
    assert 'value:"all",label:"全部案類"' in js
    assert "資料集代碼：14200" in js
    assert "8 類案件加總" in html and "並非所有刑事案件種類" in html


def test_all_selection_identifies_exactly_eight_dataset_categories():
    body = all_map()
    assert body["crime_selection"] == "all" and body["crime_type"] == "all"
    assert body["included_crime_types"] == list(CRIME_TYPE_ORDER)
    assert len(body["included_crime_types"]) == 8


def test_all_count_is_sum_of_eight_raw_category_counts():
    aggregate = all_map()
    individual = {}
    for crime_type in CRIME_TYPE_ORDER:
        body = CLIENT.get("/api/county/臺中市/map", params={"year": 2025, "months": ALL_MONTHS, "crime_type": crime_type, "metric": "count"}).json()
        individual[crime_type] = {row["district"]: row["incident_count"] for row in body["districts"]}
    for row in aggregate["districts"]:
        assert row["incident_count"] == sum(individual[crime][row["district"]] for crime in CRIME_TYPE_ORDER)


def test_all_rate_is_recalculated_from_aggregate_count_and_population():
    body = all_map(metric="rate")
    for row in body["districts"]:
        assert abs(row["rate"] - row["incident_count"] / row["population"] * 100_000) < 1e-12


def test_all_mode_month_filter_uses_only_selected_months():
    annual = all_map()
    quarter = all_map(months="1,2,3")
    assert quarter["months"] == [1, 2, 3]
    assert quarter["preliminary_county_source_total"] < annual["preliminary_county_source_total"]
    assert sum(row["incident_count"] for row in quarter["districts"]) == quarter["district_assigned_records"]


def test_all_mode_supports_county_switching_and_every_district():
    taipei = all_map("臺北市")
    taichung = all_map("臺中市")
    assert taipei["district_count"] == len(taipei["districts"]) == 12
    assert taichung["district_count"] == len(taichung["districts"]) == 29


def test_all_mode_count_and_rate_rankings_use_aggregate_values():
    body = all_map(metric="rate")
    rows = body["districts"]
    counts = sorted((row["incident_count"] for row in rows), reverse=True)
    rates = sorted((row["rate"] for row in rows), reverse=True)
    for row in rows:
        assert row["count_rank_within_county"] == counts.index(row["incident_count"]) + 1
        assert row["rate_rank_within_county"] == rates.index(row["rate"]) + 1
        assert row["rank_denominator"] == 29


def test_incomplete_category_coverage_propagates_without_becoming_zero():
    body = all_map(year=2017, metric="rate")
    assert body["source_coverage_status"] == "partial"
    assert body["district_data_quality"] == "partial_source"
    assert sum(row["incident_count"] for row in body["districts"]) > 0
    assert all(row["rate"] is None and row["value"] is None for row in body["districts"])
    assert all(row["count_rank_within_county"] is None and row["rate_rank_within_county"] is None for row in body["districts"])


def test_aggregate_assignment_rate_is_weighted_by_records_not_mean_percentages():
    aggregate = CLIENT.get("/api/county/臺中市/coverage", params={"year": 2024, "months": ALL_MONTHS, "crime_type": "all"}).json()
    parts = [CLIENT.get("/api/county/臺中市/coverage", params={"year": 2024, "months": ALL_MONTHS, "crime_type": crime}).json() for crime in CRIME_TYPE_ORDER]
    assigned = sum(part["district_assigned_records"] for part in parts)
    total = sum(part["total_source_records"] for part in parts)
    assert aggregate["district_assigned_records"] == assigned
    assert aggregate["total_source_records"] == total
    assert aggregate["district_assignment_rate"] == assigned / total
    simple_mean = sum(part["district_assignment_rate"] or 0 for part in parts) / 8
    assert aggregate["district_assignment_rate"] != simple_mean


def test_all_mode_trend_has_aggregate_quality_for_every_year():
    trend = CLIENT.get("/api/county/臺中市/district/北屯區/trend", params={"crime_type": "all"}).json()
    assert trend["crime_selection"] == "all" and len(trend["values"]) == 10
    assert trend["values"][1]["district_data_quality"] == "partial_source"
    assert trend["values"][2]["district_data_quality"] == "partial_source"
    assert trend["values"][-1]["district_data_quality"] == "complete"


def test_all_mode_official_benchmark_is_never_falsely_comparable():
    body = CLIENT.get("/api/county/臺中市/official", params={"year": 2025, "months": ALL_MONTHS, "crime_type": "all"}).json()
    assert body["comparison_status"] == "all_categories_not_directly_comparable"
    assert body["official_annual_county_count"] is None
    assert body["absolute_difference"] is None and body["percent_difference_vs_official"] is None
    assert "無完整可比對" in body["display_message"]


def test_existing_single_type_and_assignment_semantics_are_unchanged():
    residential = CLIENT.get("/api/county/臺中市/map", params={"year": 2025, "months": ALL_MONTHS, "crime_type": "住宅竊盜", "metric": "count"}).json()
    motorcycle = CLIENT.get("/api/county/臺中市/map", params={"year": 2024, "months": ALL_MONTHS, "crime_type": "機車竊盜", "metric": "count"}).json()
    assert residential["crime_selection"] == "single" and residential["preliminary_county_source_total"] == 703
    assert motorcycle["district_assignment_rate"] == 0.5
    assert motorcycle["district_data_quality"] == "incomplete_assignment"


def test_hover_first_and_scope_guards_remain_present_for_all_mode():
    source = (ROOT / "app" / "static" / "app.js").read_text(encoding="utf-8")
    assert 'addEventListener("mouseenter"' in source
    assert "owner.requestId!==state.trendRequestId" in source
    assert "state.trendController.abort()" in source

