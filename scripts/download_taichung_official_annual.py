#!/usr/bin/env python3
"""Download authoritative CIB annual crime-statistics publications for 2016-2025."""

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
RAW_DIR = REPO_ROOT / "data" / "raw" / "taichung" / "official_annual_crime"
METADATA_PATH = REPO_ROOT / "metadata" / "data_sources.json"
SOURCE_AGENCY = "內政部警政署刑事警察局"
SOURCE_PAGE = "https://www.cib.npa.gov.tw/ch/app/data/list?id=2053&module=wg136"
RESOURCE_BASE = "https://www.cib.npa.gov.tw/ch/app/data/doc?module=wg136&detailNo={detail_no}&type=s"
USER_AGENT = "Mozilla/5.0 (compatible; Tiger-Crime-Stat/2.0; official-statistics-archiver)"
TIMEOUT = (20, 180)

# The CIB index is the authoritative catalogue. 2017 is the only target year
# published as separate parts rather than as one full-book attachment.
PUBLICATIONS: tuple[dict[str, Any], ...] = (
    {"year": 2016, "detail_no": "793031589478035456", "part": "full", "title": "105年中華民國刑案統計（全書）"},
    {"year": 2017, "detail_no": "793032150680104960", "part": "general", "title": "106年中華民國刑案統計第二部分：各類刑案發生與破獲統計"},
    {"year": 2017, "detail_no": "793032944670240768", "part": "analysis", "title": "106年中華民國刑案統計第二部分：各類刑案分析統計"},
    {"year": 2018, "detail_no": "793291703015469056", "part": "full", "title": "107年中華民國刑案統計（全書）"},
    {"year": 2019, "detail_no": "793294146201743360", "part": "full", "title": "108年中華民國刑案統計（全書）"},
    {"year": 2020, "detail_no": "936180613960962048", "part": "full", "title": "109年中華民國刑案統計（全書）"},
    {"year": 2021, "detail_no": "1009309648622194688", "part": "full", "title": "110年中華民國刑案統計（全書）"},
    {"year": 2022, "detail_no": "1145614305056526336", "part": "full", "title": "111年中華民國刑案統計（全書）"},
    {"year": 2023, "detail_no": "1260800007716474880", "part": "full", "title": "112年中華民國刑案統計（全書）"},
    {"year": 2024, "detail_no": "1419976006046846976", "part": "full", "title": "113年中華民國刑案統計（全書）"},
    {"year": 2025, "detail_no": "1545229914905513984", "part": "full", "title": "114年中華民國刑案統計（全書）"},
)


class DownloadError(RuntimeError):
    pass


class GovernmentTLSAdapter(HTTPAdapter):
    """Keep normal TLS verification while relaxing OpenSSL's optional strict-SKI check."""

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
        backoff_factor=1.0,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset({"GET"}),
        raise_on_status=False,
    )
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT, "Accept": "application/pdf,text/html;q=0.8,*/*;q=0.5"})
    session.mount("https://", GovernmentTLSAdapter(max_retries=retry))
    session.mount("http://", HTTPAdapter(max_retries=retry))
    return session


def validate_pdf(data: bytes, content_type: str | None) -> None:
    if len(data) < 1024:
        raise DownloadError(f"response is too small to be an annual publication ({len(data)} bytes)")
    if not data.startswith(b"%PDF-"):
        raise DownloadError("response does not have a PDF signature")
    if content_type and "pdf" not in content_type.lower() and "octet-stream" not in content_type.lower():
        raise DownloadError(f"unexpected content type: {content_type}")


def download_one(session: requests.Session, publication: dict[str, Any]) -> dict[str, Any]:
    year = int(publication["year"])
    part = str(publication["part"])
    filename = f"cib_crime_statistics_{year}_{part}.pdf"
    destination = RAW_DIR / filename
    resource_url = RESOURCE_BASE.format(detail_no=publication["detail_no"])
    base = {
        "dataset_report_name": publication["title"],
        "source_agency": SOURCE_AGENCY,
        "publication_year": year + 1,
        "statistics_year": year,
        "source_page": SOURCE_PAGE,
        "source_url": SOURCE_PAGE,
        "resource_download_url": resource_url,
        "filename": filename,
        "downloaded_filename": filename,
        "source_type": "official annual criminal statistics publication",
        "final_annual_statistics": True,
        "notes": "Authoritative CIB annual publication; 2017 was published in separate relevant sections." if year == 2017 else "Authoritative CIB annual full-book publication.",
    }
    try:
        if destination.exists():
            data = destination.read_bytes()
            validate_pdf(data, "application/pdf")
            return {
                **base,
                "file_size": len(data),
                "sha256": sha256_bytes(data),
                "retrieved_at": utc_now(),
                "final_url": resource_url,
                "status": "existing_verified",
            }
        response = session.get(
            resource_url,
            headers={"Referer": SOURCE_PAGE},
            timeout=TIMEOUT,
            allow_redirects=True,
        )
        response.raise_for_status()
        data = response.content
        validate_pdf(data, response.headers.get("Content-Type"))
        digest = sha256_bytes(data)
        status = "downloaded"
        if destination.exists():
            existing_digest = sha256_file(destination)
            if existing_digest == digest:
                status = "existing_identical"
            else:
                preserved = destination.with_name(
                    f"{destination.stem}.previous-{existing_digest[:12]}{destination.suffix}"
                )
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
            "retrieved_at": utc_now(),
            "final_url": response.url,
            "status": status,
        }
    except (requests.RequestException, OSError, DownloadError) as exc:
        return {
            **base,
            "file_size": None,
            "sha256": None,
            "retrieved_at": utc_now(),
            "status": "failed",
            "error": str(exc),
        }


def run() -> int:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    metadata = json.loads(METADATA_PATH.read_text(encoding="utf-8")) if METADATA_PATH.is_file() else {}
    session = build_session()
    # The CIB attachment endpoint requires a browsing session and same-site referrer.
    try:
        landing = session.get(SOURCE_PAGE, timeout=TIMEOUT, allow_redirects=True)
        landing.raise_for_status()
    except requests.RequestException as exc:
        print(f"ERROR: unable to open official CIB catalogue: {exc}", file=sys.stderr)
        return 1
    resources = [download_one(session, publication) for publication in PUBLICATIONS]
    failures = [resource for resource in resources if resource["status"] == "failed"]
    metadata["official_annual_crime"] = {
        "dataset_report_name": "中華民國刑案統計（105年至114年）",
        "source_agency": SOURCE_AGENCY,
        "source_page": SOURCE_PAGE,
        "source_url": SOURCE_PAGE,
        "source_type": "official annual criminal statistics publications",
        "target_statistics_years": list(range(2016, 2026)),
        "retrieved_at": utc_now(),
        "final_annual_statistics": True,
        "notes": "Final annual city statistics are kept separate from Dataset 14200 preliminary quarterly incidents.",
        "resources": resources,
    }
    METADATA_PATH.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Official annual publications available locally: {len(resources) - len(failures)}/{len(resources)}")
    print(f"Metadata: {METADATA_PATH.relative_to(REPO_ROOT)}")
    for failure in failures:
        print(f"ERROR: {failure['statistics_year']} {failure['filename']}: {failure.get('error')}", file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(run())
