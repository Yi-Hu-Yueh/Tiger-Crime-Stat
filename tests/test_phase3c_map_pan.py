from __future__ import annotations

import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "app" / "static"


def run_pan_scenario() -> dict:
    script = r"""
const nav = require(process.argv[1]);
const rightDown = nav.panPosition(300, 200, 100, 100, 150, 130, 800, 600);
const leftUp = nav.panPosition(300, 200, 100, 100, 50, 70, 800, 600);
const lowClamp = nav.panPosition(5, 5, 0, 0, 100, 100, 800, 600);
const highClamp = nav.panPosition(790, 590, 100, 100, 0, 0, 800, 600);
const zoomedSize = nav.canvasSize(800, 500, 2);
const panned = nav.panPosition(400, 250, 100, 100, 50, 75, zoomedSize.width - 800, zoomedSize.height - 500);
const zoomAfterPan = nav.anchoredScroll(panned.left, panned.top, 120, 90, 2, nav.nextZoom(2, -1));
const nextZoom = nav.nextZoom(2, -1);
process.stdout.write(JSON.stringify({
  threshold: nav.PAN_THRESHOLD,
  small: nav.passedPanThreshold(0, 0, 2, 2),
  large: nav.passedPanThreshold(0, 0, 4, 0),
  rightDown,
  leftUp,
  lowClamp,
  highClamp,
  zoomedSize,
  panned,
  zoomAfterPan,
  nextZoom,
  pointBefore: {x: (panned.left + 120) / 2, y: (panned.top + 90) / 2},
  pointAfter: {x: (zoomAfterPan.left + 120) / nextZoom, y: (zoomAfterPan.top + 90) / nextZoom},
}));
"""
    completed = subprocess.run(
        ["node", "-e", script, str(STATIC / "map_navigation.js")],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return json.loads(completed.stdout)


def test_drag_threshold_and_pan_math_use_native_scroll_coordinates():
    result = run_pan_scenario()
    assert 3 <= result["threshold"] <= 5
    assert result["small"] is False
    assert result["large"] is True
    assert result["rightDown"] == {"left": 250, "top": 170}
    assert result["leftUp"] == {"left": 350, "top": 230}
    assert result["lowClamp"] == {"left": 0, "top": 0}
    assert result["highClamp"] == {"left": 800, "top": 600}


def test_pan_works_when_zoomed_and_pointer_zoom_uses_current_pan():
    result = run_pan_scenario()
    assert result["zoomedSize"] == {"width": 2400, "height": 1500}
    assert result["panned"]["left"] > 0
    assert result["panned"]["top"] > 0
    assert result["nextZoom"] > 2
    assert result["pointBefore"]["x"] == result["pointAfter"]["x"]
    assert result["pointBefore"]["y"] == result["pointAfter"]["y"]


def test_pointer_capture_lifecycle_and_scrollbar_synchronization_are_wired():
    source = (STATIC / "app.js").read_text(encoding="utf-8")
    assert 'viewport.addEventListener("pointerdown",startMapPan)' in source
    assert 'viewport.addEventListener("pointermove",moveMapPan)' in source
    assert 'viewport.addEventListener("pointerup",endMapPan)' in source
    assert 'viewport.addEventListener("pointercancel",endMapPan)' in source
    assert 'viewport.addEventListener("lostpointercapture",endMapPan)' in source
    assert "viewport.setPointerCapture(event.pointerId)" in source
    assert "viewport.releasePointerCapture(pointerId)" in source
    assert "viewport.scrollLeft=position.left;viewport.scrollTop=position.top" in source
    assert "viewport.scrollWidth-viewport.clientWidth" in source
    assert "viewport.scrollHeight-viewport.clientHeight" in source
    assert 'document.addEventListener("pointermove"' not in source


def test_cursor_transitions_and_drag_selection_suppression_are_scoped_to_map():
    css = (STATIC / "styles.css").read_text(encoding="utf-8")
    source = (STATIC / "app.js").read_text(encoding="utf-8")
    assert "cursor:grab;touch-action:none" in css
    assert ".map-viewport.is-panning,.map-viewport.is-panning .district-shape{cursor:grabbing;user-select:none}" in css
    assert 'viewport.classList.add("is-panning")' in source
    assert 'viewport.classList.remove("is-panning")' in source
    assert "state.suppressMapHover=true" in source[source.index("function moveMapPan") : source.index("function resetMapNavigation")]
    assert "state.suppressMapHover=false" in source[source.index("function endMapPan") : source.index("function startMapPan")]
    assert 'if(state.navigation.pan.dragging){$("mapTooltip").hidden=true;return}' in source


def test_filter_pan_contract_and_hover_only_behavior_are_preserved():
    source = (STATIC / "app.js").read_text(encoding="utf-8")
    county_start = source.index('$("countyChoices").addEventListener')
    county_end = source.index('$("allYears").addEventListener', county_start)
    assert "resetMapNavigation(true)" in source[county_start:county_end]
    for start, end in (
        ('$("allYears").addEventListener', '$("yearChoices").addEventListener'),
        ('$("yearChoices").addEventListener', '$("metricSelect").addEventListener'),
        ('$("metricSelect").addEventListener', '$("allMonths").addEventListener'),
        ('$("allMonths").addEventListener', '$("monthChoices").addEventListener'),
        ('$("monthChoices").addEventListener', '$("sortSelect").addEventListener'),
    ):
        assert "resetMapNavigation()" not in source[source.index(start) : source.index(end)]
    assert "clickedDistrict=!wasDragging" in source
    assert 'addEventListener("dblclick"' not in source
    assert "lockedDistrict" not in source
