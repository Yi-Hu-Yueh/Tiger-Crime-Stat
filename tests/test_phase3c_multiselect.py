from __future__ import annotations

import json
import subprocess
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app


CLIENT = TestClient(app)
ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "app" / "static"
GEOGRAPHY = ROOT / "data" / "processed" / "geography" / "taiwan_districts.geojson"
ALL_MONTHS = "1,2,3,4,5,6,7,8,9,10,11,12"


def scope_map(
    counties="臺中市",
    years="2025",
    months=ALL_MONTHS,
    crime="住宅竊盜",
    metric="rate",
):
    response = CLIENT.get(
        "/api/scope/map",
        params={
            "counties": counties,
            "years": years,
            "months": months,
            "crime_type": crime,
            "metric": metric,
        },
    )
    assert response.status_code == 200
    return response.json()


def county_map(county, year, months=ALL_MONTHS, crime="住宅竊盜", metric="rate"):
    return CLIENT.get(
        f"/api/county/{county}/map",
        params={"year": year, "months": months, "crime_type": crime, "metric": metric},
    ).json()


def row(body, county, district):
    return next(item for item in body["districts"] if item["county"] == county and item["district"] == district)


def test_single_county_and_year_scope_preserves_existing_values():
    scoped = scope_map()
    legacy = county_map("臺中市", 2025)
    assert scoped["district_count"] == legacy["district_count"] == 29
    for district in ("北屯區", "西屯區", "南屯區"):
        scoped_row = row(scoped, "臺中市", district)
        legacy_row = next(item for item in legacy["districts"] if item["district"] == district)
        assert scoped_row["incident_count"] == legacy_row["incident_count"]
        assert scoped_row["population"] == legacy_row["population"]
        assert scoped_row["rate"] == legacy_row["rate"]


def test_multi_county_and_all_county_geography_are_combined_without_identity_loss():
    combined = CLIENT.get("/api/scope/geography", params={"counties": "臺中市,彰化縣"}).json()
    all_counties = ",".join(item["county"] for item in CLIENT.get("/api/counties").json()["counties"])
    national = CLIENT.get("/api/scope/geography", params={"counties": all_counties}).json()
    assert len(combined["features"]) == 29 + 26
    assert {feature["properties"]["county"] for feature in combined["features"]} == {"臺中市", "彰化縣"}
    assert len(national["features"]) == 368
    assert len({(feature["properties"]["county"], feature["properties"]["district"]) for feature in national["features"]}) == 368


def test_multi_year_count_is_raw_sum_and_month_filter_applies_to_every_year():
    multi = scope_map(years="2024,2025", months="1,2,3", metric="count")
    expected = sum(
        next(item for item in county_map("臺中市", year, "1,2,3", metric="count")["districts"] if item["district"] == "北屯區")["incident_count"]
        for year in (2024, 2025)
    )
    assert row(multi, "臺中市", "北屯區")["incident_count"] == expected
    assert multi["months"] == [1, 2, 3]


def test_multi_year_rate_uses_summed_population_not_summed_yearly_rates():
    body = scope_map(years="2024,2025", metric="rate")
    target = row(body, "臺中市", "北屯區")
    annual = [
        next(item for item in county_map("臺中市", year)["districts"] if item["district"] == "北屯區")
        for year in (2024, 2025)
    ]
    expected_count = sum(item["incident_count"] for item in annual)
    expected_population = sum(item["population"] for item in annual)
    assert target["incident_count"] == expected_count
    assert target["population"] == expected_population
    assert abs(target["rate"] - expected_count / expected_population * 100_000) < 1e-12
    assert body["rate_label"] == "每十萬人口加權案件數"


def test_multi_county_ranking_and_table_scope_cover_every_district():
    body = scope_map(counties="臺中市,彰化縣", metric="rate")
    assert body["ranking_scope"] == "selected_counties"
    assert body["district_count"] == len(body["districts"]) == 55
    assert len({(item["county"], item["district"]) for item in body["districts"]}) == 55
    assert {item["rank_denominator"] for item in body["districts"]} == {55}
    source = (STATIC / "app.js").read_text(encoding="utf-8")
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    assert '<th>縣市</th><th>行政區</th>' in html
    assert "state.map.districts" in source and 'data-county="${escapeHtml(row.county)}"' in source
    assert "所選縣市" in source


def test_same_named_districts_remain_county_qualified_in_scope():
    body = scope_map(counties="臺北市,基隆市", metric="count")
    matching = [item for item in body["districts"] if item["district"] == "中正區"]
    assert {(item["county"], item["district"]) for item in matching} == {("臺北市", "中正區"), ("基隆市", "中正區")}


def test_aggregate_assignment_rate_uses_raw_totals_and_partial_scope_is_honest():
    body = scope_map(counties="臺中市,臺東縣", years="2021", crime="機車竊盜", metric="rate")
    parts = [county_map(county, 2021, crime="機車竊盜") for county in ("臺中市", "臺東縣")]
    assigned = sum(item["district_assigned_records"] for item in parts)
    total = sum(item["preliminary_county_source_total"] for item in parts)
    assert body["district_assignment_rate"] == assigned / total
    if body["source_coverage_status"] != "complete":
        assert body["district_data_quality"] == "partial_source"
        assert all(item["rate"] is None for item in body["districts"])


def test_multi_year_previous_year_comparison_is_explicitly_disabled():
    response = CLIENT.get(
        "/api/scope/district/臺中市/北屯區/summary",
        params={"counties": "臺中市,彰化縣", "years": "2024,2025", "months": ALL_MONTHS, "crime_type": "住宅竊盜"},
    )
    assert response.status_code == 200
    comparison = response.json()["previous_year_comparison"]
    assert comparison["comparable"] is False
    assert "目前選取多個年度" in comparison["display_message"]


def test_official_scope_sums_only_comparable_full_year_single_category_values():
    body = CLIENT.get(
        "/api/scope/official",
        params={"counties": "臺中市,彰化縣", "years": "2025", "months": ALL_MONTHS, "crime_type": "住宅竊盜"},
    ).json()
    parts = [
        CLIENT.get(f"/api/county/{county}/official", params={"year": 2025, "months": ALL_MONTHS, "crime_type": "住宅竊盜"}).json()
        for county in ("臺中市", "彰化縣")
    ]
    if all(part["comparison_status"] == "comparable" for part in parts):
        assert body["comparison_status"] == "comparable"
        assert body["official_annual_county_count"] == sum(part["official_annual_county_count"] for part in parts)
    all_mode = CLIENT.get(
        "/api/scope/official",
        params={"counties": "臺中市,彰化縣", "years": "2025", "months": ALL_MONTHS, "crime_type": "all"},
    ).json()
    assert all_mode["comparison_status"] == "all_categories_not_directly_comparable"
    assert all_mode["official_annual_county_count"] is None


def test_multiselect_controls_are_dynamic_nonempty_and_locking_is_absent():
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    source = (STATIC / "app.js").read_text(encoding="utf-8")
    assert all(value in html for value in ('id="countyChoices"', 'id="allCounties"', 'id="yearChoices"', 'id="allYears"'))
    assert "state.countiesMeta.counties.forEach" in source
    assert "[...state.meta.years].reverse().forEach" in source
    assert "preventEmpty" in source
    assert "lockedDistrict" not in source
    assert "lockBadge" not in html
    assert "clickedDistrict=!wasDragging" in source
    assert 'path.addEventListener("dblclick"' not in source


def test_projection_centers_small_normal_multi_and_national_geometries_without_clipping():
    script = r"""
const fs = require("fs");
const projection = require(process.argv[1]);
const geo = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));
const groups = {
  small: ["\u57fa\u9686\u5e02"],
  normal: ["\u81fa\u4e2d\u5e02"],
  multi: ["\u81fa\u4e2d\u5e02", "\u5f70\u5316\u7e23"],
  national: [...new Set(geo.features.map(f => f.properties.county))],
};
const result = {};
for (const [name, counties] of Object.entries(groups)) {
  const features = geo.features.filter(f => counties.includes(f.properties.county));
  const fit = projection.fit(features, 820, 560);
  const points = features.flatMap(f => projection.flatten(f.geometry.coordinates)).map(fit.project);
  const bounds = points.reduce((b, p) => ({minX: Math.min(b.minX,p[0]), maxX: Math.max(b.maxX,p[0]), minY: Math.min(b.minY,p[1]), maxY: Math.max(b.maxY,p[1])}), {minX:Infinity,maxX:-Infinity,minY:Infinity,maxY:-Infinity});
  result[name] = {centerX: fit.centerX, centerY: fit.centerY, ...bounds};
}
process.stdout.write(JSON.stringify(result));
"""
    completed = subprocess.run(
        ["node", "-e", script, str(STATIC / "map_projection.js"), str(GEOGRAPHY)],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    result = json.loads(completed.stdout)
    for fit in result.values():
        assert abs(fit["centerX"] - 410) < 1e-9
        assert abs(fit["centerY"] - 280) < 1e-9
        assert 0 < fit["minX"] < fit["maxX"] < 820
        assert 0 < fit["minY"] < fit["maxY"] < 560


def test_invalid_empty_duplicate_and_unknown_scope_values_are_rejected():
    base = {"years": "2025", "months": ALL_MONTHS, "crime_type": "住宅竊盜", "metric": "count"}
    assert CLIENT.get("/api/scope/map", params={**base, "counties": ""}).status_code == 404
    assert CLIENT.get("/api/scope/map", params={**base, "counties": "臺中市,臺中市"}).status_code == 404
    assert CLIENT.get("/api/scope/map", params={**base, "counties": "不存在"}).status_code == 404
    assert CLIENT.get("/api/scope/map", params={**base, "counties": "臺中市", "years": ""}).status_code == 404
