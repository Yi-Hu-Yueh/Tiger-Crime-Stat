from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
from collections import Counter
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_builder():
    path = ROOT / "scripts" / "build_taichung_crime_stats.py"
    spec = importlib.util.spec_from_file_location("build_taichung_crime_stats", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def read_csv(name: str):
    path = ROOT / "data" / "processed" / "taichung" / name
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def test_roc_and_mmdd_conversion():
    builder = load_builder()
    assert builder.parse_roc_date("105", "0101") == date(2016, 1, 1)
    assert builder.parse_roc_date("114", "1231") == date(2025, 12, 31)


def test_impossible_date_is_rejected():
    builder = load_builder()
    try:
        builder.parse_roc_date("114", "0230")
    except ValueError:
        pass
    else:
        raise AssertionError("impossible date was accepted")


def test_processed_years_counties_and_districts():
    builder = load_builder()
    rows = read_csv("taichung_crime_incidents_2016_2025.csv")
    assert {int(row["year"]) for row in rows} == set(range(2016, 2026))
    assert {row["source_county"] for row in rows} == {"臺中市"}
    assert {row["source_county_original"] for row in rows} <= builder.TAICHUNG_EXACT_ALIASES
    assert {row["district"] for row in rows} == builder.EXPECTED_DISTRICTS


def test_yearly_totals_reconcile():
    rows = read_csv("taichung_crime_incidents_2016_2025.csv")
    yearly = read_csv("taichung_crime_yearly_by_district.csv")
    raw_counts = Counter(int(row["year"]) for row in rows)
    grouped = Counter()
    for row in yearly:
        grouped[int(row["year"])] += int(row["incident_count"])
    assert grouped == raw_counts


def test_monthly_totals_reconcile():
    rows = read_csv("taichung_crime_incidents_2016_2025.csv")
    monthly = read_csv("taichung_crime_monthly_by_district.csv")
    raw_counts = Counter((int(row["year"]), int(row["month"])) for row in rows)
    grouped = Counter()
    for row in monthly:
        grouped[(int(row["year"]), int(row["month"]))] += int(row["incident_count"])
    assert grouped == raw_counts


def test_duplicate_looking_incidents_are_preserved():
    rows = read_csv("taichung_crime_incidents_2016_2025.csv")
    visible = Counter((r["date"], r["district"], r["crime_type"]) for r in rows)
    assert any(count > 1 for count in visible.values()), "fixture has no duplicate-looking official incidents"
    assert sum(visible.values()) == len(rows)


def test_all_40_raw_files_have_valid_provenance():
    metadata = json.loads((ROOT / "metadata" / "data_sources.json").read_text(encoding="utf-8"))
    resources = metadata["resources"]
    assert len(resources) == 40
    assert not metadata.get("missing_periods")
    periods = {resource["source_period"] for resource in resources}
    assert len(periods) == 40
    for resource in resources:
        assert resource["status"] != "failed"
        path = ROOT / "data" / "raw" / "taichung" / "npa_crime" / resource["downloaded_filename"]
        assert path.is_file()
        assert hashlib.sha256(path.read_bytes()).hexdigest() == resource["sha256"]
        assert resource["resource_url"].startswith("https://opdadm.moi.gov.tw/")


def test_all_expected_quarters_present():
    metadata = json.loads((ROOT / "metadata" / "data_sources.json").read_text(encoding="utf-8"))
    expected = {
        f"{year}{start}-{year}{end}"
        for year in range(105, 115)
        for start, end in (("01", "03"), ("04", "06"), ("07", "09"), ("10", "12"))
    }
    assert {item["source_period"] for item in metadata["resources"]} == expected


def raw_crime_rows():
    raw_dir = ROOT / "data" / "raw" / "taichung" / "npa_crime"
    for path in sorted(raw_dir.glob("npa_crime_*.csv")):
        parts = path.stem.split("_")
        period = f"{parts[2]}{parts[3]}-{parts[2]}{parts[4]}"
        with path.open(encoding="utf-8-sig", newline="") as handle:
            for line, row in enumerate(csv.DictReader(handle), start=2):
                row = {str(key).strip().lstrip("\ufeff"): str(value or "").strip() for key, value in row.items()}
                if row.get("type") == "案類":
                    continue
                row["source_period"] = period
                row["source_file"] = path.name
                row["source_line"] = str(line)
                yield row


def test_population_is_complete_unique_and_positive():
    builder = load_builder()
    rows = read_csv("taichung_population_by_district_2016_2025.csv")
    keys = {(int(row["year"]), row["district"]) for row in rows}
    assert len(rows) == len(keys) == 290
    assert {year for year, _ in keys} == set(range(2016, 2026))
    for year in range(2016, 2026):
        assert {district for row_year, district in keys if row_year == year} == builder.EXPECTED_DISTRICTS
    assert all(int(row["population"]) > 0 for row in rows)
    assert {row["population_basis"] for row in rows} == {"year_end_registered_population"}


def test_population_provenance_and_sha256_are_complete():
    metadata = json.loads((ROOT / "metadata" / "data_sources.json").read_text(encoding="utf-8"))
    population = metadata["population"]
    assert population["dataset_id"] == 8410
    assert population["missing_years"] == []
    assert {item["year"] for item in population["resources"]} == set(range(2016, 2026))
    assert len(population["resources"]) == 10
    for item in population["resources"]:
        assert item["status"] != "failed"
        path = ROOT / "data" / "raw" / "taichung" / "population" / item["downloaded_filename"]
        assert path.is_file()
        assert hashlib.sha256(path.read_bytes()).hexdigest() == item["sha256"]


def test_crime_population_join_and_rate_formula():
    populations = {
        (row["year"], row["district"]): int(row["population"])
        for row in read_csv("taichung_population_by_district_2016_2025.csv")
    }
    yearly = read_csv("taichung_crime_yearly_by_district.csv")
    rates = read_csv("taichung_crime_yearly_rates_by_district.csv")
    assert len(rates) == len(yearly) == 1273
    assert all((row["year"], row["district"]) in populations for row in rates)
    for row in rates:
        expected = int(row["incident_count"]) / int(row["population"]) * 100000
        assert abs(float(row["incidents_per_100k_population"]) - expected) < 1e-9


def test_phase1_count_is_unchanged():
    assert len(read_csv("taichung_crime_incidents_2016_2025.csv")) == 31307


def test_city_accounting_and_rejected_records_reconcile():
    city = read_csv("taichung_crime_yearly_city_coverage.csv")
    rejected = read_csv("taichung_crime_rejected_records.csv")
    assert sum(int(row["district_assigned_records"]) for row in city) == 31307
    assert sum(int(row["district_unassigned_records"]) for row in city) == 2913
    assert sum(int(row["invalid_date_records"]) for row in city) == 3
    assert sum(int(row["city_source_records"]) for row in city) == 34223
    reasons = Counter(row["rejection_reason"] for row in rejected)
    assert reasons == Counter({"blank_district": 2913, "invalid_date": 3})
    assert all(row["source_file"] and row["source_line"] for row in rejected)


def test_blank_regions_are_never_imputed():
    rejected = read_csv("taichung_crime_rejected_records.csv")
    blank = [row for row in rejected if row["rejection_reason"] == "blank_district"]
    assert len(blank) == 2913
    assert all(row["oc_region"] == "" for row in blank)
    incidents = read_csv("taichung_crime_incidents_2016_2025.csv")
    assert all(row["district"] for row in incidents)


def test_coverage_reconciles_with_independent_raw_reconstruction():
    builder = load_builder()
    reconstructed = Counter()
    for row in raw_crime_rows():
        if row.get("oc_county") not in builder.TAICHUNG_EXACT_ALIASES:
            continue
        year = int(row["oc_year"]) + 1911
        crime_type = row["type"]
        try:
            builder.parse_roc_date(row["oc_year"], row["oc_data"])
        except ValueError:
            status = "invalid"
        else:
            status = "assigned" if row["oc_region"] in builder.EXPECTED_DISTRICTS else "unassigned"
        reconstructed[(year, crime_type, status)] += 1
    city = read_csv("taichung_crime_yearly_city_coverage.csv")
    for row in city:
        key = (int(row["year"]), row["crime_type"])
        assert int(row["district_assigned_records"]) == reconstructed[(*key, "assigned")]
        assert int(row["district_unassigned_records"]) == reconstructed[(*key, "unassigned")]
        assert int(row["invalid_date_records"]) == reconstructed[(*key, "invalid")]


def test_residential_audit_matches_raw_by_year_and_quarter():
    builder = load_builder()
    by_year = Counter()
    by_period = Counter()
    for row in raw_crime_rows():
        if row["oc_county"] not in builder.TAICHUNG_EXACT_ALIASES or row["type"] != "住宅竊盜":
            continue
        builder.parse_roc_date(row["oc_year"], row["oc_data"])
        status = "assigned" if row["oc_region"] in builder.EXPECTED_DISTRICTS else "unassigned"
        by_year[(int(row["oc_year"]) + 1911, status)] += 1
        by_period[(row["source_period"], status)] += 1
    city = read_csv("taichung_crime_yearly_city_coverage.csv")
    residential = [row for row in city if row["crime_type"] == "住宅竊盜"]
    for row in residential:
        year = int(row["year"])
        assert int(row["district_assigned_records"]) == by_year[(year, "assigned")]
        assert int(row["district_unassigned_records"]) == by_year[(year, "unassigned")]
    expected_quarters = {
        "11201-11203": 12, "11204-11206": 9, "11207-11209": 11, "11210-11212": 15,
        "11301-11303": 9, "11304-11306": 5, "11307-11309": 51, "11310-11312": 64,
        "11401-11403": 182, "11404-11406": 125, "11407-11409": 193, "11410-11412": 203,
    }
    for period, expected in expected_quarters.items():
        assert by_period[(period, "assigned")] == expected
        assert by_period[(period, "unassigned")] == 0


def test_2019_forced_sexual_intercourse_is_explicitly_zero_for_taichung():
    builder = load_builder()
    national_periods = set()
    taichung = []
    for row in raw_crime_rows():
        if not row["source_period"].startswith("108") or row["type"] != "強制性交":
            continue
        national_periods.add(row["source_period"])
        if row["oc_county"] in builder.TAICHUNG_EXACT_ALIASES:
            taichung.append(row)
    assert national_periods == {"10801-10803", "10804-10806", "10807-10809", "10810-10812"}
    assert taichung == []
    city = read_csv("taichung_crime_yearly_city_coverage.csv")
    record = next(row for row in city if row["year"] == "2019" and row["crime_type"] == "強制性交")
    assert record["city_source_records"] == "0"
    assert record["district_assigned_records"] == "0"
    assert record["district_unassigned_records"] == "0"


def test_no_official_violent_crime_aggregate_exists():
    processed = ROOT / "data" / "processed" / "taichung"
    assert all("violent_crime" not in path.name and "暴力犯罪" not in path.name for path in processed.glob("*.csv"))
    for path in processed.glob("*.csv"):
        with path.open(encoding="utf-8-sig", newline="") as handle:
            header = next(csv.reader(handle))
        assert "violent_crime" not in header
        assert "暴力犯罪" not in header


def test_ten_year_summary_has_no_infinity():
    rows = read_csv("taichung_crime_10year_summary_by_district.csv")
    assert len(rows) == 29 * 8
    assert all("inf" not in str(value).lower() for row in rows for value in row.values())


def test_required_residential_preliminary_and_official_cross_checks():
    comparison = {
        (int(row["year"]), row["crime_type"]): row
        for row in read_csv("taichung_preliminary_vs_official_annual.csv")
    }
    expected = {
        (2023, "住宅竊盜"): (47, 91, -44),
        (2024, "住宅竊盜"): (129, 142, -13),
    }
    for key, values in expected.items():
        row = comparison[key]
        assert row["comparison_status"] == "comparable"
        assert (
            int(row["dataset14200_city_source_count"]),
            int(row["official_annual_count"]),
            int(row["absolute_difference"]),
        ) == values


def test_official_values_are_separate_and_never_scale_district_counts():
    panel = read_csv("taichung_crime_analysis_panel.csv")
    yearly = read_csv("taichung_crime_yearly_by_district.csv")
    expected = {
        (int(row["year"]), row["district"], row["crime_type"]): int(row["incident_count"])
        for row in yearly
    }
    assert all(row["statistics_layer"] == "preliminary_district" for row in panel)
    assert all("official" not in key.lower() and "scale" not in key.lower() for key in panel[0])
    for row in panel:
        key = (int(row["year"]), row["district"], row["crime_type"])
        if row["source_coverage_status"] in {"complete", "partial"}:
            assert int(row["incident_count"]) == expected.get(key, 0)
    official = read_csv("taichung_official_annual_city_crime_2016_2025.csv")
    assert all(row["statistics_layer"] == "official_annual_city" for row in official)
    assert len(official) == 10 * 8


def test_analysis_panel_complete_grid_and_unambiguous_observation_semantics():
    panel = read_csv("taichung_crime_analysis_panel.csv")
    assert len(panel) == 10 * 29 * 8
    assert len({(row["year"], row["district"], row["crime_type"]) for row in panel}) == len(panel)
    allowed = {"observed_positive", "observed_zero", "partial_coverage", "unavailable"}
    assert {row["observation_status"] for row in panel} <= allowed
    for row in panel:
        status = row["observation_status"]
        coverage = row["source_coverage_status"]
        if status == "observed_positive":
            assert coverage == "complete" and int(row["incident_count"]) > 0
            assert row["incidents_per_100k_population"] != ""
        elif status == "observed_zero":
            assert coverage == "complete" and row["incident_count"] == "0"
            assert float(row["incidents_per_100k_population"]) == 0
        elif status == "partial_coverage":
            assert coverage == "partial" and row["incident_count"] != ""
            assert row["incidents_per_100k_population"] == ""
        else:
            assert coverage == "unavailable"
            assert row["incident_count"] == ""
            assert row["incidents_per_100k_population"] == ""


def test_organization_crime_coverage_states_follow_actual_quarter_files():
    matrix = read_csv("taichung_crime_source_coverage_matrix.csv")
    organization = [row for row in matrix if row["crime_type"] == "組織犯罪防制條例"]
    by_year = {}
    for year in range(2016, 2026):
        states = [row["coverage_status"] for row in organization if int(row["year"]) == year]
        assert len(states) == 4
        by_year[year] = "complete" if states.count("complete") == 4 else (
            "unavailable" if states.count("complete") == 0 else "partial"
        )
    assert by_year[2016] == "unavailable"
    assert by_year[2017] == "unavailable"
    assert by_year[2018] == "partial"
    assert by_year[2019] == "complete"
    panel = read_csv("taichung_crime_analysis_panel.csv")
    for year, expected in ((2016, "unavailable"), (2017, "unavailable"), (2018, "partial_coverage")):
        rows = [row for row in panel if int(row["year"]) == year and row["crime_type"] == "組織犯罪防制條例"]
        assert len(rows) == 29
        assert {row["observation_status"] for row in rows} == {expected}


def test_2019_forced_sexual_intercourse_has_29_observed_zero_rows():
    rows = [
        row for row in read_csv("taichung_crime_analysis_panel.csv")
        if row["year"] == "2019" and row["crime_type"] == "強制性交"
    ]
    assert len(rows) == 29
    assert {row["source_coverage_status"] for row in rows} == {"complete"}
    assert {row["observation_status"] for row in rows} == {"observed_zero"}
    assert {row["incident_count"] for row in rows} == {"0"}
    official = next(
        row for row in read_csv("taichung_official_annual_city_crime_2016_2025.csv")
        if row["year"] == "2019" and row["crime_type"] == "強制性交"
    )
    assert official["statistics_status"] == "official_final"
    assert official["official_annual_count"] == "0"


def test_phase2b_population_join_and_rate_formula_are_complete():
    panel = read_csv("taichung_crime_analysis_panel.csv")
    populations = {
        (row["year"], row["district"]): int(row["population"])
        for row in read_csv("taichung_population_by_district_2016_2025.csv")
    }
    assert all((row["year"], row["district"]) in populations for row in panel)
    assert all(int(row["population"]) == populations[(row["year"], row["district"])] for row in panel)
    for row in panel:
        if row["source_coverage_status"] != "complete":
            continue
        expected = int(row["incident_count"]) / int(row["population"]) * 100000
        assert abs(float(row["incidents_per_100k_population"]) - expected) < 1e-9


def test_official_annual_provenance_files_and_hashes_are_valid():
    metadata = json.loads((ROOT / "metadata" / "data_sources.json").read_text(encoding="utf-8"))
    annual = metadata["official_annual_crime"]
    assert annual["final_annual_statistics"] is True
    assert annual["source_agency"] == "內政部警政署刑事警察局"
    assert {int(item["statistics_year"]) for item in annual["resources"]} == set(range(2016, 2026))
    assert len(annual["resources"]) == 11
    for item in annual["resources"]:
        assert item["status"] != "failed"
        assert item["source_page"].startswith("https://www.cib.npa.gov.tw/")
        assert item["resource_download_url"].startswith("https://www.cib.npa.gov.tw/")
        path = ROOT / "data" / "raw" / "taichung" / "official_annual_crime" / item["filename"]
        assert path.is_file()
        assert path.stat().st_size == int(item["file_size"])
        assert hashlib.sha256(path.read_bytes()).hexdigest() == item["sha256"]


def test_comparison_handles_official_zero_without_infinity():
    rows = read_csv("taichung_preliminary_vs_official_annual.csv")
    assert all("inf" not in str(value).lower() for row in rows for value in row.values())
    zeros = [row for row in rows if row["comparison_status"] == "comparable" and row["official_annual_count"] == "0"]
    assert zeros
    assert all(row["percent_difference_vs_official"] == "" for row in zeros)
    assert all(row["preliminary_to_official_ratio"] == "" for row in zeros)


def test_phase1_totals_and_city_coverage_remain_unchanged_after_phase2b():
    assert len(read_csv("taichung_crime_incidents_2016_2025.csv")) == 31307
    city = read_csv("taichung_crime_yearly_city_coverage.csv")
    assert sum(int(row["district_unassigned_records"]) for row in city) == 2913
    assert sum(int(row["district_assigned_records"]) for row in city) == 31307
