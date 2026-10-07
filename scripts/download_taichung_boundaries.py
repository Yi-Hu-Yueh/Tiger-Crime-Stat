#!/usr/bin/env python3
"""Download official Dataset 7441 township/district boundary source material."""

from __future__ import annotations

import hashlib
import json
import ssl
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


REPO_ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = REPO_ROOT / "data" / "raw" / "geography" / "town_boundaries"
METADATA_PATH = REPO_ROOT / "metadata" / "data_sources.json"
DATASET_ID = 7441
DATASET_TITLE = "鄉鎮市區界線(TWD97經緯度)"
PROVIDER = "內政部國土測繪中心"
SOURCE_PAGE = f"https://data.gov.tw/dataset/{DATASET_ID}"
METADATA_URL = f"https://data.gov.tw/api/v2/rest/dataset/{DATASET_ID}"
USER_AGENT = "Tiger-Crime-Stat/3.0 (+official-boundary-archiver; dataset 7441)"
TIMEOUT = (20, 300)


class DownloadError(RuntimeError):
    pass


class GovernmentTLSAdapter(HTTPAdapter):
    """Retain chain/hostname checks while relaxing OpenSSL's optional strict-SKI rule."""

    def init_poolmanager(self, connections: int, maxsize: int, block: bool = False, **pool_kwargs: Any) -> None:
        context = ssl.create_default_context()
        if hasattr(ssl, "VERIFY_X509_STRICT"):
            context.verify_flags &= ~ssl.VERIFY_X509_STRICT
        pool_kwargs["ssl_context"] = context
        super().init_poolmanager(connections, maxsize, block=block, **pool_kwargs)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_session() -> requests.Session:
    retry = Retry(
        total=4,
        connect=4,
        read=4,
        status=4,
        backoff_factor=0.8,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset({"GET"}),
        raise_on_status=False,
    )
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT, "Accept": "application/json,application/zip,*/*"})
    session.mount("https://", GovernmentTLSAdapter(max_retries=retry))
    session.mount("http://", HTTPAdapter(max_retries=retry))
    return session


def select_shapefile_resource(dataset: dict[str, Any]) -> dict[str, Any]:
    candidates = [
        item for item in dataset.get("distribution", [])
        if str(item.get("resourceFormat", "")).upper() in {"SHP", "ZIP"}
        and item.get("resourceDownloadUrl")
    ]
    shp = [item for item in candidates if str(item.get("resourceFormat", "")).upper() == "SHP"]
    if shp:
        return shp[0]
    if candidates:
        return candidates[0]
    raise DownloadError("Dataset 7441 metadata contains no downloadable SHP/ZIP resource")


def validate_zip(data: bytes, content_type: str | None) -> None:
    if len(data) < 1024:
        raise DownloadError(f"boundary response is too small ({len(data)} bytes)")
    if not data.startswith(b"PK"):
        raise DownloadError("boundary response is not a ZIP archive")
    if content_type and "html" in content_type.lower():
        raise DownloadError(f"unexpected HTML content type: {content_type}")


def run() -> int:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    session = build_session()
    try:
        metadata_response = session.get(METADATA_URL, timeout=TIMEOUT, allow_redirects=True)
        metadata_response.raise_for_status()
        payload = metadata_response.json()
        if not payload.get("success") or not isinstance(payload.get("result"), dict):
            raise DownloadError("Dataset 7441 metadata API returned malformed data")
        dataset = payload["result"]
        resource = select_shapefile_resource(dataset)
        resource_url = str(resource["resourceDownloadUrl"])
        response = session.get(resource_url, timeout=TIMEOUT, allow_redirects=True)
        response.raise_for_status()
        data = response.content
        validate_zip(data, response.headers.get("Content-Type"))
    except (requests.RequestException, ValueError, DownloadError) as exc:
        print(f"ERROR: unable to retrieve Dataset {DATASET_ID}: {exc}", file=sys.stderr)
        return 1

    filename = "town_boundaries_dataset_7441.zip"
    destination = RAW_DIR / filename
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

    metadata = json.loads(METADATA_PATH.read_text(encoding="utf-8")) if METADATA_PATH.is_file() else {}
    metadata["geography"] = {
        "dataset_id": DATASET_ID,
        "dataset_title": dataset.get("title", DATASET_TITLE),
        "provider": PROVIDER,
        "source_page": SOURCE_PAGE,
        "source_url": SOURCE_PAGE,
        "metadata_url": METADATA_URL,
        "metadata_retrieved_at": utc_now(),
        "coordinate_reference": "TWD97 geographic coordinates",
        "resources": [{
            "resource_name": resource.get("resourceDescription", ""),
            "resource_format": resource.get("resourceFormat", "SHP"),
            "resource_url": resource_url,
            "downloaded_filename": filename,
            "file_size": len(data),
            "sha256": digest,
            "retrieved_at": utc_now(),
            "final_url": response.url,
            "status": status,
            "notes": "Raw official archive preserved unchanged; Taichung extraction is a separate processed artifact.",
        }],
    }
    METADATA_PATH.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Boundary archive: {destination.relative_to(REPO_ROOT)} ({len(data)} bytes, {status})")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
