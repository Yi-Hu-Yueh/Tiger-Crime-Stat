"""Read-only, allowlisted adapters to the validated services (no model calculations)."""
from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.services.data_service import service

Year = Annotated[int, Field(strict=True, ge=2016, le=2025)]
Month = Annotated[int, Field(strict=True, ge=1, le=12)]
Name = Annotated[str, Field(strict=True, min_length=1, max_length=40)]
Years = Annotated[list[Year], Field(min_length=1, max_length=10)]
Months = Annotated[list[Month], Field(min_length=1, max_length=12)]
County = Annotated[Name, Field(json_schema_extra={"enum": list(service.county_districts)})]
Counties = Annotated[list[County], Field(min_length=1, max_length=22)]
Crime = Literal["all", "毒品", "強盜", "搶奪", "住宅竊盜", "汽車竊盜", "機車竊盜", "強制性交", "組織犯罪防制條例"]
Crimes = Annotated[list[Crime], Field(min_length=1, max_length=8)]


def joined(values):
    return ",".join(map(str, values))


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Filters(StrictModel):
    counties: Counties
    years: Years
    months: Months = Field(default_factory=lambda: list(range(1, 13)))
    crime_types: Crimes = Field(default_factory=lambda: ["all"])

    @model_validator(mode="after")
    def validate_filters(self):
        try:
            service.parse_counties(joined(self.counties))
            service.parse_years(joined(self.years))
            service.parse_months(joined(self.months))
            service.parse_crime_types(joined(self.crime_types))
        except KeyError as exc:
            raise ValueError("無效的縣市、年份、月份或案類") from exc
        return self


class StatisticsArgs(Filters):
    districts: Annotated[list[Name], Field(max_length=100)] = Field(default_factory=list)
    metric: Literal["count", "rate"] = "count"
    group_by: Literal["district", "year"] = Field(default="district", description="district: 所選年度合計；year: 各年度行政區值，不可混合成單一年值。")
    sort: Literal["count_desc", "count_asc", "rate_desc", "rate_asc", "district"] = "count_desc"
    limit: Annotated[int, Field(strict=True, ge=1, le=100)] = 50

    @model_validator(mode="after")
    def validate_districts(self):
        known = {d for county in self.counties for d in service.county_districts[county]}
        if len(set(self.districts)) != len(self.districts) or any(d not in known for d in self.districts):
            raise ValueError("行政區不在所選縣市範圍")
        return self


class TrendArgs(StrictModel):
    county: County
    district: Name
    crime_types: Crimes = Field(default_factory=lambda: ["all"])


class EventArgs(StrictModel):
    years: Years
    scope: Literal["global", "taiwan", "all"] = "all"


def query_statistics(args: StatisticsArgs):
    groups = [[year] for year in sorted(args.years)] if args.group_by == "year" else [args.years]
    rows, scopes = [], []
    for years in groups:
        result = service.scope_map_data(joined(args.counties), joined(years), joined(args.months), joined(args.crime_types), args.metric)
        scopes.append({key: value for key, value in result.items() if key != "districts"})
        rows.extend(row for row in result["districts"] if not args.districts or row["district"] in args.districts)
    if args.sort == "district":
        rows.sort(key=lambda row: (row["county"], row["district"], row["years"]))
    else:
        key = "rate" if args.sort.startswith("rate") else "incident_count"
        direction = -1 if args.sort.endswith("desc") else 1
        rows.sort(key=lambda row: (row[key] is None, direction * row[key] if row[key] is not None else 0, row["county"], row["district"], row["years"]))
    comparisons = []
    if args.group_by == "year" and len(args.years) == 2 and args.districts:
        for county in args.counties:
            for district in args.districts:
                if district in service.county_districts[county]:
                    comparisons.append(service.compare_district_years(county, district, sorted(args.years), joined(args.months), joined(args.crime_types)))
    return {"statistics_layer": "preliminary_district", "scopes": scopes, "rows": rows[:args.limit],
            "matching_rows": len(rows), "returned_rows": min(len(rows), args.limit), "truncated": len(rows) > args.limit,
            "comparisons": comparisons, "ranking_note": "排名沿用 DataService 所選縣市範圍，並非篩選後行政區子集合排名。"}


def get_trend(args: TrendArgs):
    result = service.county_all_crime_trends(args.county, args.district, joined(args.crime_types))
    # Event catalog has its own tool; retain all quality/interpretation metadata.
    return {key: value for key, value in result.items() if key != "events"}


def get_events(args: EventArgs):
    events = [event for year in sorted(set(args.years)) for event in service.context.events(year=year)
              if args.scope == "all" or event["scope"] == args.scope]
    return {"events": events, "causality_established": False, "disclaimer": "時間重疊不代表因果關係；收錄不代表事件影響所選行政區。"}


def get_official(args: Filters):
    return service.scope_official_data(joined(args.counties), joined(args.years), joined(args.months), joined(args.crime_types))


TOOL_REGISTRY = {
    "query_crime_statistics": (StatisticsArgs, query_statistics, "查詢警政署初步行政區統計及排名；案類 all 僅指8類，不是全部刑案。比較兩年時用 group_by=year 並指定 districts，回傳後端計算比較。"),
    "get_crime_trend": (TrendArgs, get_trend, "取得行政區2016–2025完整年度趨勢、案件數、率、涵蓋及品質、異常註解；不套用月份子集。"),
    "get_major_events": (EventArgs, get_events, "讀取固定2016–2025全球／台灣事件目錄及來源；只能當時間背景，不能推論犯罪因果。"),
    "get_official_annual_statistics": (Filters, get_official, "讀取獨立的縣市年度正式統計及與初步來源的比較；不能分配到行政區。月份不完整時不得當年度正式比較。"),
}

TOOLS = [{"type": "function", "function": {"name": name, "description": description, "parameters": schema.model_json_schema()}}
         for name, (schema, _, description) in TOOL_REGISTRY.items()]


def execute_tool(name: str, arguments: dict):
    if name not in TOOL_REGISTRY:
        raise ValueError("不允許的工具")
    schema, function, _ = TOOL_REGISTRY[name]
    return function(schema.model_validate(arguments))
