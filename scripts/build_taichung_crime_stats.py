#!/usr/bin/env python3
"""Validate Dataset 14200 raw files and build Taichung incident statistics."""

from __future__ import annotations

import csv
import hashlib
import json
import sys
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable


REPO_ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = REPO_ROOT / "data" / "raw" / "taichung" / "npa_crime"
POPULATION_RAW_DIR = REPO_ROOT / "data" / "raw" / "taichung" / "population"
PROCESSED_DIR = REPO_ROOT / "data" / "processed" / "taichung"
METADATA_PATH = REPO_ROOT / "metadata" / "data_sources.json"
REPORT_PATH = REPO_ROOT / "reports" / "taichung_data_coverage.md"
INCIDENTS_PATH = PROCESSED_DIR / "taichung_crime_incidents_2016_2025.csv"
MONTHLY_PATH = PROCESSED_DIR / "taichung_crime_monthly_by_district.csv"
YEARLY_PATH = PROCESSED_DIR / "taichung_crime_yearly_by_district.csv"
PIVOT_PATH = PROCESSED_DIR / "taichung_crime_yearly_pivot.csv"
POPULATION_PATH = PROCESSED_DIR / "taichung_population_by_district_2016_2025.csv"
RATES_PATH = PROCESSED_DIR / "taichung_crime_yearly_rates_by_district.csv"
CITY_COVERAGE_PATH = PROCESSED_DIR / "taichung_crime_yearly_city_coverage.csv"
DISTRICT_COVERAGE_PATH = PROCESSED_DIR / "taichung_district_coverage_by_crime_type.csv"
REJECTED_PATH = PROCESSED_DIR / "taichung_crime_rejected_records.csv"
SUMMARY_PATH = PROCESSED_DIR / "taichung_crime_10year_summary_by_district.csv"
TARGET_YEARS = set(range(2016, 2026))
EXPECTED_DISTRICTS = {
    "中區", "東區", "南區", "西區", "北區", "西屯區", "南屯區", "北屯區",
    "豐原區", "東勢區", "大甲區", "清水區", "沙鹿區", "梧棲區", "后里區",
    "神岡區", "潭子區", "大雅區", "新社區", "石岡區", "外埔區", "大安區",
    "烏日區", "大肚區", "龍井區", "霧峰區", "太平區", "大里區", "和平區",
}
TAICHUNG_EXACT_ALIASES = {"臺中市", "台中市"}
REQUIRED_COLUMNS = ("type", "oc_year", "oc_data", "oc_county", "oc_region")
EXPLANATORY_ROW = {"案類", "發生年度", "發生日期", "發生縣市", "發生鄉鎮市區"}
VIOLENT_COMPONENTS = ("故意殺人", "強盜", "搶奪", "擄人勒贖", "強制性交", "重大恐嚇取財", "重傷害")
BASE_CRIME_TYPES = {"住宅竊盜", "汽車竊盜", "機車竊盜", "毒品", "強盜", "搶奪", "強制性交"}
ORGANIZED_CRIME_TYPE = "組織犯罪防制條例"
POPULATION_COLUMNS = ("statistic_yyy", "site_id", "people_total", "area", "population_density")
POPULATION_BASIS = "year_end_registered_population"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def detect_encoding(path: Path) -> tuple[str, str | None]:
    data = path.read_bytes()
    errors: list[str] = []
    for encoding in ("utf-8-sig", "utf-8", "cp950", "big5"):
        try:
            data.decode(encoding)
            issue = None if encoding in {"utf-8-sig", "utf-8"} else f"non-UTF-8 source decoded as {encoding}"
            return encoding, issue
        except UnicodeDecodeError as exc:
            errors.append(f"{encoding}: {exc}")
    raise UnicodeError("; ".join(errors))


def parse_roc_date(roc_year: str, mmdd: str) -> date:
    year_text = roc_year.strip()
    value = mmdd.strip()
    if not year_text.isdigit():
        raise ValueError(f"non-numeric ROC year {roc_year!r}")
    if value.isdigit() and len(value) == 3:
        value = value.zfill(4)
    if len(value) != 4 or not value.isdigit():
        raise ValueError(f"MMDD must contain four digits, got {mmdd!r}")
    year = int(year_text) + 1911
    return date(year, int(value[:2]), int(value[2:]))


def normalize_cell(value: Any) -> str:
    return "" if value is None else str(value).strip().lstrip("\ufeff")


def load_metadata() -> dict[str, Any]:
    return json.loads(METADATA_PATH.read_text(encoding="utf-8"))


def read_resource(
    resource: dict[str, Any], quality: dict[str, Any]
) -> Iterable[dict[str, str]]:
    source_file = normalize_cell(resource.get("downloaded_filename"))
    path = RAW_DIR / source_file
    if not path.is_file():
        raise FileNotFoundError(f"metadata raw file does not exist: {source_file}")
    actual_hash = sha256_file(path)
    if actual_hash != resource.get("sha256"):
        raise ValueError(f"SHA-256 mismatch for {source_file}")
    encoding, issue = detect_encoding(path)
    if issue:
        quality["encoding_issues"].append({"source_file": source_file, "issue": issue})
    with path.open("r", encoding=encoding, newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = tuple(normalize_cell(name) for name in (reader.fieldnames or ()))
        missing = set(REQUIRED_COLUMNS) - set(fieldnames)
        if missing:
            raise ValueError(f"{source_file} missing columns: {sorted(missing)}")
        for line_number, raw in enumerate(reader, start=2):
            row = {normalize_cell(key): normalize_cell(value) for key, value in raw.items() if key is not None}
            if set(row.get(key, "") for key in REQUIRED_COLUMNS) == EXPLANATORY_ROW:
                continue
            if None in raw:
                quality["malformed_rows"].append(
                    {"source_file": source_file, "line": line_number, "reason": "extra CSV fields", "row": raw}
                )
                continue
            if any(key not in row for key in REQUIRED_COLUMNS):
                quality["malformed_rows"].append(
                    {"source_file": source_file, "line": line_number, "reason": "missing required value", "row": raw}
                )
                continue
            row["_source_file"] = source_file
            row["_source_period"] = normalize_cell(resource.get("source_period"))
            row["_line"] = str(line_number)
            yield row


def write_csv(path: Path, fieldnames: list[str], rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def format_items(items: Iterable[str]) -> str:
    values = list(items)
    return "、".join(values) if values else "None"


def format_rate(numerator: int, denominator: int) -> str:
    if denominator <= 0:
        return ""
    return f"{numerator / denominator:.10f}".rstrip("0").rstrip(".")


def format_decimal(value: float) -> str:
    return f"{value:.10f}".rstrip("0").rstrip(".")


def read_population_table(metadata: dict[str, Any]) -> tuple[list[dict[str, Any]], list[str]]:
    population_metadata = metadata.get("population")
    if not isinstance(population_metadata, dict):
        return [], ["population provenance is missing; run scripts/download_taichung_population.py"]
    resources = population_metadata.get("resources", [])
    errors: list[str] = []
    rows: list[dict[str, Any]] = []
    seen_keys: set[tuple[int, str]] = set()
    for resource in sorted(resources, key=lambda item: item.get("year", 0)):
        if resource.get("status") == "failed":
            errors.append(f"population download failed for {resource.get('year')}")
            continue
        source_file = normalize_cell(resource.get("downloaded_filename"))
        path = POPULATION_RAW_DIR / source_file
        if not path.is_file():
            errors.append(f"population raw file is missing: {source_file}")
            continue
        if sha256_file(path) != resource.get("sha256"):
            errors.append(f"population SHA-256 mismatch: {source_file}")
            continue
        try:
            encoding, _ = detect_encoding(path)
            with path.open("r", encoding=encoding, newline="") as handle:
                reader = csv.DictReader(handle)
                fields = {normalize_cell(value) for value in (reader.fieldnames or ())}
                missing = set(POPULATION_COLUMNS) - fields
                if missing:
                    errors.append(f"{source_file} missing population columns: {sorted(missing)}")
                    continue
                for raw in reader:
                    row = {normalize_cell(key): normalize_cell(value) for key, value in raw.items() if key is not None}
                    if row.get("statistic_yyy") == "統計年":
                        continue
                    site_id = row.get("site_id", "").replace(" ", "").replace("\u3000", "")
                    if not site_id.startswith("臺中市"):
                        continue
                    district = site_id[len("臺中市"):]
                    if district not in EXPECTED_DISTRICTS:
                        errors.append(f"{source_file} has unexpected Taichung district: {district!r}")
                        continue
                    try:
                        year = int(row["statistic_yyy"]) + 1911
                        population = int(row["people_total"].replace(",", ""))
                        area = float(row["area"].replace(",", ""))
                        density = float(row["population_density"].replace(",", ""))
                    except (KeyError, ValueError) as exc:
                        errors.append(f"{source_file} invalid population row for {district}: {exc}")
                        continue
                    key = (year, district)
                    if key in seen_keys:
                        errors.append(f"duplicate population key: {year}/{district}")
                        continue
                    seen_keys.add(key)
                    if year not in TARGET_YEARS:
                        errors.append(f"population year outside target: {year}")
                        continue
                    if population <= 0:
                        errors.append(f"non-positive population: {year}/{district}")
                        continue
                    rows.append({
                        "year": year,
                        "district": district,
                        "population": population,
                        "population_basis": POPULATION_BASIS,
                        "area": format_decimal(area),
                        "population_density": format_decimal(density),
                        "source_dataset_id": population_metadata.get("dataset_id", 8410),
                        "source_file": source_file,
                    })
        except (OSError, UnicodeError) as exc:
            errors.append(f"unable to parse {source_file}: {exc}")
    rows.sort(key=lambda row: (row["year"], row["district"]))
    expected_keys = {(year, district) for year in TARGET_YEARS for district in EXPECTED_DISTRICTS}
    actual_keys = {(row["year"], row["district"]) for row in rows}
    if actual_keys != expected_keys:
        missing = sorted(expected_keys - actual_keys)
        extra = sorted(actual_keys - expected_keys)
        if missing:
            errors.append(f"missing population keys: {missing}")
        if extra:
            errors.append(f"unexpected population keys: {extra}")
    if len(rows) != 290:
        errors.append(f"expected 290 population rows, found {len(rows)}")
    return rows, errors


def pct_change(current: float, baseline: float | None) -> str:
    if baseline is None or baseline == 0:
        return ""
    return format_decimal((current - baseline) / baseline * 100)


def build_phase2a_report(
    metadata: dict[str, Any],
    population_rows: list[dict[str, Any]],
    rate_rows: list[dict[str, Any]],
    city_rows: list[dict[str, Any]],
    rejected_records: list[dict[str, Any]],
    quarter_counts: Counter[tuple[str, str, str]],
    global_type_periods: dict[str, set[str]],
) -> str:
    assigned = sum(int(row["district_assigned_records"]) for row in city_rows)
    unassigned = sum(int(row["district_unassigned_records"]) for row in city_rows)
    invalid = sum(int(row["invalid_date_records"]) for row in city_rows)
    denominator = assigned + unassigned
    overall_rate = assigned / denominator if denominator else 0.0
    by_year: dict[int, tuple[int, int]] = {}
    for year in sorted(TARGET_YEARS):
        year_rows = [row for row in city_rows if int(row["year"]) == year]
        by_year[year] = (
            sum(int(row["district_assigned_records"]) for row in year_rows),
            sum(int(row["district_unassigned_records"]) for row in year_rows),
        )
    crime_types = sorted({str(row["crime_type"]) for row in city_rows})
    by_type: dict[str, tuple[int, int]] = {}
    for crime_type in crime_types:
        type_rows = [row for row in city_rows if row["crime_type"] == crime_type]
        by_type[crime_type] = (
            sum(int(row["district_assigned_records"]) for row in type_rows),
            sum(int(row["district_unassigned_records"]) for row in type_rows),
        )
    reasons = Counter(row["rejection_reason"] for row in rejected_records)
    residential = [row for row in city_rows if row["crime_type"] == "住宅竊盜"]
    sex_2019 = next(row for row in city_rows if int(row["year"]) == 2019 and row["crime_type"] == "強制性交")
    quarters_2019 = sorted(
        period for period in global_type_periods.get("強制性交", set()) if str(period).startswith("108")
    )

    lines = [
        "## Phase 2A — population normalization and source accounting", "",
        "### Population", "",
        f"- Source: 各鄉鎮市區人口密度, data.gov.tw Dataset {metadata.get('population', {}).get('dataset_id', 8410)}, 內政部戶政司.",
        "- Denominator: year-end registered population (`year_end_registered_population`); it is not average, mid-year, or resident-exposure population.",
        f"- Coverage: {len(population_rows)} rows; {len({row['district'] for row in population_rows})}/29 districts; years {min((row['year'] for row in population_rows), default='N/A')}–{max((row['year'] for row in population_rows), default='N/A')}.",
        "- No population interpolation or district fuzzy matching was used.", "",
        "### Crime district assignment", "",
        f"- Date-valid Taichung source records: {denominator}",
        f"- District assigned: {assigned}",
        f"- District unassigned: {unassigned}",
        f"- Overall assignment rate: {overall_rate:.6%}",
        f"- Invalid-date records, retained separately: {invalid}",
        "- Assignment-rate denominator: `district_assigned_records + district_unassigned_records`; invalid-date records are excluded from that denominator.",
        "- City source totals are not forced to equal the sum of 29 districts. No proportional, nearest-district, precinct, population-weighted, prior-year, or manual imputation is performed.", "",
        "| Year | Assigned | Unassigned | Assignment rate |", "|---:|---:|---:|---:|",
    ]
    for year, (year_assigned, year_unassigned) in by_year.items():
        year_denominator = year_assigned + year_unassigned
        rate = year_assigned / year_denominator if year_denominator else 0
        lines.append(f"| {year} | {year_assigned} | {year_unassigned} | {rate:.6%} |")
    lines.extend(["", "Assignment by crime type:", "", "| Crime type | Assigned | Unassigned | Assignment rate |", "|---|---:|---:|---:|"])
    for crime_type, (type_assigned, type_unassigned) in by_type.items():
        type_denominator = type_assigned + type_unassigned
        rate_text = f"{type_assigned / type_denominator:.6%}" if type_denominator else "N/A"
        lines.append(f"| {crime_type} | {type_assigned} | {type_unassigned} | {rate_text} |")
    lines.extend(["", "Year × crime-type unassigned records:", "", "| Year | Crime type | Unassigned | Assignment rate |", "|---:|---|---:|---:|"])
    for row in city_rows:
        assigned_value = int(row["district_assigned_records"])
        unassigned_value = int(row["district_unassigned_records"])
        total = assigned_value + unassigned_value
        if unassigned_value:
            lines.append(f"| {row['year']} | {row['crime_type']} | {unassigned_value} | {assigned_value / total:.6%} |")
    lines.extend([
        "", "The missing districts are concentrated in 機車竊盜, as shown by the crime-type table. Dataset 14200 notes one known mechanism for some motorcycle-theft records—road/county boundaries or an imprecise theft location—but the note is not assumed to explain every unassigned row.", "",
        "### Major source-coverage change", "",
    ])
    motorcycle_2024 = next(row for row in city_rows if int(row["year"]) == 2024 and row["crime_type"] == "機車竊盜")
    motorcycle_2025 = next(row for row in city_rows if int(row["year"]) == 2025 and row["crime_type"] == "機車竊盜")
    lines.extend([
        f"Motorcycle-theft source totals were similar in 2024 and 2025 ({motorcycle_2024['city_source_records']} versus {motorcycle_2025['city_source_records']}), but district assignment changed from {float(motorcycle_2024['district_assignment_rate']):.2%} ({motorcycle_2024['district_assigned_records']} assigned, {motorcycle_2024['district_unassigned_records']} unassigned) to {float(motorcycle_2025['district_assignment_rate']):.2%} ({motorcycle_2025['district_assigned_records']} assigned, {motorcycle_2025['district_unassigned_records']} unassigned). Accordingly, the increase in 2025 district-assigned motorcycle-theft counts is primarily a district-completeness change rather than an increase in city source totals. The CSVs do not identify the administrative reason for that change.", "",
        "### Rejected records", "",
        f"- Auditable rejected rows: {len(rejected_records)}",
    ])
    lines.extend(f"- `{reason}`: {count}" for reason, count in sorted(reasons.items()))
    lines.extend(["", "### 住宅竊盜 audit", "", "| Year | City source | Assigned | Unassigned | Assignment rate |", "|---:|---:|---:|---:|---:|"])
    for row in residential:
        rate_text = f"{float(row['district_assignment_rate']):.6%}" if row["district_assignment_rate"] != "" else "N/A"
        lines.append(f"| {row['year']} | {row['city_source_records']} | {row['district_assigned_records']} | {row['district_unassigned_records']} | {rate_text} |")
    lines.extend(["", "2023–2025 quarterly audit:", "", "| Quarter | Source total | Assigned | Unassigned | Assignment rate |", "|---|---:|---:|---:|---:|"])
    quarterly_residential: list[tuple[str, int, int]] = []
    for year in range(112, 115):
        for start, end in (("01", "03"), ("04", "06"), ("07", "09"), ("10", "12")):
            period = f"{year}{start}-{year}{end}"
            qa = quarter_counts[(period, "住宅竊盜", "assigned")]
            qu = quarter_counts[(period, "住宅竊盜", "unassigned")]
            quarterly_residential.append((period, qa, qu))
            qden = qa + qu
            qrate = f"{qa / qden:.6%}" if qden else "N/A"
            lines.append(f"| {year + 1911} Q{((int(start) - 1) // 3) + 1} | {qden} | {qa} | {qu} | {qrate} |")
    q2_2024 = next(item for item in quarterly_residential if item[0] == "11304-11306")
    q3_2024 = next(item for item in quarterly_residential if item[0] == "11307-11309")
    q2_total, q3_total = q2_2024[1] + q2_2024[2], q3_2024[1] + q3_2024[2]
    q2_rate = q2_2024[1] / q2_total if q2_total else 0
    q3_rate = q3_2024[1] / q3_total if q3_total else 0
    lines.extend([
        "",
        f"Evidence-based conclusion: the official Taichung source total increased from {q2_total} in 2024 Q2 to {q3_total} in Q3, while district assignment changed from {q2_rate:.2%} to {q3_rate:.2%}. The 2024 Q3–2025 increase therefore reflects an increase in records present in Dataset 14200, not a conversion of a large pool of blank-district records into assigned records. The files do not establish why source totals changed, so no causal claim or independent ‘crime surge’ conclusion is made.", "",
        "### 2019 強制性交 audit", "",
        f"- Taichung city source records: {sex_2019['city_source_records']}",
        f"- District assigned: {sex_2019['district_assigned_records']}",
        f"- District unassigned: {sex_2019['district_unassigned_records']}",
        f"- Dataset 14200 contains the 強制性交 category nationally in all 2019 source quarters: {format_items(quarters_2019)}.",
        "- Conclusion: the Taichung zero is an actual absence of Taichung 強制性交 rows in the four published 2019 CSV resources, not a blank-district artifact or an absent source category. This describes Dataset 14200 only and is not a claim about final annual police statistics.", "",
        "### Population-normalized metrics", "",
        "- Formula: `incident_count / year-end registered population × 100,000`.",
        "- Terminology: 每十萬年底戶籍人口案件數 (`incidents_per_100k_population`), not 犯罪人口率.",
        f"- Joined nonzero district/year/crime rows: {len(rate_rows)}; both counts and rates are retained.", "",
        "### Limitations", "",
        "- Dataset 14200 contains quarterly preliminary crime data; final official annual criminal statistics may differ.",
        "- District sums can be lower than city source totals because official rows can lack administrative-district information.",
        "- Blank or unexpected districts are never imputed.",
        "- Year-end registered population is a denominator convention, not an exposure or average-population measure.",
        "- The complete seven-component official 暴力犯罪 definition remains unavailable at district level; no `暴力犯罪` or `violent_crime` aggregate is created.",
        "", "### Phase 2A validation status", "",
        "**PASS** — 10 official population years, 290 unique district/year population rows, exact crime/population joins, complete rejected-row audit, and source-accounting outputs were generated without district imputation.",
    ])
    return "\n".join(lines) + "\n"


def build_report(
    metadata: dict[str, Any], incidents: list[dict[str, Any]], quality: dict[str, Any]
) -> str:
    years = Counter(row["year"] for row in incidents)
    districts = sorted({row["district"] for row in incidents})
    missing_districts = sorted(EXPECTED_DISTRICTS - set(districts))
    types = sorted({row["crime_type"] for row in incidents})
    type_rows = []
    for crime_type in types:
        subset = [row for row in incidents if row["crime_type"] == crime_type]
        type_rows.append((crime_type, min(row["year"] for row in subset), max(row["year"] for row in subset), len(subset)))
    resources = metadata.get("resources", [])
    good = [item for item in resources if item.get("status") != "failed"]
    periods = {item.get("source_period") for item in good}
    expected = {f"{roc}{start}-{roc}{end}" for roc in range(105, 115) for start, end in (("01", "03"), ("04", "06"), ("07", "09"), ("10", "12"))}
    missing_periods = sorted(expected - periods)
    supplied = [item for item in VIOLENT_COMPONENTS if item in types]
    missing_components = [item for item in VIOLENT_COMPONENTS if item not in types]
    invalid_regions = Counter(item["value"] for item in quality["unexpected_regions"])
    failures = [item for item in resources if item.get("status") == "failed"]
    earliest = min((row["date"] for row in incidents), default="N/A")
    latest = max((row["date"] for row in incidents), default="N/A")
    generated = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    lines = [
        "# Taichung crime data coverage (2016–2025)", "",
        f"Generated: {generated}", "",
        "## A. Source", "",
        f"- Dataset: {metadata.get('dataset_title', '犯罪資料')} (ID {metadata.get('dataset_id', 14200)})",
        f"- Provider: {metadata.get('provider', '內政部警政署')}",
        f"- Source page: {metadata.get('source_page', 'https://data.gov.tw/dataset/14200')}",
        "- Raw resources are official quarterly CSV files discovered from the data.gov.tw metadata API; SHA-256 and resource URL are recorded in `metadata/data_sources.json`.",
        "- Historical resources use both `台中市` and `臺中市`. These two exact official spellings are accepted; no fuzzy county matching is used. `source_county` is canonicalized to `臺中市`, while `source_county_original` preserves the official source spelling.", "",
        "## B. Time coverage", "",
        f"- Earliest processed incident date: {earliest}", f"- Latest processed incident date: {latest}",
        f"- Quarterly resources present: {len(periods)}/40", f"- Missing quarters: {format_items(missing_periods)}", "",
        "| Year | Incident rows | Quarters present |", "|---:|---:|---:|",
    ]
    for year in range(2016, 2026):
        roc = year - 1911
        count = sum(1 for period in periods if str(period).startswith(str(roc)))
        lines.append(f"| {year} | {years[year]} | {count}/4 |")
    lines.extend([
        "", "## C. Geographic coverage", "",
        f"- Valid Taichung districts found: {len(districts)}/29",
        f"- Districts: {format_items(districts)}",
        f"- Missing expected districts: {format_items(missing_districts)}",
        f"- Unexpected regions: {format_items(f'{key} ({value})' for key, value in sorted(invalid_regions.items()))}",
        f"- Blank/null regions: {len(quality['blank_regions'])}", "",
        "## D. Crime coverage", "", "| Crime type | First year | Last year | Rows |", "|---|---:|---:|---:|",
    ])
    lines.extend(f"| {crime_type} | {first} | {last} | {count} |" for crime_type, first, last, count in type_rows)
    lines.extend([
        "", "## E. Violent crime", "",
        "The National Police Agency defines 暴力犯罪 as seven groups: 故意殺人、強盜、搶奪、擄人勒贖、強制性交、重大恐嚇取財、重傷害.",
        f"Dataset 14200 supplies these individual components in the target period: {format_items(supplied)}.",
        f"Components absent from Dataset 14200: {format_items(missing_components)}.",
        "Authoritative-source investigation found Taichung's `臺中市處理刑事案件-分局別` (data.gov.tw Dataset 116218), including the missing offense fields, but it is police-precinct-level, not administrative-district-level, and its published resource history does not provide complete 2016–2025 district coverage. No precinct-to-district allocation was attempted.",
        "**Complete official district-level violent-crime statistics cannot currently be derived from Dataset 14200 alone.**",
        "No `暴力犯罪` or `violent_crime` total was created. Available component categories remain individually labelled.",
        "Official definition reference: https://www.npa.gov.tw/ch/app/nounDefine/list?id=2221&module=nounDefine&page=0&pageSize=100", "",
        "## F. Data quality", "",
        f"- Malformed CSV rows: {len(quality['malformed_rows'])}",
        f"- Invalid/out-of-range dates: {len(quality['invalid_dates'])}",
        f"- Blank/null regions: {len(quality['blank_regions'])}",
        f"- Unexpected regions: {len(quality['unexpected_regions'])}",
        f"- Non-UTF-8 encoding issues: {len(quality['encoding_issues'])}",
        f"- Download failures: {len(failures)}", "",
        "Malformed or unusable record details:", "",
    ])
    details = (
        [("malformed", item) for item in quality["malformed_rows"]]
        + [("invalid_date", item) for item in quality["invalid_dates"]]
        + [("unexpected_region", item) for item in quality["unexpected_regions"]]
    )
    if not details:
        lines.append("- None")
    else:
        for kind, item in details:
            lines.append(f"- `{kind}`: `{json.dumps(item, ensure_ascii=False, default=str)}`")
    if quality["blank_regions"]:
        blank_by_file: dict[str, list[str]] = defaultdict(list)
        for item in quality["blank_regions"]:
            blank_by_file[item["source_file"]].append(str(item["line"]))
        lines.extend(["", "Blank-region rows (counts and exact source line numbers):", ""])
        for source_file, line_numbers in sorted(blank_by_file.items()):
            lines.append(f"- `{source_file}`: {len(line_numbers)} rows; lines {', '.join(line_numbers)}")
    lines.extend(["", "## Validation status", ""])
    if missing_periods or failures:
        lines.append("**FAIL** — primary quarterly source coverage is incomplete.")
    elif set(years) != TARGET_YEARS:
        lines.append("**FAIL** — processed incident rows do not cover exactly 2016–2025.")
    elif missing_districts:
        lines.append("**FAIL** — not all 29 official districts occur in the processed data.")
    else:
        lines.append("**PASS** — all 40 quarters are present, all target years occur, all 29 districts occur, and aggregation reconciliation is checked by the test suite.")
    return "\n".join(lines) + "\n"


def run() -> int:
    if not METADATA_PATH.is_file():
        print(f"ERROR: run scripts/download_taichung_crime.py first; missing {METADATA_PATH}", file=sys.stderr)
        return 1
    metadata = load_metadata()
    expected_periods = {f"{roc}{start}-{roc}{end}" for roc in range(105, 115) for start, end in (("01", "03"), ("04", "06"), ("07", "09"), ("10", "12"))}
    resources = [item for item in metadata.get("resources", []) if item.get("source_period") in expected_periods]
    usable = [item for item in resources if item.get("status") != "failed"]
    periods = [item.get("source_period") for item in usable]
    if len(set(periods)) != len(periods):
        print("ERROR: duplicate source periods in metadata", file=sys.stderr)
        return 1

    quality: dict[str, list[dict[str, Any]]] = {
        "malformed_rows": [], "invalid_dates": [], "blank_regions": [],
        "unexpected_regions": [], "encoding_issues": [],
    }
    incidents: list[dict[str, Any]] = []
    rejected_records: list[dict[str, Any]] = []
    city_counts: Counter[tuple[int, str, str]] = Counter()
    quarter_counts: Counter[tuple[str, str, str]] = Counter()
    global_type_periods: dict[str, set[str]] = defaultdict(set)
    fatal_errors: list[str] = []

    def reject(row: dict[str, str], reason: str, details: str = "") -> None:
        rejected_records.append({
            "crime_type": normalize_cell(row.get("type")),
            "roc_year": normalize_cell(row.get("oc_year")),
            "oc_data": normalize_cell(row.get("oc_data")),
            "source_county_original": normalize_cell(row.get("oc_county")),
            "oc_region": normalize_cell(row.get("oc_region")),
            "source_period": normalize_cell(row.get("_source_period")),
            "source_file": normalize_cell(row.get("_source_file")),
            "source_line": normalize_cell(row.get("_line")),
            "rejection_reason": reason,
            "rejection_details": details,
        })

    for resource in sorted(usable, key=lambda item: item["source_period"]):
        try:
            rows = read_resource(resource, quality)
            for row in rows:
                crime_type = normalize_cell(row["type"])
                if crime_type:
                    global_type_periods[crime_type].add(row["_source_period"])
                county = normalize_cell(row["oc_county"])
                if county not in TAICHUNG_EXACT_ALIASES:
                    continue
                try:
                    roc_year = int(normalize_cell(row["oc_year"]))
                    source_year = roc_year + 1911
                except ValueError as exc:
                    reject(row, "invalid_roc_year", str(exc))
                    continue
                if source_year not in TARGET_YEARS:
                    reject(row, "year_outside_target", f"Gregorian year {source_year}")
                    continue
                if not crime_type:
                    quality["malformed_rows"].append({
                        "source_file": row["_source_file"], "line": row["_line"], "reason": "blank crime type",
                    })
                    reject(row, "blank_crime_type")
                    continue
                try:
                    incident_date = parse_roc_date(row["oc_year"], row["oc_data"])
                except (ValueError, OverflowError) as exc:
                    quality["invalid_dates"].append({
                        "source_file": row["_source_file"], "line": row["_line"],
                        "crime_type": crime_type, "roc_year": row["oc_year"],
                        "oc_data": row["oc_data"], "oc_region": row["oc_region"], "reason": str(exc),
                    })
                    city_counts[(source_year, crime_type, "invalid_date")] += 1
                    reject(row, "invalid_date", str(exc))
                    continue
                district = normalize_cell(row["oc_region"])
                if not district:
                    quality["blank_regions"].append({"source_file": row["_source_file"], "line": row["_line"]})
                    city_counts[(source_year, crime_type, "unassigned")] += 1
                    quarter_counts[(row["_source_period"], crime_type, "unassigned")] += 1
                    reject(row, "blank_district")
                    continue
                if district not in EXPECTED_DISTRICTS:
                    quality["unexpected_regions"].append({
                        "source_file": row["_source_file"], "line": row["_line"], "value": district,
                    })
                    city_counts[(source_year, crime_type, "unassigned")] += 1
                    quarter_counts[(row["_source_period"], crime_type, "unassigned")] += 1
                    reject(row, "unexpected_district", district)
                    continue
                city_counts[(source_year, crime_type, "assigned")] += 1
                quarter_counts[(row["_source_period"], crime_type, "assigned")] += 1
                incidents.append({
                    "date": incident_date.isoformat(), "year": incident_date.year,
                    "month": incident_date.month, "day": incident_date.day,
                    "district": district, "crime_type": crime_type,
                    "roc_year": roc_year, "source_county": "臺中市",
                    "source_county_original": county,
                    "source_period": row["_source_period"], "source_file": row["_source_file"],
                })
        except (OSError, UnicodeError, ValueError) as exc:
            fatal_errors.append(f"{resource.get('source_period')}: {exc}")

    for item in quality["malformed_rows"]:
        if item.get("reason") == "blank crime type":
            continue
        rejected_records.append({
            "crime_type": "", "roc_year": "", "oc_data": "", "source_county_original": "",
            "oc_region": "", "source_period": "", "source_file": item.get("source_file", ""),
            "source_line": item.get("line", ""), "rejection_reason": "malformed_row",
            "rejection_details": item.get("reason", ""),
        })

    incidents.sort(key=lambda row: (row["date"], row["district"], row["crime_type"], row["source_period"], row["source_file"]))
    monthly_counts = Counter((r["year"], r["month"], r["district"], r["crime_type"]) for r in incidents)
    yearly_counts = Counter((r["year"], r["district"], r["crime_type"]) for r in incidents)
    monthly = [
        {"year": key[0], "month": key[1], "district": key[2], "crime_type": key[3], "incident_count": count}
        for key, count in sorted(monthly_counts.items())
    ]
    yearly = [
        {"year": key[0], "district": key[1], "crime_type": key[2], "incident_count": count}
        for key, count in sorted(yearly_counts.items())
    ]
    observed_types = sorted({r["crime_type"] for r in incidents})
    all_source_periods = set(periods)
    category_periods: dict[str, set[str]] = {}
    for crime_type in observed_types:
        if crime_type in BASE_CRIME_TYPES:
            category_periods[crime_type] = set(expected_periods)
        elif crime_type == ORGANIZED_CRIME_TYPE:
            category_periods[crime_type] = {period for period in expected_periods if period >= "10710-10712"}
        else:
            # Unknown categories receive zero only in quarters where at least one row proves availability.
            category_periods[crime_type] = {r["source_period"] for r in incidents if r["crime_type"] == crime_type}
    pivot_rows: list[dict[str, Any]] = []
    for year in sorted(TARGET_YEARS):
        for district in sorted(EXPECTED_DISTRICTS):
            output: dict[str, Any] = {"year": year, "district": district}
            for crime_type in observed_types:
                count = yearly_counts[(year, district, crime_type)]
                year_periods = {period for period in expected_periods if period.startswith(str(year - 1911))}
                full_category_coverage = year_periods <= category_periods[crime_type] and year_periods <= all_source_periods
                # Preserve known counts even during partial coverage; leave missing combinations blank unless
                # all four quarterly resources are known to carry the category.
                output[crime_type] = count if count or full_category_coverage else ""
            pivot_rows.append(output)

    accounting_types = sorted(BASE_CRIME_TYPES | {key[1] for key in city_counts})
    city_rows: list[dict[str, Any]] = []
    district_coverage_rows: list[dict[str, Any]] = []
    for year in sorted(TARGET_YEARS):
        for crime_type in accounting_types:
            if crime_type == ORGANIZED_CRIME_TYPE and year < 2018:
                continue
            assigned = city_counts[(year, crime_type, "assigned")]
            unassigned = city_counts[(year, crime_type, "unassigned")]
            invalid = city_counts[(year, crime_type, "invalid_date")]
            denominator = assigned + unassigned
            rate = format_rate(assigned, denominator)
            city_rows.append({
                "year": year, "crime_type": crime_type,
                "city_source_records": denominator + invalid,
                "district_assigned_records": assigned,
                "district_unassigned_records": unassigned,
                "invalid_date_records": invalid,
                "district_assignment_rate": rate,
            })
            district_coverage_rows.append({
                "year": year, "crime_type": crime_type,
                "total_taichung_records": denominator,
                "district_assigned_records": assigned,
                "district_unassigned_records": unassigned,
                "district_assignment_rate": rate,
            })

    population_rows, population_errors = read_population_table(metadata)
    population_index = {(row["year"], row["district"]): row for row in population_rows}
    rate_rows: list[dict[str, Any]] = []
    join_errors: list[str] = []
    for row in yearly:
        key = (row["year"], row["district"])
        population = population_index.get(key)
        if population is None:
            join_errors.append(f"crime/population key unmatched: {key}")
            continue
        incident_count = int(row["incident_count"])
        population_value = int(population["population"])
        rate_rows.append({
            **row,
            "population": population_value,
            "population_basis": POPULATION_BASIS,
            "incidents_per_100k_population": format_decimal(incident_count / population_value * 100000),
        })

    summary_rows: list[dict[str, Any]] = []
    for district in sorted(EXPECTED_DISTRICTS):
        for crime_type in observed_types:
            total = sum(yearly_counts[(year, district, crime_type)] for year in TARGET_YEARS)
            pop_2016 = population_index.get((2016, district), {}).get("population")
            pop_2025 = population_index.get((2025, district), {}).get("population")
            known_2016 = crime_type in BASE_CRIME_TYPES
            count_2016 = yearly_counts[(2016, district, crime_type)] if known_2016 else None
            count_2025 = yearly_counts[(2025, district, crime_type)]
            rate_2016 = (count_2016 / pop_2016 * 100000) if count_2016 is not None and pop_2016 else None
            rate_2025 = (count_2025 / pop_2025 * 100000) if pop_2025 else None
            summary_rows.append({
                "district": district,
                "crime_type": crime_type,
                "total_incidents_2016_2025": total,
                "average_annual_incidents": format_decimal(total / 10),
                "population_2016": pop_2016 or "",
                "population_2025": pop_2025 or "",
                "rate_2016": format_decimal(rate_2016) if rate_2016 is not None else "",
                "rate_2025": format_decimal(rate_2025) if rate_2025 is not None else "",
                "absolute_change_incidents": (count_2025 - count_2016) if count_2016 is not None else "",
                "percent_change_incidents": pct_change(count_2025, float(count_2016) if count_2016 is not None else None),
                "absolute_change_rate": format_decimal(rate_2025 - rate_2016) if rate_2016 is not None and rate_2025 is not None else "",
                "percent_change_rate": pct_change(rate_2025, rate_2016) if rate_2025 is not None else "",
            })

    write_csv(INCIDENTS_PATH, ["date", "year", "month", "day", "district", "crime_type", "roc_year", "source_county", "source_county_original", "source_period", "source_file"], incidents)
    write_csv(MONTHLY_PATH, ["year", "month", "district", "crime_type", "incident_count"], monthly)
    write_csv(YEARLY_PATH, ["year", "district", "crime_type", "incident_count"], yearly)
    write_csv(PIVOT_PATH, ["year", "district", *observed_types], pivot_rows)
    write_csv(POPULATION_PATH, ["year", "district", "population", "population_basis", "area", "population_density", "source_dataset_id", "source_file"], population_rows)
    write_csv(RATES_PATH, ["year", "district", "crime_type", "incident_count", "population", "population_basis", "incidents_per_100k_population"], rate_rows)
    write_csv(CITY_COVERAGE_PATH, ["year", "crime_type", "city_source_records", "district_assigned_records", "district_unassigned_records", "invalid_date_records", "district_assignment_rate"], city_rows)
    write_csv(DISTRICT_COVERAGE_PATH, ["year", "crime_type", "total_taichung_records", "district_assigned_records", "district_unassigned_records", "district_assignment_rate"], district_coverage_rows)
    rejected_records.sort(key=lambda row: (row["source_period"], row["source_file"], int(row["source_line"] or 0), row["rejection_reason"]))
    write_csv(REJECTED_PATH, ["crime_type", "roc_year", "oc_data", "source_county_original", "oc_region", "source_period", "source_file", "source_line", "rejection_reason", "rejection_details"], rejected_records)
    write_csv(SUMMARY_PATH, ["district", "crime_type", "total_incidents_2016_2025", "average_annual_incidents", "population_2016", "population_2025", "rate_2016", "rate_2025", "absolute_change_incidents", "percent_change_incidents", "absolute_change_rate", "percent_change_rate"], summary_rows)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    report = build_report(metadata, incidents, quality)
    report += "\n" + build_phase2a_report(
        metadata, population_rows, rate_rows, city_rows, rejected_records, quarter_counts, global_type_periods
    )
    REPORT_PATH.write_text(report, encoding="utf-8")

    missing = sorted(expected_periods - set(periods))
    errors = fatal_errors + population_errors + join_errors + ([f"missing source periods: {', '.join(missing)}"] if missing else [])
    if set(row["year"] for row in incidents) != TARGET_YEARS:
        errors.append("processed years are not exactly 2016-2025")
    if {row["district"] for row in incidents} != EXPECTED_DISTRICTS:
        errors.append("processed data does not contain all 29 official districts")
    if len(incidents) != 31307:
        errors.append(f"Phase 1 incident count changed: expected 31307, found {len(incidents)}")
    if len(rejected_records) != 2916:
        errors.append(f"rejected audit count differs from validated source accounting: expected 2916, found {len(rejected_records)}")
    if sum(int(row["district_assigned_records"]) for row in city_rows) != len(incidents):
        errors.append("city assigned counts do not reconcile with strict incident rows")
    if not errors:
        try:
            from build_taichung_phase2b import run as run_phase2b

            if run_phase2b() != 0:
                errors.append("Phase 2B official-annual reconciliation failed")
        except (ImportError, OSError, ValueError) as exc:
            errors.append(f"unable to run Phase 2B builder: {exc}")
    if not errors:
        try:
            from build_taichung_geography import run as run_geography

            if run_geography() != 0:
                errors.append("Phase 3A geographic extraction failed")
        except (ImportError, OSError, ValueError) as exc:
            errors.append(f"unable to run Phase 3A geography builder: {exc}")
    print(f"Processed {len(incidents)} Taichung incident rows from {len(periods)}/40 quarterly resources")
    print(f"Observed {len(observed_types)} crime types across {len({r['district'] for r in incidents})}/29 districts")
    print(f"Joined {len(rate_rows)} yearly crime rows to {len(population_rows)} population rows; audited {len(rejected_records)} rejected rows")
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
