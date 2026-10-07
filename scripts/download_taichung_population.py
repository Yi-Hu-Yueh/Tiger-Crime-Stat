#!/usr/bin/env python3
"""Discover and download official MOI year-end district population files."""

from __future__ import annotations

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
RAW_DIR = REPO_ROOT / "data" / "raw" / "taichung" / "population"
METADATA_PATH = REPO_ROOT / "metadata" / "data_sources.json"
DATASET_ID = 8410
DATASET_TITLE = "各鄉鎮市區人口密度"
PROVIDER = "內政部戶政司"
SOURCE_PAGE = f"https://data.gov.tw/dataset/{DATASET_ID}"
METADATA_URL = f"https://data.gov.tw/api/v2/rest/dataset/{DATASET_ID}"
USER_AGENT = "Tiger-Crime-Stat/2.0 (+official-data-research; dataset 8410)"
TIMEOUT = (15, 90)
TARGET_ROC_YEARS = set(range(105, 115))
REQUIRED_COLUMNS = {"statistic_yyy", "site_id", "people_total", "area", "population_density"}
YEAR_RE = re.compile(r"^(?P<year>\d{3})年?各鄉鎮市區人口密度$")


class DownloadError(RuntimeError):
    pass


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


def decode_csv(data: bytes) -> tuple[str, str]:
    errors: list[str] = []
    for encoding in ("utf-8-sig", "utf-8", "cp950", "big5"):
        try:
            return data.decode(encoding), encoding
        except UnicodeDecodeError as exc:
            errors.append(f"{encoding}: {exc}")
    raise DownloadError("unsupported CSV encoding: " + "; ".join(errors))


def validate_csv_payload(data: bytes, content_type: str | None, roc_year: int) -> str:
    if not data:
        raise DownloadError("empty response")
    prefix = data[:1024].lstrip().lower()
    if prefix.startswith((b"<!doctype html", b"<html", b"<?xml")):
        raise DownloadError("response is HTML/XML rather than CSV")
    if content_type and "html" in content_type.lower():
        raise DownloadError(f"unexpected HTML content type: {content_type}")
    text, encoding = decode_csv(data)
    reader = csv.DictReader(io.StringIO(text, newline=""))
    fields = {str(value).strip().lstrip("\ufeff") for value in (reader.fieldnames or ())}
    missing = REQUIRED_COLUMNS - fields
    if missing:
        raise DownloadError(f"CSV missing required columns: {sorted(missing)}")
    taichung_rows = 0
    for row in reader:
        normalized = {str(key).strip().lstrip("\ufeff"): str(value or "").strip() for key, value in row.items()}
        if normalized.get("statistic_yyy") == str(roc_year) and normalized.get("site_id", "").startswith("臺中市"):
            taichung_rows += 1
    if taichung_rows != 29:
        raise DownloadError(f"expected 29 Taichung rows for ROC {roc_year}, found {taichung_rows}")
    return encoding


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def discover_resources(dataset: dict[str, Any]) -> tuple[dict[int, dict[str, Any]], list[dict[str, Any]]]:
    candidates: dict[int, list[dict[str, Any]]] = {}
    for resource in dataset.get("distribution", []):
        if str(resource.get("resourceFormat", "")).upper() != "CSV":
            continue
        match = YEAR_RE.match(str(resource.get("resourceDescription", "")).strip())
        if not match:
            continue
        year = int(match.group("year"))
        if year in TARGET_ROC_YEARS:
            candidates.setdefault(year, []).append(resource)
    selected: dict[int, dict[str, Any]] = {}
    duplicate_notes: list[dict[str, Any]] = []
    for year, choices in candidates.items():
        ordered = sorted(
            choices,
            key=lambda item: (str(item.get("resourceQualityCheckTime", "")), str(item.get("resourceDownloadUrl", ""))),
        )
        selected[year] = ordered[-1]
        if len(ordered) > 1:
            duplicate_notes.append({
                "year": year + 1911,
                "selection_rule": "latest resourceQualityCheckTime, then URL",
                "selected_url": ordered[-1].get("resourceDownloadUrl"),
                "other_urls": [item.get("resourceDownloadUrl") for item in ordered[:-1]],
            })
    return selected, duplicate_notes


def download_one(session: requests.Session, resource: dict[str, Any], roc_year: int) -> dict[str, Any]:
    year = roc_year + 1911
    url = str(resource.get("resourceDownloadUrl", ""))
    filename = f"population_density_{roc_year}.csv"
    destination = RAW_DIR / filename
    base = {
        "dataset_id": DATASET_ID,
        "dataset_title": DATASET_TITLE,
        "provider": PROVIDER,
        "source_page": SOURCE_PAGE,
        "resource_url": url,
        "resource_name": resource.get("resourceDescription", ""),
        "year": year,
        "roc_year": roc_year,
        "downloaded_filename": filename,
    }
    try:
        if not url:
            raise DownloadError("resource has no download URL")
        response = session.get(url, timeout=TIMEOUT, allow_redirects=True)
        response.raise_for_status()
        data = response.content
        encoding = validate_csv_payload(data, response.headers.get("Content-Type"), roc_year)
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
            "file_size": len(data),
            "sha256": digest,
            "downloaded_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "status": status,
            "detected_encoding": encoding,
            "final_url": response.url,
            "resource_quality_check_time": resource.get("resourceQualityCheckTime"),
        }
    except (requests.RequestException, OSError, DownloadError) as exc:
        return {
            **base,
            "file_size": None,
            "sha256": None,
            "downloaded_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "status": "failed",
            "error": str(exc),
        }


def run() -> int:
    if not METADATA_PATH.is_file():
        print("ERROR: crime provenance metadata is missing; run the Phase 1 downloader first", file=sys.stderr)
        return 1
    RAW_DIR.mkdir(parents=True, exist_ok=True)
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

    discovered, duplicate_notes = discover_resources(dataset)
    records = [download_one(session, discovered[year], year) for year in sorted(discovered)]
    available_years = {item["roc_year"] for item in records if item["status"] != "failed"}
    missing_roc_years = sorted(TARGET_ROC_YEARS - available_years)
    metadata = json.loads(METADATA_PATH.read_text(encoding="utf-8"))
    metadata["population"] = {
        "dataset_id": DATASET_ID,
        "dataset_title": dataset.get("title", DATASET_TITLE),
        "provider": PROVIDER,
        "source_page": SOURCE_PAGE,
        "metadata_url": METADATA_URL,
        "metadata_retrieved_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "population_basis": "year_end_registered_population",
        "target_years": list(range(2016, 2026)),
        "duplicate_resource_notes": duplicate_notes,
        "missing_years": [year + 1911 for year in missing_roc_years],
        "resources": records,
    }
    METADATA_PATH.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    failures = [item for item in records if item["status"] == "failed"]
    print(f"Discovered population resources for {len(discovered)} target years; available locally: {len(available_years)}/10")
    print(f"Metadata: {METADATA_PATH.relative_to(REPO_ROOT)}")
    if missing_roc_years or failures:
        for year in missing_roc_years:
            print(f"ERROR: no usable official resource for ROC year {year}", file=sys.stderr)
        for failure in failures:
            print(f"ERROR: {failure['year']}: {failure.get('error')}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
