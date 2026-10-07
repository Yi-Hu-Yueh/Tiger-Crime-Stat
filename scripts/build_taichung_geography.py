#!/usr/bin/env python3
"""Extract and validate Taichung's 29 districts from official Dataset 7441."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import sys
import zipfile
from pathlib import Path
from typing import Any, Iterable

import shapefile


REPO_ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = REPO_ROOT / "data" / "raw" / "geography" / "town_boundaries"
PROCESSED_DIR = REPO_ROOT / "data" / "processed" / "geography"
OUTPUT_PATH = PROCESSED_DIR / "taichung_districts.geojson"
PANEL_PATH = REPO_ROOT / "data" / "processed" / "taichung" / "taichung_crime_analysis_panel.csv"
METADATA_PATH = REPO_ROOT / "metadata" / "data_sources.json"
EXPECTED_COUNTY = "臺中市"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalize_known_tai_variant(value: str) -> str:
    return value.strip().replace("台", "臺")


def statistical_districts() -> set[str]:
    with PANEL_PATH.open("r", encoding="utf-8-sig", newline="") as handle:
        return {str(row["district"]).strip() for row in csv.DictReader(handle)}


def find_main_shapefile(archive: zipfile.ZipFile) -> tuple[str, str, str]:
    names = archive.namelist()
    shapefiles = [name for name in names if name.lower().endswith(".shp") and "town_moi" in name.lower()]
    if len(shapefiles) != 1:
        raise ValueError(f"expected one TOWN_MOI shapefile, found {shapefiles}")
    shp = shapefiles[0]
    stem = shp[:-4]
    shx = next((name for name in names if name.lower() == (stem + ".shx").lower()), "")
    dbf = next((name for name in names if name.lower() == (stem + ".dbf").lower()), "")
    if not shx or not dbf:
        raise ValueError("official archive is missing SHP companion files")
    return shp, shx, dbf


def iter_positions(value: Any) -> Iterable[tuple[float, float]]:
    if isinstance(value, (list, tuple)) and len(value) >= 2 and all(isinstance(item, (int, float)) for item in value[:2]):
        yield float(value[0]), float(value[1])
        return
    if isinstance(value, (list, tuple)):
        for item in value:
            yield from iter_positions(item)


def validate_geometry(geometry: dict[str, Any], district: str) -> None:
    if geometry.get("type") not in {"Polygon", "MultiPolygon"}:
        raise ValueError(f"{district}: unexpected geometry type {geometry.get('type')}")
    positions = list(iter_positions(geometry.get("coordinates", [])))
    if len(positions) < 4:
        raise ValueError(f"{district}: geometry contains too few positions")
    if not all(118 <= lon <= 123 and 20 <= lat <= 27 for lon, lat in positions):
        raise ValueError(f"{district}: geometry coordinates fall outside Taiwan bounds")


def run() -> int:
    errors: list[str] = []
    metadata = json.loads(METADATA_PATH.read_text(encoding="utf-8"))
    geography = metadata.get("geography", {})
    resources = geography.get("resources", [])
    if len(resources) != 1:
        print("ERROR: Dataset 7441 provenance is missing; run scripts/download_taichung_boundaries.py", file=sys.stderr)
        return 1
    resource = resources[0]
    archive_path = RAW_DIR / str(resource.get("downloaded_filename", ""))
    if not archive_path.is_file():
        print(f"ERROR: boundary archive is missing: {archive_path}", file=sys.stderr)
        return 1
    if sha256_file(archive_path) != resource.get("sha256"):
        print("ERROR: boundary archive SHA-256 does not match metadata", file=sys.stderr)
        return 1

    try:
        with zipfile.ZipFile(archive_path) as archive:
            shp_name, shx_name, dbf_name = find_main_shapefile(archive)
            reader = shapefile.Reader(
                shp=io.BytesIO(archive.read(shp_name)),
                shx=io.BytesIO(archive.read(shx_name)),
                dbf=io.BytesIO(archive.read(dbf_name)),
                encoding="utf-8",
            )
            field_names = [field[0] for field in reader.fields[1:]]
            required = {"TOWNID", "TOWNCODE", "COUNTYNAME", "TOWNNAME", "TOWNENG", "COUNTYID", "COUNTYCODE"}
            if not required <= set(field_names):
                raise ValueError(f"official DBF is missing fields: {sorted(required - set(field_names))}")
            features: list[dict[str, Any]] = []
            town_codes: set[str] = set()
            for shape_record in reader.iterShapeRecords():
                record = shape_record.record.as_dict()
                county = normalize_known_tai_variant(str(record["COUNTYNAME"]))
                if county != EXPECTED_COUNTY:
                    continue
                district = normalize_known_tai_variant(str(record["TOWNNAME"]))
                town_code = str(record["TOWNCODE"]).strip()
                if town_code in town_codes:
                    errors.append(f"duplicate TOWNCODE: {town_code}")
                    continue
                town_codes.add(town_code)
                geometry_value = dict(shape_record.shape.__geo_interface__)
                validate_geometry(geometry_value, district)
                features.append({
                    "type": "Feature",
                    "properties": {"district": district, "town_code": town_code, "county": county},
                    "geometry": geometry_value,
                })
    except (OSError, ValueError, zipfile.BadZipFile, shapefile.ShapefileException) as exc:
        print(f"ERROR: unable to process official boundaries: {exc}", file=sys.stderr)
        return 1

    features.sort(key=lambda feature: feature["properties"]["town_code"])
    geography_districts = {feature["properties"]["district"] for feature in features}
    stats_districts = statistical_districts()
    if len(features) != 29:
        errors.append(f"expected 29 Taichung features, found {len(features)}")
    if len(geography_districts) != len(features):
        errors.append("duplicate boundary district name")
    if geography_districts != stats_districts:
        errors.append(f"district mismatch; missing geography={sorted(stats_districts - geography_districts)}, unexpected geography={sorted(geography_districts - stats_districts)}")
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1

    feature_collection = {
        "type": "FeatureCollection",
        "name": "taichung_districts",
        "crs_note": "Official Dataset 7441 TWD97 geographic coordinates; not simplified.",
        "features": features,
    }
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(feature_collection, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    geography["processed"] = {
        "filename": str(OUTPUT_PATH.relative_to(REPO_ROOT)).replace("\\", "/"),
        "feature_count": len(features),
        "district_count": len(geography_districts),
        "sha256": sha256_file(OUTPUT_PATH),
        "file_size": OUTPUT_PATH.stat().st_size,
        "properties": ["district", "town_code", "county"],
        "geometry_simplified": False,
        "district_match": "exact_1_to_1",
        "source_archive": archive_path.name,
    }
    metadata["geography"] = geography
    METADATA_PATH.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(features)} exact-matched Taichung district features to {OUTPUT_PATH.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
