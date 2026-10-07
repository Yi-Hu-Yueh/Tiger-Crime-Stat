"""Allowlisted dashboard commands. No executable content or statistical writes."""
from typing import Annotated, Literal

from pydantic import Field, TypeAdapter, model_validator

from app.services.data_service import service
from app.services.llm_tools import Filters, Name, StrictModel

Panel = Literal["map", "district_trend", "all_district_trends", "ranking", "context"]


class ViewScope(Filters):
    districts: Annotated[list[Name], Field(max_length=1)]
    metric: Literal["count", "rate"]

    @model_validator(mode="after")
    def validate_view(self):
        for values in (self.counties, self.districts, self.years, self.months, self.crime_types):
            if len(values) != len(set(values)):
                raise ValueError("篩選值不可重複")
        if "all" in self.crime_types:
            raise ValueError("Dashboard 案類須使用既有八類名稱")
        if self.districts and (len(self.counties) != 1 or self.districts[0] not in service.county_districts[self.counties[0]]):
            raise ValueError("請提供單一且相符的縣市及行政區")
        return self


class SetScope(ViewScope):
    type: Literal["set_dashboard_scope"]


class SelectDistrict(StrictModel):
    type: Literal["select_district"]
    county: Name
    district: Name

    @model_validator(mode="after")
    def validate_district(self):
        if self.district not in service.county_districts.get(self.county, ()):
            raise ValueError("行政區與縣市不相符")
        return self


class SetMetric(StrictModel):
    type: Literal["set_metric"]
    metric: Literal["count", "rate"]


class OpenPanel(StrictModel):
    type: Literal["open_panel"]
    panel: Panel


Action = Annotated[SetScope | SelectDistrict | SetMetric | OpenPanel, Field(discriminator="type")]
ACTION_SET = TypeAdapter(Annotated[list[Action], Field(min_length=1, max_length=4)])


def validate_actions(actions, current_scope):
    """Validate the whole transaction, including relationships across actions."""
    parsed = ACTION_SET.validate_python(actions)
    if len({a.type for a in parsed}) != len(parsed):
        raise ValueError("動作類型不可重複")
    scope_action = next((a for a in parsed if isinstance(a, SetScope)), None)
    counties = scope_action.counties if scope_action else current_scope["selected_counties"]
    selected = next((a for a in parsed if isinstance(a, SelectDistrict)), None)
    if selected:
        if selected.county not in counties:
            raise ValueError("選取行政區不在本次縣市範圍")
        if scope_action and (len(counties) != 1 or scope_action.districts != [selected.district]):
            raise ValueError("行政區動作與範圍互相衝突")
    metric = next((a for a in parsed if isinstance(a, SetMetric)), None)
    if metric and scope_action and metric.metric != scope_action.metric:
        raise ValueError("指標動作互相衝突")
    return [a.model_dump() for a in parsed]


class UpdateView(ViewScope):
    panel: Panel = "map"


def view_actions(view, scope):
    values = view.model_dump(exclude={"panel"})
    actions = [{"type": "set_dashboard_scope", **values}]
    if view.districts:
        actions.append({"type": "select_district", "county": view.counties[0], "district": view.districts[0]})
    actions.append({"type": "open_panel", "panel": view.panel})
    return validate_actions(actions, scope)


ACTION_TOOL = {"type": "function", "function": {
    "name": "update_dashboard_view",
    "description": "僅在使用者要求看、改看或同步儀表板時使用。回傳待套用的結構化範圍及已查證統計；不執行程式。明示條件優先於最近明確對話，再用儀表板。多縣市不可繼承單一行政區；不確定時先詢問。",
    "parameters": UpdateView.model_json_schema(),
}}
