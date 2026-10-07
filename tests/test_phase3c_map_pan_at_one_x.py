from __future__ import annotations

import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "app" / "static"


def one_x_scenario() -> dict:
    script = r"""
const nav = require(process.argv[1]);
const viewport = {width: 800, height: 500};
const canvas = nav.canvasSize(viewport.width, viewport.height, 1);
const center = nav.centeredScroll(viewport.width, viewport.height, canvas.width, canvas.height);
const horizontal = nav.panPosition(center.left, center.top, 100, 100, 50, 100, canvas.width - viewport.width, canvas.height - viewport.height);
const vertical = nav.panPosition(center.left, center.top, 100, 100, 100, 50, canvas.width - viewport.width, canvas.height - viewport.height);
const zoomed = nav.nextZoom(1, -1);
const afterPanZoom = nav.anchoredScroll(horizontal.left, vertical.top, 150, 125, 1, zoomed);
const backAtOne = nav.canvasSize(viewport.width, viewport.height, nav.nextZoom(1, 1));
process.stdout.write(JSON.stringify({
  overscan: nav.OVERSCAN_RATIO,
  viewport,
  canvas,
  center,
  horizontal,
  vertical,
  zoomed,
  afterPanZoom,
  backAtOne,
  visibleGeometryCenter: {x: canvas.width / 2 - center.left, y: canvas.height / 2 - center.top},
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


def test_one_x_canvas_has_two_axis_pan_room_and_centered_initial_view():
    result = one_x_scenario()
    assert 1.4 <= result["overscan"] <= 1.8
    assert result["canvas"]["width"] > result["viewport"]["width"]
    assert result["canvas"]["height"] > result["viewport"]["height"]
    assert result["canvas"]["width"] - result["viewport"]["width"] > 0
    assert result["canvas"]["height"] - result["viewport"]["height"] > 0
    assert result["center"]["left"] == 200
    assert result["center"]["top"] == 125
    assert result["visibleGeometryCenter"] == {"x": 400, "y": 250}


def test_one_x_horizontal_and_vertical_drags_change_native_scroll_positions():
    result = one_x_scenario()
    assert result["horizontal"]["left"] != result["center"]["left"]
    assert result["horizontal"]["top"] == result["center"]["top"]
    assert result["vertical"]["left"] == result["center"]["left"]
    assert result["vertical"]["top"] != result["center"]["top"]


def test_zoom_after_one_x_pan_and_return_to_one_x_keep_pan_room():
    result = one_x_scenario()
    assert result["zoomed"] > 1
    assert result["afterPanZoom"]["left"] > result["horizontal"]["left"]
    assert result["afterPanZoom"]["top"] > result["vertical"]["top"]
    assert result["backAtOne"]["width"] > result["viewport"]["width"]
    assert result["backAtOne"]["height"] > result["viewport"]["height"]


def test_rendering_offsets_fitted_geometry_into_overscan_without_rescaling_it():
    source = (STATIC / "app.js").read_text(encoding="utf-8")
    css = (STATIC / "styles.css").read_text(encoding="utf-8")
    assert "MapProjection.fit(state.geography.features,viewWidth,viewHeight)" in source
    assert "offsetX=(baseCanvas.width-viewWidth)/2" in source
    assert "offsetY=(baseCanvas.height-viewHeight)/2" in source
    assert "projected[0]+offsetX,projected[1]+offsetY" in source
    assert 'setAttribute("viewBox",`0 0 ${baseCanvas.width} ${baseCanvas.height}`)' in source
    assert ".map-canvas{position:relative;width:150%;height:150%;min-width:150%;min-height:150%}" in css


def test_geography_reset_recenters_one_x_while_other_filters_preserve_navigation():
    source = (STATIC / "app.js").read_text(encoding="utf-8")
    assert "centerOnNextRender:true" in source
    assert "function centerMapViewport()" in source
    assert "state.navigation.centerOnNextRender=centerNextRender" in source
    assert source.count("resetMapNavigation(true)") == 3
    assert "if(geographyChanged)resetMapNavigation(true)" in source
    for start, end in (
        ('$("allYears").addEventListener', '$("yearChoices").addEventListener'),
        ('$("yearChoices").addEventListener', '$("metricSelect").addEventListener'),
        ('$("metricSelect").addEventListener', '$("allMonths").addEventListener'),
        ('$("allMonths").addEventListener', '$("monthChoices").addEventListener'),
        ('$("monthChoices").addEventListener', '$("sortSelect").addEventListener'),
    ):
        assert "resetMapNavigation" not in source[source.index(start) : source.index(end)]
    assert "centerNavigation ? .5" in source


def test_one_x_pan_keeps_hover_only_and_layout_refit_contracts():
    source = (STATIC / "app.js").read_text(encoding="utf-8")
    assert 'path.addEventListener("mouseenter"' in source
    assert 'path.addEventListener("mousemove"' in source
    assert "clickedDistrict=!wasDragging" in source
    assert 'addEventListener("dblclick"' not in source
    assert "lockedDistrict" not in source
    assert "scheduleMapRefit()" in source
    refit = source[source.index("function scheduleMapRefit") : source.index("function syncLayoutModes")]
    assert "resetMapNavigation" not in refit
