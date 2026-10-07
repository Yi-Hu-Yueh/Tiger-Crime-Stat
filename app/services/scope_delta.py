"""Deterministic Dashboard scope extraction, independent of answer routing."""
from dataclasses import dataclass
import re
import unicodedata

from app.services.chat_router import ALL_MONTHS, ALL_YEARS, THEFT_CRIME_TYPES, _entities, _periods
from app.services.dashboard_actions import UpdateView, validate_actions
from app.services.data_service import service


@dataclass(frozen=True)
class ScopeDelta:
    """A fully resolved and validated Dashboard transaction."""

    view: UpdateView
    actions: tuple[dict, ...]
    explicit: frozenset[str]
    clean_request: bool


def normalize(message):
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", message)).replace("台", "臺")


def _extract(message, scope):
    """Extract high-confidence scope values without choosing an answer branch."""
    original = normalize(message)
    periods = _periods(original)
    if periods is None:
        return None
    text, years, months = periods
    explicit = set()
    if years:
        explicit.add("years")
    if months:
        explicit.add("months")

    text, counties = _entities(text, service.county_districts)
    text, districts = _entities(text, {district for values in service.county_districts.values() for district in values})
    if counties:
        explicit.add("counties")
    if districts:
        explicit.add("district")
    if len(counties) != len(set(counties)) or len(districts) != len(set(districts)) or len(districts) > 1:
        return None

    aliases = {name: name for name in service.crime_types}
    aliases.update({"組織犯罪": "組織犯罪防制條例", "全部案類": "all", "所有案類": "all"})
    text, crime_names = _entities(text, aliases)
    explicit_crimes = [aliases[name] for name in crime_names]
    generic_theft = "竊盜" in text
    if generic_theft:
        text = text.replace("竊盜", " ")
    if generic_theft and explicit_crimes:
        return None
    crimes = list(THEFT_CRIME_TYPES) if generic_theft else explicit_crimes
    if crimes:
        explicit.add("crime_types")
    if len(explicit_crimes) != len(set(explicit_crimes)) or ("all" in explicit_crimes and len(explicit_crimes) != 1):
        return None

    rate_metric = bool(re.search(r"每十萬人口|每10萬人口|案件率|發生率", original))
    count_metric = bool(re.search(r"案件數|件數|有幾件|幾件|是多少|多少", original))
    if rate_metric and count_metric:
        return None
    metric = "rate" if rate_metric else "count" if count_metric else scope["metric"]
    if rate_metric or count_metric:
        explicit.add("metric")

    panel, panel_explicit = "map", False
    if "各行政區趨勢" in original:
        panel, panel_explicit = "all_district_trends", True
    elif re.search(r"十年趨勢|趨勢", original):
        panel, panel_explicit = "district_trend", True
    elif "排名" in original:
        panel, panel_explicit = "ranking", True
    elif re.search(r"事件背景|重大事件|背景", original):
        panel, panel_explicit = "context", True
    elif "地圖" in original:
        panel, panel_explicit = "map", True
    if panel_explicit:
        explicit.add("panel")
    if not explicit:
        return None

    previous = scope.get("current_district")
    selected_counties = list(scope["selected_counties"])
    if counties:
        resolved_counties = counties
        if districts:
            if len(counties) != 1 or districts[0] not in service.county_districts.get(counties[0], ()):
                return None
            resolved_districts = districts
        elif previous and len(counties) == 1 and previous["county"] == counties[0]:
            resolved_districts = [previous["district"]]
        else:
            resolved_districts = []
    elif districts:
        district = districts[0]
        contextual = []
        if previous and district in service.county_districts.get(previous["county"], ()):
            contextual = [previous["county"]]
        if not contextual:
            contextual = [county for county in selected_counties if district in service.county_districts.get(county, ())]
        if len(contextual) != 1:
            global_candidates = [county for county, values in service.county_districts.items() if district in values]
            if contextual or len(global_candidates) != 1:
                return None
            contextual = global_candidates
        resolved_counties, resolved_districts = contextual, districts
    else:
        if scope.get("_ambiguous_geography"):
            return None
        resolved_counties = [previous["county"]] if previous else selected_counties
        resolved_districts = [previous["district"]] if previous else []

    trend = panel in ("district_trend", "all_district_trends")
    if trend and ((years and years != ALL_YEARS) or (months and months != ALL_MONTHS)):
        return None
    if panel in ("district_trend", "context") and not resolved_districts:
        return None
    resolved_years = list(ALL_YEARS) if trend else years or list(scope["selected_years"])
    resolved_months = list(ALL_MONTHS) if trend else months or list(scope["selected_months"])
    resolved_crimes = crimes or list(scope["selected_crime_types"])
    if "all" in resolved_crimes:
        if len(resolved_crimes) != 1:
            return None
        resolved_crimes = list(service.crime_types)

    request_prefix = bool(re.match(r"^(?:請)?(?:幫我看|改看|改成|看|查詢|查|比較|切換|顯示|開啟)", original))
    if districts and request_prefix and not (rate_metric or count_metric):
        metric = "count"

    unmatched_geography = re.search(r"[\u4e00-\u9fff]{1,6}(?:區|鄉|鎮|市)", text)
    if unmatched_geography and unmatched_geography.group() not in {"這區", "縣市", "行政區"}:
        return None

    try:
        view = UpdateView(counties=resolved_counties, districts=resolved_districts,
                          years=resolved_years, months=resolved_months,
                          crime_types=resolved_crimes, metric=metric, panel=panel)
        actions = [{"type": "set_dashboard_scope", **view.model_dump(exclude={"panel"})}]
        if view.districts:
            actions.append({"type": "select_district", "county": view.counties[0], "district": view.districts[0]})
        if panel_explicit:
            actions.append({"type": "open_panel", "panel": panel})
        actions = validate_actions(actions, scope)
    except (ValueError, KeyError, TypeError):
        return None

    residual = re.sub(
        r"各行政區趨勢|十年趨勢|趨勢|重大事件|事件背景|背景|每十萬人口|每10萬人口|案件率|發生率|"
        r"有幾件|幾件|是多少|多少|案件數|件數|案件|幫我看|改看|改成|查詢|切換|顯示|開啟|比較|排名|地圖|"
        r"請問|請|查|看|跟|和|與|及|年|月|的|有|嗎|全年", "", text)
    clean_request = not bool(re.sub(r"[?？。，、,\s]", "", residual))
    return ScopeDelta(view, tuple(actions), frozenset(explicit), clean_request)


def conversation_scope(history, scope):
    """Replay only validated user deltas; assistant prose is never scope evidence."""
    result = dict(scope)
    geography_names = set(service.county_districts) | {district for values in service.county_districts.values() for district in values}
    for turn in history:
        if turn.get("role") != "user":
            continue
        message = turn["content"]
        delta = _extract(message, result)
        if delta:
            view = delta.view
            result.update({"selected_counties": list(view.counties), "selected_years": list(view.years),
                           "selected_months": list(view.months), "selected_crime_types": list(view.crime_types),
                           "metric": view.metric,
                           "current_district": {"county": view.counties[0], "district": view.districts[0]}
                           if len(view.counties) == len(view.districts) == 1 else None})
            result.pop("_ambiguous_geography", None)
        elif any(name in normalize(message) for name in geography_names):
            result["current_district"] = None
            result["_ambiguous_geography"] = True
    return result


def extract_scope_delta(message, scope, history=()):
    """Resolve explicit current-message values over conversation and UI context."""
    return _extract(message, conversation_scope(history, scope))


def extract_dashboard_actions(message, scope, history=()):
    delta = extract_scope_delta(message, scope, history)
    return delta.actions if delta else ()
