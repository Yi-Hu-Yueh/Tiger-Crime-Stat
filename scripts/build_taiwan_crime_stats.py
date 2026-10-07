#!/usr/bin/env python3
"""Build the validated nationwide 2016-2025 crime-statistics foundation."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import sys
import zipfile
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import shapefile
from pypdf import PdfReader


REPO_ROOT = Path(__file__).resolve().parents[1]
RAW_CRIME_DIR = REPO_ROOT / "data" / "raw" / "taichung" / "npa_crime"
RAW_POPULATION_DIR = REPO_ROOT / "data" / "raw" / "taichung" / "population"
RAW_OFFICIAL_DIR = REPO_ROOT / "data" / "raw" / "taichung" / "official_annual_crime"
RAW_BOUNDARY_DIR = REPO_ROOT / "data" / "raw" / "geography" / "town_boundaries"
GEOGRAPHY_DIR = REPO_ROOT / "data" / "processed" / "geography"
OUTPUT_DIR = REPO_ROOT / "data" / "processed" / "taiwan"
METADATA_PATH = REPO_ROOT / "metadata" / "data_sources.json"
REPORT_PATH = REPO_ROOT / "reports" / "taiwan_data_coverage.md"

YEARS = tuple(range(2016, 2026))
TARGET_CRIME_TYPES = (
    "毒品", "強盜", "搶奪", "住宅竊盜", "汽車竊盜", "機車竊盜", "強制性交", "組織犯罪防制條例",
)
OFFICIAL_CRIME_TYPES = TARGET_CRIME_TYPES[:-1]
POPULATION_BASIS = "year_end_registered_population"
DISTRICT_STATISTICS_LABEL = "警政署季度初步案件資料"
OFFICIAL_STATISTICS_LABEL = "警政署／刑事警察局年度正式統計"
REQUIRED_CRIME_COLUMNS = ("type", "oc_year", "oc_data", "oc_county", "oc_region")
EXPLANATORY_ROW = {"案類", "發生年度", "發生日期", "發生縣市", "發生鄉鎮市區"}
REQUIRED_BOUNDARY_FIELDS = {"TOWNID", "TOWNCODE", "COUNTYNAME", "TOWNNAME", "TOWNENG", "COUNTYID", "COUNTYCODE"}
POPULATION_COLUMNS = {"statistic_yyy", "site_id", "people_total", "area", "population_density"}

GEOJSON_PATH = GEOGRAPHY_DIR / "taiwan_districts.geojson"
ADMIN_PATH = GEOGRAPHY_DIR / "taiwan_administrative_units.csv"
INCIDENTS_PATH = OUTPUT_DIR / "taiwan_crime_incidents_2016_2025.csv"
REJECTED_PATH = OUTPUT_DIR / "taiwan_crime_rejected_records.csv"
COVERAGE_PATH = OUTPUT_DIR / "taiwan_district_assignment_coverage.csv"
POPULATION_PATH = OUTPUT_DIR / "taiwan_population_by_district_2016_2025.csv"
CROSSWALK_PATH = OUTPUT_DIR / "taiwan_administrative_crosswalk.csv"
YEARLY_PATH = OUTPUT_DIR / "taiwan_crime_yearly_by_district.csv"
RATES_PATH = OUTPUT_DIR / "taiwan_crime_yearly_rates_by_district.csv"
PANEL_PATH = OUTPUT_DIR / "taiwan_crime_analysis_panel.csv"
PRELIMINARY_COUNTY_PATH = OUTPUT_DIR / "taiwan_preliminary_yearly_by_county.csv"
OFFICIAL_PATH = OUTPUT_DIR / "taiwan_official_annual_county_crime_2016_2025.csv"
COMPARISON_PATH = OUTPUT_DIR / "taiwan_preliminary_vs_official_annual.csv"

CATEGORY_MARKERS = {
    "毒品": "Narcotics",
    "強盜": "Robbery",
    "搶奪": "Forceful Taking",
    "汽車竊盜": "Motor Vehicle Theft",
    "機車竊盜": "Motorcycle Theft",
    "強制性交": "Forcible Sexual Intercourse",
}
COUNTY_ENGLISH = {
    "新北市": "New Taipei City", "臺北市": "Taipei City", "桃園市": "Taoyuan City",
    "臺中市": "Taichung City", "臺南市": "Tainan City", "高雄市": "Kaohsiung City",
    "宜蘭縣": "Ilan County", "新竹縣": "Hsinchu County", "苗栗縣": "Miaoli County",
    "彰化縣": "Changhua County", "南投縣": "Nantou County", "雲林縣": "Yunlin County",
    "嘉義縣": "Chiayi County", "屏東縣": "Pingtung County", "臺東縣": "Taitung County",
    "花蓮縣": "Hualien County", "澎湖縣": "Penghu County", "基隆市": "Keelung City",
    "新竹市": "Hsinchu City", "嘉義市": "Chiayi City", "金門縣": "Kinmen County",
    "連江縣": "Lienchiang County",
}


def normalize(value: Any) -> str:
    return "" if value is None else str(value).strip().lstrip("\ufeff").replace("台", "臺")


def source_text(value: Any) -> str:
    """Trim transport artifacts without changing the source's 台/臺 spelling."""
    return "" if value is None else str(value).strip().lstrip("\ufeff")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def detect_encoding(path: Path) -> str:
    data = path.read_bytes()
    for encoding in ("utf-8-sig", "utf-8", "cp950", "big5"):
        try:
            data.decode(encoding)
            return encoding
        except UnicodeDecodeError:
            pass
    raise UnicodeError(f"unable to decode {path.name}")


def write_csv(path: Path, fields: list[str], rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def decimal(value: float) -> str:
    return f"{value:.10f}".rstrip("0").rstrip(".")


def rate(numerator: int, denominator: int) -> str:
    return decimal(numerator / denominator) if denominator else ""


def parse_date(roc_year: str, mmdd: str) -> date:
    year_text = roc_year.strip()
    value = mmdd.strip()
    if not year_text.isdigit():
        raise ValueError(f"non-numeric ROC year {roc_year!r}")
    if value.isdigit() and len(value) == 3:
        value = value.zfill(4)
    if len(value) != 4 or not value.isdigit():
        raise ValueError(f"MMDD must contain four digits, got {mmdd!r}")
    return date(int(year_text) + 1911, int(value[:2]), int(value[2:]))


def administrative_rejection_reason(
    county: str,
    district: str,
    admin_keys: set[tuple[str, str]],
    counties: set[str],
    district_counties: dict[str, set[str]],
) -> str | None:
    """Return a deterministic validation failure; never fuzzy-match names."""
    if not county:
        return "blank_county"
    if county not in counties:
        return "unknown_county"
    if not district:
        return "blank_district"
    if (county, district) in admin_keys:
        return None
    return "geography_mismatch" if district in district_counties else "unexpected_district"


def iter_positions(value: Any) -> Iterable[tuple[float, float]]:
    if isinstance(value, (list, tuple)) and len(value) >= 2 and all(isinstance(x, (int, float)) for x in value[:2]):
        yield float(value[0]), float(value[1])
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from iter_positions(item)


def load_geography(metadata: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    geography = metadata.get("geography", {})
    resources = geography.get("resources", [])
    if len(resources) != 1:
        raise ValueError("Dataset 7441 provenance must identify exactly one raw archive")
    resource = resources[0]
    archive_path = RAW_BOUNDARY_DIR / str(resource.get("downloaded_filename", ""))
    if not archive_path.is_file() or sha256_file(archive_path) != resource.get("sha256"):
        raise ValueError("Dataset 7441 archive is missing or failed SHA-256 validation")
    with zipfile.ZipFile(archive_path) as archive:
        shp_files = [name for name in archive.namelist() if name.lower().endswith(".shp") and "town_moi" in name.lower()]
        if len(shp_files) != 1:
            raise ValueError(f"expected one TOWN_MOI shapefile, found {shp_files}")
        shp = shp_files[0]
        stem = shp[:-4]
        shx = next((n for n in archive.namelist() if n.lower() == (stem + ".shx").lower()), "")
        dbf = next((n for n in archive.namelist() if n.lower() == (stem + ".dbf").lower()), "")
        if not shx or not dbf:
            raise ValueError("Dataset 7441 archive lacks SHP companion files")
        reader = shapefile.Reader(
            shp=io.BytesIO(archive.read(shp)), shx=io.BytesIO(archive.read(shx)),
            dbf=io.BytesIO(archive.read(dbf)), encoding="utf-8",
        )
        fields = {field[0] for field in reader.fields[1:]}
        if not REQUIRED_BOUNDARY_FIELDS <= fields:
            raise ValueError(f"Dataset 7441 fields missing: {sorted(REQUIRED_BOUNDARY_FIELDS - fields)}")
        features: list[dict[str, Any]] = []
        admin_rows: list[dict[str, Any]] = []
        keys: set[tuple[str, str]] = set()
        town_codes: set[str] = set()
        county_to_code: dict[str, str] = {}
        code_to_county: dict[str, str] = {}
        for item in reader.iterShapeRecords():
            record = item.record.as_dict()
            county = normalize(record["COUNTYNAME"])
            district = normalize(record["TOWNNAME"])
            county_code = normalize(record["COUNTYCODE"])
            town_code = normalize(record["TOWNCODE"])
            if not county or not district or not county_code or not town_code:
                raise ValueError("blank county/district/code in Dataset 7441")
            key = (county, district)
            if key in keys:
                raise ValueError(f"duplicate geography key: {key}")
            if town_code in town_codes:
                raise ValueError(f"duplicate TOWNCODE: {town_code}")
            if county in county_to_code and county_to_code[county] != county_code:
                raise ValueError(f"county has conflicting COUNTYCODE: {county}")
            if county_code in code_to_county and code_to_county[county_code] != county:
                raise ValueError(f"COUNTYCODE maps to multiple counties: {county_code}")
            keys.add(key)
            town_codes.add(town_code)
            county_to_code[county] = county_code
            code_to_county[county_code] = county
            geometry = dict(item.shape.__geo_interface__)
            if geometry.get("type") not in {"Polygon", "MultiPolygon"}:
                raise ValueError(f"invalid geometry type for {key}: {geometry.get('type')}")
            positions = list(iter_positions(geometry.get("coordinates", [])))
            # The official units include the outlying islands administered by 頭城鎮 and
            # 旗津區, so validation covers the authoritative archive's territorial extent.
            if len(positions) < 4 or not all(114 <= x <= 125 and 10 <= y <= 27.5 for x, y in positions):
                raise ValueError(f"invalid geometry coordinates for {key}")
            properties = {"county": county, "district": district, "county_code": county_code, "town_code": town_code}
            features.append({"type": "Feature", "properties": properties, "geometry": geometry})
            admin_rows.append({**properties, "geometry_available": "true"})
    features.sort(key=lambda row: (row["properties"]["county_code"], row["properties"]["town_code"]))
    admin_rows.sort(key=lambda row: (row["county_code"], row["town_code"]))
    if set(COUNTY_ENGLISH) != {row["county"] for row in admin_rows}:
        raise ValueError("official annual county-name map does not exactly match Dataset 7441 counties")
    return features, admin_rows


def load_population(metadata: dict[str, Any], admin_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    population_meta = metadata.get("population", {})
    resources = population_meta.get("resources", [])
    if len(resources) != len(YEARS):
        raise ValueError(f"expected {len(YEARS)} Dataset 8410 resources, found {len(resources)}")
    admin_keys = {(row["county"], row["district"]) for row in admin_rows}
    counties = sorted({row["county"] for row in admin_rows}, key=len, reverse=True)
    result: list[dict[str, Any]] = []
    seen: set[tuple[int, str, str]] = set()
    for resource in sorted(resources, key=lambda row: int(row.get("year", 0))):
        source_file = str(resource.get("downloaded_filename", ""))
        path = RAW_POPULATION_DIR / source_file
        if not path.is_file() or sha256_file(path) != resource.get("sha256"):
            raise ValueError(f"Dataset 8410 source missing or hash mismatch: {source_file}")
        with path.open("r", encoding=detect_encoding(path), newline="") as handle:
            reader = csv.DictReader(handle)
            fields = {normalize(x) for x in (reader.fieldnames or ())}
            if not POPULATION_COLUMNS <= fields:
                raise ValueError(f"{source_file} missing population columns: {sorted(POPULATION_COLUMNS - fields)}")
            for raw in reader:
                row = {normalize(k): normalize(v) for k, v in raw.items() if k is not None}
                if not row.get("statistic_yyy", "").isdigit():
                    continue
                site = row.get("site_id", "").replace(" ", "").replace("\u3000", "")
                county = next((candidate for candidate in counties if site.startswith(candidate)), "")
                district = site[len(county):] if county else ""
                if (county, district) not in admin_keys:
                    # Dataset 8410 also includes aggregate rows and two South China Sea island rows
                    # that are not TOWN_MOI administrative units. They are intentionally excluded.
                    continue
                year = int(row["statistic_yyy"]) + 1911
                key = (year, county, district)
                if key in seen:
                    raise ValueError(f"duplicate population key: {key}")
                try:
                    population = int(row["people_total"].replace(",", ""))
                    area = float(row["area"].replace(",", ""))
                    density = float(row["population_density"].replace(",", ""))
                except ValueError as exc:
                    raise ValueError(f"invalid population row {key}: {exc}") from exc
                if population <= 0:
                    raise ValueError(f"non-positive population without an official exception: {key}")
                seen.add(key)
                result.append({
                    "year": year, "county": county, "district": district, "population": population,
                    "population_basis": POPULATION_BASIS, "area": decimal(area),
                    "population_density": decimal(density), "source_dataset_id": population_meta.get("dataset_id", 8410),
                    "source_file": source_file,
                })
    expected = {(year, row["county"], row["district"]) for year in YEARS for row in admin_rows}
    if seen != expected:
        raise ValueError(f"population key mismatch: missing={sorted(expected-seen)[:20]}, extra={sorted(seen-expected)[:20]}")
    result.sort(key=lambda row: (row["year"], row["county"], row["district"]))
    return result


def build_crime(
    metadata: dict[str, Any], admin_rows: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], Counter[tuple[int, str, str, str]], dict[tuple[int, str], str], int]:
    resources = sorted(metadata.get("resources", []), key=lambda row: str(row.get("source_period", "")))
    if len(resources) != 40 or any(row.get("status") == "failed" for row in resources):
        raise ValueError("the 40 Dataset 14200 national quarterly resources are not all available")
    admin_keys = {(row["county"], row["district"]) for row in admin_rows}
    counties = {row["county"] for row in admin_rows}
    district_counties: dict[str, set[str]] = defaultdict(set)
    for county, district in admin_keys:
        district_counties[district].add(county)
    incidents: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    coverage_counts: Counter[tuple[int, str, str, str]] = Counter()
    quarter_available: dict[tuple[int, int, str], bool] = {}
    raw_source_rows = 0

    def reject(row: dict[str, str], reason: str, details: str = "") -> None:
        rejected.append({
            "crime_type": normalize(row.get("type")), "roc_year": normalize(row.get("oc_year")),
            "oc_data": source_text(row.get("oc_data")), "source_county_original": source_text(row.get("oc_county")),
            "source_region_original": source_text(row.get("oc_region")), "source_period": row.get("_source_period", ""),
            "source_file": row.get("_source_file", ""), "source_line": row.get("_line", ""),
            "rejection_reason": reason, "rejection_details": details,
        })

    periods_seen: set[str] = set()
    for resource in resources:
        source_file = str(resource.get("downloaded_filename", ""))
        source_period = str(resource.get("source_period", ""))
        match = re.fullmatch(r"(\d{3})(\d{2})-(\d{3})(\d{2})", source_period)
        if not match or source_period in periods_seen:
            raise ValueError(f"invalid or duplicate source period: {source_period}")
        periods_seen.add(source_period)
        year = int(match.group(1)) + 1911
        quarter = (int(match.group(2)) - 1) // 3 + 1
        path = RAW_CRIME_DIR / source_file
        if not path.is_file() or sha256_file(path) != resource.get("sha256"):
            raise ValueError(f"Dataset 14200 source missing or hash mismatch: {source_file}")
        types_in_file: set[str] = set()
        with path.open("r", encoding=detect_encoding(path), newline="") as handle:
            reader = csv.DictReader(handle)
            fields = tuple(normalize(x) for x in (reader.fieldnames or ()))
            missing = set(REQUIRED_CRIME_COLUMNS) - set(fields)
            if missing:
                raise ValueError(f"{source_file} missing crime columns: {sorted(missing)}")
            for line_number, raw in enumerate(reader, start=2):
                row = {source_text(k): source_text(v) for k, v in raw.items() if k is not None}
                if set(row.get(key, "") for key in REQUIRED_CRIME_COLUMNS) == EXPLANATORY_ROW:
                    continue
                raw_source_rows += 1
                row.update({"_source_period": source_period, "_source_file": source_file, "_line": str(line_number)})
                if None in raw:
                    reject(row, "malformed_row", "extra CSV fields")
                    continue
                crime_type = normalize(row.get("type"))
                if crime_type:
                    types_in_file.add(crime_type)
                if not crime_type:
                    reject(row, "malformed_row", "blank crime type")
                    continue
                try:
                    incident_date = parse_date(row.get("oc_year", ""), row.get("oc_data", ""))
                except (ValueError, OverflowError) as exc:
                    reject(row, "invalid_date", str(exc))
                    continue
                if incident_date.year not in YEARS:
                    reject(row, "year_outside_target", str(incident_date.year))
                    continue
                county = normalize(row.get("oc_county"))
                district = normalize(row.get("oc_region"))
                admin_rejection = administrative_rejection_reason(county, district, admin_keys, counties, district_counties)
                if admin_rejection in {"blank_county", "unknown_county"}:
                    reject(row, admin_rejection, county)
                    continue
                if admin_rejection == "blank_district":
                    coverage_counts[(incident_date.year, county, crime_type, "unassigned")] += 1
                    reject(row, "blank_district")
                    continue
                if admin_rejection is not None:
                    coverage_counts[(incident_date.year, county, crime_type, "unassigned")] += 1
                    reject(row, admin_rejection, district)
                    continue
                coverage_counts[(incident_date.year, county, crime_type, "assigned")] += 1
                incidents.append({
                    "date": incident_date.isoformat(), "year": incident_date.year, "month": incident_date.month,
                    "day": incident_date.day, "county": county, "district": district, "crime_type": crime_type,
                    "roc_year": normalize(row.get("oc_year")),
                    "source_county_original": source_text(row.get("oc_county")),
                    "source_region_original": source_text(row.get("oc_region")),
                    "source_period": source_period, "source_file": source_file,
                })
        for crime_type in TARGET_CRIME_TYPES:
            quarter_available[(year, quarter, crime_type)] = crime_type in types_in_file
    annual_coverage: dict[tuple[int, str], str] = {}
    for year in YEARS:
        for crime_type in TARGET_CRIME_TYPES:
            present = sum(quarter_available.get((year, quarter, crime_type), False) for quarter in range(1, 5))
            annual_coverage[(year, crime_type)] = "complete" if present == 4 else ("unavailable" if present == 0 else "partial")
    incidents.sort(key=lambda row: (row["date"], row["county"], row["district"], row["crime_type"], row["source_period"], row["source_file"]))
    rejected.sort(key=lambda row: (row["source_period"], row["source_file"], int(row["source_line"] or 0), row["rejection_reason"]))
    return incidents, rejected, coverage_counts, annual_coverage, raw_source_rows


def resource_for_year(metadata: dict[str, Any], year: int, purpose: str) -> dict[str, Any] | None:
    candidates = [
        row for row in metadata.get("official_annual_crime", {}).get("resources", [])
        if int(row.get("statistics_year", 0)) == year and row.get("status") != "failed"
    ]
    if purpose == "residential":
        preferred = [row for row in candidates if "analysis" in str(row.get("filename", ""))]
        if preferred:
            return preferred[0]
    if purpose == "general":
        preferred = [row for row in candidates if "general" in str(row.get("filename", ""))]
        if preferred:
            return preferred[0]
    full = [row for row in candidates if "full" in str(row.get("filename", ""))]
    return full[0] if full else (candidates[0] if candidates else None)


def page_matches_category(text: str, crime_type: str, year: int) -> bool:
    if "Taichung City" not in text:
        return False
    if crime_type == "住宅竊盜":
        return f"Geographic Distribution of Residential Burglary by Month, {year}" in text
    lines = [line.strip() for line in text.splitlines()]
    matches = [line for line in lines if line.endswith(CATEGORY_MARKERS[crime_type])]
    if crime_type == "汽車竊盜":
        matches = [line for line in matches if "Larceny and" not in line]
    if crime_type == "強制性交":
        matches = [line for line in matches if "Joint" not in line]
    return bool(matches)


def county_count_from_page(text: str, english_name: str) -> int | None:
    lines = text.splitlines()
    known_names = sorted(COUNTY_ENGLISH.values(), key=len, reverse=True)
    for index, line in enumerate(lines):
        # Select the longest known county label on the row so that `Taipei City`
        # cannot accidentally match the `New Taipei City` row.
        matched_name = next((name for name in known_names if name in line), None)
        if matched_name != english_name:
            continue
        remainder = line.split(matched_name, 1)[1]
        if not remainder.strip() and index + 1 < len(lines):
            remainder = lines[index + 1]
        match = re.search(r"(?:^|\s)(-|\d[\d,]*)(?=\s|$)", remainder.strip())
        if match:
            token = match.group(1)
            return 0 if token == "-" else int(token.replace(",", ""))
    return None


def extract_official(
    metadata: dict[str, Any], counties: set[str], preliminary_index: dict[tuple[int, str, str], dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    values: dict[tuple[int, str, str], int] = {}
    evidence: dict[tuple[int, str], dict[str, Any]] = {}
    for year in YEARS:
        resources = {
            "general": resource_for_year(metadata, year, "general"),
            "residential": resource_for_year(metadata, year, "residential"),
        }
        readers: dict[str, PdfReader] = {}
        for purpose, resource in resources.items():
            if resource is None:
                continue
            filename = str(resource.get("filename") or resource.get("downloaded_filename") or "")
            path = RAW_OFFICIAL_DIR / filename
            if not path.is_file() or (resource.get("sha256") and sha256_file(path) != resource.get("sha256")):
                raise ValueError(f"official annual source missing or hash mismatch: {filename}")
            readers[purpose] = PdfReader(path)
        wanted = set(OFFICIAL_CRIME_TYPES)
        for purpose, reader in readers.items():
            scan_wanted = {"住宅竊盜"} if purpose == "residential" else wanted - {"住宅竊盜"}
            if resources["general"] == resources["residential"]:
                scan_wanted = wanted
            for page_index in range(min(len(reader.pages), 170)):
                if not scan_wanted:
                    break
                text = reader.pages[page_index].extract_text() or ""
                for crime_type in tuple(scan_wanted):
                    if not page_matches_category(text, crime_type, year):
                        continue
                    for county in counties:
                        value = county_count_from_page(text, COUNTY_ENGLISH[county])
                        if value is not None:
                            values[(year, county, crime_type)] = value
                    resource = resources[purpose]
                    assert resource is not None
                    evidence[(year, crime_type)] = {
                        "source_document": resource.get("dataset_report_name", ""),
                        "source_file": resource.get("filename", ""),
                        "source_note": f"當年發生件數 (current-year occurrences), PDF page {page_index + 1}; supplemental reports excluded.",
                    }
                    scan_wanted.remove(crime_type)
            if resources["general"] == resources["residential"]:
                break
    official_rows: list[dict[str, Any]] = []
    comparison_rows: list[dict[str, Any]] = []
    for year in YEARS:
        for county in sorted(counties):
            for crime_type in OFFICIAL_CRIME_TYPES:
                key = (year, county, crime_type)
                value = values.get(key)
                proof = evidence.get((year, crime_type), {})
                status = "official_final" if value is not None else "unavailable_unverified"
                official_rows.append({
                    "year": year, "county": county, "crime_type": crime_type,
                    "official_annual_count": "" if value is None else value, "statistics_status": status,
                    "source_document": proof.get("source_document", ""), "source_file": proof.get("source_file", ""),
                    "source_note": proof.get("source_note", "Value could not be verified automatically; no estimate was used."),
                    "statistics_layer": "official_annual_county", "official_statistics_label": OFFICIAL_STATISTICS_LABEL,
                })
                preliminary = preliminary_index[(year, county, crime_type)]
                preliminary_count = preliminary["dataset14200_source_total"] if preliminary["coverage_status"] != "unavailable" else ""
                difference: int | str = ""
                percent: str = ""
                if value is not None and preliminary_count != "":
                    difference = int(preliminary_count) - value
                    percent = decimal(difference / value * 100) if value else ""
                comparison_rows.append({
                    "year": year, "county": county, "crime_type": crime_type,
                    "dataset14200_preliminary_count": preliminary_count, "official_annual_count": "" if value is None else value,
                    "absolute_difference": difference, "percent_difference_vs_official": percent,
                    "comparison_status": "comparable" if value is not None else "official_unavailable_unverified",
                    "preliminary_statistics_label": DISTRICT_STATISTICS_LABEL,
                    "official_statistics_label": OFFICIAL_STATISTICS_LABEL,
                })
    return official_rows, comparison_rows


def validate_taichung(
    incidents: list[dict[str, Any]], rejected: list[dict[str, Any]], population_rows: list[dict[str, Any]],
    panel_rows: list[dict[str, Any]], preliminary_rows: list[dict[str, Any]],
) -> list[str]:
    errors: list[str] = []
    taichung_incidents = [row for row in incidents if row["county"] == "臺中市"]
    taichung_unassigned = [
        row for row in rejected
        if normalize(row["source_county_original"]) == "臺中市" and row["rejection_reason"] in {"blank_district", "unexpected_district", "geography_mismatch"}
    ]
    taichung_population = [row for row in population_rows if row["county"] == "臺中市"]
    taichung_panel = [row for row in panel_rows if row["county"] == "臺中市"]
    checks = [
        (len(taichung_incidents) == 31307, f"Taichung assigned expected 31307, found {len(taichung_incidents)}"),
        (len(taichung_unassigned) == 2913, f"Taichung unassigned expected 2913, found {len(taichung_unassigned)}"),
        (len({row['district'] for row in taichung_incidents}) == 29, "Taichung district count is not 29"),
        (len(taichung_population) == 290, f"Taichung population expected 290, found {len(taichung_population)}"),
        (len(taichung_panel) == 2320, f"Taichung panel expected 2320, found {len(taichung_panel)}"),
    ]
    prelim = {(int(row["year"]), row["crime_type"]): int(row["dataset14200_source_total"]) for row in preliminary_rows if row["county"] == "臺中市"}
    checks.extend([
        (prelim.get((2023, "住宅竊盜")) == 47, f"Taichung 2023 住宅竊盜 preliminary is {prelim.get((2023, '住宅竊盜'))}"),
        (prelim.get((2024, "住宅竊盜")) == 129, f"Taichung 2024 住宅竊盜 preliminary is {prelim.get((2024, '住宅竊盜'))}"),
    ])
    sex_zero = [row for row in taichung_panel if int(row["year"]) == 2019 and row["crime_type"] == "強制性交" and row["observation_status"] == "observed_zero" and str(row["incident_count"]) == "0"]
    checks.append((len(sex_zero) == 29, f"Taichung 2019 強制性交 observed-zero rows: {len(sex_zero)}"))
    motorcycle = next(row for row in preliminary_rows if int(row["year"]) == 2024 and row["county"] == "臺中市" and row["crime_type"] == "機車竊盜")
    checks.append((abs(float(motorcycle["district_assignment_rate"]) - 0.5) < 1e-12, f"Taichung 2024 機車竊盜 assignment rate: {motorcycle['district_assignment_rate']}"))
    old_incidents = read_csv(REPO_ROOT / "data" / "processed" / "taichung" / "taichung_crime_incidents_2016_2025.csv")
    old_counter = Counter((row["date"], row["district"], row["crime_type"], row["source_period"], row["source_file"]) for row in old_incidents)
    new_counter = Counter((row["date"], row["district"], row["crime_type"], row["source_period"], row["source_file"]) for row in taichung_incidents)
    checks.append((old_counter == new_counter, "Taichung incident multiset differs from the validated output"))
    old_population = read_csv(REPO_ROOT / "data" / "processed" / "taichung" / "taichung_population_by_district_2016_2025.csv")
    old_pop_index = {(int(row["year"]), row["district"]): int(row["population"]) for row in old_population}
    new_pop_index = {(int(row["year"]), row["district"]): int(row["population"]) for row in taichung_population}
    checks.append((old_pop_index == new_pop_index, "Taichung population keys/values differ from the validated output"))
    errors.extend(message for passed, message in checks if not passed)
    return errors


def make_report(
    admin_rows: list[dict[str, Any]], raw_source_rows: int, incidents: list[dict[str, Any]], rejected: list[dict[str, Any]],
    population_rows: list[dict[str, Any]], panel_rows: list[dict[str, Any]], coverage_rows: list[dict[str, Any]],
    official_rows: list[dict[str, Any]], taichung_errors: list[str],
) -> str:
    counties = sorted({row["county"] for row in admin_rows})
    reasons = Counter(row["rejection_reason"] for row in rejected)
    status_counts = Counter(row["observation_status"] for row in panel_rows)
    assigned = len(incidents)
    unassigned = sum(reasons[reason] for reason in ("blank_district", "unexpected_district", "geography_mismatch"))
    denominator = assigned + unassigned
    by_county: dict[str, tuple[int, int]] = {}
    for county in counties:
        rows = [row for row in coverage_rows if row["county"] == county]
        by_county[county] = (sum(int(row["district_assigned_records"]) for row in rows), sum(int(row["district_unassigned_records"]) for row in rows))
    by_type: dict[str, tuple[int, int]] = {}
    for crime_type in TARGET_CRIME_TYPES:
        rows = [row for row in coverage_rows if row["crime_type"] == crime_type]
        by_type[crime_type] = (sum(int(row["district_assigned_records"]) for row in rows), sum(int(row["district_unassigned_records"]) for row in rows))
    by_year: dict[int, tuple[int, int]] = {}
    for year in YEARS:
        rows = [row for row in coverage_rows if int(row["year"]) == year]
        by_year[year] = (sum(int(row["district_assigned_records"]) for row in rows), sum(int(row["district_unassigned_records"]) for row in rows))
    crime_keys = {(row["county"], row["district"]) for row in incidents}
    fully_matched = sum((row["county"], row["district"]) in crime_keys for row in admin_rows)
    worst = sorted(
        [row for row in coverage_rows if int(row["total_source_records"]) > 0],
        key=lambda row: (float(row["district_assignment_rate"]), -int(row["total_source_records"]), row["county"], int(row["year"]), row["crime_type"]),
    )[:20]
    verified = sum(row["statistics_status"] == "official_final" for row in official_rows)
    coverage_states = Counter((int(row["year"]), row["crime_type"], row["source_coverage_status"]) for row in panel_rows)
    annual_states = Counter()
    for year, crime_type, status in coverage_states:
        annual_states[status] += 1
    lines = [
        "# Taiwan nationwide crime data coverage (Phase 3B)", "",
        "## A. Administrative geography", "",
        f"- Counties/cities: {len(counties)} ({'、'.join(counties)}).",
        f"- Administrative units: {len(admin_rows)}.",
        "- Dataset 7441 geometry validation: PASS; county+district keys and town codes are unique, names/codes are nonblank, and every geometry is a valid Polygon or MultiPolygon within the official territorial coordinate extent.",
        "- Geometry was not simplified; the authoritative raw archive is unchanged.", "",
        "## B. Crime source", "",
        f"- Target period: {min(YEARS)}–{max(YEARS)}.",
        "- Source: 40 already-verified national quarterly resources from Dataset 14200; exact existing bytes were reused without redownload or relocation.",
        f"- Total national Dataset 14200 source rows: {raw_source_rows}.",
        f"- Valid district-assigned rows: {assigned}.",
        f"- District-unassigned rows: {unassigned}.",
        f"- All auditable rejected rows: {len(rejected)}.",
    ]
    lines.extend(f"- `{reason}`: {count}." for reason, count in sorted(reasons.items()))
    lines.extend([
        "- Legitimate duplicate-looking incident rows are preserved. No district/county imputation or incident-field deduplication was performed.", "",
        "## C. Assignment coverage", "",
        f"- National assignment rate: {assigned / denominator:.6%} ({assigned}/{denominator}).",
        "", "### By county/city", "", "| County/city | Assigned | Unassigned | Assignment rate |", "|---|---:|---:|---:|",
    ])
    for county, (a, u) in by_county.items():
        lines.append(f"| {county} | {a} | {u} | {a / (a + u):.6%} |" if a + u else f"| {county} | 0 | 0 | N/A |")
    lines.extend(["", "### By year", "", "| Year | Assigned | Unassigned | Assignment rate |", "|---:|---:|---:|---:|"])
    for year, (a, u) in by_year.items():
        lines.append(f"| {year} | {a} | {u} | {a / (a + u):.6%} |" if a + u else f"| {year} | 0 | 0 | N/A |")
    lines.extend(["", "### By crime type", "", "| Crime type | Assigned | Unassigned | Assignment rate |", "|---|---:|---:|---:|"])
    for crime_type, (a, u) in by_type.items():
        lines.append(f"| {crime_type} | {a} | {u} | {a / (a + u):.6%} |" if a + u else f"| {crime_type} | 0 | 0 | N/A |")
    lines.extend(["", "### Lowest county/year/crime assignment rates with source records", "", "| Year | County/city | Crime type | Source | Assigned | Unassigned | Rate |", "|---:|---|---|---:|---:|---:|---:|"])
    for row in worst:
        lines.append(f"| {row['year']} | {row['county']} | {row['crime_type']} | {row['total_source_records']} | {row['district_assigned_records']} | {row['district_unassigned_records']} | {float(row['district_assignment_rate']):.6%} |")
    lines.extend([
        "", "## D. Population", "",
        "- Source: 內政部戶政司 Dataset 8410 各鄉鎮市區人口密度.",
        f"- Dataset 8410 years: {min(YEARS)}–{max(YEARS)}.",
        f"- Population rows: {len(population_rows)} ({len(YEARS)} years × {len(admin_rows)} administrative units).",
        "- Missing population keys: 0; unmatched accepted population keys: 0. Values are positive; there is no interpolation or fuzzy matching.", "",
        "## E. Administrative crosswalk", "",
        f"- Fully matched geography ↔ population ↔ crime units: {fully_matched}/{len(admin_rows)}.",
        f"- Documented exceptions: {len(admin_rows) - fully_matched}.",
        f"- Unresolved units: {len(admin_rows) - fully_matched}.",
        "- Matching uses exact county+district keys after surrounding-whitespace cleanup and deterministic 台→臺 normalization; no fuzzy or spatial-nearest matching is used.", "",
        "## F. Crime-category coverage", "",
    ])
    for status in ("complete", "partial", "unavailable"):
        lines.append(f"- `{status}` year/category combinations: {annual_states[status]}.")
    for year in YEARS:
        organized = next(row["source_coverage_status"] for row in panel_rows if int(row["year"]) == year and row["crime_type"] == "組織犯罪防制條例")
        lines.append(f"- 組織犯罪防制條例 {year}: `{organized}`.")
    lines.extend([
        "", "## G. Official annual benchmark", "",
        f"- Verified county/year/category official annual values: {verified}/{len(official_rows)}.",
        f"- Unavailable or unverified values: {len(official_rows) - verified}.",
        "- Values remain an independent county/city final layer. They are never scaled or distributed to districts.", "",
        "## Observation semantics", "",
        f"- Analysis-panel rows: {len(panel_rows)}.",
    ])
    for status in ("observed_positive", "observed_zero", "partial_coverage", "unavailable"):
        lines.append(f"- `{status}`: {status_counts[status]}.")
    lines.extend([
        "", "## H. Taichung regression", "",
        "- Result: " + ("PASS" if not taichung_errors else "FAIL"),
        "- 31,307 assigned; 2,913 unassigned; 29 districts; 290 population rows; 2,320 analysis-panel rows.",
        "- 2023/2024 住宅竊盜 preliminary totals, 2019 強制性交 observed zeros, 2024 機車竊盜 assignment, incident multisets, and population keys/values were checked.",
    ])
    lines.extend(f"- Error: {error}" for error in taichung_errors)
    lines.extend(["", "No safety, danger, risk, or composite crime ranking is produced.", ""])
    return "\n".join(lines)


def run() -> int:
    errors: list[str] = []
    try:
        metadata = json.loads(METADATA_PATH.read_text(encoding="utf-8"))
        features, admin_rows = load_geography(metadata)
        population_rows = load_population(metadata, admin_rows)
        incidents, rejected, coverage_counts, annual_coverage, raw_source_rows = build_crime(metadata, admin_rows)
        admin_keys = {(row["county"], row["district"]) for row in admin_rows}
        counties = {row["county"] for row in admin_rows}
        population_index = {(int(row["year"]), row["county"], row["district"]): int(row["population"]) for row in population_rows}
        yearly_counts = Counter((int(row["year"]), row["county"], row["district"], row["crime_type"]) for row in incidents)

        coverage_rows: list[dict[str, Any]] = []
        preliminary_rows: list[dict[str, Any]] = []
        for year in YEARS:
            for county in sorted(counties):
                for crime_type in TARGET_CRIME_TYPES:
                    assigned = coverage_counts[(year, county, crime_type, "assigned")]
                    unassigned = coverage_counts[(year, county, crime_type, "unassigned")]
                    total = assigned + unassigned
                    status = annual_coverage[(year, crime_type)]
                    row = {
                        "year": year, "county": county, "crime_type": crime_type,
                        "total_source_records": total, "district_assigned_records": assigned,
                        "district_unassigned_records": unassigned, "district_assignment_rate": rate(assigned, total),
                        "coverage_status": status,
                    }
                    coverage_rows.append(row)
                    preliminary_rows.append({
                        "year": year, "county": county, "crime_type": crime_type,
                        "dataset14200_source_total": total, "district_assigned_records": assigned,
                        "district_unassigned_records": unassigned, "district_assignment_rate": rate(assigned, total),
                        "coverage_status": status, "statistics_layer": "preliminary_county",
                        "statistics_label": DISTRICT_STATISTICS_LABEL,
                    })
        preliminary_index = {(int(row["year"]), row["county"], row["crime_type"]): row for row in preliminary_rows}

        yearly_rows = [
            {"year": key[0], "county": key[1], "district": key[2], "crime_type": key[3], "incident_count": count}
            for key, count in sorted(yearly_counts.items())
        ]
        rates_rows: list[dict[str, Any]] = []
        for row in yearly_rows:
            population = population_index[(int(row["year"]), row["county"], row["district"])]
            rates_rows.append({
                **row, "population": population, "population_basis": POPULATION_BASIS,
                "incidents_per_100k_population": decimal(int(row["incident_count"]) / population * 100000),
            })

        panel_rows: list[dict[str, Any]] = []
        for year in YEARS:
            for admin in admin_rows:
                county, district = admin["county"], admin["district"]
                population = population_index[(year, county, district)]
                for crime_type in TARGET_CRIME_TYPES:
                    coverage = annual_coverage[(year, crime_type)]
                    count = yearly_counts[(year, county, district, crime_type)]
                    if coverage == "complete":
                        observation = "observed_positive" if count else "observed_zero"
                        incident_count: int | str = count
                        population_rate = decimal(count / population * 100000)
                    elif coverage == "partial":
                        observation, incident_count, population_rate = "partial_coverage", count, ""
                    else:
                        observation, incident_count, population_rate = "unavailable", "", ""
                    preliminary = preliminary_index[(year, county, crime_type)]
                    panel_rows.append({
                        "year": year, "county": county, "district": district, "crime_type": crime_type,
                        "incident_count": incident_count, "population": population, "population_basis": POPULATION_BASIS,
                        "incidents_per_100k_population": population_rate, "source_coverage_status": coverage,
                        "observation_status": observation,
                        "district_assignment_rate_county_year_type": preliminary["district_assignment_rate"],
                        "statistics_layer": "preliminary_district",
                    })

        crime_keys = {(row["county"], row["district"]) for row in incidents}
        crosswalk_rows = [{
            "county": row["county"], "district": row["district"], "county_code": row["county_code"],
            "town_code": row["town_code"], "population_match": "true", "crime_match": str((row["county"], row["district"]) in crime_keys).lower(),
            "match_status": "matched" if (row["county"], row["district"]) in crime_keys else "valid_zero_incident_unit",
            "notes": "Exact deterministic county+district match; only 台/臺 normalization applied.",
        } for row in admin_rows]

        official_rows, comparison_rows = extract_official(metadata, counties, preliminary_index)
        taichung_errors = validate_taichung(incidents, rejected, population_rows, panel_rows, preliminary_rows)
        errors.extend(taichung_errors)

        feature_collection = {
            "type": "FeatureCollection", "name": "taiwan_districts",
            "crs_note": "Official Dataset 7441 TWD97 geographic coordinates; not simplified.", "features": features,
        }
        GEOGRAPHY_DIR.mkdir(parents=True, exist_ok=True)
        GEOJSON_PATH.write_text(json.dumps(feature_collection, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
        write_csv(ADMIN_PATH, ["county", "district", "county_code", "town_code", "geometry_available"], admin_rows)
        write_csv(INCIDENTS_PATH, ["date", "year", "month", "day", "county", "district", "crime_type", "roc_year", "source_county_original", "source_region_original", "source_period", "source_file"], incidents)
        write_csv(REJECTED_PATH, ["crime_type", "roc_year", "oc_data", "source_county_original", "source_region_original", "source_period", "source_file", "source_line", "rejection_reason", "rejection_details"], rejected)
        write_csv(COVERAGE_PATH, ["year", "county", "crime_type", "total_source_records", "district_assigned_records", "district_unassigned_records", "district_assignment_rate", "coverage_status"], coverage_rows)
        write_csv(POPULATION_PATH, ["year", "county", "district", "population", "population_basis", "area", "population_density", "source_dataset_id", "source_file"], population_rows)
        write_csv(CROSSWALK_PATH, ["county", "district", "county_code", "town_code", "population_match", "crime_match", "match_status", "notes"], crosswalk_rows)
        write_csv(YEARLY_PATH, ["year", "county", "district", "crime_type", "incident_count"], yearly_rows)
        write_csv(RATES_PATH, ["year", "county", "district", "crime_type", "incident_count", "population", "population_basis", "incidents_per_100k_population"], rates_rows)
        write_csv(PANEL_PATH, ["year", "county", "district", "crime_type", "incident_count", "population", "population_basis", "incidents_per_100k_population", "source_coverage_status", "observation_status", "district_assignment_rate_county_year_type", "statistics_layer"], panel_rows)
        write_csv(PRELIMINARY_COUNTY_PATH, ["year", "county", "crime_type", "dataset14200_source_total", "district_assigned_records", "district_unassigned_records", "district_assignment_rate", "coverage_status", "statistics_layer", "statistics_label"], preliminary_rows)
        write_csv(OFFICIAL_PATH, ["year", "county", "crime_type", "official_annual_count", "statistics_status", "source_document", "source_file", "source_note", "statistics_layer", "official_statistics_label"], official_rows)
        write_csv(COMPARISON_PATH, ["year", "county", "crime_type", "dataset14200_preliminary_count", "official_annual_count", "absolute_difference", "percent_difference_vs_official", "comparison_status", "preliminary_statistics_label", "official_statistics_label"], comparison_rows)

        REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
        REPORT_PATH.write_text(make_report(admin_rows, raw_source_rows, incidents, rejected, population_rows, panel_rows, coverage_rows, official_rows, taichung_errors), encoding="utf-8")

        output_paths = [GEOJSON_PATH, ADMIN_PATH, INCIDENTS_PATH, REJECTED_PATH, COVERAGE_PATH, POPULATION_PATH, CROSSWALK_PATH, YEARLY_PATH, RATES_PATH, PANEL_PATH, PRELIMINARY_COUNTY_PATH, OFFICIAL_PATH, COMPARISON_PATH, REPORT_PATH]
        metadata["nationwide_processing"] = {
            "phase": "3B", "built_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "years": [min(YEARS), max(YEARS)], "county_count": len(counties), "administrative_unit_count": len(admin_rows),
            "crime_source_dataset_id": metadata.get("dataset_id", 14200),
            "crime_raw_directory_reused": "data/raw/taichung/npa_crime",
            "crime_raw_files_are_national": True, "crime_raw_resource_count": len(metadata.get("resources", [])),
            "population_source_dataset_id": metadata.get("population", {}).get("dataset_id", 8410),
            "population_raw_directory_reused": "data/raw/taichung/population",
            "boundary_source_dataset_id": metadata.get("geography", {}).get("dataset_id", 7441),
            "official_county_totals_distributed_to_districts": False,
            "normalization_rules": ["strip surrounding whitespace", "replace 台 with 臺"],
            "outputs": {
                str(path.relative_to(REPO_ROOT)).replace("\\", "/"): {"sha256": sha256_file(path), "file_size": path.stat().st_size}
                for path in output_paths
            },
        }
        METADATA_PATH.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

        expected_panel = len(YEARS) * len(admin_rows) * len(TARGET_CRIME_TYPES)
        if len(panel_rows) != expected_panel:
            errors.append(f"analysis panel expected {expected_panel}, found {len(panel_rows)}")
        if any(row["observation_status"] == "unavailable" and row["incident_count"] != "" for row in panel_rows):
            errors.append("unavailable panel row has a numeric incident count")
        if any(row["observation_status"] == "partial_coverage" and row["incidents_per_100k_population"] != "" for row in panel_rows):
            errors.append("partial panel row has a full-year rate")
        if sum(int(row["incident_count"]) for row in yearly_rows) != len(incidents):
            errors.append("national yearly totals do not reconcile with strict incidents")
        if any((row["county"], row["district"]) not in admin_keys for row in incidents):
            errors.append("accepted crime row lacks a geography match")
    except (OSError, ValueError, UnicodeError, zipfile.BadZipFile, shapefile.ShapefileException) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print(f"Built nationwide foundation: {len(counties)} counties/cities, {len(admin_rows)} units, {len(incidents)} assigned incidents, {len(panel_rows)} panel rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
