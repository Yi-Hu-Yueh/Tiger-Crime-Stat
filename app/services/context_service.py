from __future__ import annotations

import math
import statistics
from copy import deepcopy
from datetime import date
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from app.data.major_events_2016_2025 import MAJOR_EVENTS_2016_2025


CAUSALITY_DISCLAIMER = "事件時間重疊僅供背景解讀，不代表該事件造成犯罪數據變化。"
RELIABLE_QUALITY = {"complete"}
QUALITY_WARNINGS = {
    "incomplete_assignment": "行政區分配不完整；資料品質限制優先於事件背景解讀。",
    "no_district_assignment": "無行政區分配資料；不進行一般統計異常判定。",
    "partial_source": "來源僅部分涵蓋；不進行一般統計異常判定。",
    "unavailable": "該年度資料未提供；不進行統計異常判定。",
}


def _median_absolute_deviation(values: list[int], median: float) -> float:
    return statistics.median(abs(value - median) for value in values)


def detect_anomalies(
    values: list[dict[str, Any]], county: str, district: str, crime_type: str
) -> list[dict[str, Any]]:
    """Return interpretation metadata without mutating any input observation."""
    results: list[dict[str, Any]] = []
    reliable_history: list[dict[str, Any]] = []
    previous: dict[str, Any] | None = None
    for row in values:
        count = row.get("incident_count")
        quality = row.get("district_data_quality", "unavailable")
        prior_count = previous.get("incident_count") if previous else None
        comparable_yoy = bool(
            previous
            and previous.get("year") == row.get("year") - 1
            and previous.get("district_data_quality") in RELIABLE_QUALITY
            and quality in RELIABLE_QUALITY
            and count is not None
            and prior_count is not None
        )
        yoy = None
        zero_baseline = comparable_yoy and prior_count == 0
        if comparable_yoy and prior_count != 0:
            yoy = (count - prior_count) / prior_count * 100
        elif comparable_yoy and count == prior_count == 0:
            yoy = 0.0

        baseline_rows = reliable_history[-3:]
        baseline = [item["incident_count"] for item in baseline_rows]
        baseline_median = statistics.median(baseline) if len(baseline) == 3 else None
        mad = _median_absolute_deviation(baseline, baseline_median) if baseline_median is not None else None
        robust_score = None
        median_change_percent = None
        if count is not None and baseline_median is not None:
            if mad:
                robust_score = 0.6745 * (count - baseline_median) / mad
            elif count == baseline_median:
                robust_score = 0.0
            if baseline_median:
                median_change_percent = (count - baseline_median) / baseline_median * 100

        warning = QUALITY_WARNINGS.get(quality, "")
        if previous and quality in RELIABLE_QUALITY and not comparable_yoy:
            warning = "前一年度缺失或資料品質不完整，不能將涵蓋或分配變化視為一般統計異常。"
        level = "normal"
        reasons: list[str] = []
        if quality not in RELIABLE_QUALITY or count is None:
            level = "insufficient_data"
            reasons.append(warning or "資料不足，無法進行可靠的異常判定。")
        elif len(baseline) < 3:
            level = "insufficient_data"
            reasons.append("至少需要三個先前可靠年度才能建立近期中位數基準。")
        elif not comparable_yoy:
            level = "insufficient_data"
            warning = "前一年度缺失或資料品質不完整，不能將涵蓋或分配變化視為一般統計異常。"
            reasons.append(warning)
        elif zero_baseline and count != 0:
            level = "insufficient_data"
            reasons.append("前一年為零，無法計算年增減百分比；本方法不以無限增幅判定異常。")
        else:
            robust_extreme = robust_score is not None and abs(robust_score) >= 3.5
            robust_notable = robust_score is not None and abs(robust_score) >= 2.5
            median_extreme = median_change_percent is not None and abs(median_change_percent) >= 75
            median_notable = median_change_percent is not None and abs(median_change_percent) >= 40
            yoy_extreme = yoy is not None and abs(yoy) >= 75
            yoy_notable = yoy is not None and abs(yoy) >= 40
            if (robust_extreme or median_extreme) and yoy_extreme:
                level = "high"
            elif (robust_notable or median_notable) and yoy_notable:
                level = "notable"
            if level != "normal":
                if yoy is not None:
                    reasons.append(f"較前一年變動 {yoy:+.1f}%。")
                elif zero_baseline:
                    reasons.append("前一年為零，百分比變化不具可解讀性。")
                if robust_score is not None:
                    reasons.append(f"相對前三個可靠年度中位數的穩健分數為 {robust_score:+.2f}。")
                if median_change_percent is not None:
                    reasons.append(f"相對前三個可靠年度中位數變動 {median_change_percent:+.1f}%。")
                reasons.append("門檻：年增減 ≥40% 且（|穩健分數| ≥2.5 或中位數偏離 ≥40%）；顯著變化門檻為 75%、3.5、75%（均採絕對值）。")
            else:
                reasons.append("未同時達到年增減與近期穩健基準的異常門檻。")

        results.append(
            {
                "year": row.get("year"),
                "county": county,
                "district": district,
                "crime_type": crime_type,
                "incident_count": count,
                "previous_year_count": prior_count,
                "previous_year": previous.get("year") if previous else None,
                "yoy_comparable": comparable_yoy and not (zero_baseline and count != 0),
                "yoy_change_percent": round(yoy, 4) if yoy is not None and math.isfinite(yoy) else None,
                "recent_median": baseline_median,
                "baseline_years": [item["year"] for item in baseline_rows],
                "median_absolute_deviation": mad,
                "median_change_percent": round(median_change_percent, 4) if median_change_percent is not None else None,
                "robust_score": round(robust_score, 4) if robust_score is not None and math.isfinite(robust_score) else None,
                "anomaly_level": level,
                "anomaly_reason": " ".join(reasons),
                "district_data_quality": quality,
                "source_coverage_status": row.get("source_coverage_status"),
                "district_assignment_rate": row.get("district_assignment_rate"),
                "data_quality_warning": warning,
                "metadata_only": True,
            }
        )
        if quality in RELIABLE_QUALITY and count is not None:
            reliable_history.append(row)
        previous = row
    return results


class ContextService:
    def __init__(self) -> None:
        # The shipped catalog is the only production source. No file ingestion or network.
        events = [deepcopy(event) for year in range(2016, 2026)
                  for scope in ("global", "taiwan")
                  for event in MAJOR_EVENTS_2016_2025[year][scope]]
        required = {
            "id", "year", "title", "start_date", "end_date", "scope", "category",
            "summary", "source_title", "source_url", "source_agency", "status", "relevance_tags",
        }
        ids = set()
        for event in events:
            missing = required - event.keys()
            if missing or not event.get("source_title") or not event.get("source_url") or not event.get("source_agency"):
                raise ValueError(f"major event missing required source metadata: {sorted(missing)}")
            if date.fromisoformat(event["start_date"]) > date.fromisoformat(event["end_date"]):
                raise ValueError("major event start date must precede end date")
            if not (2016 <= event["year"] <= 2025) or any(
                date.fromisoformat(event[key]).year != event["year"] for key in ("start_date", "end_date")
            ):
                raise ValueError("major event dates must belong to its catalog year")
            if event["scope"] not in {"global", "taiwan"} or event["id"] in ids:
                raise ValueError("major event scope or unique id is invalid")
            if event["status"] not in {
                "implemented", "announced", "proposed", "market_reaction", "public_health_measure",
                "natural_disaster", "conflict", "policy_change", "incident", "institutional_change", "promulgated",
            }:
                raise ValueError("major event status is invalid")
            if not event["relevance_tags"]:
                raise ValueError("major event requires contextual tags")
            ids.add(event["id"])
            source_url = urlparse(event["source_url"])
            if source_url.scheme != "https" or not source_url.netloc:
                raise ValueError("major event source must be an HTTPS URL")
            for source in event.get("sources", []):
                if not source.get("title") or not source.get("url") or not source.get("agency"):
                    raise ValueError("major event contains an incomplete supporting source")
                parsed = urlparse(source["url"])
                if parsed.scheme != "https" or not parsed.netloc:
                    raise ValueError("supporting source must be an HTTPS URL")
        self._events = events

    def events(self, county: str | None = None, year: int | None = None) -> list[dict[str, Any]]:
        # National/global history is available in every district. This does not
        # assert that a local disaster or policy affected the selected district.
        result = []
        for event in self._events:
            if year is None or year == event["year"]:
                result.append({**deepcopy(event), "causality_established": False, "context_disclaimer": CAUSALITY_DISCLAIMER})
        return result


def build_context_service(repo_root: Path) -> ContextService:
    return ContextService()
