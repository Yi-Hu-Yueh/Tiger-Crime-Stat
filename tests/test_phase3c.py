from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app


CLIENT = TestClient(app)
ROOT = Path(__file__).resolve().parents[1]
ALL_MONTHS = "1,2,3,4,5,6,7,8,9,10,11,12"


def get_map(county="臺中市", year=2025, crime="住宅竊盜", metric="rate", months=ALL_MONTHS):
    response = CLIENT.get(
        f"/api/county/{county}/map",
        params={"year": year, "months": months, "crime_type": crime, "metric": metric},
    )
    assert response.status_code == 200
    return response.json()


def test_dynamic_county_domain_and_default_filters_are_nationwide():
    counties = CLIENT.get("/api/counties").json()
    meta = CLIENT.get("/api/meta").json()
    assert counties["county_count"] == len(counties["counties"]) == 22
    assert counties["district_count"] == 368
    assert counties["default_county"] == meta["default_filters"]["county"] == "臺中市"
    assert meta["default_filters"]["year"] == 2025
    assert meta["default_filters"]["months"] == list(range(1, 13))


def test_each_county_geography_and_map_have_all_official_units():
    for item in CLIENT.get("/api/counties").json()["counties"]:
        county, expected = item["county"], item["district_count"]
        geography = CLIENT.get(f"/api/county/{county}/geography").json()
        result = get_map(county=county)
        assert len(geography["features"]) == len(result["districts"]) == expected
        assert {f["properties"]["district"] for f in geography["features"]} == {r["district"] for r in result["districts"]}


def test_month_filtering_changes_counts_and_all_months_reproduce_panel():
    annual = get_map(metric="count")
    quarter = get_map(metric="count", months="1,2,3")
    assert annual["preliminary_county_source_total"] != quarter["preliminary_county_source_total"]
    assert sum(r["incident_count"] for r in annual["districts"]) == annual["district_assigned_records"]
    assert sum(r["incident_count"] for r in quarter["districts"]) == quarter["district_assigned_records"]
    assert annual["all_months_selected"] is True and quarter["all_months_selected"] is False


def test_partial_month_official_comparison_is_explicitly_blocked():
    body = CLIENT.get(
        "/api/county/臺中市/official",
        params={"year": 2025, "months": "1,2,3", "crime_type": "住宅竊盜"},
    ).json()
    assert body["comparison_status"] == "partial_months_not_comparable"
    assert body["absolute_difference"] is None
    assert body["percent_difference_vs_official"] is None
    assert "非完整年度" in body["display_message"]


def test_county_and_district_identity_prevents_name_collisions():
    taipei = CLIENT.get("/api/county/臺北市/district/中正區/trend", params={"crime_type": "毒品"}).json()
    keelung = CLIENT.get("/api/county/基隆市/district/中正區/trend", params={"crime_type": "毒品"}).json()
    assert taipei["county"] == "臺北市" and keelung["county"] == "基隆市"
    assert taipei["district"] == keelung["district"] == "中正區"
    assert CLIENT.get("/api/county/臺中市/district/中正區/trend", params={"crime_type": "毒品"}).status_code == 404


def test_competition_count_and_rate_rankings_are_correct_and_complete():
    body = get_map(metric="rate")
    rows = body["districts"]
    assert body["ranking_method"].startswith("competition ranking")
    assert {r["rank_denominator"] for r in rows} == {29}
    for key, rank_key in (("incident_count", "count_rank_within_county"), ("rate", "rate_rank_within_county")):
        values = sorted((r[key] for r in rows), reverse=True)
        for row in rows:
            assert row[rank_key] == values.index(row[key]) + 1


def test_no_assignment_is_null_and_unranked():
    body = get_map("澎湖縣", 2021, "機車竊盜", "count")
    assert body["district_assignment_rate"] == 0
    assert body["district_data_quality"] == "no_district_assignment"
    assert all(r["value"] is None and r["incident_count"] is None and r["count_rank_within_county"] is None and r["rank_denominator"] == 0 for r in body["districts"])
    assert "無法進行區級比較" in body["districts"][0]["display_warning"]


def test_incomplete_assignment_retains_values_ranks_and_warning():
    body = get_map("臺中市", 2024, "機車竊盜", "count")
    assert body["district_assignment_rate"] == 0.5
    assert body["district_data_quality"] == "incomplete_assignment"
    assert any(r["incident_count"] > 0 and r["count_rank_within_county"] is not None for r in body["districts"])
    assert all("僅代表已成功分配" in r["display_warning"] for r in body["districts"])


def test_taitung_assignment_rate_remains_exactly_source_driven():
    body = CLIENT.get("/api/county/臺東縣/coverage", params={"year": 2021, "months": ALL_MONTHS, "crime_type": "機車竊盜"}).json()
    assert body["total_source_records"] == 38 and body["district_assigned_records"] == 4
    assert abs(body["district_assignment_rate"] - 0.10526315789473684) < 1e-15
    assert body["district_data_quality"] == "incomplete_assignment"


def test_valid_complete_zero_stays_numeric_zero():
    body = get_map("臺中市", 2019, "強制性交", "rate")
    assert body["district_data_quality"] == "complete"
    assert all(r["incident_count"] == 0 and r["rate"] == 0 and r["value"] == 0 for r in body["districts"])
    assert all(r["observation_status"] == "observed_zero" for r in body["districts"])


def test_partial_source_preserves_counts_but_never_manufactures_rate_or_rank():
    count = get_map("臺中市", 2018, "組織犯罪防制條例", "count")
    rate = get_map("臺中市", 2018, "組織犯罪防制條例", "rate")
    assert count["district_data_quality"] == "partial_source"
    assert all(r["observation_status"] == "partial_coverage" for r in count["districts"])
    assert all(r["rate"] is None and r["rate_rank_within_county"] is None and r["count_rank_within_county"] is None for r in rate["districts"])
    assert all(r["value"] is None for r in rate["districts"])


def test_unavailable_is_never_converted_to_zero():
    body = get_map("臺中市", 2017, "組織犯罪防制條例", "count")
    assert body["district_data_quality"] == "unavailable"
    assert all(r["incident_count"] is None and r["rate"] is None and r["value"] is None for r in body["districts"])


def test_trend_has_ten_full_year_points_with_quality_semantics():
    body = CLIENT.get("/api/county/臺中市/district/中區/trend", params={"crime_type": "組織犯罪防制條例"}).json()
    assert body["full_year_only"] is True
    assert [r["year"] for r in body["values"]] == list(range(2016, 2026))
    assert body["values"][1]["district_data_quality"] == "unavailable"
    assert body["values"][2]["district_data_quality"] == "partial_source"


def test_official_county_layer_is_separate_and_not_distributed():
    official = CLIENT.get("/api/county/臺中市/official", params={"year": 2024, "months": ALL_MONTHS, "crime_type": "住宅竊盜"}).json()
    mapped = get_map("臺中市", 2024, "住宅竊盜", "count")
    assert official["statistics_layer"] == "official_annual_county"
    assert official["district_values_are_not_derived_from_official_totals"] is True
    assert mapped["district_values_are_not_derived_from_official_totals"] is True
    assert sum(r["incident_count"] for r in mapped["districts"]) == official["dataset14200_preliminary_count"] == 129
    assert official["official_annual_county_count"] == 142
    assert all("official_annual_county_count" not in r for r in mapped["districts"])


def test_frontend_uses_tiles_month_checkboxes_hover_and_internal_scroll():
    html = CLIENT.get("/").text
    js = (ROOT / "app" / "static" / "app.js").read_text(encoding="utf-8")
    css = (ROOT / "app" / "static" / "styles.css").read_text(encoding="utf-8")
    assert "臺灣犯罪統計" in html and "行政區資料為警政署季度初步案件資料" in html
    assert 'id="crimeTiles"' in html and 'id="crimeTypeSelect"' not in html
    assert 'class="month-check"' in js and 'addEventListener("mouseenter"' in js
    assert "height:100vh" in css and ".table-scroll{height:" in css and "overflow:auto" in css
    assert all(label in html for label in ("各行政區比較", "縣市年度正式統計", "資料品質說明", "資料來源與統計說明"))


def test_invalid_national_filters_and_months_are_rejected():
    assert CLIENT.get("/api/county/不存在/geography").status_code == 404
    assert CLIENT.get("/api/county/臺中市/map", params={"year": 2025, "months": "0,13", "crime_type": "毒品", "metric": "count"}).status_code == 404
    assert CLIENT.get("/api/county/臺中市/map", params={"year": 2025, "months": "1,1", "crime_type": "毒品", "metric": "count"}).status_code == 404

