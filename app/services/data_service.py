from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

from app.services.context_service import build_context_service, detect_anomalies

REPO_ROOT = Path(__file__).resolve().parents[2]
PROCESSED_TAICHUNG = REPO_ROOT / "data" / "processed" / "taichung"
PROCESSED_TAIWAN = REPO_ROOT / "data" / "processed" / "taiwan"
GEOGRAPHY_DIR = REPO_ROOT / "data" / "processed" / "geography"
CRIME_TYPE_ORDER = ("毒品", "強盜", "搶奪", "住宅竊盜", "汽車竊盜", "機車竊盜", "強制性交", "組織犯罪防制條例")
ALL_CRIME_SELECTION = "all"
YEARS = tuple(range(2016, 2026))
ALL_MONTHS = tuple(range(1, 13))
METRICS = ({"value": "count", "label": "案件數"}, {"value": "rate", "label": "每十萬年底戶籍人口案件數"})
STATISTICAL_LABELS = {"district": "警政署季度初步案件資料", "official_city": "警政署／刑事警察局年度正式統計", "population_rate": "每十萬年底戶籍人口案件數"}
OBSERVATION_MEANINGS = {
    "observed_positive": "資料涵蓋完整且該行政區有案件紀錄",
    "observed_zero": "資料涵蓋完整且該行政區無案件紀錄；這是有效的零值",
    "partial_coverage": "此年度僅有部分期間資料，不宜與完整年度直接比較",
    "unavailable": "此年度此案類資料未提供",
}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def iter_csv(path: Path) -> Iterable[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        yield from csv.DictReader(handle)


def int_or_none(value: str | None) -> int | None:
    return None if value in {None, ""} else int(value)


def float_or_none(value: str | None) -> float | None:
    return None if value in {None, ""} else float(value)


class DashboardDataService:
    """Preserve the Phase 3A contract while serving the Phase 3C national view."""

    def __init__(self) -> None:
        # Phase 3A compatibility attributes.
        self.panel_rows = read_csv(PROCESSED_TAICHUNG / "taichung_crime_analysis_panel.csv")
        self.official_rows = read_csv(PROCESSED_TAICHUNG / "taichung_official_annual_city_crime_2016_2025.csv")
        self.comparison_rows = read_csv(PROCESSED_TAICHUNG / "taichung_preliminary_vs_official_annual.csv")
        self.geography = json.loads((GEOGRAPHY_DIR / "taichung_districts.geojson").read_text(encoding="utf-8"))
        self.panel = {(int(r["year"]), r["district"], r["crime_type"]): r for r in self.panel_rows}
        self.official = {(int(r["year"]), r["crime_type"]): r for r in self.official_rows}
        self.comparison = {(int(r["year"]), r["crime_type"]): r for r in self.comparison_rows}
        self.years = list(YEARS)
        self.districts = [f["properties"]["district"] for f in self.geography["features"]]
        self.crime_types = list(CRIME_TYPE_ORDER)
        if len(self.districts) != 29 or len(self.panel_rows) != 2320:
            raise ValueError("legacy Taichung dashboard foundation is incomplete")

        # Validated Phase 3B nationwide foundations.
        self.taiwan_geography = json.loads((GEOGRAPHY_DIR / "taiwan_districts.geojson").read_text(encoding="utf-8"))
        self.county_features: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for feature in self.taiwan_geography["features"]:
            self.county_features[feature["properties"]["county"]].append(feature)
        for features in self.county_features.values():
            features.sort(key=lambda f: f["properties"]["town_code"])
        self.counties = sorted(self.county_features, key=lambda c: min(f["properties"]["county_code"] for f in self.county_features[c]))
        self.county_districts = {c: [f["properties"]["district"] for f in fs] for c, fs in self.county_features.items()}
        self.national_panel_rows = read_csv(PROCESSED_TAIWAN / "taiwan_crime_analysis_panel.csv")
        self.national_panel = {(int(r["year"]), r["county"], r["district"], r["crime_type"]): r for r in self.national_panel_rows}
        self.population = {(int(r["year"]), r["county"], r["district"]): int(r["population"]) for r in iter_csv(PROCESSED_TAIWAN / "taiwan_population_by_district_2016_2025.csv")}
        self.coverage = {(int(r["year"]), r["county"], r["crime_type"]): r for r in iter_csv(PROCESSED_TAIWAN / "taiwan_district_assignment_coverage.csv")}
        self.national_official = {(int(r["year"]), r["county"], r["crime_type"]): r for r in iter_csv(PROCESSED_TAIWAN / "taiwan_official_annual_county_crime_2016_2025.csv")}
        self.national_comparison = {(int(r["year"]), r["county"], r["crime_type"]): r for r in iter_csv(PROCESSED_TAIWAN / "taiwan_preliminary_vs_official_annual.csv")}
        self.monthly_assigned: Counter[tuple[int, int, str, str, str]] = Counter()
        self.monthly_assigned_county: Counter[tuple[int, int, str, str]] = Counter()
        for row in iter_csv(PROCESSED_TAIWAN / "taiwan_crime_incidents_2016_2025.csv"):
            year, month = int(row["year"]), int(row["month"])
            self.monthly_assigned[(year, month, row["county"], row["district"], row["crime_type"])] += 1
            self.monthly_assigned_county[(year, month, row["county"], row["crime_type"])] += 1
        self.monthly_unassigned: Counter[tuple[int, int, str, str]] = Counter()
        for row in iter_csv(PROCESSED_TAIWAN / "taiwan_crime_rejected_records.csv"):
            if row["rejection_reason"] != "blank_district" or not row["roc_year"].isdigit():
                continue
            county = row["source_county_original"].strip().replace("台", "臺")
            date = row["oc_data"].zfill(4)
            if county not in self.county_features or len(date) < 2:
                continue
            try:
                year, month = int(row["roc_year"]) + 1911, int(date[:2])
            except ValueError:
                continue
            if year in YEARS and month in ALL_MONTHS and row["crime_type"] in CRIME_TYPE_ORDER:
                self.monthly_unassigned[(year, month, county, row["crime_type"])] += 1
        if len(self.counties) != 22 or sum(map(len, self.county_districts.values())) != 368 or len(self.national_panel) != 29440:
            raise ValueError("nationwide Phase 3B foundation is incomplete")
        self.context = build_context_service(REPO_ROOT)

    # ----- Phase 3A backward-compatible methods -----
    def meta(self) -> dict[str, Any]:
        return {
            "years": self.years, "districts": self.districts, "crime_types": self.crime_types,
            "metric_options": list(METRICS), "statistical_labels": STATISTICAL_LABELS,
            "observation_status_meanings": OBSERVATION_MEANINGS,
            "coverage_states": ["complete", "partial", "unavailable"],
            "default_filters": {"county": "臺中市", "year": 2025, "months": list(ALL_MONTHS), "crime_type": "all", "crime_types": list(CRIME_TYPE_ORDER), "metric": "rate"},
            "nationwide": {"county_count": 22, "district_count": 368},
        }

    def validate_filters(self, year: int, crime_type: str, metric: str | None = None) -> None:
        if year not in YEARS:
            raise KeyError(f"year must be one of {list(YEARS)}")
        if crime_type not in CRIME_TYPE_ORDER:
            raise KeyError(f"unknown crime type: {crime_type}")
        if metric is not None and metric not in {m["value"] for m in METRICS}:
            raise KeyError("metric must be count or rate")

    @staticmethod
    def warnings(row: dict[str, str]) -> list[str]:
        result = ["區級數據屬季度初步資料"]
        if row["observation_status"] == "unavailable":
            result.append("此年度此案類資料未提供")
        elif row["observation_status"] == "partial_coverage":
            result.append("此年度僅有部分期間資料，不宜與完整年度直接比較")
        rate = float_or_none(row.get("district_assignment_rate_city_year_type"))
        if rate is not None and rate < 1:
            result.append(f"部分臺中市案件缺少行政區資訊；各區加總可能低於臺中市來源總件數。行政區可分配率：{rate:.1%}")
        return result

    def serialize_panel_row(self, row: dict[str, str], metric: str | None = None) -> dict[str, Any]:
        count, rate = int_or_none(row["incident_count"]), float_or_none(row["incidents_per_100k_population"])
        result = {
            "district": row["district"], "year": int(row["year"]), "crime_type": row["crime_type"],
            "incident_count": count, "population": int_or_none(row["population"]), "rate": rate,
            "observation_status": row["observation_status"], "source_coverage_status": row["source_coverage_status"],
            "district_assignment_rate": float_or_none(row.get("district_assignment_rate_city_year_type")),
            "display_warning": "；".join(self.warnings(row)), "statistics_layer": "preliminary_district",
            "statistics_label": STATISTICAL_LABELS["district"],
        }
        if metric is not None:
            result["value"] = count if metric == "count" else rate
        return result

    def map_data(self, year: int, crime_type: str, metric: str) -> dict[str, Any]:
        self.validate_filters(year, crime_type, metric)
        return {"year": year, "crime_type": crime_type, "metric": metric, "statistics_layer": "preliminary_district", "statistics_label": STATISTICAL_LABELS["district"], "districts": [self.serialize_panel_row(self.panel[(year, d, crime_type)], metric) for d in self.districts]}

    def district_trend(self, district: str, crime_type: str) -> dict[str, Any]:
        if district not in self.districts:
            raise KeyError(f"unknown district: {district}")
        self.validate_filters(2016, crime_type)
        return {"district": district, "crime_type": crime_type, "statistics_layer": "preliminary_district", "statistics_label": STATISTICAL_LABELS["district"], "values": [self.serialize_panel_row(self.panel[(y, district, crime_type)]) for y in YEARS]}

    def district_summary(self, district: str) -> dict[str, Any]:
        if district not in self.districts:
            raise KeyError(f"unknown district: {district}")
        summaries = []
        for crime_type in CRIME_TYPE_ORDER:
            rows = [self.panel[(y, district, crime_type)] for y in YEARS]
            statuses: dict[str, int] = defaultdict(int)
            for row in rows:
                statuses[row["observation_status"]] += 1
            summaries.append({"crime_type": crime_type, "observed_period_incident_sum": sum(int(r["incident_count"]) for r in rows if r["incident_count"] != ""), "years_by_observation_status": dict(statuses), "latest_year": self.serialize_panel_row(rows[-1])})
        return {"district": district, "statistics_layer": "preliminary_district", "statistics_label": STATISTICAL_LABELS["district"], "crime_types": summaries, "note": "加總僅涵蓋有提供資料的期間；部分涵蓋年度保留觀測值但不視為完整年度。"}

    def official_data(self, year: int | None = None, crime_type: str | None = None) -> dict[str, Any]:
        if year is not None and year not in YEARS:
            raise KeyError(f"year must be one of {list(YEARS)}")
        if crime_type is not None and crime_type not in CRIME_TYPE_ORDER:
            raise KeyError(f"unknown crime type: {crime_type}")
        records = []
        for key in sorted(self.official, key=lambda k: (k[0], self.crime_types.index(k[1]))):
            y, ctype = key
            if (year is not None and y != year) or (crime_type is not None and ctype != crime_type):
                continue
            official, comp = self.official[key], self.comparison[key]
            records.append({
                "year": y, "crime_type": ctype,
                "dataset14200_preliminary_city_source_count": int_or_none(comp["dataset14200_city_source_count"]),
                "official_annual_city_count": int_or_none(official["official_annual_count"]),
                "absolute_difference": int_or_none(comp["absolute_difference"]),
                "official_status": official["statistics_status"], "comparison_status": comp["comparison_status"],
                "statistics_layer": "official_annual_city", "statistics_label": STATISTICAL_LABELS["official_city"],
                "source_agency": official["source_agency"], "source_document": official["source_document"], "source_url": official["source_url"],
                "display_message": "無可比對年度正式值" if comp["comparison_status"] != "comparable" else "",
            })
        return {"statistics_layer": "official_annual_city", "statistics_label": STATISTICAL_LABELS["official_city"], "district_values_are_not_derived_from_official_totals": True, "records": records}

    # ----- Phase 3C nationwide methods -----
    @staticmethod
    def parse_months(months: str | None) -> tuple[int, ...]:
        if months is None or not months.strip():
            return ALL_MONTHS
        try:
            values = tuple(sorted(int(v.strip()) for v in months.split(",") if v.strip()))
        except ValueError as exc:
            raise KeyError("months must be comma-separated integers from 1 to 12") from exc
        if not values or len(values) != len(set(values)) or any(v not in ALL_MONTHS for v in values):
            raise KeyError("months must contain unique values from 1 to 12")
        return values

    def parse_crime_types(self, crime_types_text: str | None) -> tuple[str, ...]:
        if crime_types_text is None or not crime_types_text.strip():
            raise KeyError("crime_types must contain at least one crime type")
        if crime_types_text == ALL_CRIME_SELECTION:
            return CRIME_TYPE_ORDER
        values = tuple(value.strip() for value in crime_types_text.split(",") if value.strip())
        if not values or len(values) != len(set(values)):
            raise KeyError("crime_types must contain unique crime types")
        unknown = [value for value in values if value not in CRIME_TYPE_ORDER]
        if unknown:
            raise KeyError(f"unknown crime type: {unknown[0]}")
        return tuple(crime_type for crime_type in CRIME_TYPE_ORDER if crime_type in values)

    @staticmethod
    def crime_selection_mode(included_types: tuple[str, ...] | list[str]) -> str:
        if len(included_types) == len(CRIME_TYPE_ORDER):
            return "all"
        return "single" if len(included_types) == 1 else "multiple"

    @staticmethod
    def crime_selection_value(included_types: tuple[str, ...] | list[str]) -> str:
        if len(included_types) == len(CRIME_TYPE_ORDER):
            return ALL_CRIME_SELECTION
        return included_types[0] if len(included_types) == 1 else ",".join(included_types)

    def _validate_national_filters(self, county: str, year: int, crime_type: str, metric: str | None = None) -> None:
        if county not in self.county_features:
            raise KeyError(f"unknown county: {county}")
        if year not in YEARS:
            raise KeyError(f"year must be one of {list(YEARS)}")
        self.parse_crime_types(crime_type)
        if metric is not None and metric not in {m["value"] for m in METRICS}:
            raise KeyError("metric must be count or rate")

    def counties_data(self) -> dict[str, Any]:
        return {"default_county": "臺中市", "counties": [{"county": c, "district_count": len(self.county_districts[c]), "districts": list(self.county_districts[c])} for c in self.counties], "county_count": 22, "district_count": 368}

    def parse_counties(self, counties_text: str | None) -> tuple[str, ...]:
        if counties_text is None or not counties_text.strip():
            raise KeyError("counties must contain at least one county")
        values = tuple(value.strip() for value in counties_text.split(",") if value.strip())
        if not values or len(values) != len(set(values)):
            raise KeyError("counties must contain unique county names")
        unknown = [value for value in values if value not in self.county_features]
        if unknown:
            raise KeyError(f"unknown county: {unknown[0]}")
        return tuple(county for county in self.counties if county in values)

    @staticmethod
    def parse_years(years_text: str | None) -> tuple[int, ...]:
        if years_text is None or not years_text.strip():
            raise KeyError("years must contain at least one year")
        try:
            values = tuple(sorted(int(value.strip()) for value in years_text.split(",") if value.strip()))
        except ValueError as exc:
            raise KeyError("years must be comma-separated integers from 2016 to 2025") from exc
        if not values or len(values) != len(set(values)) or any(value not in YEARS for value in values):
            raise KeyError("years must contain unique values from 2016 to 2025")
        return values

    def county_geography(self, county: str) -> dict[str, Any]:
        if county not in self.county_features:
            raise KeyError(f"unknown county: {county}")
        return {"type": "FeatureCollection", "name": f"{county}_districts", "crs_note": self.taiwan_geography.get("crs_note", ""), "features": self.county_features[county]}

    def scope_geography(self, counties_text: str | None) -> dict[str, Any]:
        counties = self.parse_counties(counties_text)
        return {
            "type": "FeatureCollection",
            "name": "selected_counties_districts",
            "crs_note": self.taiwan_geography.get("crs_note", ""),
            "counties": list(counties),
            "features": [feature for county in counties for feature in self.county_features[county]],
        }

    def _coverage_values(self, county: str, year: int, crime_type: str, months: tuple[int, ...]) -> tuple[str, int, int, int, float | None]:
        source = self.coverage[(year, county, crime_type)]
        status = source["coverage_status"]
        if status == "unavailable":
            return status, 0, 0, 0, None
        assigned = sum(self.monthly_assigned_county[(year, m, county, crime_type)] for m in months)
        unassigned = sum(self.monthly_unassigned[(year, m, county, crime_type)] for m in months)
        total = assigned + unassigned
        return status, total, assigned, unassigned, assigned / total if total else None

    @staticmethod
    def _quality(status: str, total: int, assignment_rate: float | None) -> str:
        if status == "unavailable": return "unavailable"
        if status == "partial": return "partial_source"
        if total == 0: return "complete"
        if assignment_rate == 0: return "no_district_assignment"
        if assignment_rate is not None and assignment_rate < 1: return "incomplete_assignment"
        return "complete"

    @staticmethod
    def _competition_ranks(rows: list[dict[str, Any]], key: str, target: str) -> int:
        valid = [r for r in rows if r[key] is not None and r["district_data_quality"] in {"complete", "incomplete_assignment"}]
        valid.sort(key=lambda r: (-r[key], r["district"]))
        prior: float | int | None = None
        rank = 0
        for index, row in enumerate(valid, start=1):
            if prior is None or row[key] != prior:
                rank, prior = index, row[key]
            row[target] = rank
        return len(valid)

    @staticmethod
    def _warning(quality: str, assignment_rate: float | None, all_months: bool) -> str:
        messages = ["行政區資料為警政署季度初步案件資料"]
        if not all_months: messages.append("目前僅顯示已選月份，非完整年度")
        if quality == "unavailable": messages.append("此年度此案類資料未提供")
        elif quality == "partial_source": messages.append("此年度僅有部分資料；不提供完整年度案件率或排名")
        elif quality == "no_district_assignment": messages.append("此縣市該年度案件均缺少鄉鎮市區資訊，無法進行區級比較")
        elif quality == "incomplete_assignment": messages.append("部分案件缺少鄉鎮市區資訊；各區數值僅代表已成功分配行政區的案件")
        if assignment_rate is not None and quality in {"no_district_assignment", "incomplete_assignment"}:
            messages.append(f"行政區可分配率：{assignment_rate:.1%}")
        return "；".join(messages)

    def county_map_data(self, county: str, year: int, months_text: str | None, crime_type: str, metric: str) -> dict[str, Any]:
        self._validate_national_filters(county, year, crime_type, metric)
        months = self.parse_months(months_text)
        included_types = list(self.parse_crime_types(crime_type))
        selection_mode = self.crime_selection_mode(included_types)
        selection_value = self.crime_selection_value(included_types)
        coverage_parts = [self._coverage_values(county, year, selected_type, months) for selected_type in included_types]
        if len(included_types) > 1:
            if all(part[0] == "complete" for part in coverage_parts):
                status = "complete"
            elif all(part[0] == "unavailable" for part in coverage_parts):
                status = "unavailable"
            else:
                status = "partial"
            source_total = sum(part[1] for part in coverage_parts)
            assigned_total = sum(part[2] for part in coverage_parts)
            unassigned_total = sum(part[3] for part in coverage_parts)
            assignment_rate = assigned_total / source_total if source_total else None
        else:
            status, source_total, assigned_total, unassigned_total, assignment_rate = coverage_parts[0]
        quality = self._quality(status, source_total, assignment_rate)
        rows = []
        for district in self.county_districts[county]:
            population = self.population[(year, county, district)]
            count = None if quality in {"unavailable", "no_district_assignment"} else sum(
                self.monthly_assigned[(year, month, county, district, selected_type)]
                for month in months for selected_type in included_types
            )
            rate = None if count is None or quality == "partial_source" else count / population * 100_000
            observation = "unavailable" if quality == "unavailable" else "partial_coverage" if quality == "partial_source" else "observed_positive" if count and count > 0 else "observed_zero"
            stored_observation = (
                "aggregate_incomplete" if quality == "partial_source" else
                "aggregate_observed" if len(included_types) > 1 else
                self.national_panel[(year, county, district, included_types[0])]["observation_status"]
            )
            rows.append({
                "county": county, "district": district, "year": year, "months": list(months), "month_scope": "全年" if len(months) == 12 else "、".join(f"{m}月" for m in months),
                "crime_type": selection_value, "crime_types": included_types, "incident_count": count, "population": population, "rate": rate,
                "crime_selection": selection_mode, "included_crime_types": included_types,
                "value": count if metric == "count" else rate, "observation_status": observation, "stored_observation_status": stored_observation,
                "source_coverage_status": status, "district_assignment_rate": assignment_rate, "district_data_quality": quality,
                "count_rank_within_county": None, "rate_rank_within_county": None, "rank_denominator": 0,
                "display_warning": self._warning(quality, assignment_rate, len(months) == 12),
                "statistics_layer": "preliminary_district", "statistics_label": STATISTICAL_LABELS["district"],
            })
        count_denominator = self._competition_ranks(rows, "incident_count", "count_rank_within_county") if quality in {"complete", "incomplete_assignment"} else 0
        rate_denominator = self._competition_ranks(rows, "rate", "rate_rank_within_county") if quality in {"complete", "incomplete_assignment"} else 0
        for row in rows:
            row["rank_denominator"] = min(count_denominator, rate_denominator) if row["count_rank_within_county"] is not None else 0
        return {
            "county": county, "year": year, "months": list(months), "all_months_selected": len(months) == 12,
            "crime_type": selection_value, "crime_types": included_types, "crime_selection": selection_mode,
            "included_crime_types": included_types, "metric": metric, "district_count": len(rows), "preliminary_county_source_total": source_total,
            "district_assigned_records": assigned_total, "district_unassigned_records": unassigned_total, "district_assignment_rate": assignment_rate,
            "source_coverage_status": status, "district_data_quality": quality,
            "ranking_method": "competition ranking（同值同名次，下一名次依序位跳號）",
            "statistics_layer": "preliminary_district", "district_values_are_not_derived_from_official_totals": True, "districts": rows,
        }

    def scope_map_data(
        self,
        counties_text: str | None,
        years_text: str | None,
        months_text: str | None,
        crime_type: str,
        metric: str,
    ) -> dict[str, Any]:
        counties = self.parse_counties(counties_text)
        years = self.parse_years(years_text)
        months = self.parse_months(months_text)
        self._validate_national_filters(counties[0], years[0], crime_type, metric)
        included_types = list(self.parse_crime_types(crime_type))
        selection_mode = self.crime_selection_mode(included_types)
        selection_value = self.crime_selection_value(included_types)
        maps = {
            (county, year): self.county_map_data(county, year, months_text, crime_type, "count")
            for county in counties for year in years
        }
        source_total = sum(item["preliminary_county_source_total"] for item in maps.values())
        assigned_total = sum(item["district_assigned_records"] for item in maps.values())
        unassigned_total = sum(item["district_unassigned_records"] for item in maps.values())
        assignment_rate = assigned_total / source_total if source_total else None
        statuses = [item["source_coverage_status"] for item in maps.values()]
        if statuses and all(status == "complete" for status in statuses):
            source_status = "complete"
        elif statuses and all(status == "unavailable" for status in statuses):
            source_status = "unavailable"
        else:
            source_status = "partial"
        scope_quality = self._quality(source_status, source_total, assignment_rate)
        rows: list[dict[str, Any]] = []
        for county in counties:
            county_maps = [maps[(county, year)] for year in years]
            county_source_total = sum(item["preliminary_county_source_total"] for item in county_maps)
            county_assigned = sum(item["district_assigned_records"] for item in county_maps)
            county_rate = county_assigned / county_source_total if county_source_total else None
            county_statuses = [item["source_coverage_status"] for item in county_maps]
            if all(status == "complete" for status in county_statuses):
                county_status = "complete"
            elif all(status == "unavailable" for status in county_statuses):
                county_status = "unavailable"
            else:
                county_status = "partial"
            county_quality = self._quality(county_status, county_source_total, county_rate)
            for district in self.county_districts[county]:
                source_rows = [
                    next(row for row in maps[(county, year)]["districts"] if row["district"] == district)
                    for year in years
                ]
                valid_counts = [row["incident_count"] for row in source_rows if row["incident_count"] is not None]
                count = None if county_quality in {"unavailable", "no_district_assignment"} else sum(valid_counts)
                population = sum(self.population[(year, county, district)] for year in years)
                rate = None if count is None or scope_quality in {"unavailable", "partial_source", "no_district_assignment"} else count / population * 100_000
                observation = (
                    "unavailable" if county_quality == "unavailable" else
                    "partial_coverage" if county_quality == "partial_source" or scope_quality == "partial_source" else
                    "observed_positive" if count and count > 0 else "observed_zero"
                )
                effective_quality = "partial_source" if scope_quality == "partial_source" and county_quality != "unavailable" else county_quality
                rows.append({
                    "county": county,
                    "district": district,
                    "year": years[0] if len(years) == 1 else None,
                    "years": list(years),
                    "months": list(months),
                    "month_scope": "全年" if len(months) == 12 else "、".join(f"{month}月" for month in months),
                    "year_scope": str(years[0]) if len(years) == 1 else f"{years[0]}–{years[-1]}（{len(years)} 年）",
                    "crime_type": selection_value,
                    "crime_types": included_types,
                    "incident_count": count,
                    "population": population,
                    "population_basis": "年底戶籍人口" if len(years) == 1 else "所選年度年底戶籍人口合計",
                    "rate": rate,
                    "crime_selection": selection_mode,
                    "included_crime_types": included_types,
                    "value": count if metric == "count" else rate,
                    "observation_status": observation,
                    "source_coverage_status": source_status,
                    "district_assignment_rate": county_rate,
                    "district_data_quality": effective_quality,
                    "count_rank_within_county": None,
                    "rate_rank_within_county": None,
                    "rank_denominator": 0,
                    "display_warning": self._warning(effective_quality, county_rate, len(months) == 12),
                    "statistics_layer": "preliminary_district",
                    "statistics_label": STATISTICAL_LABELS["district"],
                })
        can_rank = scope_quality in {"complete", "incomplete_assignment"}
        count_denominator = self._competition_ranks(rows, "incident_count", "count_rank_within_county") if can_rank else 0
        rate_denominator = self._competition_ranks(rows, "rate", "rate_rank_within_county") if can_rank else 0
        for row in rows:
            row["rank_denominator"] = min(count_denominator, rate_denominator) if row["count_rank_within_county"] is not None else 0
        return {
            "counties": list(counties),
            "years": list(years),
            "months": list(months),
            "all_months_selected": len(months) == 12,
            "crime_type": selection_value,
            "crime_types": included_types,
            "crime_selection": selection_mode,
            "included_crime_types": included_types,
            "metric": metric,
            "county_count": len(counties),
            "district_count": len(rows),
            "preliminary_county_source_total": source_total,
            "district_assigned_records": assigned_total,
            "district_unassigned_records": unassigned_total,
            "district_assignment_rate": assignment_rate,
            "source_coverage_status": source_status,
            "district_data_quality": scope_quality,
            "ranking_scope": "county" if len(counties) == 1 else "selected_counties",
            "ranking_method": "competition ranking（同值同名次，下一名次依序位跳號）",
            "rate_label": "每十萬人口案件數" if len(years) == 1 else "每十萬人口加權案件數",
            "population_basis": "年底戶籍人口" if len(years) == 1 else "所選年度年底戶籍人口合計",
            "statistics_layer": "preliminary_district",
            "district_values_are_not_derived_from_official_totals": True,
            "districts": rows,
        }

    def scope_district_trends(self, counties_text: str | None, crime_type: str) -> dict[str, Any]:
        counties = self.parse_counties(counties_text)
        self._validate_national_filters(counties[0], YEARS[0], crime_type)
        included_types = list(self.parse_crime_types(crime_type))
        selection_mode = self.crime_selection_mode(included_types)
        selection_value = self.crime_selection_value(included_types)
        district_series: dict[tuple[str, str], list[dict[str, Any]]] = {
            (county, district): []
            for county in counties
            for district in self.county_districts[county]
        }
        for county in counties:
            for year in YEARS:
                annual = self.county_map_data(county, year, None, crime_type, "rate")
                for row in annual["districts"]:
                    district_series[(county, row["district"])].append({
                        key: row[key]
                        for key in (
                            "year", "incident_count", "population", "rate", "observation_status",
                            "source_coverage_status", "district_assignment_rate",
                            "district_data_quality", "display_warning",
                        )
                    })
        districts = [
            {"county": county, "district": district, "series": district_series[(county, district)]}
            for county in counties
            for district in self.county_districts[county]
        ]
        return {
            "counties": list(counties),
            "crime_type": selection_value,
            "crime_types": included_types,
            "included_crime_types": included_types,
            "crime_selection": selection_mode,
            "years": list(YEARS),
            "full_year_only": True,
            "district_count": len(districts),
            "statistics_layer": "preliminary_district",
            "districts": districts,
        }

    def compare_district_years(self, county: str, district: str, years: list[int], months_text: str, crime_type: str) -> dict[str, Any]:
        """Read-only comparison of two validated series; never compare partial values."""
        if len(years) != 2 or years[0] >= years[1]:
            raise KeyError("comparison requires two distinct ascending years")
        rows = []
        for year in years:
            data = self.scope_map_data(county, str(year), months_text, crime_type, "count")
            if district not in self.county_districts[county]:
                raise KeyError("unknown district")
            rows.append(next(row for row in data["districts"] if row["district"] == district))
        earlier, later = rows
        comparable = all(row["district_data_quality"] == "complete" and row["incident_count"] is not None for row in rows)
        change = later["incident_count"] - earlier["incident_count"] if comparable else None
        percent = None
        if comparable:
            if earlier["incident_count"]:
                percent = change / earlier["incident_count"] * 100
            elif later["incident_count"] == 0:
                percent = 0.0
        return {"county": county, "district": district, "earlier_year": years[0], "later_year": years[1],
                "earlier_count": earlier["incident_count"], "later_count": later["incident_count"],
                "earlier_quality": earlier["district_data_quality"], "later_quality": later["district_data_quality"],
                "comparable": comparable, "absolute_change": change, "percent_change": percent,
                "display_message": "資料完整度不同，不建議直接比較" if not comparable else "前期為零，無法計算百分比" if percent is None else "",
                "statistics_layer": "preliminary_district"}

    def scope_summary(
        self,
        counties_text: str | None,
        years_text: str | None,
        months_text: str | None,
        crime_type: str,
        county: str,
        district: str,
    ) -> dict[str, Any]:
        scope = self.scope_map_data(counties_text, years_text, months_text, crime_type, "rate")
        if county not in scope["counties"] or district not in self.county_districts[county]:
            raise KeyError(f"unknown district for selected scope: {county} {district}")
        detail = next(row for row in scope["districts"] if row["county"] == county and row["district"] == district)
        years = tuple(scope["years"])
        comparison = {
            "current_year": years[0] if len(years) == 1 else None,
            "previous_year": years[0] - 1 if len(years) == 1 and years[0] > 2016 else None,
            "current_count": detail["incident_count"],
            "previous_count": None,
            "percent_change": None,
            "comparable": False,
            "display_message": "年增減：—\n目前選取多個年度" if len(years) > 1 else "年增減：—\n資料完整度不同，不建議直接比較",
        }
        if len(years) == 1 and years[0] > 2016:
            prior_map = self.scope_map_data(county, str(years[0] - 1), months_text, crime_type, "rate")
            prior = next(row for row in prior_map["districts"] if row["county"] == county and row["district"] == district)
            comparison["previous_count"] = prior["incident_count"]
            valid = detail["district_data_quality"] == prior["district_data_quality"] == "complete" and detail["incident_count"] is not None and prior["incident_count"] is not None
            if valid and prior["incident_count"] != 0:
                comparison.update({"comparable": True, "percent_change": (detail["incident_count"] - prior["incident_count"]) / prior["incident_count"] * 100, "display_message": ""})
            elif valid and prior["incident_count"] == detail["incident_count"] == 0:
                comparison.update({"comparable": True, "percent_change": 0.0, "display_message": "前後年度皆為有效零值"})
            elif valid:
                comparison["display_message"] = "年增減：—\n前一年為零，無法計算百分比"
        return {
            "counties": scope["counties"], "years": list(years), "months": scope["months"],
            "county": county, "district": district, "crime_type": scope["crime_type"],
            "crime_types": scope["crime_types"], "crime_selection": scope["crime_selection"],
            "detail": detail, "previous_year_comparison": comparison,
        }

    def scope_official_data(
        self,
        counties_text: str | None,
        years_text: str | None,
        months_text: str | None,
        crime_type: str,
    ) -> dict[str, Any]:
        counties = self.parse_counties(counties_text)
        years = self.parse_years(years_text)
        months = self.parse_months(months_text)
        included_types = list(self.parse_crime_types(crime_type))
        selection_mode = self.crime_selection_mode(included_types)
        selection_value = self.crime_selection_value(included_types)
        scope = self.scope_map_data(counties_text, years_text, months_text, crime_type, "count")
        base = {
            "counties": list(counties), "years": list(years), "months": list(months), "crime_type": selection_value,
            "crime_types": included_types, "included_crime_types": included_types, "crime_selection": selection_mode,
            "dataset14200_preliminary_count": scope["preliminary_county_source_total"],
            "official_annual_county_count": None, "absolute_difference": None,
            "percent_difference_vs_official": None, "statistics_layer": "official_annual_county",
            "official_aggregate_label": "所選案類年度正式統計合計",
            "district_values_are_not_derived_from_official_totals": True,
        }
        if len(months) < 12:
            return {**base, "comparison_status": "partial_months_not_comparable", "display_message": "已選月份非完整年度，無法直接對照年度正式統計"}
        official_values: list[int] = []
        for county in counties:
            for year in years:
                for selected_type in included_types:
                    official = self.national_official.get((year, county, selected_type))
                    comparison = self.national_comparison.get((year, county, selected_type))
                    value = int_or_none(official.get("official_annual_count")) if official else None
                    if value is None or comparison is None or comparison["comparison_status"] != "comparable":
                        status = "all_categories_not_directly_comparable" if selection_mode == "all" else "category_not_comparable"
                        return {**base, "comparison_status": status, "display_message": "所選案類包含無等價、已驗證年度正式統計的類別，無法直接比較"}
                    official_values.append(value)
        official_total = sum(official_values)
        difference = scope["preliminary_county_source_total"] - official_total
        return {
            **base,
            "official_annual_county_count": official_total,
            "absolute_difference": difference,
            "percent_difference_vs_official": difference / official_total * 100 if official_total else None,
            "comparison_status": "comparable",
            "display_message": "",
        }

    def county_trend(self, county: str, district: str, crime_type: str) -> dict[str, Any]:
        self._validate_national_filters(county, 2016, crime_type)
        if district not in self.county_districts[county]:
            raise KeyError(f"unknown district for {county}: {district}")
        included_types = list(self.parse_crime_types(crime_type))
        selection_mode = self.crime_selection_mode(included_types)
        selection_value = self.crime_selection_value(included_types)
        values = []
        for year in YEARS:
            data = self.county_map_data(county, year, None, crime_type, "rate")
            values.append(next(r for r in data["districts"] if r["district"] == district))
        return {"county": county, "district": district, "crime_type": selection_value, "crime_types": included_types, "crime_selection": selection_mode, "included_crime_types": included_types, "years": list(YEARS), "full_year_only": True, "values": values}

    def _trend_annotations(self, values: list[dict[str, Any]], county: str, district: str, crime_type: str) -> list[dict[str, Any]]:
        annotations = detect_anomalies(values, county, district, crime_type)
        for item in annotations:
            # Read the validated county comparisons as context only. Never allocate
            # official totals to districts or use them to correct observations.
            comparisons = []
            warnings = [item["data_quality_warning"]] if item["data_quality_warning"] else []
            for category in self.parse_crime_types(crime_type):
                record = self.national_comparison.get((item["year"], county, category), {})
                status = record.get("comparison_status", "category_not_comparable")
                difference = int_or_none(record.get("absolute_difference")) if status == "comparable" else None
                comparisons.append({
                    "crime_type": category,
                    "comparison_status": status,
                    "preliminary_county_count": int_or_none(record.get("dataset14200_preliminary_count")),
                    "official_county_count": int_or_none(record.get("official_annual_count")),
                    "absolute_difference": difference,
                })
                if status != "comparable":
                    warnings.append(f"{category}：無等價的縣市年度正式值可直接比較。")
                elif difference:
                    warnings.append(f"{category}：縣市初步－正式統計差異 {difference:+,} 件；此為縣市口徑差異，不能據此修正行政區值或解釋區級變動。")
            item["official_comparisons"] = comparisons
            item["data_quality_warning"] = "；".join(warnings)
        return annotations

    def county_all_crime_trends(self, county: str, district: str, crime_types_text: str = ALL_CRIME_SELECTION) -> dict[str, Any]:
        self._validate_national_filters(county, YEARS[0], crime_types_text)
        if district not in self.county_districts[county]:
            raise KeyError(f"unknown district for {county}: {district}")
        included_types = list(self.parse_crime_types(crime_types_text))
        selection_mode = self.crime_selection_mode(included_types)
        selection_value = self.crime_selection_value(included_types)
        crime_types = []
        for crime_type in included_types:
            trend = self.county_trend(county, district, crime_type)
            crime_types.append({
                "crime_type": crime_type,
                "values": trend["values"],
                "anomalies": self._trend_annotations(trend["values"], county, district, crime_type),
            })
        aggregate = None
        if len(included_types) > 1:
            aggregate_trend = self.county_trend(county, district, selection_value)
            aggregate = {
                "title": f"全部案類（{len(included_types)} 類合計）" if selection_mode == "all" else f"所選案類合計（{len(included_types)} 類）",
                "crime_types": included_types,
                "values": aggregate_trend["values"],
                "anomalies": self._trend_annotations(aggregate_trend["values"], county, district, selection_value),
            }
        return {
            "county": county,
            "district": district,
            "years": list(YEARS),
            "full_year_only": True,
            "statistics_layer": "preliminary_district",
            "crime_selection": selection_mode,
            "selected_crime_types": included_types,
            "aggregate": aggregate,
            "crime_types": crime_types,
            "events": self.context.events(county=county),
            "interpretation_policy": {
                "raw_values_modified": False,
                "causality_established": False,
                "context_disclaimer": "事件時間重疊僅供背景解讀，不代表該事件造成犯罪數據變化。",
                "data_quality_precedes_event_context": True,
            },
        }

    def district_anomalies(self, county: str, district: str, crime_types_text: str = ALL_CRIME_SELECTION) -> dict[str, Any]:
        trends = self.county_all_crime_trends(county, district, crime_types_text)
        series = ([trends["aggregate"]] if trends["aggregate"] else []) + trends["crime_types"]
        return {
            "county": county,
            "district": district,
            "statistics_layer": "contextual_interpretation",
            "raw_values_modified": False,
            "series": [
                {
                    "crime_type": item.get("title", item.get("crime_type")),
                    "anomalies": item["anomalies"],
                }
                for item in series
            ],
            "events": trends["events"],
            "interpretation_policy": trends["interpretation_policy"],
        }

    def county_summary(self, county: str, district: str, year: int, months_text: str | None, crime_type: str) -> dict[str, Any]:
        self._validate_national_filters(county, year, crime_type)
        if district not in self.county_districts[county]:
            raise KeyError(f"unknown district for {county}: {district}")
        current_map = self.county_map_data(county, year, months_text, crime_type, "rate")
        current = next(r for r in current_map["districts"] if r["district"] == district)
        comparison = {"current_year": year, "previous_year": year - 1 if year > 2016 else None, "current_count": current["incident_count"], "previous_count": None, "percent_change": None, "comparable": False, "display_message": "年增減：—\n資料完整度不同，不建議直接比較"}
        if year > 2016:
            prior_map = self.county_map_data(county, year - 1, months_text, crime_type, "rate")
            prior = next(r for r in prior_map["districts"] if r["district"] == district)
            comparison["previous_count"] = prior["incident_count"]
            valid = current["district_data_quality"] == prior["district_data_quality"] == "complete" and current["incident_count"] is not None and prior["incident_count"] is not None
            if valid and prior["incident_count"] != 0:
                comparison.update({"comparable": True, "percent_change": (current["incident_count"] - prior["incident_count"]) / prior["incident_count"] * 100, "display_message": ""})
            elif valid and prior["incident_count"] == current["incident_count"] == 0:
                comparison.update({"comparable": True, "percent_change": 0.0, "display_message": "前後年度皆為有效零值"})
            elif valid:
                comparison["display_message"] = "年增減：—\n前一年為零，無法計算百分比"
        return {"county": county, "district": district, "year": year, "months": current_map["months"], "crime_type": crime_type, "detail": current, "previous_year_comparison": comparison}

    def county_official_data(self, county: str, year: int, months_text: str | None, crime_type: str) -> dict[str, Any]:
        self._validate_national_filters(county, year, crime_type)
        months = self.parse_months(months_text)
        map_data = self.county_map_data(county, year, months_text, crime_type, "count")
        if crime_type == ALL_CRIME_SELECTION:
            return {
                "county": county, "year": year, "months": list(months), "crime_type": crime_type,
                "crime_selection": "all", "included_crime_types": list(CRIME_TYPE_ORDER),
                "dataset14200_preliminary_count": map_data["preliminary_county_source_total"],
                "official_annual_county_count": None, "absolute_difference": None,
                "percent_difference_vs_official": None, "comparison_status": "all_categories_not_directly_comparable",
                "display_message": "無完整可比對的「全部案類」年度正式統計；正式基準未提供直接等同 Dataset 14200 八類加總的驗證總計。",
                "statistics_layer": "official_annual_county", "district_values_are_not_derived_from_official_totals": True,
                "preliminary_statistics_label": "警政署季度初步案件資料", "official_statistics_label": "警政署／刑事警察局年度正式統計",
            }
        official = self.national_official.get((year, county, crime_type))
        comparison = self.national_comparison.get((year, county, crime_type))
        official_count = int_or_none(official.get("official_annual_count")) if official else None
        if len(months) < 12:
            status, difference, percent, message = "partial_months_not_comparable", None, None, "已選月份非完整年度，無法直接對照年度正式統計"
        elif comparison is None:
            status, difference, percent, message = "category_not_comparable", None, None, "無可比對年度正式值"
        else:
            status = comparison["comparison_status"]
            difference, percent = int_or_none(comparison["absolute_difference"]), float_or_none(comparison["percent_difference_vs_official"])
            message = "" if status == "comparable" else "無可比對年度正式值"
        return {
            "county": county, "year": year, "months": list(months), "crime_type": crime_type,
            "dataset14200_preliminary_count": map_data["preliminary_county_source_total"], "official_annual_county_count": official_count,
            "absolute_difference": difference, "percent_difference_vs_official": percent, "comparison_status": status, "display_message": message,
            "statistics_layer": "official_annual_county", "district_values_are_not_derived_from_official_totals": True,
            "preliminary_statistics_label": "警政署季度初步案件資料", "official_statistics_label": "警政署／刑事警察局年度正式統計",
        }

    def county_coverage_data(self, county: str, year: int, months_text: str | None, crime_type: str) -> dict[str, Any]:
        self._validate_national_filters(county, year, crime_type)
        months = self.parse_months(months_text)
        included_types = list(CRIME_TYPE_ORDER) if crime_type == ALL_CRIME_SELECTION else [crime_type]
        parts = [self._coverage_values(county, year, selected_type, months) for selected_type in included_types]
        if crime_type == ALL_CRIME_SELECTION:
            status = "complete" if all(part[0] == "complete" for part in parts) else "partial"
            total, assigned, unassigned = sum(part[1] for part in parts), sum(part[2] for part in parts), sum(part[3] for part in parts)
            rate = assigned / total if total else None
        else:
            status, total, assigned, unassigned, rate = parts[0]
        quality = self._quality(status, total, rate)
        return {"county": county, "year": year, "months": list(months), "crime_type": crime_type, "crime_selection": "all" if crime_type == ALL_CRIME_SELECTION else "single", "included_crime_types": included_types, "total_source_records": total, "district_assigned_records": assigned, "district_unassigned_records": unassigned, "district_assignment_rate": rate, "source_coverage_status": status, "district_data_quality": quality, "display_warning": self._warning(quality, rate, len(months) == 12)}


service = DashboardDataService()
