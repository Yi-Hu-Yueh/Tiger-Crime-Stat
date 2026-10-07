from __future__ import annotations

import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SELECTION_MODULE = ROOT / "app" / "static" / "selection_state.js"
APP_JS = ROOT / "app" / "static" / "app.js"


def run_selection_scenario() -> dict:
    script = r"""
const selection = require(process.argv[1]);
const rows = [
  {county: "臺北市", district: "中正區"},
  {county: "基隆市", district: "中正區"},
  {county: "臺中市", district: "北屯區"},
];
const taipei = selection.identity("臺北市", "中正區");
const keelung = selection.identity("基隆市", "中正區");
process.stdout.write(JSON.stringify({
  taipei,
  keelung,
  distinct: !selection.sameIdentity(taipei, keelung.county, keelung.district),
  retained: selection.reconcileIdentity(taipei, rows),
  cleared: selection.reconcileIdentity(selection.identity("新北市", "板橋區"), rows),
  staleRejected: selection.isCurrent(8, 9, "scope-a", "scope-a"),
  scopeRejected: selection.isCurrent(9, 9, "scope-a", "scope-b"),
  currentAccepted: selection.isCurrent(9, 9, "scope-a", "scope-a"),
}));
"""
    completed = subprocess.run(
        ["node", "-e", script, str(SELECTION_MODULE)],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return json.loads(completed.stdout)


def test_county_and_district_form_the_complete_selection_identity():
    result = run_selection_scenario()
    assert result["taipei"] == {"county": "臺北市", "district": "中正區"}
    assert result["keelung"] == {"county": "基隆市", "district": "中正區"}
    assert result["distinct"] is True


def test_scope_reconciliation_preserves_only_an_available_identity():
    result = run_selection_scenario()
    assert result["retained"] == {"county": "臺北市", "district": "中正區"}
    assert result["cleared"] is None


def test_request_guard_rejects_stale_versions_and_changed_scopes():
    result = run_selection_scenario()
    assert result["staleRejected"] is False
    assert result["scopeRejected"] is False
    assert result["currentAccepted"] is True


def test_map_redraw_suppresses_stationary_pointer_but_hover_resumes_on_entry_and_move():
    source = APP_JS.read_text(encoding="utf-8")
    assert "state.suppressMapHover=true;" in source
    assert "group.replaceChildren();" in source
    assert "if(moved){state.suppressMapHover=false;display(event)}" in source
    assert 'viewport.addEventListener("pointerenter",handleMapPointerEnter)' in source
    assert "document.elementFromPoint(clientX,clientY)" in source
    assert 'path.addEventListener("mouseenter"' in source
    assert "owner.requestId!==state.trendRequestId" in source
