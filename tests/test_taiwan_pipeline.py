from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter
from pathlib import Path

import pytest

from scripts.build_taiwan_crime_stats import administrative_rejection_reason


ROOT = Path(__file__).resolve().parents[1]
TAIWAN = ROOT / "data" / "processed" / "taiwan"
GEOGRAPHY = ROOT / "data" / "processed" / "geography"
YEARS = set(range(2016, 2026))
CRIME_TYPES = {
    "毒品", "強盜", "搶奪", "住宅竊盜", "汽車竊盜", "機車竊盜", "強制性交", "組織犯罪防制條例",
}


def rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


@pytest.fixture(scope="module")
def national() -> dict[str, object]:
    admin = rows(GEOGRAPHY / "taiwan_administrative_units.csv")
    population = rows(TAIWAN / "taiwan_population_by_district_2016_2025.csv")
    incidents = rows(TAIWAN / "taiwan_crime_incidents_2016_2025.csv")
    rejected = rows(TAIWAN / "taiwan_crime_rejected_records.csv")
    coverage = rows(TAIWAN / "taiwan_district_assignment_coverage.csv")
    yearly = rows(TAIWAN / "taiwan_crime_yearly_by_district.csv")
    panel = rows(TAIWAN / "taiwan_crime_analysis_panel.csv")
    preliminary = rows(TAIWAN / "taiwan_preliminary_yearly_by_county.csv")
    official = rows(TAIWAN / "taiwan_official_annual_county_crime_2016_2025.csv")
    crosswalk = rows(TAIWAN / "taiwan_administrative_crosswalk.csv")
    return locals()


def test_nationwide_geography_is_unique_and_valid(national: dict[str, object]) -> None:
    admin = national["admin"]
    assert len(admin) == len({(row["county"], row["district"]) for row in admin})
    assert len(admin) == len({row["town_code"] for row in admin})
    county_codes: dict[str, set[str]] = {}
    for row in admin:
        assert row["county"] and row["district"] and row["county_code"] and row["town_code"]
        assert row["geometry_available"] == "true"
        county_codes.setdefault(row["county"], set()).add(row["county_code"])
    assert all(len(codes) == 1 for codes in county_codes.values())
    geojson = json.loads((GEOGRAPHY / "taiwan_districts.geojson").read_text(encoding="utf-8"))
    assert len(geojson["features"]) == len(admin)
    assert {(f["properties"]["county"], f["properties"]["district"]) for f in geojson["features"]} == {
        (row["county"], row["district"]) for row in admin
    }


def test_population_exactly_covers_geography_for_all_years(national: dict[str, object]) -> None:
    admin_keys = {(row["county"], row["district"]) for row in national["admin"]}
    population = national["population"]
    keys = {(int(row["year"]), row["county"], row["district"]) for row in population}
    assert {int(row["year"]) for row in population} == YEARS
    assert keys == {(year, county, district) for year in YEARS for county, district in admin_keys}
    assert len(keys) == len(population)
    assert all(int(row["population"]) > 0 for row in population)
    assert all(row["population_basis"] == "year_end_registered_population" for row in population)


def test_every_accepted_crime_key_matches_geography(national: dict[str, object]) -> None:
    admin_keys = {(row["county"], row["district"]) for row in national["admin"]}
    assert national["incidents"]
    assert all((row["county"], row["district"]) in admin_keys for row in national["incidents"])
    assert {row["crime_type"] for row in national["incidents"]} == CRIME_TYPES


def test_unknown_counties_and_blank_districts_are_rejected_not_matched(national: dict[str, object]) -> None:
    rejected = national["rejected"]
    reasons = Counter(row["rejection_reason"] for row in rejected)
    assert reasons["unknown_county"] == 76
    assert reasons["blank_county"] == 8
    assert reasons["blank_district"] == 33740
    assert not any(not row["district"].strip() for row in national["incidents"])
    assert sum(int(row["district_unassigned_records"]) for row in national["coverage"]) == reasons["blank_district"]


def test_unknown_districts_are_rejected_without_fuzzy_matching(national: dict[str, object]) -> None:
    admin_keys = {(row["county"], row["district"]) for row in national["admin"]}
    counties = {county for county, _ in admin_keys}
    district_counties: dict[str, set[str]] = {}
    for county, district in admin_keys:
        district_counties.setdefault(district, set()).add(county)
    assert administrative_rejection_reason("臺中市", "不存在區", admin_keys, counties, district_counties) == "unexpected_district"
    assert administrative_rejection_reason("臺中市", "板橋區", admin_keys, counties, district_counties) == "geography_mismatch"
    assert administrative_rejection_reason("臺中", "中區", admin_keys, counties, district_counties) == "unknown_county"


def test_analysis_panel_size_is_derived_from_geography(national: dict[str, object]) -> None:
    admin_count = len(national["admin"])
    panel = national["panel"]
    assert len(panel) == len(YEARS) * admin_count * len(CRIME_TYPES)
    keys = {(int(row["year"]), row["county"], row["district"], row["crime_type"]) for row in panel}
    assert len(keys) == len(panel)


def test_observation_semantics_are_explicit(national: dict[str, object]) -> None:
    panel = national["panel"]
    statuses = Counter(row["observation_status"] for row in panel)
    assert statuses == {
        "observed_positive": 13730,
        "observed_zero": 13870,
        "partial_coverage": 1104,
        "unavailable": 736,
    }
    for row in panel:
        status = row["observation_status"]
        if status == "observed_zero":
            assert row["incident_count"] == "0"
            assert row["incidents_per_100k_population"] == "0"
        elif status == "unavailable":
            assert row["incident_count"] == ""
            assert row["incidents_per_100k_population"] == ""
        elif status == "partial_coverage":
            assert row["incident_count"] != ""
            assert row["incidents_per_100k_population"] == ""


def test_organization_crime_uses_actual_quarter_coverage(national: dict[str, object]) -> None:
    statuses = {
        int(row["year"]): row["source_coverage_status"]
        for row in national["panel"]
        if row["county"] == "臺中市" and row["district"] == "中區" and row["crime_type"] == "組織犯罪防制條例"
    }
    assert statuses == {
        2016: "unavailable", 2017: "unavailable", 2018: "partial", 2019: "complete",
        2020: "complete", 2021: "partial", 2022: "partial", 2023: "complete",
        2024: "complete", 2025: "complete",
    }


def test_county_coverage_reconciles_with_incidents_and_rejections(national: dict[str, object]) -> None:
    assigned = Counter((int(row["year"]), row["county"], row["crime_type"]) for row in national["incidents"])
    unassigned = Counter()
    for row in national["rejected"]:
        if row["rejection_reason"] != "blank_district" or not row["roc_year"].isdigit():
            continue
        unassigned[(int(row["roc_year"]) + 1911, row["source_county_original"].replace("台", "臺"), row["crime_type"])] += 1
    for row in national["coverage"]:
        key = (int(row["year"]), row["county"], row["crime_type"])
        assert int(row["district_assigned_records"]) == assigned[key]
        assert int(row["district_unassigned_records"]) == unassigned[key]
        assert int(row["total_source_records"]) == assigned[key] + unassigned[key]


def test_yearly_counts_and_rates_reconcile(national: dict[str, object]) -> None:
    grouped = Counter((int(row["year"]), row["county"], row["district"], row["crime_type"]) for row in national["incidents"])
    yearly = {
        (int(row["year"]), row["county"], row["district"], row["crime_type"]): int(row["incident_count"])
        for row in national["yearly"]
    }
    assert yearly == grouped
    assert sum(yearly.values()) == len(national["incidents"])
    population = {
        (int(row["year"]), row["county"], row["district"]): int(row["population"])
        for row in national["population"]
    }
    for row in rows(TAIWAN / "taiwan_crime_yearly_rates_by_district.csv"):
        key = (int(row["year"]), row["county"], row["district"], row["crime_type"])
        expected = yearly[key] / population[key[:3]] * 100000
        assert float(row["incidents_per_100k_population"]) == pytest.approx(expected)


def test_crosswalk_is_exact_and_complete(national: dict[str, object]) -> None:
    crosswalk = national["crosswalk"]
    assert len(crosswalk) == len(national["admin"])
    assert all(row["population_match"] == "true" for row in crosswalk)
    assert all(row["crime_match"] == "true" for row in crosswalk)
    assert all(row["match_status"] == "matched" for row in crosswalk)


def test_official_values_are_separate_and_not_distributed(national: dict[str, object]) -> None:
    official = national["official"]
    assert len(official) == len(YEARS) * len({row["county"] for row in national["admin"]}) * 7
    assert all(row["statistics_status"] == "official_final" for row in official)
    assert all(row["statistics_layer"] == "official_annual_county" for row in official)
    assert all("official" not in key for key in national["panel"][0])
    assert all(row["statistics_layer"] == "preliminary_district" for row in national["panel"])
    old = rows(ROOT / "data" / "processed" / "taichung" / "taichung_official_annual_city_crime_2016_2025.csv")
    old_values = {(int(row["year"]), row["crime_type"]): int(row["official_annual_count"]) for row in old if row["statistics_status"] == "official_final"}
    new_values = {(int(row["year"]), row["crime_type"]): int(row["official_annual_count"]) for row in official if row["county"] == "臺中市"}
    assert new_values == old_values
    national_values = {
        (int(row["year"]), row["county"], row["crime_type"]): int(row["official_annual_count"])
        for row in official
    }
    # Direct transcription checks from the 2024 residential-burglary county table.
    assert national_values[(2024, "新北市", "住宅竊盜")] == 842
    assert national_values[(2024, "臺北市", "住宅竊盜")] == 191
    assert national_values[(2024, "臺中市", "住宅竊盜")] == 142


def test_taichung_slice_reproduces_validated_outputs(national: dict[str, object]) -> None:
    incidents = [row for row in national["incidents"] if row["county"] == "臺中市"]
    rejected = [
        row for row in national["rejected"]
        if row["source_county_original"].replace("台", "臺") == "臺中市" and row["rejection_reason"] == "blank_district"
    ]
    population = [row for row in national["population"] if row["county"] == "臺中市"]
    panel = [row for row in national["panel"] if row["county"] == "臺中市"]
    assert len(incidents) == 31307
    assert len(rejected) == 2913
    assert len({row["district"] for row in incidents}) == 29
    assert len(population) == 290
    assert len(panel) == 2320
    preliminary = {
        (int(row["year"]), row["crime_type"]): row
        for row in national["preliminary"] if row["county"] == "臺中市"
    }
    assert int(preliminary[(2023, "住宅竊盜")]["dataset14200_source_total"]) == 47
    assert int(preliminary[(2024, "住宅竊盜")]["dataset14200_source_total"]) == 129
    assert float(preliminary[(2024, "機車竊盜")]["district_assignment_rate"]) == pytest.approx(0.5)
    sex = [row for row in panel if int(row["year"]) == 2019 and row["crime_type"] == "強制性交"]
    assert len(sex) == 29
    assert all(row["observation_status"] == "observed_zero" and row["incident_count"] == "0" for row in sex)


def test_national_source_accounting_is_exhaustive(national: dict[str, object]) -> None:
    reasons = Counter(row["rejection_reason"] for row in national["rejected"])
    assert len(national["incidents"]) + sum(reasons.values()) == 369521
    assert reasons == {"blank_county": 8, "blank_district": 33740, "invalid_date": 47, "unknown_county": 76}


def test_nationwide_provenance_hashes_are_current() -> None:
    metadata = json.loads((ROOT / "metadata" / "data_sources.json").read_text(encoding="utf-8"))
    national = metadata["nationwide_processing"]
    assert national["crime_raw_files_are_national"] is True
    assert national["crime_raw_resource_count"] == 40
    assert national["official_county_totals_distributed_to_districts"] is False
    for item in metadata["resources"]:
        path = ROOT / "data" / "raw" / "taichung" / "npa_crime" / item["downloaded_filename"]
        assert sha256(path) == item["sha256"]
    for relative, details in national["outputs"].items():
        path = ROOT / relative
        assert path.is_file()
        assert path.stat().st_size == details["file_size"]
        assert sha256(path) == details["sha256"]
