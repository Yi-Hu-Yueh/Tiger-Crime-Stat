#!/usr/bin/env python3
"""Discover and download NPA Dataset 14200 quarterly crime CSV files."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


REPO_ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = REPO_ROOT / "data" / "raw" / "taichung" / "npa_crime"
METADATA_PATH = REPO_ROOT / "metadata" / "data_sources.json"
DATASET_ID = 14200
DATASET_TITLE = "犯罪資料"
PROVIDER = "內政部警政署"
SOURCE_PAGE = f"https://data.gov.tw/dataset/{DATASET_ID}"
METADATA_URL = f"https://data.gov.tw/api/v2/rest/dataset/{DATASET_ID}"
USER_AGENT = "Tiger-Crime-Stat/1.0 (+official-data-research; dataset 14200)"
TIMEOUT = (15, 90)
TARGET_ROC_YEARS = range(105, 115)
QUARTERS = (("01", "03"), ("04", "06"), ("07", "09"), ("10", "12"))
PERIOD_RE = re.compile(
    r"(?P<year>\d{3})(?P<start>\d{2})\s*[-－~～至]\s*(?:(?P<year2>\d{3}))?(?P<end>\d{2}).*犯罪資料"
)
REQUIRED_COLUMNS = {"type", "oc_year", "oc_data", "oc_county", "oc_region"}


class DownloadError(RuntimeError):
    pass


def expected_periods() -> list[str]:
    return [f"{year}{start}-{year}{end}" for year in TARGET_ROC_YEARS for start, end in QUARTERS]


def build_session() -> requests.Session:
    retry = Retry(
        total=3,
        connect=3,
        read=3,
        status=3,
        backoff_factor=0.8,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset({"GET"}),
        raise_on_status=False,
    )
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT, "Accept": "application/json,text/csv,text/plain,*/*"})
    session.mount("https://", HTTPAdapter(max_retries=retry))
    session.mount("http://", HTTPAdapter(max_retries=retry))
    return session


def parse_period(name: str) -> tuple[str, str, str] | None:
    match = PERIOD_RE.search(name.strip())
    if not match:
        return None
    year, year2, start, end = match.group("year", "year2", "start", "end")
    if year2 and year2 != year:
        return None
    if int(year) not in TARGET_ROC_YEARS or (start, end) not in QUARTERS:
        return None
    return f"{year}{start}-{year}{end}", year, f"{start}-{end}"


def decode_csv(data: bytes) -> tuple[str, str]:
    errors: list[str] = []
    for encoding in ("utf-8-sig", "utf-8", "cp950", "big5"):
        try:
            return data.decode(encoding), encoding
        except UnicodeDecodeError as exc:
            errors.append(f"{encoding}: {exc}")
    raise DownloadError("CSV encoding is unsupported: " + "; ".join(errors))


def validate_csv_payload(data: bytes, content_type: str | None) -> str:
    if not data:
        raise DownloadError("empty response")
    prefix = data[:1024].lstrip().lower()
    if prefix.startswith((b"<!doctype html", b"<html", b"<?xml")):
        raise DownloadError("response is an HTML/XML error page, not CSV")
    if content_type and "html" in content_type.lower():
        raise DownloadError(f"unexpected HTML content type: {content_type}")
    text, encoding = decode_csv(data)
    reader = csv.reader(io.StringIO(text, newline=""))
    try:
        header = next(reader)
        next(reader)
    except StopIteration as exc:
        raise DownloadError("CSV has no data rows") from exc
    normalized = {cell.strip().lstrip("\ufeff") for cell in header}
    if not REQUIRED_COLUMNS.issubset(normalized):
        raise DownloadError(f"CSV header is missing required columns: {sorted(REQUIRED_COLUMNS - normalized)}")
    return encoding


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def discover_resources(dataset: dict[str, Any]) -> tuple[dict[str, dict[str, Any]], list[str]]:
    found: dict[str, dict[str, Any]] = {}
    problems: list[str] = []
    for resource in dataset.get("distribution", []):
        name = str(resource.get("resourceDescription", ""))
        parsed = parse_period(name)
        if not parsed:
            continue
        period, _, _ = parsed
        url = resource.get("resourceDownloadUrl")
        if not url:
            problems.append(f"{period}: resource has no download URL")
            continue
        if period in found:
            problems.append(f"{period}: duplicate resource metadata")
            continue
        found[period] = resource
    missing = sorted(set(expected_periods()) - set(found))
    problems.extend(f"{period}: no resource discovered" for period in missing)
    return found, problems


def coverage_dates(period: str) -> tuple[str, str]:
    match = re.fullmatch(r"(\d{3})(\d{2})-(\d{3})(\d{2})", period)
    if not match:
        raise ValueError(period)
    roc_year, start_month, _, end_month = match.groups()
    year = int(roc_year) + 1911
    end_day = {"03": 31, "06": 30, "09": 30, "12": 31}[end_month]
    return f"{year}-{start_month}-01", f"{year}-{end_month}-{end_day:02d}"


def download_one(session: requests.Session, resource: dict[str, Any], period: str) -> dict[str, Any]:
    url = str(resource["resourceDownloadUrl"])
    start, end = coverage_dates(period)
    roc_year = period[:3]
    start_month, end_month = period[3:5], period[-2:]
    filename = f"npa_crime_{roc_year}_{start_month}_{end_month}.csv"
    destination = RAW_DIR / filename
    base = {
        "dataset_id": DATASET_ID,
        "dataset_title": DATASET_TITLE,
        "provider": PROVIDER,
        "source_page": SOURCE_PAGE,
        "resource_name": resource.get("resourceDescription", ""),
        "resource_url": url,
        "source_period": period,
        "downloaded_filename": filename,
        "coverage_start": start,
        "coverage_end": end,
    }
    try:
        response = session.get(url, timeout=TIMEOUT, allow_redirects=True)
        response.raise_for_status()
        data = response.content
        encoding = validate_csv_payload(data, response.headers.get("Content-Type"))
        digest = sha256_bytes(data)
        status = "downloaded"
        if destination.exists():
            existing_digest = sha256_file(destination)
            if existing_digest == digest:
                status = "existing_identical"
            else:
                preserved = destination.with_name(f"{destination.stem}.previous-{existing_digest[:12]}{destination.suffix}")
                if not preserved.exists():
                    destination.replace(preserved)
                destination.write_bytes(data)
                status = "updated_preserved_previous"
        else:
            destination.write_bytes(data)
        return {
            **base,
            "sha256": digest,
            "downloaded_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "file_size": len(data),
            "status": status,
            "detected_encoding": encoding,
            "final_url": response.url,
        }
    except (requests.RequestException, OSError, DownloadError) as exc:
        return {
            **base,
            "sha256": None,
            "downloaded_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "file_size": None,
            "status": "failed",
            "error": str(exc),
        }


def run() -> int:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    METADATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    session = build_session()
    try:
        response = session.get(METADATA_URL, timeout=TIMEOUT, allow_redirects=True)
        response.raise_for_status()
        payload = response.json()
        if not payload.get("success") or not isinstance(payload.get("result"), dict):
            raise DownloadError("metadata API returned an unsuccessful or malformed response")
        dataset = payload["result"]
    except (requests.RequestException, ValueError, DownloadError) as exc:
        print(f"ERROR: unable to retrieve Dataset {DATASET_ID} metadata: {exc}", file=sys.stderr)
        return 1

    resources, discovery_problems = discover_resources(dataset)
    records = [download_one(session, resources[p], p) for p in expected_periods() if p in resources]
    downloaded_periods = {item["source_period"] for item in records if item["status"] != "failed"}
    missing_periods = sorted(set(expected_periods()) - downloaded_periods)
    document = {
        "dataset_id": DATASET_ID,
        "dataset_title": dataset.get("title", DATASET_TITLE),
        "provider": PROVIDER,
        "source_page": SOURCE_PAGE,
        "metadata_url": METADATA_URL,
        "metadata_retrieved_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "target_coverage": {"start": "2016-01-01", "end": "2025-12-31", "expected_quarters": 40},
        "discovery_problems": discovery_problems,
        "missing_periods": missing_periods,
        "resources": records,
    }
    # Phase 2A adds population provenance to the same file. Preserve that independent
    # section when the Phase 1 crime downloader is rerun.
    if METADATA_PATH.is_file():
        try:
            existing_metadata = json.loads(METADATA_PATH.read_text(encoding="utf-8"))
            if isinstance(existing_metadata.get("population"), dict):
                document["population"] = existing_metadata["population"]
            if isinstance(existing_metadata.get("official_annual_crime"), dict):
                document["official_annual_crime"] = existing_metadata["official_annual_crime"]
            if isinstance(existing_metadata.get("statistical_semantics"), dict):
                document["statistical_semantics"] = existing_metadata["statistical_semantics"]
            if isinstance(existing_metadata.get("geography"), dict):
                document["geography"] = existing_metadata["geography"]
        except (OSError, ValueError):
            pass
    METADATA_PATH.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    failures = [item for item in records if item["status"] == "failed"]
    print(f"Discovered {len(resources)} target resources; available locally: {len(downloaded_periods)}/40")
    print(f"Metadata: {METADATA_PATH.relative_to(REPO_ROOT)}")
    if discovery_problems or failures or missing_periods:
        for problem in discovery_problems:
            print(f"ERROR: {problem}", file=sys.stderr)
        for failure in failures:
            print(f"ERROR: {failure['source_period']}: {failure.get('error')}", file=sys.stderr)
        return 1
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    raise SystemExit(run())


if __name__ == "__main__":
    main()
