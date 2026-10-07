from __future__ import annotations

import json
import subprocess
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app


ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "app" / "static"
CLIENT = TestClient(app)


def run_navigation_scenario() -> dict:
    script = r"""
const nav = require(process.argv[1]);
let zoom = nav.MIN_ZOOM;
const normal = nav.wheelResult(zoom, {ctrlKey: false, deltaY: -1});
const zoomedIn = nav.wheelResult(zoom, {ctrlKey: true, deltaY: -1});
const zoomedOut = nav.wheelResult(zoomedIn.zoom, {ctrlKey: true, deltaY: 1});
let maximum = zoom;
for (let index = 0; index < 100; index += 1) maximum = nav.nextZoom(maximum, -1);
let minimum = maximum;
for (let index = 0; index < 100; index += 1) minimum = nav.nextZoom(minimum, 1);
const size = nav.canvasSize(800, 500, 2);
const anchored = nav.anchoredScroll(100, 50, 200, 100, 1, 2);
process.stdout.write(JSON.stringify({
  min: nav.MIN_ZOOM,
  max: nav.MAX_ZOOM,
  step: nav.ZOOM_STEP,
  normal,
  zoomedIn,
  zoomedOut,
  maximum,
  minimum,
  size,
  anchored,
  oldPoint: {x: (100 + 200) / 1, y: (50 + 100) / 1},
  newPoint: {x: (anchored.left + 200) / 2, y: (anchored.top + 100) / 2},
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


def test_ctrl_wheel_zoom_is_deterministic_clamped_and_pointer_centered():
    result = run_navigation_scenario()
    assert result["min"] == result["minimum"] == 1
    assert result["max"] == result["maximum"] == 6
    assert 1.10 <= result["step"] <= 1.20
    assert result["normal"] == {"handled": False, "zoom": 1}
    assert result["zoomedIn"]["handled"] is True
    assert result["zoomedIn"]["zoom"] > 1
    assert result["zoomedOut"]["zoom"] == 1
    assert result["oldPoint"] == result["newPoint"]


def test_zoomed_canvas_provides_both_map_only_scroll_axes():
    result = run_navigation_scenario()
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    css = (STATIC / "styles.css").read_text(encoding="utf-8")
    assert result["size"] == {"width": 2400, "height": 1500}
    assert 'id="mapViewport" class="map-viewport"' in html
    assert 'id="mapCanvas" class="map-canvas"' in html
    assert '.map-viewport{width:100%;height:100%;overflow:auto;' in css
    assert '.map-stage{position:relative;min-height:0;overflow:hidden;' in css
    assert "html,body{margin:0;height:100%;overflow:hidden}" in css


def test_ctrl_wheel_is_intercepted_only_by_the_map_and_uses_animation_frame():
    source = (STATIC / "app.js").read_text(encoding="utf-8")
    handler_start = source.index("function handleMapWheel")
    handler_end = source.index("function bindControls", handler_start)
    handler = source[handler_start:handler_end]
    assert "MapNavigation.wheelResult" in handler
    assert "if(!result.handled||state.navigation.pan.pointerId!==null)return;event.preventDefault()" in handler
    assert "requestAnimationFrame(applyQueuedMapZoom)" in handler
    assert 'viewport.addEventListener("wheel",handleMapWheel,{passive:false})' in source
    assert 'document.addEventListener("wheel"' not in source
    assert "fetch(" not in handler


def test_geography_filters_reset_navigation_while_other_filters_preserve_it():
    source = (STATIC / "app.js").read_text(encoding="utf-8")
    assert "navigation:{zoom:1" in source
    assert "state.navigation.zoom=MapNavigation.MIN_ZOOM" in source
    county_position = source.index("state.counties=selectedValues")
    assert "resetMapNavigation(true)" in source[county_position : county_position + 350]
    for start, end in (
        ('$("allYears").addEventListener', '$("yearChoices").addEventListener'),
        ('$("yearChoices").addEventListener', '$("metricSelect").addEventListener'),
        ('$("metricSelect").addEventListener', '$("allMonths").addEventListener'),
        ('$("allMonths").addEventListener', '$("monthChoices").addEventListener'),
        ('$("monthChoices").addEventListener', '$("sortSelect").addEventListener'),
    ):
        handler = source[source.index(start) : source.index(end)]
        assert "resetMapNavigation()" not in handler
    crime_start = source.index('button.addEventListener("click",()=>{state.crimeType')
    crime_end = source.index('});$("crimeTiles")', crime_start)
    assert "resetMapNavigation()" not in source[crime_start:crime_end]
    refit_start = source.index("function scheduleMapRefit")
    refit_end = source.index("function syncLayoutModes", refit_start)
    assert "resetMapNavigation" not in source[refit_start:refit_end]
    assert "renderMap()" in source[refit_start:refit_end]
    assert "state.navigation.zoom" in source[source.index("function updateMapCanvasSize") : source.index("function resetMapNavigation")]


def test_zoom_keeps_svg_hit_areas_and_hover_identity_without_locking():
    source = (STATIC / "app.js").read_text(encoding="utf-8")
    css = (STATIC / "styles.css").read_text(encoding="utf-8")
    assert '#districtMap{width:100%;height:100%;display:block}' in css
    assert 'path.dataset.county=row.county;path.dataset.district=row.district' in source
    assert 'path.addEventListener("mouseenter"' in source
    assert 'path.addEventListener("mousemove"' in source
    assert "clickedDistrict=!wasDragging" in source
    assert 'addEventListener("dblclick"' not in source
    assert "lockedDistrict" not in source
    wheel_start = source.index("function handleMapWheel")
    wheel_end = source.index("function bindControls", wheel_start)
    assert "selection" not in source[wheel_start:wheel_end]
    assert "hoveredDistrict" not in source[wheel_start:wheel_end]


def test_nationwide_geometry_still_contains_all_368_districts():
    counties = CLIENT.get("/api/counties").json()["counties"]
    names = ",".join(item["county"] for item in counties)
    response = CLIENT.get("/api/scope/geography", params={"counties": names})
    assert response.status_code == 200
    features = response.json()["features"]
    identities = {
        (feature["properties"]["county"], feature["properties"]["district"])
        for feature in features
    }
    assert len(features) == len(identities) == 368
