"""Conservative command fast path layered over the existing statistics router."""
import re
import unicodedata

from app.services.chat_router import ALL_MONTHS, ALL_YEARS, THEFT_CRIME_TYPES, RoutePlan, ToolQuery, _district_entities, _entities, _periods, route_message
from app.services.dashboard_actions import UpdateView, view_actions
from app.services.data_service import service
from app.services.scope_delta import conversation_scope as resolve_conversation_scope, extract_scope_delta


def _command(message, scope):
    text = re.sub(r"\s+", "", unicodedata.normalize("NFKC", message)).replace("台", "臺")
    crime_request = "|".join(re.escape(name) for name in sorted([*service.crime_types, "竊盜"], key=len, reverse=True))
    bare_crime_request = re.fullmatch(rf"(?:{crime_request})(?:案件|趨勢)?", text)
    supported_year = "(?:" + "|".join(map(str, ALL_YEARS)) + ")"
    standalone_year_selection = re.fullmatch(rf"{supported_year}年?(?:(?:跟|、|,|和|與|及){supported_year}年?)*", text)
    clear_statistic_question = bool(re.search(r"有幾件|幾件|是多少|多少|案件數|件數", text))
    if not re.match(r"^(?:請)?(?:幫我看|改看|改成|看|查詢|查|比較|切換|顯示|開啟)", text) and not bare_crime_request and not standalone_year_selection and not clear_statistic_question:
        return None
    periods = _periods(text)
    if periods is None:
        return None
    text, years, months = periods
    text, counties = _entities(text, service.county_districts)
    previous = scope.get("current_district")
    text, districts, _used_alias, ambiguous_alias = _district_entities(
        text,
        explicit_counties=counties,
        selected_counties=scope.get("selected_counties") or [],
        current_district=previous,
    )
    if ambiguous_alias:
        return None
    aliases = {c: c for c in service.crime_types}
    aliases.update({"組織犯罪": "組織犯罪防制條例", "全部案類": "all"})
    text, crime_names = _entities(text, aliases)
    explicit_crimes = [aliases[c] for c in crime_names]
    generic_theft = "竊盜" in text
    if generic_theft and explicit_crimes:
        return None
    if generic_theft:
        text = text.replace("竊盜", " ")
    crimes = list(THEFT_CRIME_TYPES) if generic_theft else explicit_crimes
    if len(districts) > 1 or len(counties) != len(set(counties)) or len(crimes) != len(set(crimes)):
        return None
    trend = "趨勢" in text
    panel = "district_trend" if trend else "ranking" if "排名" in text else "context" if "事件背景" in text else "map"
    if "各行政區趨勢" in text:
        panel = "all_district_trends"
    metric = "rate" if re.search(r"每十萬人口|案件率|發生率", text) else "count" if "案件數" in text else scope["metric"]
    # A fresh explicit view uses counts; subsequent year/crime changes preserve metric.
    if districts and not re.search(r"每十萬人口|案件率|發生率", text):
        metric = "count"
    residual = re.sub(r"各行政區趨勢|十年趨勢|趨勢|事件背景|每十萬人口|案件率|發生率|有幾件|幾件|是多少|多少|案件數|件數|案件|幫我看|改看|改成|查詢|切換|顯示|開啟|比較|排名|地圖|請|查|看|跟|和|與|及|年|的|有|嗎", "", text)
    if re.sub(r"[?？。，、,\s]", "", residual):
        return None
    if not (years or months or counties or districts or crimes or re.search(r"趨勢|排名|地圖|背景|案件率|發生率|案件數|每十萬人口", text)):
        return None
    if counties:
        # Explicit county-only requests must not retain a district from older context.
        resolved_counties, resolved_districts = counties, districts
    elif districts:
        candidates = [c for c in scope["selected_counties"] if districts[0] in service.county_districts[c]]
        if not candidates:
            candidates = [c for c, ds in service.county_districts.items() if districts[0] in ds]
        if len(candidates) != 1:
            return None
        resolved_counties, resolved_districts = candidates, districts
    else:
        if scope.get("_ambiguous_geography"):
            return None
        resolved_counties = [previous["county"]] if previous else scope["selected_counties"]
        resolved_districts = [previous["district"]] if previous else []
    if trend and ((years and years != ALL_YEARS) or (months and months != ALL_MONTHS)):
        return None
    if panel in ("district_trend", "context") and not resolved_districts:
        return None
    years = ALL_YEARS if trend else years or scope["selected_years"]
    months = ALL_MONTHS if trend else months or scope["selected_months"]
    crimes = crimes or scope["selected_crime_types"]
    if "all" in crimes:
        if len(crimes) != 1:
            return None
        crimes = list(service.crime_types)
    try:
        view = UpdateView(counties=resolved_counties, districts=resolved_districts, years=years,
                          months=months, crime_types=crimes, metric=metric, panel=panel)
        actions = view_actions(view, scope)
    except (ValueError, KeyError):
        return None
    if trend:
        queries = (ToolQuery("get_crime_trend", {"county": view.counties[0], "district": view.districts[0], "crime_types": crimes}),)
    else:
        queries = (ToolQuery("query_crime_statistics", {**view.model_dump(exclude={"panel"}),
                    "group_by": "year" if len(years) == 2 and view.districts else "district",
                    "limit": 2 if len(years) == 2 and view.districts else 1 if view.districts else 5}),)
    return RoutePlan("trend" if trend else "comparison" if len(years) == 2 and view.districts else "statistic", queries, tuple(years), tuple(actions))


def conversation_scope(history, scope):
    return resolve_conversation_scope(history, scope)


def _delta_plan(delta):
    view = delta.view
    trend = view.panel in ("district_trend", "all_district_trends")
    if trend:
        if not view.districts:
            return None
        queries = (ToolQuery("get_crime_trend", {"county": view.counties[0], "district": view.districts[0],
                                                  "crime_types": list(view.crime_types)}),)
        intent = "trend"
    else:
        comparison = len(view.years) == 2 and bool(view.districts)
        queries = (ToolQuery("query_crime_statistics", {**view.model_dump(exclude={"panel"}),
                    "group_by": "year" if comparison else "district",
                    "limit": 2 if comparison else 1 if view.districts else 5}),)
        intent = "comparison" if comparison else "statistic"
    return RoutePlan(intent, queries, tuple(view.years), delta.actions)


def route_dashboard_message(message, scope, history=(), delta=None):
    """Answer routing consumes, but does not own, deterministic scope actions."""
    resolved = conversation_scope(history, scope)
    delta = delta or extract_scope_delta(message, scope, history)
    legacy = _command(message, resolved)
    if legacy:
        return RoutePlan(legacy.intent, legacy.tools, legacy.years,
                         delta.actions if delta else legacy.dashboard_actions)
    if delta and delta.clean_request:
        return _delta_plan(delta)
    return None
