"""Conservative deterministic intent parsing; no network and no statistical arithmetic.

Only known entities, explicit date patterns and a small request vocabulary are
consumed. Any unconsumed text/unsupported condition sends the original question
to the existing LLM tool loop, rather than silently discarding a constraint.
"""
from dataclasses import dataclass
import re
import unicodedata

from app.services.data_service import service
from app.services.llm_tools import TOOL_REGISTRY

ALL_MONTHS = list(range(1, 13))
ALL_YEARS = list(range(2016, 2026))
THEFT_CRIME_TYPES = ["住宅竊盜", "汽車竊盜", "機車竊盜"]


@dataclass(frozen=True)
class ToolQuery:
    name: str
    arguments: dict


@dataclass(frozen=True)
class RoutePlan:
    intent: str
    tools: tuple[ToolQuery, ...]
    years: tuple[int, ...]
    dashboard_actions: tuple[dict, ...] = ()


def _entities(text, names):
    matches = []
    pattern = "|".join(re.escape(name) for name in sorted(names, key=len, reverse=True))
    def consume(match):
        matches.append(match.group())
        return " "
    return re.sub(pattern, consume, text), matches


def _periods(text):
    """Reject mixed year-specific month windows; do not create Cartesian guesses."""
    if re.search(r"(?:19|20)\d{2}年?\D*?\d{1,2}月.*(?:19|20)\d{2}", text):
        return None
    years, months = [], []
    invalid = False
    def year_range(match):
        nonlocal invalid
        start, end = map(int, match.groups())
        if not 2016 <= start <= end <= 2025:
            invalid = True
        else:
            years.extend(range(start, end + 1))
        return " "
    text = re.sub(r"(?<!\d)((?:19|20)\d{2})年?(?:至|到|[-–—~～])((?:19|20)\d{2})(?!\d)年?", year_range, text)
    def year(match):
        nonlocal invalid
        value = int(match.group(1))
        if value not in ALL_YEARS:
            invalid = True
        years.append(value)
        return " "
    text = re.sub(r"(?<!\d)((?:19|20)\d{2})(?!\d)年?", year, text)
    def month_range(match):
        nonlocal invalid
        start, end = map(int, match.groups())
        if not 1 <= start <= end <= 12:
            invalid = True
        else:
            months.extend(range(start, end + 1))
        return " "
    text = re.sub(r"(?<!\d)(\d{1,2})月?(?:至|到|[-–—~～])(\d{1,2})月", month_range, text)
    def month(match):
        nonlocal invalid
        values = [int(value) for value in re.split(r"[、,及和]", match.group(1))]
        if any(value not in ALL_MONTHS for value in values):
            invalid = True
        months.extend(values)
        return " "
    text = re.sub(r"(?<!\d)(\d{1,2}(?:[、,及和]\d{1,2})*)月", month, text)
    full_year = "全年" in text
    if full_year and months:
        invalid = True
    if full_year:
        months = ALL_MONTHS.copy()
        text = text.replace("全年", " ")
    return None if invalid else (text, sorted(set(years)), sorted(set(months)))


def conversation_geography(history, scope):
    """Replay explicit user geography only; ambiguous turns invalidate older context.

    Assistant prose can mention event locations, so it is never geography evidence.
    A location is established only by a request our conservative parser understands.
    """
    current, ambiguous = None, False
    names = set(service.county_districts) | {d for ds in service.county_districts.values() for d in ds}
    for turn in history:
        if turn.get("role") != "user":
            continue
        message = unicodedata.normalize("NFKC", turn["content"]).replace("台", "臺")
        if not any(name in message for name in names):
            continue
        replay_scope = {**scope, "current_district": current}
        if current:
            replay_scope["selected_counties"] = [current["county"]]
        plan = route_message(message, replay_scope)
        current, ambiguous = None, True
        if plan:
            args = plan.tools[0].arguments
            if "district" in args:
                current = {"county": args["county"], "district": args["district"]}
            elif args.get("districts") and len(args["counties"]) == len(args["districts"]) == 1:
                current = {"county": args["counties"][0], "district": args["districts"][0]}
            ambiguous = current is None
    return current, ambiguous


def route_message(message: str, scope: dict, history=()) -> RoutePlan | None:
    text = re.sub(r"\s+", "", unicodedata.normalize("NFKC", message)).replace("台", "臺")
    # Relative periods, exclusions, causal demands and additional dimensions are
    # intentionally not inferred from a keyword match or conversation history.
    if re.search(r"去年|今年|前年|上個|最近|近十年|前十年|上半年|下半年|季度|第[一二三四1-4]季|除了|不含|(?<!是)不是|導致|造成|證明|為什麼|為何|暴力犯罪", text):
        return None
    original = text
    event = bool(re.search(r"重大事件|事件背景|背景", text))
    trend = bool(re.search(r"趨勢|十年", text))
    comparison = bool(re.search(r"差多少|差幾件|相差|比較|增減|增加多少|減少多少", text))
    official = bool(re.search(r"正式|官方年度", text))
    availability = bool(re.search(r"資料|可用|未提供|是否|是不是|為零|為0|是零|是0", text))
    statistic = bool(re.search(r"幾件|多少|案件數|案件|件數|每十萬人口|每10萬人口|發生率|案件率", text))
    if not any((event, trend, comparison, official, availability, statistic)):
        return None
    if (event and (comparison or official)) or (trend and (comparison or official)):
        return None
    if comparison and re.search(r"每十萬人口|每10萬人口|發生率|案件率", text):
        return None  # Existing two-year comparisons are counts, not rate differences.
    periods = _periods(text)
    if periods is None:
        return None
    text, explicit_years, explicit_months = periods
    years = explicit_years or list(scope["selected_years"])
    months = explicit_months or list(scope["selected_months"])
    text, counties = _entities(text, service.county_districts)
    text, districts = _entities(text, {name for names in service.county_districts.values() for name in names})
    if len(counties) > 1 or len(districts) > 1:
        return None
    crime_aliases = {name: name for name in service.crime_types}
    crime_aliases.update({"組織犯罪": "組織犯罪防制條例", "全部案類": "all", "所有案類": "all"})
    text, crime_mentions = _entities(text, crime_aliases)
    explicit_crimes = [crime_aliases[name] for name in crime_mentions]
    generic_theft = "竊盜" in text
    if generic_theft and explicit_crimes:
        return None
    if generic_theft:
        text = text.replace("竊盜", " ")
    crimes = list(THEFT_CRIME_TYPES) if generic_theft else explicit_crimes
    if len(explicit_crimes) != len(set(explicit_crimes)) or ("all" in explicit_crimes and len(explicit_crimes) != 1):
        return None
    if len(explicit_crimes) > 1 and not re.search(r"合計|總計", original):
        return None
    crimes = crimes or list(scope["selected_crime_types"])

    # Explicit geography overrides UI selections, but never invents a district.
    recent, ambiguous = conversation_geography(history, scope) if history else (None, False)
    current = recent or (None if ambiguous else scope.get("current_district"))
    county, district = (counties[0] if counties else None), (districts[0] if districts else None)
    if official:
        if district or "這區" in text or "目前行政區" in text:
            return None
        resolved_counties = counties or list(scope["selected_counties"])
    else:
        if district:
            candidates = [county] if county else ([recent["county"]] if recent else scope["selected_counties"])
            candidates = [name for name in candidates if district in service.county_districts[name]]
            if not candidates and not county:
                candidates = [name for name, names in service.county_districts.items() if district in names]
            if len(candidates) != 1:
                return None
            county = candidates[0]
        else:
            # A named county alone is a county query, not a request for its UI district.
            if not current or (county and not re.search(r"這區|目前行政區|當前行政區", text)):
                return None
            if county and county != current["county"]:
                return None
            county, district = current["county"], current["district"]
        if county not in service.county_districts or district not in service.county_districts[county]:
            return None
        resolved_counties = [county]

    intent = "event_context" if event else "trend" if trend else "comparison" if comparison else "official" if official else "availability" if availability else "statistic"
    if comparison and len(years) != 2:
        return None
    if not comparison and not event and not trend and len(explicit_years) > 1 and not re.search(r"合計|總計", original):
        return None
    if event and len(years) != 1:
        return None
    if (trend or event) and months != ALL_MONTHS:
        return None  # Existing trend tool is full-year only, never discard a month filter.
    if trend and explicit_years and explicit_years != ALL_YEARS:
        return None
    event_scope = "all"
    if event:
        if "臺灣" in text and "全球" not in text:
            event_scope = "taiwan"
        elif "全球" in text and "臺灣" not in text:
            event_scope = "global"
        text = text.replace("臺灣", " ").replace("全球", " ")
    # Remove only expressions whose semantics were accounted for above.
    if availability:
        text = re.sub(r"(?:是不是|是否為|是|為)(?:0|零)件?", " ", text)
    words = ["你好", "請問", "請幫我", "幫我", "請", "查詢", "查", "我想知道", "想知道", "告訴我", "目前行政區", "當前行政區", "這區",
             "十年", "趨勢", "重大事件", "事件背景", "有哪些", "哪些", "可作為", "作為", "背景", "案件變化", "變化",
             "相差", "差多少", "差幾件", "增加多少", "減少多少", "增減", "比較", "有幾件", "幾件", "是多少", "多少",
             "每十萬人口", "每10萬人口", "發生率", "案件率", "案件數", "案件", "件數", "資料", "可用", "未提供", "是否有", "是否", "是不是",
             "正式年度統計", "正式統計", "官方年度統計", "正式", "年度", "統計", "合計", "總計", "跟", "和", "與", "及", "的", "有", "是", "為", "嗎", "件", "年"]
    residual = re.sub("|".join(re.escape(word) for word in sorted(words, key=len, reverse=True)), "", text)
    if re.sub(r"[\s?？。，、,;；:：()（）]", "", residual):
        return None
    metric = "rate" if re.search(r"每十萬人口|每10萬人口|發生率|案件率", original) else "count" if statistic else scope["metric"]
    filters = {"counties": resolved_counties, "years": years, "months": months, "crime_types": crimes}
    if official:
        queries = [ToolQuery("get_official_annual_statistics", filters)]
    elif trend or event:
        queries = [ToolQuery("get_crime_trend", {"county": county, "district": district, "crime_types": crimes})]
        if event:
            queries.append(ToolQuery("get_major_events", {"years": years, "scope": event_scope}))
    else:
        queries = [ToolQuery("query_crime_statistics", {**filters, "districts": [district], "metric": metric,
            "group_by": "year" if comparison else "district", "limit": 2 if comparison else 1})]
    try:
        for query in queries:
            TOOL_REGISTRY[query.name][0].model_validate(query.arguments)
    except (ValueError, KeyError, TypeError):
        return None
    return RoutePlan(intent, tuple(queries), tuple(years))
