from __future__ import annotations

import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "app" / "static"


def interaction_scenario() -> dict:
    script = r"""
const selection = require(process.argv[1]);
const A = selection.identity("臺中市", "北屯區");
const B = selection.identity("臺中市", "西屯區");
const C = selection.identity("臺中市", "南屯區");
const display = (hovered, selected, pinned) => selection.displayedIdentity(hovered, selected, pinned);
process.stdout.write(JSON.stringify({
  hoverA: display(A, null, false),
  hoverB: display(B, null, false),
  clickA: display(A, A, true),
  pinnedHoverB: display(B, A, true),
  pinnedHoverC: display(C, A, true),
  pinnedAfterZoom: display(C, A, true),
  pinnedAfterPan: display(C, A, true),
  pinnedAfterScroll: display(C, A, true),
  pinnedAfterMonth: display(C, A, true),
  pinnedAfterCrime: display(C, A, true),
  replaceWithB: display(C, B, true),
  afterLeave: display(null, A, true),
  reenterB: display(B, A, true),
  afterToggleOff: display(B, null, false),
  moveC: display(C, null, false),
  staleHoverCannotApply: selection.canApplyDetail(B, B, A, true),
  pinnedRequestCanApply: selection.canApplyDetail(A, B, A, true),
}));
"""
    completed = subprocess.run(
        ["node", "-e", script, str(STATIC / "selection_state.js")],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return json.loads(completed.stdout)


def reentry_render_scenario() -> dict:
    script = r"""
const fs = require("fs");
const vm = require("vm");
const selection = require(process.argv[1]);
const source = fs.readFileSync(process.argv[2], "utf8");
const viewport = {contains: element => Boolean(element && element.isDistrict)};
const pinBadge = {hidden: false};
const tooltip = {hidden: false};
const makePath = district => ({
  isDistrict: true,
  dataset: {county: "臺中市", district},
  closest: selector => selector === ".district-shape" ? makePath.cache[district] : null,
});
makePath.cache = {};
for (const district of ["北屯區", "西屯區", "南屯區", "太平區"]) makePath.cache[district] = makePath(district);
const context = {
  DistrictSelectionState: selection,
  DashboardLayoutState: {create: () => ({verticalRatio:.54,horizontalRatio:.62,verticalMode:null,horizontalMode:null})},
  MapNavigation: {},
  MapProjection: {},
  Intl,
  URLSearchParams,
  console,
  innerWidth: 1400,
  innerHeight: 900,
  cancelAnimationFrame: () => {},
  requestAnimationFrame: callback => { callback(); return 1; },
  fetch: async () => { throw new Error("unexpected fetch"); },
  hit: null,
};
context.document = {
  getElementById: id => ({mapViewport: viewport, pinBadge, mapTooltip: tooltip}[id] || {}),
  querySelectorAll: () => [],
  querySelector: () => ({}),
  elementFromPoint: () => context.hit,
  addEventListener: () => {},
};
context.globalThis = context;
vm.createContext(context);
vm.runInContext(source, context);
vm.runInContext(`
  renderTable=()=>{};
  updateMapSelectionClasses=()=>{};
  showTooltip=()=>{};
  loadDistrictExtras=()=>{};
  renderDetail=row=>{globalThis.rendered={county:row.county,district:row.district}};
  state.map={districts:["北屯區","西屯區","南屯區","太平區"].map(district=>({county:"臺中市",district}))};
  state.selectedDistrict=identity("臺中市","北屯區");
  state.hoveredDistrict=identity("臺中市","西屯區");
  state.isDistrictPinned=true;
  globalThis.rendered=identity("臺中市","北屯區");
`, context);
vm.runInContext('handleMapPointerLeave()', context);
context.hit = makePath.cache["西屯區"];
vm.runInContext('handleMapPointerEnter({clientX:50,clientY:60})', context);
const first = JSON.parse(vm.runInContext('JSON.stringify({active:activeIdentity(),rendered:globalThis.rendered,pinned:state.isDistrictPinned,selected:state.selectedDistrict,badgeHidden:document.getElementById("pinBadge").hidden})', context));
context.hit = makePath.cache["南屯區"];
vm.runInContext('handleMapPointerMove({clientX:70,clientY:80})', context);
const moved = JSON.parse(vm.runInContext('JSON.stringify({active:activeIdentity(),rendered:globalThis.rendered})', context));
vm.runInContext('toggleDistrictPin(state.map.districts.find(row=>row.district==="北屯區"))', context);
const unpinned = JSON.parse(vm.runInContext('JSON.stringify({active:activeIdentity(),rendered:globalThis.rendered,pinned:state.isDistrictPinned,selected:state.selectedDistrict})', context));
vm.runInContext('pinDistrict(state.map.districts.find(row=>row.district==="南屯區"))', context);
vm.runInContext('handleMapPointerLeave()', context);
context.hit = makePath.cache["太平區"];
vm.runInContext('handleMapPointerEnter({clientX:90,clientY:100})', context);
const second = JSON.parse(vm.runInContext('JSON.stringify({active:activeIdentity(),rendered:globalThis.rendered,pinned:state.isDistrictPinned,selected:state.selectedDistrict})', context));
context.hit = null;
vm.runInContext('handleMapPointerEnter({clientX:5,clientY:5})', context);
const empty = JSON.parse(vm.runInContext('JSON.stringify({active:activeIdentity(),pinned:state.isDistrictPinned,selected:state.selectedDistrict})', context));
process.stdout.write(JSON.stringify({first,moved,unpinned,second,empty}));
"""
    completed = subprocess.run(
        ["node", "-e", script, str(STATIC / "selection_state.js"), str(STATIC / "app.js")],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return json.loads(completed.stdout)


def test_exact_hover_pin_leave_and_reentry_priority_sequence():
    result = interaction_scenario()
    a = {"county": "臺中市", "district": "北屯區"}
    b = {"county": "臺中市", "district": "西屯區"}
    c = {"county": "臺中市", "district": "南屯區"}
    assert result["hoverA"] == a
    assert result["hoverB"] == b
    assert result["clickA"] == a
    assert result["pinnedHoverB"] == a
    assert result["pinnedHoverC"] == a
    assert result["pinnedAfterZoom"] == a
    assert result["pinnedAfterPan"] == a
    assert result["pinnedAfterScroll"] == a
    assert result["pinnedAfterMonth"] == a
    assert result["pinnedAfterCrime"] == a
    assert result["replaceWithB"] == b
    assert result["afterLeave"] == a
    assert result["reenterB"] == a
    assert result["afterToggleOff"] == b
    assert result["moveC"] == c


def test_map_leave_and_reentry_preserve_pin_until_explicit_toggle():
    result = reentry_render_scenario()
    b = {"county": "臺中市", "district": "西屯區"}
    c = {"county": "臺中市", "district": "南屯區"}
    taiping = {"county": "臺中市", "district": "太平區"}
    assert result["first"] == {
        "active": {"county": "臺中市", "district": "北屯區"},
        "rendered": {"county": "臺中市", "district": "北屯區"},
        "pinned": True,
        "selected": {"county": "臺中市", "district": "北屯區"},
        "badgeHidden": False,
    }
    assert result["moved"] == {
        "active": {"county": "臺中市", "district": "北屯區"},
        "rendered": {"county": "臺中市", "district": "北屯區"},
    }
    assert result["unpinned"] == {"active": c, "rendered": c, "pinned": False, "selected": None}
    assert result["second"] == {
        "active": c,
        "rendered": c,
        "pinned": True,
        "selected": c,
    }
    assert result["empty"] == {"active": c, "pinned": True, "selected": c}


def test_stale_hover_is_rejected_by_pinned_priority_before_async_apply():
    result = interaction_scenario()
    source = (STATIC / "app.js").read_text(encoding="utf-8")
    assert result["staleHoverCannotApply"] is False
    assert result["pinnedRequestCanApply"] is True
    assert "owner.requestId!==state.trendRequestId" in source
    assert "if(state.trendController)state.trendController.abort()" in source
    assert "validateTrendResponse(trends)" in source


def test_state_is_explicit_and_single_click_pins_without_double_click_behavior():
    source = (STATIC / "app.js").read_text(encoding="utf-8")
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    css = (STATIC / "styles.css").read_text(encoding="utf-8")
    assert "selectedDistrict:null,hoveredDistrict:null,isDistrictPinned:false" in source
    assert "return DistrictSelectionState.displayedIdentity(state.hoveredDistrict,state.selectedDistrict,state.isDistrictPinned)" in source
    assert 'pan.candidateDistrict=path?identity(path.dataset.county,path.dataset.district):null' in source
    assert 'clickedDistrict=!wasDragging&&event?.type==="pointerup"?pan.candidateDistrict:null' in source
    assert "if(row)toggleDistrictPin(row)" in source
    assert "state.selectedDistrict=identity(row.county,row.district);state.isDistrictPinned=true" in source
    assert 'addEventListener("dblclick"' not in source
    assert "lockedDistrict" not in source
    assert 'id="pinBadge"' in html and "已固定" in html
    assert ".district-shape.pinned{" in css


def test_drag_threshold_prevents_pan_gesture_from_becoming_a_pin():
    source = (STATIC / "app.js").read_text(encoding="utf-8")
    assert "MapNavigation.passedPanThreshold" in source
    assert "clickedDistrict=!wasDragging" in source
    assert "pan.candidateDistrict=null" in source
    assert "MapNavigation.passedPanThreshold" in source


def test_map_leave_and_reentry_do_not_unlock_or_clear_selected_pin():
    source = (STATIC / "app.js").read_text(encoding="utf-8")
    assert 'viewport.addEventListener("pointerleave",handleMapPointerLeave)' in source
    leave_start = source.index("function handleMapPointerLeave")
    leave_end = source.index("function handleMapPointerMove", leave_start)
    assert "clearDistrictPin" not in source[leave_start:leave_end]
    assert "selectedDistrict=null" not in source[leave_start:leave_end]
    enter_start = source.index("function handleMapPointerEnter")
    assert "clearDistrictPin" not in source[enter_start:leave_start]
    polygon_leave_start = source.index('path.addEventListener("mouseleave"')
    polygon_leave_end = source.index('path.addEventListener("focus"', polygon_leave_start)
    assert "clearDistrictPin" not in source[polygon_leave_start:polygon_leave_end]
    assert "state.isDistrictPinned=false;state.selectedDistrict=null" in source


def test_pointermove_fallback_remains_without_reentry_unlock_hit_test():
    source = (STATIC / "app.js").read_text(encoding="utf-8")
    assert 'viewport.addEventListener("pointerenter",handleMapPointerEnter)' in source
    assert 'viewport.addEventListener("pointermove",handleMapPointerMove)' in source
    assert "document.elementFromPoint(clientX,clientY)" in source
    assert "DistrictSelectionState.identityFromElement" in source
    enter = source[source.index("function handleMapPointerEnter") : source.index("function handleMapPointerLeave")]
    assert "clearDistrictPin" not in enter
    assert "elementFromPoint" not in enter
    assert "if(state.navigation.pan.dragging)return" in source[source.index("function resolveMapPointer") : source.index("function handleMapPointerEnter")]
    assert "if(state.isDistrictPinned||!changed)return" in source


def test_clicking_pinned_district_or_visible_button_explicitly_unpins():
    source = (STATIC / "app.js").read_text(encoding="utf-8")
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    assert "function toggleDistrictPin(row){if(state.isDistrictPinned&&sameIdentity(state.selectedDistrict,row.county,row.district))clearDistrictPin(true);else pinDistrict(row)}" in source
    assert 'id="unpinDistrict"' in html and "解除固定" in html
    assert '$("unpinDistrict").addEventListener("click",()=>clearDistrictPin(true))' in source
    assert '$("unpinDistrict").hidden=hidden' in source


def test_hover_styling_can_move_while_pinned_data_remains_selected():
    source = (STATIC / "app.js").read_text(encoding="utf-8")
    assert "state.hoveredDistrict=identity(row.county,row.district);updateMapSelectionClasses();showTooltip(event,row);if(state.isDistrictPinned||!changed)return" in source
    assert 'path.classList.toggle("hovered"' in source
    assert 'path.classList.toggle("pinned",state.isDistrictPinned' in source


def test_zoom_pan_scroll_and_redraw_do_not_mutate_valid_pin():
    source = (STATIC / "app.js").read_text(encoding="utf-8")
    for start, end in (
        ("function moveMapPan", "function resetMapNavigation"),
        ("function applyQueuedMapZoom", "function handleMapWheel"),
        ("function handleMapWheel", "function bindControls"),
        ("function renderMap", "function showTooltip"),
        ("function scheduleMapRefit", "function syncLayoutModes"),
    ):
        section = source[source.index(start) : source.index(end)]
        assert "selectedDistrict=null" not in section
        assert "isDistrictPinned=false" not in section


def test_non_geography_filters_preserve_pin_and_invalid_county_scope_clears_it():
    source = (STATIC / "app.js").read_text(encoding="utf-8")
    for start, end in (
        ('$("allYears").addEventListener', '$("yearChoices").addEventListener'),
        ('$("yearChoices").addEventListener', '$("metricSelect").addEventListener'),
        ('$("metricSelect").addEventListener', '$("allMonths").addEventListener'),
        ('$("allMonths").addEventListener', '$("monthChoices").addEventListener'),
        ('$("monthChoices").addEventListener', '$("sortSelect").addEventListener'),
    ):
        handler = source[source.index(start) : source.index(end)]
        assert "clearDistrictPin" not in handler
    assert "state.isDistrictPinned&&!state.counties.includes(state.selectedDistrict?.county)" in source
    assert "state.isDistrictPinned&&!identities.has(identityKey(state.selectedDistrict))" in source
