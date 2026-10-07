#!/usr/bin/env python3
"""Build Phase 2B official-annual reconciliation and explicit coverage panel."""

from __future__ import annotations

import csv
import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

from pypdf import PdfReader


REPO_ROOT = Path(__file__).resolve().parents[1]
RAW_CRIME_DIR = REPO_ROOT / "data" / "raw" / "taichung" / "npa_crime"
RAW_OFFICIAL_DIR = REPO_ROOT / "data" / "raw" / "taichung" / "official_annual_crime"
PROCESSED_DIR = REPO_ROOT / "data" / "processed" / "taichung"
METADATA_PATH = REPO_ROOT / "metadata" / "data_sources.json"
REPORT_PATH = REPO_ROOT / "reports" / "taichung_data_coverage.md"
OFFICIAL_PATH = PROCESSED_DIR / "taichung_official_annual_city_crime_2016_2025.csv"
COMPARISON_PATH = PROCESSED_DIR / "taichung_preliminary_vs_official_annual.csv"
COVERAGE_MATRIX_PATH = PROCESSED_DIR / "taichung_crime_source_coverage_matrix.csv"
ANALYSIS_PANEL_PATH = PROCESSED_DIR / "taichung_crime_analysis_panel.csv"
RESIDENTIAL_RECONCILIATION_PATH = PROCESSED_DIR / "taichung_residential_burglary_reconciliation_2022_2025.csv"

TARGET_YEARS = tuple(range(2016, 2026))
TARGET_CRIME_TYPES = ("毒品", "強盜", "搶奪", "住宅竊盜", "汽車竊盜", "機車竊盜", "強制性交")
ORGANIZED_CRIME_TYPE = "組織犯罪防制條例"
ALL_CRIME_TYPES = TARGET_CRIME_TYPES + (ORGANIZED_CRIME_TYPE,)
EXPECTED_DISTRICTS = (
    "中區", "東區", "南區", "西區", "北區", "西屯區", "南屯區", "北屯區",
    "豐原區", "東勢區", "大甲區", "清水區", "沙鹿區", "梧棲區", "后里區",
    "神岡區", "潭子區", "大雅區", "新社區", "石岡區", "外埔區", "大安區",
    "烏日區", "大肚區", "龍井區", "霧峰區", "太平區", "大里區", "和平區",
)
DISTRICT_STATISTICS_LABEL = "警政署季度初步案件資料"
OFFICIAL_STATISTICS_LABEL = "警政署／刑事警察局年度正式統計"
POPULATION_RATE_LABEL = "每十萬年底戶籍人口案件數"
POPULATION_BASIS = "year_end_registered_population"
OFFICIAL_AGENCY = "內政部警政署刑事警察局"

# These English captions are present in the CIB annual publications even where
# legacy embedded Chinese fonts do not expose usable Unicode text.
CATEGORY_MARKERS = {
    "毒品": "Narcotics",
    "強盜": "Robbery",
    "搶奪": "Forceful Taking",
    "汽車竊盜": "Motor Vehicle Theft",
    "機車竊盜": "Motorcycle Theft",
    "強制性交": "Forcible Sexual Intercourse",
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, fieldnames: list[str], rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def format_decimal(value: float) -> str:
    return f"{value:.10f}".rstrip("0").rstrip(".")


def resource_for_year(metadata: dict[str, Any], year: int, purpose: str) -> dict[str, Any] | None:
    resources = metadata.get("official_annual_crime", {}).get("resources", [])
    candidates = [item for item in resources if int(item.get("statistics_year", 0)) == year and item.get("status") != "failed"]
    if purpose == "residential":
        preferred = [item for item in candidates if "analysis" in str(item.get("filename", ""))]
        if preferred:
            return preferred[0]
    preferred = [item for item in candidates if "general" in str(item.get("filename", ""))]
    if purpose == "general" and preferred:
        return preferred[0]
    full = [item for item in candidates if "full" in str(item.get("filename", ""))]
    return full[0] if full else (candidates[0] if candidates else None)


def page_matches_category(text: str, crime_type: str, year: int) -> bool:
    if "Taichung City" not in text:
        return False
    if crime_type == "住宅竊盜":
        return f"Geographic Distribution of Residential Burglary by Month, {year}" in text
    marker = CATEGORY_MARKERS[crime_type]
    lines = [line.strip() for line in text.splitlines()]
    matching = [line for line in lines if line.endswith(marker)]
    if crime_type == "汽車竊盜":
        matching = [line for line in matching if "Larceny and" not in line]
    if crime_type == "強制性交":
        matching = [line for line in matching if "Joint" not in line]
    return bool(matching)


def extract_taichung_current_year_count(text: str) -> int | None:
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if "Taichung City" not in line:
            continue
        remainder = line.split("Taichung City", 1)[1]
        if not remainder.strip() and index + 1 < len(lines):
            remainder = lines[index + 1]
        match = re.search(r"(?:^|\s)(-|\d[\d,]*)(?=\s|$)", remainder.strip())
        if match:
            token = match.group(1)
            return 0 if token == "-" else int(token.replace(",", ""))
    return None


def extract_official_values(metadata: dict[str, Any]) -> tuple[dict[tuple[int, str], int], dict[tuple[int, str], dict[str, Any]], list[str]]:
    values: dict[tuple[int, str], int] = {}
    evidence: dict[tuple[int, str], dict[str, Any]] = {}
    errors: list[str] = []
    for year in TARGET_YEARS:
        resources: dict[str, dict[str, Any] | None] = {
            "general": resource_for_year(metadata, year, "general"),
            "residential": resource_for_year(metadata, year, "residential"),
        }
        readers: dict[str, PdfReader] = {}
        for purpose, resource in resources.items():
            if resource is None:
                continue
            filename = str(resource.get("filename") or resource.get("downloaded_filename") or "")
            path = RAW_OFFICIAL_DIR / filename
            if not path.is_file():
                errors.append(f"official source missing: {filename}")
                continue
            if resource.get("sha256") and sha256_file(path) != resource["sha256"]:
                errors.append(f"official source SHA-256 mismatch: {filename}")
                continue
            readers[purpose] = PdfReader(path)

        wanted = set(TARGET_CRIME_TYPES)
        for purpose, reader in readers.items():
            scan_wanted = {"住宅竊盜"} if purpose == "residential" else wanted - {"住宅竊盜"}
            if resources["general"] == resources["residential"]:
                scan_wanted = wanted
            # Target tables occur in the analytical/statistical first portion of
            # each annual book. Split publications are shorter and are scanned fully.
            limit = min(len(reader.pages), 170)
            for page_index in range(limit):
                if not scan_wanted:
                    break
                text = reader.pages[page_index].extract_text() or ""
                for crime_type in tuple(scan_wanted):
                    if not page_matches_category(text, crime_type, year):
                        continue
                    count = extract_taichung_current_year_count(text)
                    if count is None:
                        continue
                    resource = resources[purpose]
                    assert resource is not None
                    key = (year, crime_type)
                    values[key] = count
                    evidence[key] = {
                        "source_document": resource.get("dataset_report_name", ""),
                        "source_url": resource.get("resource_download_url", ""),
                        "source_file": resource.get("filename", ""),
                        "source_note": f"當年發生件數 (current-year occurrences), PDF page {page_index + 1}; supplemental reports are not added.",
                    }
                    scan_wanted.remove(crime_type)
            if resources["general"] == resources["residential"]:
                break
    return values, evidence, errors


def build_coverage_matrix(metadata: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[tuple[int, str], str], list[str]]:
    rows: list[dict[str, Any]] = []
    errors: list[str] = []
    by_year_type: dict[tuple[int, str], list[bool]] = defaultdict(list)
    resources = sorted(metadata.get("resources", []), key=lambda item: str(item.get("source_period", "")))
    for resource in resources:
        period = str(resource.get("source_period", ""))
        match = re.fullmatch(r"(\d{3})(\d{2})-(\d{3})(\d{2})", period)
        if not match:
            errors.append(f"invalid source period in metadata: {period}")
            continue
        roc_year, start_month, _, _ = match.groups()
        year = int(roc_year) + 1911
        quarter = (int(start_month) - 1) // 3 + 1
        source_file = str(resource.get("downloaded_filename", ""))
        path = RAW_CRIME_DIR / source_file
        if not path.is_file():
            errors.append(f"coverage source missing: {source_file}")
            continue
        if resource.get("sha256") and sha256_file(path) != resource["sha256"]:
            errors.append(f"coverage source SHA-256 mismatch: {source_file}")
            continue
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            types = {
                str(raw.get("type", "")).strip()
                for raw in csv.DictReader(handle)
                if str(raw.get("type", "")).strip() not in {"", "案類"}
            }
        for crime_type in ALL_CRIME_TYPES:
            available = crime_type in types
            status = "complete" if available else "unavailable"
            rows.append({
                "year": year,
                "quarter": quarter,
                "crime_type": crime_type,
                "category_available": str(available).lower(),
                "coverage_status": status,
                "source_file": source_file,
                "notes": "Category is present in the actual national quarterly source file." if available else "Category is absent from the actual quarterly source file; absence is not interpreted as zero.",
            })
            by_year_type[(year, crime_type)].append(available)
    annual: dict[tuple[int, str], str] = {}
    for key, availability in by_year_type.items():
        present = sum(availability)
        annual[key] = "complete" if present == 4 else ("unavailable" if present == 0 else "partial")
    rows.sort(key=lambda row: (int(row["year"]), int(row["quarter"]), str(row["crime_type"])))
    return rows, annual, errors


def build_report_section(
    official_rows: list[dict[str, Any]],
    comparison_rows: list[dict[str, Any]],
    annual_coverage: dict[tuple[int, str], str],
    panel_rows: list[dict[str, Any]],
) -> str:
    verified = [row for row in official_rows if row["statistics_status"] == "official_final"]
    comparable = [row for row in comparison_rows if row["comparison_status"] == "comparable"]
    exact = [row for row in comparable if int(row["absolute_difference"]) == 0]
    largest = sorted(comparable, key=lambda row: abs(int(row["absolute_difference"])), reverse=True)[:5]
    unavailable = [row for row in official_rows if row["statistics_status"] != "official_final"]
    status_counts = Counter(row["observation_status"] for row in panel_rows)
    lines = [
        "## Preliminary district data vs official annual statistics", "",
        "Dataset 14200 contains preliminary quarterly incident data. It remains valuable because it provides administrative-district information, but it is not the final annual statistical series. Final annual city totals can differ from Dataset 14200 totals.", "",
        f"The official layer uses {OFFICIAL_STATISTICS_LABEL}; the district layer uses {DISTRICT_STATISTICS_LABEL}. They remain separate. Official city totals are benchmarks only and are never scaled, proportionally distributed, or otherwise used to manufacture finalized district counts.", "",
        "Missing analytical rows do not automatically mean zero. `observed_zero` means all four quarterly source files carried the category and no district incident was present. `partial_coverage` means only part of the year carried the category, so a full-year rate/comparison is unsafe. `unavailable` means the source category was not available and both count and rate remain NA.", "",
        f"Rates are labelled {POPULATION_RATE_LABEL} and use year-end registered population. Partial and unavailable observations do not receive full-year rates.", "",
        "### Authoritative annual extraction", "",
        f"- Verified official year/type values: {len(verified)}.",
        f"- Official values unavailable or category not comparable: {len(unavailable)}.",
        "- Count basis: CIB annual table `當年發生件數` (current-year occurrences); supplemental reports are not added.",
        "- 組織犯罪防制條例 is kept non-comparable rather than assumed equivalent across sources.", "",
        "### Required residential-burglary reconciliation", "",
        "| Year | Dataset 14200 preliminary | Official final | Difference |", "|---:|---:|---:|---:|",
    ]
    for year in (2023, 2024):
        row = next(item for item in comparison_rows if int(item["year"]) == year and item["crime_type"] == "住宅竊盜")
        lines.append(f"| {year} | {row['dataset14200_city_source_count']} | {row['official_annual_count']} | {row['absolute_difference']} |")
    lines.extend(["", f"Exact preliminary/final matches among comparable values: {len(exact)}.", "", "Largest absolute preliminary/final differences (neutral audit listing):", "", "| Year | Crime type | Preliminary | Official | Difference |", "|---:|---|---:|---:|---:|"])
    for row in largest:
        lines.append(f"| {row['year']} | {row['crime_type']} | {row['dataset14200_city_source_count']} | {row['official_annual_count']} | {row['absolute_difference']} |")
    lines.extend(["", "### Source coverage and observation semantics", "", f"- Quarter/category matrix rows: {40 * len(ALL_CRIME_TYPES)}."])
    for year in TARGET_YEARS:
        lines.append(f"- 組織犯罪防制條例 {year}: `{annual_coverage[(year, ORGANIZED_CRIME_TYPE)]}`.")
    lines.extend(["", f"Analysis-panel rows: {len(panel_rows)}."])
    for status in ("observed_positive", "observed_zero", "partial_coverage", "unavailable"):
        lines.append(f"- `{status}`: {status_counts[status]}.")
    lines.extend(["", "The complete seven-component official 暴力犯罪 definition still cannot be recreated from Dataset 14200 district data. No `暴力犯罪` or `violent_crime` district aggregate is produced.", ""])
    return "\n".join(lines)


def run() -> int:
    metadata = json.loads(METADATA_PATH.read_text(encoding="utf-8"))
    errors: list[str] = []
    coverage_rows, annual_coverage, coverage_errors = build_coverage_matrix(metadata)
    errors.extend(coverage_errors)
    official_values, official_evidence, extraction_errors = extract_official_values(metadata)
    errors.extend(extraction_errors)

    official_rows: list[dict[str, Any]] = []
    for year in TARGET_YEARS:
        for crime_type in ALL_CRIME_TYPES:
            key = (year, crime_type)
            if crime_type == ORGANIZED_CRIME_TYPE:
                official_rows.append({
                    "year": year,
                    "crime_type": crime_type,
                    "official_annual_count": "",
                    "statistics_status": "not_comparable",
                    "source_agency": OFFICIAL_AGENCY,
                    "source_document": "",
                    "source_url": metadata.get("official_annual_crime", {}).get("source_page", ""),
                    "source_file": "",
                    "source_note": "Handled separately; statistical equivalence with the annual publication category is not asserted.",
                    "statistics_layer": "official_annual_city",
                    "official_statistics_label": OFFICIAL_STATISTICS_LABEL,
                })
                continue
            value = official_values.get(key)
            proof = official_evidence.get(key, {})
            official_rows.append({
                "year": year,
                "crime_type": crime_type,
                "official_annual_count": "" if value is None else value,
                "statistics_status": "unavailable" if value is None else "official_final",
                "source_agency": OFFICIAL_AGENCY,
                "source_document": proof.get("source_document", ""),
                "source_url": proof.get("source_url", metadata.get("official_annual_crime", {}).get("source_page", "")),
                "source_file": proof.get("source_file", ""),
                "source_note": proof.get("source_note", "Authoritative annual value could not be verified automatically; no estimate was used."),
                "statistics_layer": "official_annual_city",
                "official_statistics_label": OFFICIAL_STATISTICS_LABEL,
            })

    official_index = {(int(row["year"]), row["crime_type"]): row for row in official_rows}
    city_rows = read_csv(PROCESSED_DIR / "taichung_crime_yearly_city_coverage.csv")
    city_index = {(int(row["year"]), row["crime_type"]): row for row in city_rows}
    comparison_rows: list[dict[str, Any]] = []
    for year in TARGET_YEARS:
        for crime_type in ALL_CRIME_TYPES:
            key = (year, crime_type)
            coverage = annual_coverage[key]
            city = city_index.get(key)
            preliminary = "" if coverage == "unavailable" else int(city["city_source_records"]) if city else 0
            official = official_index[key]
            official_count = official["official_annual_count"]
            if crime_type == ORGANIZED_CRIME_TYPE:
                status = "category_not_comparable"
            elif official["statistics_status"] != "official_final":
                status = "official_unavailable"
            else:
                status = "comparable"
            difference: int | str = ""
            percent: str = ""
            ratio: str = ""
            if status == "comparable" and preliminary != "":
                difference = int(preliminary) - int(official_count)
                if int(official_count) != 0:
                    percent = format_decimal(difference / int(official_count) * 100)
                    ratio = format_decimal(int(preliminary) / int(official_count))
            comparison_rows.append({
                "year": year,
                "crime_type": crime_type,
                "dataset14200_city_source_count": preliminary,
                "official_annual_count": official_count,
                "absolute_difference": difference,
                "percent_difference_vs_official": percent,
                "preliminary_to_official_ratio": ratio,
                "comparison_status": status,
                "preliminary_statistics_label": DISTRICT_STATISTICS_LABEL,
                "official_statistics_label": OFFICIAL_STATISTICS_LABEL,
            })

    population_rows = read_csv(PROCESSED_DIR / "taichung_population_by_district_2016_2025.csv")
    population_index = {(int(row["year"]), row["district"]): int(row["population"]) for row in population_rows}
    yearly_rows = read_csv(PROCESSED_DIR / "taichung_crime_yearly_by_district.csv")
    yearly_counts: Counter[tuple[int, str, str]] = Counter()
    for row in yearly_rows:
        yearly_counts[(int(row["year"]), row["district"], row["crime_type"])] += int(row["incident_count"])
    panel_rows: list[dict[str, Any]] = []
    for year in TARGET_YEARS:
        for district in EXPECTED_DISTRICTS:
            for crime_type in ALL_CRIME_TYPES:
                coverage = annual_coverage[(year, crime_type)]
                count = yearly_counts[(year, district, crime_type)]
                population = population_index.get((year, district))
                city = city_index.get((year, crime_type), {})
                if coverage == "complete":
                    observation = "observed_positive" if count > 0 else "observed_zero"
                    incident_count: int | str = count
                    rate = format_decimal(count / population * 100000) if population else ""
                elif coverage == "partial":
                    observation = "partial_coverage"
                    incident_count = count
                    rate = ""
                else:
                    observation = "unavailable"
                    incident_count = ""
                    rate = ""
                panel_rows.append({
                    "year": year,
                    "district": district,
                    "crime_type": crime_type,
                    "incident_count": incident_count,
                    "population": population or "",
                    "population_basis": POPULATION_BASIS,
                    "incidents_per_100k_population": rate,
                    "source_coverage_status": coverage,
                    "observation_status": observation,
                    "district_assignment_rate_city_year_type": city.get("district_assignment_rate", ""),
                    "statistics_layer": "preliminary_district",
                    "district_statistics_label": DISTRICT_STATISTICS_LABEL,
                    "population_rate_label": POPULATION_RATE_LABEL,
                })

    reconciliation_rows: list[dict[str, Any]] = []
    comparison_index = {(int(row["year"]), row["crime_type"]): row for row in comparison_rows}
    for year in range(2022, 2026):
        row = comparison_index[(year, "住宅竊盜")]
        city = city_index[(year, "住宅竊盜")]
        official_count = row["official_annual_count"]
        reconciliation_rows.append({
            "year": year,
            "dataset14200_preliminary_total": row["dataset14200_city_source_count"],
            "official_annual_total": official_count,
            "absolute_difference": row["absolute_difference"],
            "ratio": row["preliminary_to_official_ratio"],
            "district_assignment_rate": city["district_assignment_rate"],
            "official_status": official_index[(year, "住宅竊盜")]["statistics_status"],
        })

    write_csv(OFFICIAL_PATH, ["year", "crime_type", "official_annual_count", "statistics_status", "source_agency", "source_document", "source_url", "source_file", "source_note", "statistics_layer", "official_statistics_label"], official_rows)
    write_csv(COMPARISON_PATH, ["year", "crime_type", "dataset14200_city_source_count", "official_annual_count", "absolute_difference", "percent_difference_vs_official", "preliminary_to_official_ratio", "comparison_status", "preliminary_statistics_label", "official_statistics_label"], comparison_rows)
    write_csv(COVERAGE_MATRIX_PATH, ["year", "quarter", "crime_type", "category_available", "coverage_status", "source_file", "notes"], coverage_rows)
    write_csv(ANALYSIS_PANEL_PATH, ["year", "district", "crime_type", "incident_count", "population", "population_basis", "incidents_per_100k_population", "source_coverage_status", "observation_status", "district_assignment_rate_city_year_type", "statistics_layer", "district_statistics_label", "population_rate_label"], panel_rows)
    write_csv(RESIDENTIAL_RECONCILIATION_PATH, ["year", "dataset14200_preliminary_total", "official_annual_total", "absolute_difference", "ratio", "district_assignment_rate", "official_status"], reconciliation_rows)

    metadata["statistical_semantics"] = {
        "district_statistics_label": DISTRICT_STATISTICS_LABEL,
        "official_annual_city_statistics_label": OFFICIAL_STATISTICS_LABEL,
        "population_rate_label": POPULATION_RATE_LABEL,
        "coverage_states": ["complete", "partial", "unavailable"],
        "observation_states": ["observed_positive", "observed_zero", "partial_coverage", "unavailable"],
        "official_count_basis": "當年發生件數 (current-year occurrences); supplemental reports excluded",
        "official_city_totals_distributed_to_districts": False,
        "violent_crime_district_aggregate_created": False,
    }
    metadata["official_annual_crime"]["verified_value_count"] = sum(row["statistics_status"] == "official_final" for row in official_rows)
    METADATA_PATH.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    marker = "## Preliminary district data vs official annual statistics"
    report = REPORT_PATH.read_text(encoding="utf-8") if REPORT_PATH.is_file() else ""
    if marker in report:
        report = report.split(marker, 1)[0]
    report = report.rstrip() + "\n\n" + build_report_section(official_rows, comparison_rows, annual_coverage, panel_rows)
    REPORT_PATH.write_text(report.rstrip() + "\n", encoding="utf-8")

    required = {(2023, "住宅竊盜"): 91, (2024, "住宅竊盜"): 142}
    for key, expected in required.items():
        actual = official_values.get(key)
        if actual != expected:
            errors.append(f"required official cross-check failed for {key}: expected {expected}, found {actual}")
    expected_preliminary = {(2023, "住宅竊盜"): 47, (2024, "住宅竊盜"): 129}
    for key, expected in expected_preliminary.items():
        actual = comparison_index[key]["dataset14200_city_source_count"]
        if actual != expected:
            errors.append(f"preliminary cross-check failed for {key}: expected {expected}, found {actual}")
    if len(panel_rows) != 10 * 29 * 8:
        errors.append(f"analysis panel expected 2320 rows, found {len(panel_rows)}")
    if len(coverage_rows) != 40 * 8:
        errors.append(f"coverage matrix expected 320 rows, found {len(coverage_rows)}")
    if set(population_index) != {(year, district) for year in TARGET_YEARS for district in EXPECTED_DISTRICTS}:
        errors.append("population join is incomplete")

    print(f"Verified {len(official_values)} official annual city values; wrote {len(panel_rows)} analysis rows")
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
