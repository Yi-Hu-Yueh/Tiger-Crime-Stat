from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from app.services.data_service import CRIME_TYPE_ORDER


CLIENT = TestClient(app)
ROOT = Path(__file__).resolve().parents[1]
YEARS = list(range(2016, 2026))


def scope_trends(counties: str, crime_type: str = "住宅竊盜") -> dict:
    response = CLIENT.get(
        "/api/scope/trends",
        params={"counties": counties, "crime_type": crime_type},
    )
    assert response.status_code == 200
    return response.json()


def assert_complete_scope_shape(body: dict, expected_districts: int) -> None:
    assert body["years"] == YEARS
    assert body["full_year_only"] is True
    assert body["district_count"] == len(body["districts"]) == expected_districts
    assert len({(item["county"], item["district"]) for item in body["districts"]}) == expected_districts
    for item in body["districts"]:
        assert [row["year"] for row in item["series"]] == YEARS
        assert all("incident_count" in row for row in item["series"])


def test_selected_district_trend_has_an_explicit_count_for_every_year_slot():
    body = CLIENT.get(
        "/api/county/臺中市/district/北屯區/trend",
        params={"crime_type": "住宅竊盜"},
    ).json()
    assert [row["year"] for row in body["values"]] == YEARS
    assert all("incident_count" in row for row in body["values"])
    assert len(body["values"]) == 10


def test_bulk_trends_return_every_taichung_and_keelung_district():
    taichung = scope_trends("臺中市")
    keelung = scope_trends("基隆市")
    assert_complete_scope_shape(taichung, 29)
    assert_complete_scope_shape(keelung, 7)
    assert {item["county"] for item in taichung["districts"]} == {"臺中市"}
    assert {item["county"] for item in keelung["districts"]} == {"基隆市"}


def test_bulk_trends_support_multi_county_scope_without_name_collisions():
    body = scope_trends("臺中市,彰化縣")
    assert_complete_scope_shape(body, 55)
    assert set(body["counties"]) == {"臺中市", "彰化縣"}
    assert {item["county"] for item in body["districts"]} == {"臺中市", "彰化縣"}


def test_bulk_trends_preserve_unavailable_partial_and_zero_semantics():
    body = scope_trends("臺中市", "組織犯罪防制條例")
    district = next(item for item in body["districts"] if item["district"] == "中區")
    by_year = {row["year"]: row for row in district["series"]}
    assert by_year[2017]["district_data_quality"] == "unavailable"
    assert by_year[2017]["incident_count"] is None
    assert by_year[2018]["district_data_quality"] == "partial_source"
    assert by_year[2018]["rate"] is None
    for row in district["series"]:
        if row["district_data_quality"] in {"unavailable", "no_district_assignment"}:
            assert row["incident_count"] is None and row["rate"] is None


def test_selected_district_all_crime_trends_return_every_required_chart_series():
    response = CLIENT.get("/api/county/臺中市/district/北屯區/trends")
    assert response.status_code == 200
    body = response.json()
    assert body["county"] == "臺中市" and body["district"] == "北屯區"
    assert body["years"] == YEARS and body["full_year_only"] is True
    assert [item["crime_type"] for item in body["crime_types"]] == list(CRIME_TYPE_ORDER)
    assert all([row["year"] for row in item["values"]] == YEARS for item in body["crime_types"])
    assert all(len(item["values"]) == 10 for item in body["crime_types"])


def test_selected_all_crime_trends_keep_unavailable_and_partial_years_honest():
    body = CLIENT.get("/api/county/臺中市/district/中區/trends").json()
    organized = next(item for item in body["crime_types"] if item["crime_type"] == "組織犯罪防制條例")
    by_year = {row["year"]: row for row in organized["values"]}
    assert by_year[2017]["district_data_quality"] == "unavailable"
    assert by_year[2017]["incident_count"] is None and by_year[2017]["rate"] is None
    assert by_year[2018]["district_data_quality"] == "partial_source"
    assert by_year[2018]["rate"] is None


def test_district_trend_tab_and_main_all_crime_chart_container_are_present():
    html = CLIENT.get("/").text
    js = (ROOT / "app" / "static" / "app.js").read_text(encoding="utf-8")
    assert 'data-tab="district-trends"' in html
    assert "各行政區趨勢圖" in html
    assert 'id="districtTrendGrid"' in html
    assert 'id="crimeTrendScroll"' in html and 'id="crimeTrendCharts"' in html
    assert 'id="trendYearCounts"' not in html
    assert "renderTrendYearCounts" not in js
    assert "data.crime_types.filter" in js
    assert 'class="trend-value-label ${quality}"' in js
    assert 'count=row.incident_count===null?"—":fmt(row.incident_count)' in js
    assert 'state.metric==="count"?"incident_count":"rate"' in js


def test_all_district_charts_use_one_bulk_request_and_scope_cache():
    js = (ROOT / "app" / "static" / "app.js").read_text(encoding="utf-8")
    assert "const districtTrendCache=new Map()" in js
    assert "function districtTrendScopeKey()" in js
    assert "getJson(`/api/scope/trends?counties=" in js
    assert "renderDistrictTrends(token)" in js
    render_start = js.index("async function renderDistrictTrends")
    render_end = js.index("async function loadDistrictExtras", render_start)
    assert "/api/county/${encodeURIComponent" not in js[render_start:render_end]


def test_district_trend_cards_scroll_internally_without_page_overflow():
    css = (ROOT / "app" / "static" / "styles.css").read_text(encoding="utf-8")
    assert "html,body{margin:0;height:100%;overflow:hidden}" in css
    assert ".district-trends-pane.active{display:grid;grid-template-rows:42px minmax(0,1fr);overflow:hidden}" in css
    assert ".district-trend-scroll{min-height:0;overflow-y:auto;overscroll-behavior:contain" in css
    assert ".mini-year-counts{display:grid;grid-template-columns:repeat(5" in css


def test_main_all_crime_charts_scroll_internally_and_use_one_district_request():
    html = CLIENT.get("/").text
    js = (ROOT / "app" / "static" / "app.js").read_text(encoding="utf-8")
    css = (ROOT / "app" / "static" / "styles.css").read_text(encoding="utf-8")
    assert "圖中數字為各年度案件數" in html
    assert ".crime-trend-scroll{height:min(56vh,430px);min-height:280px;overflow-y:auto" in css
    assert ".crime-trend-chart svg{width:100%;height:100%;display:block;overflow:hidden}" in css
    assert "const districtCrimeTrendCache=new Map()" in js
    assert "/district/${encodeURIComponent(row.district)}/trends?crime_types=" in js
    assert "renderCrimeTypeTrends(trends)" in js


def test_scope_trends_rejects_invalid_scope_and_crime_type():
    assert CLIENT.get(
        "/api/scope/trends", params={"counties": "不存在", "crime_type": "住宅竊盜"}
    ).status_code == 404
    assert CLIENT.get(
        "/api/scope/trends", params={"counties": "臺中市", "crime_type": "不存在"}
    ).status_code == 404
