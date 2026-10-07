from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app


ROOT = Path(__file__).resolve().parents[1]
CLIENT = TestClient(app)


def read_csv(name: str) -> list[dict[str, str]]:
    path = ROOT / "data" / "processed" / "taichung" / name
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def test_health_reports_application_and_data_readiness():
    response = CLIENT.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok" and body["ready"] is True
    assert body["data"] == {
        "years": 10,
        "districts": 29,
        "crime_types": 8,
        "panel_rows": 2320,
        "geography_features": 29,
    }


def test_meta_has_exact_year_district_and_crime_type_domains():
    body = CLIENT.get("/api/meta").json()
    assert body["years"] == list(range(2016, 2026))
    assert len(body["districts"]) == len(set(body["districts"])) == 29
    assert body["crime_types"] == ["毒品", "強盜", "搶奪", "住宅竊盜", "汽車竊盜", "機車竊盜", "強制性交", "組織犯罪防制條例"]
    assert {item["value"] for item in body["metric_options"]} == {"count", "rate"}


def test_map_returns_all_29_districts_with_required_fields():
    response = CLIENT.get("/api/map", params={"year": 2025, "crime_type": "住宅竊盜", "metric": "rate"})
    assert response.status_code == 200
    body = response.json()
    assert body["statistics_layer"] == "preliminary_district"
    assert len(body["districts"]) == 29
    required = {
        "district", "value", "incident_count", "population", "rate", "observation_status",
        "source_coverage_status", "district_assignment_rate", "display_warning",
    }
    assert all(required <= set(row) for row in body["districts"])


def test_unavailable_is_null_not_zero_and_partial_stays_partial():
    unavailable = CLIENT.get("/api/map", params={"year": 2017, "crime_type": "組織犯罪防制條例", "metric": "count"}).json()["districts"]
    assert len(unavailable) == 29
    assert {row["observation_status"] for row in unavailable} == {"unavailable"}
    assert all(row["incident_count"] is None and row["rate"] is None and row["value"] is None for row in unavailable)
    assert all("此年度此案類資料未提供" in row["display_warning"] for row in unavailable)

    partial = CLIENT.get("/api/map", params={"year": 2018, "crime_type": "組織犯罪防制條例", "metric": "rate"}).json()["districts"]
    assert {row["observation_status"] for row in partial} == {"partial_coverage"}
    assert {row["source_coverage_status"] for row in partial} == {"partial"}
    assert all(row["rate"] is None and row["value"] is None for row in partial)
    assert all("部分期間資料" in row["display_warning"] for row in partial)


def test_2019_forced_sexual_intercourse_is_29_numeric_observed_zeros():
    rows = CLIENT.get("/api/map", params={"year": 2019, "crime_type": "強制性交", "metric": "count"}).json()["districts"]
    assert len(rows) == 29
    assert {row["observation_status"] for row in rows} == {"observed_zero"}
    assert {row["source_coverage_status"] for row in rows} == {"complete"}
    assert all(row["incident_count"] == 0 and row["rate"] == 0 and row["value"] == 0 for row in rows)
    assert all("未提供" not in row["display_warning"] for row in rows)


def test_map_rate_values_match_validated_analysis_panel():
    panel = {
        (row["year"], row["district"], row["crime_type"]): row
        for row in read_csv("taichung_crime_analysis_panel.csv")
    }
    rows = CLIENT.get("/api/map", params={"year": 2025, "crime_type": "住宅竊盜", "metric": "rate"}).json()["districts"]
    for row in rows:
        source = panel[("2025", row["district"], "住宅竊盜")]
        assert row["incident_count"] == int(source["incident_count"])
        assert row["population"] == int(source["population"])
        assert abs(row["rate"] - float(source["incidents_per_100k_population"])) < 1e-12


def test_motorcycle_assignment_warning_is_driven_by_coverage_data():
    rows_2024 = CLIENT.get("/api/map", params={"year": 2024, "crime_type": "機車竊盜", "metric": "count"}).json()["districts"]
    assert {row["district_assignment_rate"] for row in rows_2024} == {0.5}
    assert all("行政區可分配率：50.0%" in row["display_warning"] for row in rows_2024)
    rows_2025 = CLIENT.get("/api/map", params={"year": 2025, "crime_type": "機車竊盜", "metric": "count"}).json()["districts"]
    assert {row["district_assignment_rate"] for row in rows_2025} == {1.0}
    assert all("行政區可分配率" not in row["display_warning"] for row in rows_2025)


def test_trend_has_ten_years_and_preserves_gaps():
    trend = CLIENT.get("/api/district/中區/trend", params={"crime_type": "組織犯罪防制條例"})
    assert trend.status_code == 200
    values = trend.json()["values"]
    assert [row["year"] for row in values] == list(range(2016, 2026))
    assert values[0]["incident_count"] is None and values[0]["observation_status"] == "unavailable"
    assert values[2]["observation_status"] == "partial_coverage" and values[2]["rate"] is None


def test_district_summary_is_descriptive_and_contains_no_composite():
    response = CLIENT.get("/api/district/中區/summary")
    assert response.status_code == 200
    body = response.json()
    assert body["statistics_layer"] == "preliminary_district"
    assert len(body["crime_types"]) == 8
    text = json.dumps(body, ensure_ascii=False).lower()
    assert all(term not in text for term in ("safety score", "danger score", "crime index", "最安全", "最危險"))


def test_official_city_endpoint_is_a_separate_unscaled_layer():
    official = CLIENT.get("/api/city/official", params={"year": 2024, "crime_type": "住宅竊盜"}).json()
    assert official["statistics_layer"] == "official_annual_city"
    assert official["district_values_are_not_derived_from_official_totals"] is True
    assert len(official["records"]) == 1
    record = official["records"][0]
    assert record["dataset14200_preliminary_city_source_count"] == 129
    assert record["official_annual_city_count"] == 142
    assert record["absolute_difference"] == -13

    district_map = CLIENT.get("/api/map", params={"year": 2024, "crime_type": "住宅竊盜", "metric": "count"}).json()
    assert district_map["statistics_layer"] == "preliminary_district"
    assert all("official_annual_city_count" not in row for row in district_map["districts"])
    panel_sum = sum(row["incident_count"] for row in district_map["districts"])
    assert panel_sum == 129 and panel_sum != record["official_annual_city_count"]


def test_noncomparable_official_value_is_not_rendered_as_zero():
    record = CLIENT.get("/api/city/official", params={"year": 2017, "crime_type": "組織犯罪防制條例"}).json()["records"][0]
    assert record["official_annual_city_count"] is None
    assert record["comparison_status"] == "category_not_comparable"
    assert record["display_message"] == "無可比對年度正式值"


def test_geography_has_29_exactly_matched_official_features():
    geography = CLIENT.get("/api/geography").json()
    meta = CLIENT.get("/api/meta").json()
    assert geography["type"] == "FeatureCollection"
    assert len(geography["features"]) == 29
    names = {feature["properties"]["district"] for feature in geography["features"]}
    assert names == set(meta["districts"])
    assert len({feature["properties"]["town_code"] for feature in geography["features"]}) == 29
    assert {feature["properties"]["county"] for feature in geography["features"]} == {"臺中市"}
    assert all(feature["geometry"]["type"] in {"Polygon", "MultiPolygon"} for feature in geography["features"])


def test_boundary_provenance_and_processed_hash_are_valid():
    metadata = json.loads((ROOT / "metadata" / "data_sources.json").read_text(encoding="utf-8"))
    geography = metadata["geography"]
    assert geography["dataset_id"] == 7441
    assert geography["provider"] == "內政部國土測繪中心"
    resource = geography["resources"][0]
    raw = ROOT / "data" / "raw" / "geography" / "town_boundaries" / resource["downloaded_filename"]
    assert raw.is_file() and hashlib.sha256(raw.read_bytes()).hexdigest() == resource["sha256"]
    processed = ROOT / geography["processed"]["filename"]
    assert processed.is_file() and hashlib.sha256(processed.read_bytes()).hexdigest() == geography["processed"]["sha256"]
    assert geography["processed"]["feature_count"] == 29
    assert geography["processed"]["district_match"] == "exact_1_to_1"


def test_frontend_root_and_assets_are_usable_without_a_build_step():
    response = CLIENT.get("/")
    assert response.status_code == 200
    assert "臺中市犯罪統計" in response.text
    assert '<div class="header-copy"><h1>臺灣犯罪統計</h1><div class="header-author-line">' in response.text
    assert "樂以虎" in response.text and "youtransgame@gmail.com" in response.text and "使用Codex" in response.text
    assert '<a href="mailto:youtransgame@gmail.com">youtransgame@gmail.com</a>' in response.text
    github_url = "https://github.com/Yi-Hu-Yueh/Tiger-Crime-Stat?tab=readme-ov-file"
    assert f'<a class="header-github" href="{github_url}" target="_blank" rel="noopener noreferrer">{github_url}</a>' in response.text
    assert '<div class="header-context"><p class="eyebrow">Tiger-Crime-Stat</p><p class="header-subtitle">2016–2025｜縣市與鄉鎮市區統計</p></div>' in response.text
    assert "行政區資料為警政署季度初步案件資料" in response.text
    assert "資料來源與統計說明" in response.text
    styles = CLIENT.get("/static/styles.css")
    assert styles.status_code == 200
    assert ".app-header{position:relative" in styles.text
    assert ".header-copy{position:absolute;left:50%" in styles.text and "transform:translateX(-50%)" in styles.text
    assert ".header-author-line{display:flex" in styles.text
    assert "justify-content:center" in styles.text and "flex-wrap:nowrap" in styles.text and "white-space:nowrap" in styles.text
    assert ".app-header h1{font-size:21px" in styles.text
    assert ".app-header .header-author{font-size:14px" in styles.text
    assert ".app-header .header-github{font-size:9px" in styles.text
    assert "overflow-x:auto" in styles.text and "html,body{height:auto;overflow:auto}" in styles.text
    assert CLIENT.get("/static/app.js").status_code == 200


def test_invalid_api_filters_are_rejected():
    assert CLIENT.get("/api/map", params={"year": 2015, "crime_type": "住宅竊盜", "metric": "count"}).status_code == 404
    assert CLIENT.get("/api/map", params={"year": 2025, "crime_type": "不存在", "metric": "count"}).status_code == 404
    assert CLIENT.get("/api/map", params={"year": 2025, "crime_type": "住宅竊盜", "metric": "score"}).status_code == 422
