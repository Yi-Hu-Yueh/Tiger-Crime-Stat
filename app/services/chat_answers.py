"""Deterministic presentation of tool evidence. Never computes source statistics."""
import re

from app.services.chat_router import THEFT_CRIME_TYPES, RoutePlan


def crime_label(crimes):
    if crimes == ["all"]:
        return "全部案類（既有8類，非全部刑案）"
    if list(crimes) == THEFT_CRIME_TYPES:
        return "三類竊盜合計（住宅竊盜、汽車竊盜、機車竊盜；非官方獨立案類）"
    return "、".join(crimes)


def count_text(row):
    count, quality = row.get("incident_count"), row.get("district_data_quality")
    if quality == "unavailable":
        return "該年度此案類資料為 unavailable，因此不能解讀為 0 件。"
    if quality == "no_district_assignment":
        return "no_district_assignment：無行政區分配，不能解讀為 0 件。"
    if count is None:
        return "案件數未提供，不能解讀為 0 件。"
    if quality == "partial_source":
        return f"已收錄 {count} 件；partial_source：來源僅部分涵蓋，非完整總數。"
    if quality == "incomplete_assignment":
        return f"已分配 {count} 件；incomplete_assignment：行政區分配不完整，非完整總數。"
    return f"{count} 件" + ("（有效觀測零值）。" if count == 0 else "（資料完整）。")


def event_answer(plan: RoutePlan, evidence: list[dict]) -> str:
    trend = next(item for item in evidence if item["tool"] == "get_crime_trend")
    args, data = trend["arguments"], trend["result"]
    lines = [f"{args['county']}{args['district']}｜{plan.years[0]}年事件背景；初步行政區統計，非正式年度統計。"]
    # The tool already computes the selected-category aggregate and comparability.
    series = [data["aggregate"]] if data.get("aggregate") else data["crime_types"][:1]
    for entry in series:
        row = next(value for value in entry["values"] if value["year"] == plan.years[0])
        label = entry.get("crime_type") or entry.get("title") or crime_label(args["crime_types"])
        lines.append(f"{label}｜{row['year']}：{count_text(row)}")
        anomaly = next((v for v in entry.get("anomalies", []) if v["year"] == row["year"]), None)
        if anomaly and anomaly.get("yoy_comparable") and anomaly.get("yoy_change_percent") is not None:
            lines.append(f"{anomaly['previous_year']}：{anomaly['previous_year_count']} 件；年變動率 {anomaly['yoy_change_percent']:+.2f}%。")
        else:
            lines.append("年增減缺少可比較資料，不推算變化。")
    events = next(item["result"]["events"] for item in evidence if item["tool"] == "get_major_events")
    # Geographic relevance, not a claim about causal impact. Keep catalog order within ties.
    events = sorted(events, key=lambda e: (args["county"][:2] not in e["title"], e.get("scope") != "taiwan"))
    for event in events[:3]:
        lines.append(f"• {event['start_date']} {event['title']}；來源：{event['source_agency']} {event['source_url']}")
    if not events:
        lines.append("所選範圍無收錄事件；不代表當年沒有事件。")
    lines.append("時間重疊不代表因果關係，也不代表事件影響所選行政區。")
    return "\n".join(lines)


def deterministic_answer(plan: RoutePlan, evidence: list[dict]) -> str:
    if plan.intent == "event_context":
        return event_answer(plan, evidence)
    lines = ["以下依已查證的犯罪統計資料整理："]
    for item in evidence:
        name, args, data = item["tool"], item["arguments"], item["result"]
        if name == "query_crime_statistics":
            lines.append(f"{crime_label(args['crime_types'])}｜月份：{'、'.join(map(str, args['months']))}月｜初步行政區統計，非正式年度統計。")
            for row in data["rows"]:
                lines.append(f"{row['county']}{row['district']}｜{'、'.join(map(str, row['years']))}年{'合計' if len(row['years']) > 1 else ''}：{count_text(row)}")
                if args["metric"] == "rate":
                    lines.append(f"{data['scopes'][0]['rate_label']}：{row['rate']:.2f}；同樣受上述資料品質限制。" if row["rate"] is not None else "人口率未提供，不能解讀為零。")
                if row.get("display_warning"):
                    lines.append(row["display_warning"])
            for comparison in data.get("comparisons", []):
                if comparison["comparable"] and comparison["absolute_change"] is not None:
                    lines.append(f"{comparison['later_year']} 相較 {comparison['earlier_year']}，件數變化：{comparison['absolute_change']:+} 件。")
                    if comparison["percent_change"] is not None:
                        lines.append(f"變動率：{comparison['percent_change']:+.2f}%。")
                    else:
                        lines.append(comparison["display_message"])
                else:
                    lines.append("資料品質或涵蓋不同，不建議直接比較，未計算增減。")
        elif name == "get_crime_trend":
            lines.append(f"{args['county']}{args['district']}｜全年初步行政區趨勢（非正式年度統計）。")
            series = ([data["aggregate"]] if data.get("aggregate") else []) + data["crime_types"]
            for entry in series:
                lines.append(entry.get("crime_type") or entry.get("title") or crime_label(args["crime_types"]))
                for row in entry["values"]:
                    if plan.intent != "event_context" or row["year"] in plan.years:
                        lines.append(f"{row['year']}：{count_text(row)}")
                        if plan.intent == "event_context":
                            anomaly = next((value for value in entry.get("anomalies", []) if value["year"] == row["year"]), None)
                            if anomaly and anomaly.get("yoy_comparable") and anomaly.get("yoy_change_percent") is not None:
                                lines.append(f"{anomaly['previous_year']}：{anomaly['previous_year_count']} 件；後端計算年變動率 {anomaly['yoy_change_percent']:+.2f}%。")
                            elif anomaly:
                                lines.append("年增減缺少可比較資料，不推算變化。")
        elif name == "get_major_events":
            lines.append("固定重大事件目錄（僅供背景）：")
            for event in data["events"]:
                lines.append(f"{event['start_date']}～{event['end_date']}：{event['title']}。來源：{event['source_agency']} {event['source_url']}")
            if not data["events"]:
                lines.append("所選範圍無收錄事件；不代表當年沒有事件。")
            lines.append("時間重疊不代表因果關係，也不代表事件影響所選行政區。")
        elif name == "get_official_annual_statistics":
            lines.append(f"{'、'.join(args['counties'])}｜{'、'.join(map(str, args['years']))}年｜{crime_label(args['crime_types'])}")
            count = data["official_annual_county_count"]
            lines.append("正式年度值未提供或月份範圍不可比較，不能解讀為 0 件。" if count is None else f"縣市年度正式統計合計：{count} 件。")
            lines.append("此為獨立縣市正式統計，不分配至行政區，亦不混同初步行政區資料。")
    return "\n".join(lines)


def numbers_grounded(answer: str, evidence: list[dict]) -> bool:
    """Reject novel numeric claims, allowing formatting/rounding, not new arithmetic.

    This is a conservative extra guard, not a semantic fact-checker: labels and
    interpretation still depend on the system prompt and the returned evidence.
    """
    rows = [row for item in evidence if item["tool"] == "query_crime_statistics" for row in item["result"]["rows"]]
    if any(row["district_data_quality"] in ("partial_source", "incomplete_assignment") for row in rows):
        if not re.search(r"partial_source|incomplete_assignment|部分|不完整", answer):
            return False
    if len(rows) == 1 and (rows[0]["incident_count"] is None or rows[0]["district_data_quality"] in ("unavailable", "no_district_assignment")):
        if not re.search(r"unavailable|no_district_assignment|未提供|無.{0,8}(?:資料|分配)|不可得", answer):
            return False
        for match in re.finditer(r"(?:0|零)\s*件", answer):
            if not re.search(r"不能|不代表|不等於|不是|不可|無法", answer[max(0, match.start() - 18):match.start()]):
                return False
    allowed = {"0", "8", "10", "100000"}  # null != 0; eight categories; standard rate units
    def collect(value):
        if isinstance(value, bool) or value is None:
            return
        if isinstance(value, (int, float)):
            allowed.add(str(value))
            for places in range(5):
                allowed.add(f"{value:.{places}f}")
        elif isinstance(value, str):
            allowed.update(re.findall(r"\d+(?:\.\d+)?", value))
        elif isinstance(value, dict):
            for key, item in value.items():
                collect(item)
                if key == "district_assignment_rate" and isinstance(item, (int, float)):
                    collect(item * 100)  # display conversion of a validated fraction only
        elif isinstance(value, list):
            for item in value:
                collect(item)
    collect(evidence)
    text = re.sub(r"https?://\S+", "", answer)
    text = re.sub(r"(?m)^\s*\d+[.)、]\s*", "", text).replace(",", "")
    return all(number in allowed for number in re.findall(r"\d+(?:\.\d+)?", text))
