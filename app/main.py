from __future__ import annotations

from typing import Literal
from contextlib import asynccontextmanager

from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.services.data_service import REPO_ROOT, service
from app.services.llm_service import ChatError, ChatRequest, llm_service


STATIC_DIR = REPO_ROOT / "app" / "static"


@asynccontextmanager
async def lifespan(_app: FastAPI):
    async with llm_service:
        yield


app = FastAPI(
    title="臺灣犯罪統計",
    description="2016–2025｜22 縣市與 368 行政區；行政區資料為警政署季度初步案件資料。",
    version="3.4.0",
    lifespan=lifespan,
)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.post("/api/chat")
async def chat(
    request: ChatRequest,
    x_nvidia_api_key: str | None = Header(
        default=None,
        alias="X-NVIDIA-API-Key",
    ),
    x_nvidia_model: str | None = Header(
        default=None,
        alias="X-NVIDIA-Model",
    ),
) -> dict:
    try:
        return await llm_service.chat(request, api_key=x_nvidia_api_key, model_name=x_nvidia_model)
    except ChatError as exc:
        body = {"detail": str(exc)}
        if exc.diagnostics is not None:
            body["diagnostics"] = exc.diagnostics
        return JSONResponse(status_code=exc.status, content=body)


def not_found(exc: KeyError) -> HTTPException:
    return HTTPException(status_code=404, detail=str(exc).strip("'"))


def crime_query(crime_types: str | None, crime_type: str | None) -> str:
    if crime_types is not None:
        return crime_types
    if crime_type is not None:
        return crime_type
    raise KeyError("crime_types must contain at least one crime type")


@app.get("/", include_in_schema=False)
def root() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html", media_type="text/html")


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "ready": True,
        "application": "Tiger-Crime-Stat Phase 3D",
        "llm": llm_service.model_metadata(),
        "data": {
            "years": len(service.years),
            "districts": len(service.districts),
            "crime_types": len(service.crime_types),
            "panel_rows": len(service.panel_rows),
            "geography_features": len(service.geography["features"]),
        },
    }


@app.get("/api/meta")
def meta() -> dict:
    return service.meta()


@app.get("/api/context/events")
def context_events(county: str | None = None, year: int | None = None) -> dict:
    if year is not None and year not in service.years:
        raise HTTPException(status_code=404, detail=f"year must be one of {service.years}")
    if county is not None and county not in service.counties:
        raise HTTPException(status_code=404, detail=f"unknown county: {county}")
    return {
        "events": service.context.events(county=county, year=year),
        "context_disclaimer": "事件時間重疊僅供背景解讀，不代表該事件造成犯罪數據變化。",
    }


@app.get("/api/geography")
def geography() -> dict:
    return service.geography


@app.get("/api/map")
def map_data(
    year: int = Query(...),
    crime_type: str = Query(...),
    metric: Literal["count", "rate"] = Query(...),
) -> dict:
    try:
        return service.map_data(year, crime_type, metric)
    except KeyError as exc:
        raise not_found(exc) from exc


@app.get("/api/district/{district}/trend")
def district_trend(district: str, crime_type: str = Query(...)) -> dict:
    try:
        return service.district_trend(district, crime_type)
    except KeyError as exc:
        raise not_found(exc) from exc


@app.get("/api/district/{district}/summary")
def district_summary(district: str) -> dict:
    try:
        return service.district_summary(district)
    except KeyError as exc:
        raise not_found(exc) from exc


@app.get("/api/city/official")
def city_official(year: int | None = None, crime_type: str | None = None) -> dict:
    try:
        return service.official_data(year, crime_type)
    except KeyError as exc:
        raise not_found(exc) from exc


@app.get("/api/counties")
def counties() -> dict:
    return service.counties_data()


@app.get("/api/scope/geography")
def scope_geography(counties: str = Query(...)) -> dict:
    try:
        return service.scope_geography(counties)
    except KeyError as exc:
        raise not_found(exc) from exc


@app.get("/api/scope/map")
def scope_map(
    counties: str = Query(...),
    years: str = Query(...),
    months: str = Query("1,2,3,4,5,6,7,8,9,10,11,12"),
    crime_types: str | None = Query(None),
    crime_type: str | None = Query(None),
    metric: Literal["count", "rate"] = Query(...),
) -> dict:
    try:
        return service.scope_map_data(counties, years, months, crime_query(crime_types, crime_type), metric)
    except KeyError as exc:
        raise not_found(exc) from exc


@app.get("/api/scope/trends")
def scope_trends(
    counties: str = Query(...),
    crime_types: str | None = Query(None),
    crime_type: str | None = Query(None),
) -> dict:
    try:
        return service.scope_district_trends(counties, crime_query(crime_types, crime_type))
    except KeyError as exc:
        raise not_found(exc) from exc


@app.get("/api/scope/district/{county}/{district}/summary")
def scope_district_summary(
    county: str,
    district: str,
    counties: str = Query(...),
    years: str = Query(...),
    months: str = Query("1,2,3,4,5,6,7,8,9,10,11,12"),
    crime_types: str | None = Query(None),
    crime_type: str | None = Query(None),
) -> dict:
    try:
        return service.scope_summary(counties, years, months, crime_query(crime_types, crime_type), county, district)
    except KeyError as exc:
        raise not_found(exc) from exc


@app.get("/api/scope/official")
def scope_official(
    counties: str = Query(...),
    years: str = Query(...),
    months: str = Query("1,2,3,4,5,6,7,8,9,10,11,12"),
    crime_types: str | None = Query(None),
    crime_type: str | None = Query(None),
) -> dict:
    try:
        return service.scope_official_data(counties, years, months, crime_query(crime_types, crime_type))
    except KeyError as exc:
        raise not_found(exc) from exc


@app.get("/api/county/{county}/geography")
def county_geography(county: str) -> dict:
    try:
        return service.county_geography(county)
    except KeyError as exc:
        raise not_found(exc) from exc


@app.get("/api/county/{county}/map")
def county_map(
    county: str,
    year: int = Query(...),
    months: str = Query("1,2,3,4,5,6,7,8,9,10,11,12"),
    crime_type: str = Query(...),
    metric: Literal["count", "rate"] = Query(...),
) -> dict:
    try:
        return service.county_map_data(county, year, months, crime_type, metric)
    except KeyError as exc:
        raise not_found(exc) from exc


@app.get("/api/county/{county}/district/{district}/trend")
def county_district_trend(county: str, district: str, crime_type: str = Query(...)) -> dict:
    try:
        return service.county_trend(county, district, crime_type)
    except KeyError as exc:
        raise not_found(exc) from exc


@app.get("/api/county/{county}/district/{district}/trends")
def county_district_all_crime_trends(
    county: str,
    district: str,
    crime_types: str = Query("all"),
) -> dict:
    try:
        return service.county_all_crime_trends(county, district, crime_types)
    except KeyError as exc:
        raise not_found(exc) from exc


@app.get("/api/county/{county}/district/{district}/anomalies")
def county_district_anomalies(
    county: str,
    district: str,
    crime_types: str = Query("all"),
) -> dict:
    try:
        return service.district_anomalies(county, district, crime_types)
    except KeyError as exc:
        raise not_found(exc) from exc


@app.get("/api/county/{county}/district/{district}/summary")
def county_district_summary(
    county: str,
    district: str,
    year: int = Query(...),
    months: str = Query("1,2,3,4,5,6,7,8,9,10,11,12"),
    crime_type: str = Query(...),
) -> dict:
    try:
        return service.county_summary(county, district, year, months, crime_type)
    except KeyError as exc:
        raise not_found(exc) from exc


@app.get("/api/county/{county}/official")
def county_official(
    county: str,
    year: int = Query(...),
    months: str = Query("1,2,3,4,5,6,7,8,9,10,11,12"),
    crime_type: str = Query(...),
) -> dict:
    try:
        return service.county_official_data(county, year, months, crime_type)
    except KeyError as exc:
        raise not_found(exc) from exc


@app.get("/api/county/{county}/coverage")
def county_coverage(
    county: str,
    year: int = Query(...),
    months: str = Query("1,2,3,4,5,6,7,8,9,10,11,12"),
    crime_type: str = Query(...),
) -> dict:
    try:
        return service.county_coverage_data(county, year, months, crime_type)
    except KeyError as exc:
        raise not_found(exc) from exc
