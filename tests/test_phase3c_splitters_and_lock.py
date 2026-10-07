from __future__ import annotations

import json
import subprocess
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app


ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "app" / "static"
CLIENT = TestClient(app)
ALL_MONTHS = "1,2,3,4,5,6,7,8,9,10,11,12"


def run_node(script: str, *paths: Path) -> dict:
    completed = subprocess.run(
        ["node", "-e", script, *(str(path) for path in paths)],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return json.loads(completed.stdout)


def test_vertical_and_horizontal_splitters_are_semantic_and_visible():
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    css = (STATIC / "styles.css").read_text(encoding="utf-8")
    assert 'id="verticalSplitter"' in html
    assert 'aria-orientation="vertical"' in html
    assert 'id="horizontalSplitter"' in html
    assert 'aria-orientation="horizontal"' in html
    assert ".splitter-vertical{cursor:col-resize}" in css
    assert ".splitter-horizontal{cursor:row-resize}" in css
    for control in (
        "maximizeLeft",
        "maximizeRight",
        "maximizeUp",
        "maximizeDownSplitter",
        "maximizeDown",
    ):
        assert f'id="{control}"' in html
    assert html.count('class="splitter-control"') == 4
    assert all('aria-pressed="false"' in html.split(f'id="{control}"', 1)[1].split(">", 1)[0] for control in (
        "maximizeLeft", "maximizeRight", "maximizeUp", "maximizeDownSplitter", "maximizeDown"
    ))


def test_down_maximize_control_is_discoverable_in_the_lower_tab_area():
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    css = (STATIC / "styles.css").read_text(encoding="utf-8")
    tabs_start = html.index('<div class="tabs"')
    tabs_end = html.index('<div class="tab-body"', tabs_start)
    tabs_markup = html[tabs_start:tabs_end]
    assert 'id="maximizeDown"' in tabs_markup
    assert 'class="lower-maximize-control"' in tabs_markup
    assert "▼ 放大下方" in tabs_markup
    assert ".lower-maximize-control{" in css
    assert '.lower-maximize-control[aria-pressed="true"]' in css


def test_all_four_maximize_modes_restore_exact_split_ratios_and_replace_conflicts():
    result = run_node(
        r"""
const layout = require(process.argv[1]);
const original = layout.create(0.413, 0.677);
const left = layout.toggleVertical(original, "left");
const leftRestored = layout.toggleVertical(left, "left");
const right = layout.toggleVertical(left, "right");
const rightRestored = layout.toggleVertical(right, "right");
const up = layout.toggleHorizontal(original, "up");
const upRestored = layout.toggleHorizontal(up, "up");
const down = layout.toggleHorizontal(up, "down");
const downRestored = layout.toggleHorizontal(down, "down");
const downFirst = layout.toggleHorizontal(original, "down");
const upFromDown = layout.toggleHorizontal(downFirst, "up");
process.stdout.write(JSON.stringify({original,left,leftRestored,right,rightRestored,up,upRestored,down,downRestored,downFirst,upFromDown}));
""",
        STATIC / "layout_state.js",
    )
    assert result["left"]["verticalMode"] == "left"
    assert result["leftRestored"]["verticalMode"] is None
    assert result["right"]["verticalMode"] == "right"
    assert result["rightRestored"]["verticalMode"] is None
    assert result["up"]["horizontalMode"] == "up"
    assert result["upRestored"]["horizontalMode"] is None
    assert result["down"]["horizontalMode"] == "down"
    assert result["downRestored"]["horizontalMode"] is None
    assert result["downFirst"]["horizontalMode"] == "down"
    assert result["upFromDown"]["horizontalMode"] == "up"
    for state in result.values():
        assert state["verticalRatio"] == 0.413
        assert state["horizontalRatio"] == 0.677


def test_maximize_css_collapses_only_the_requested_pane_and_keeps_internal_scrolling():
    css = (STATIC / "styles.css").read_text(encoding="utf-8")
    assert ".app-shell.layout-vertical-left .detail-panel{display:none}" in css
    assert ".app-shell.layout-vertical-right .map-panel{display:none}" in css
    assert ".app-shell.layout-horizontal-up .bottom-panel{display:none}" in css
    assert ".app-shell.layout-horizontal-down .main-content{display:none}" in css
    assert ".app-shell.layout-horizontal-down{grid-template-rows:78px 76px 0 14px minmax(0,1fr)}" in css
    assert ".main-content{grid-row:3;" in css
    assert "#horizontalSplitter{grid-row:4}" in css
    assert ".bottom-panel{grid-row:5;" in css
    assert ".detail-panel{min-width:0;min-height:0;overflow-y:auto" in css
    assert ".table-scroll{height:calc(100% - 40px)}" in css
    assert "html,body{margin:0;height:100%;overflow:hidden}" in css


def test_split_ratios_update_and_are_clamped_for_both_supported_viewports():
    result = run_node(
        r"""
const layout = require(process.argv[1]);
const result = {
  wideLeft: layout.fromPosition(50, 1414, "vertical"),
  wideRight: layout.fromPosition(1400, 1414, "vertical"),
  narrowLeft: layout.fromPosition(10, 1154, "vertical"),
  upperSmall: layout.fromPosition(10, 688, "horizontal"),
  lowerSmall: layout.fromPosition(680, 688, "horizontal"),
  verticalChanged: layout.fromPosition(800, 1414, "vertical"),
  horizontalChanged: layout.fromPosition(360, 688, "horizontal"),
};
process.stdout.write(JSON.stringify(result));
""",
        STATIC / "layout_state.js",
    )
    assert 0.30 <= result["wideLeft"] <= 0.31
    assert 0.69 <= result["wideRight"] <= 0.70
    assert result["narrowLeft"] >= 320 / 1154
    assert result["upperSmall"] >= 300 / 688
    assert result["lowerSmall"] <= 1 - 180 / 688
    assert result["verticalChanged"] != 0.54
    assert result["horizontalChanged"] != 0.62


def test_splitter_state_is_persistent_and_independent_of_filters():
    source = (STATIC / "app.js").read_text(encoding="utf-8")
    assert 'tigerCrimeStat.mainVerticalSplitRatio' in source
    assert 'tigerCrimeStat.mainHorizontalSplitRatio' in source
    assert "localStorage.setItem(VERTICAL_SPLIT_KEY" in source
    assert "localStorage.setItem(HORIZONTAL_SPLIT_KEY" in source
    for filter_update in (
        "state.years=selectedValues",
        "state.counties=selectedValues",
        "state.metric=event.target.value;refreshData()",
        "CrimeSelectionState.toggle(state.crimeTypes,item.value,state.meta.crime_types)",
        "state.sort=event.target.value;renderTable()",
    ):
        assert filter_update in source
    assert "setupSplitters();await refreshAll(true)" in source
    assert "togglePaneMaximize" in source
    assert '["maximizeDownSplitter","horizontal","down"]' in source
    assert '["maximizeDown","horizontal","down"]' in source
    assert '["maximizeDownSplitter",downActive]' in source
    assert '["maximizeDown",downActive]' in source
    assert "scheduleMapRefit()" in source


def test_map_handlers_are_hover_only_and_keep_async_scope_guards():
    source = (STATIC / "app.js").read_text(encoding="utf-8")
    assert 'addEventListener("mouseenter"' in source
    assert 'addEventListener("mousemove"' in source
    assert "clickedDistrict=!wasDragging" in source
    assert 'addEventListener("dblclick"' not in source
    assert 'viewport.addEventListener("pointerenter",handleMapPointerEnter)' in source
    assert 'viewport.addEventListener("pointerleave",handleMapPointerLeave)' in source
    assert "lockedDistrict" not in source
    assert "state.suppressMapHover=true;" in source
    assert "group.replaceChildren();" in source
    assert "scheduleMapRefit()" in source
    assert "owner.requestId!==state.trendRequestId" in source
    assert "beginTrendRequest()" in source


def test_resize_does_not_change_table_data_and_taichung_still_has_all_rows():
    response = CLIENT.get(
        "/api/county/臺中市/map",
        params={
            "year": 2025,
            "months": ALL_MONTHS,
            "crime_type": "all",
            "metric": "rate",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["district_count"] == len(body["districts"]) == 29
    assert len({row["district"] for row in body["districts"]}) == 29


def test_map_refit_uses_live_container_dimensions_and_retains_state_guards():
    source = (STATIC / "app.js").read_text(encoding="utf-8")
    assert "stage.clientWidth" in source and "stage.clientHeight" in source
    assert 'setAttribute("viewBox"' in source
    assert "requestAnimationFrame" in source
    assert "MapProjection.fit(state.geography.features" in source
    assert "validateTrendResponse(trends)" in source

