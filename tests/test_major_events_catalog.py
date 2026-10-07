from __future__ import annotations

import json
import subprocess
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

import pytest
from fastapi.testclient import TestClient

from app.data.major_events_2016_2025 import MAJOR_EVENTS_2016_2025
from app.main import app
from app.services.context_service import ContextService

ROOT = Path(__file__).resolve().parents[1]
CLIENT = TestClient(app)


def test_every_year_has_three_sourced_global_and_taiwan_events():
    assert set(MAJOR_EVENTS_2016_2025) == set(range(2016, 2026))
    ids = set()
    for year, groups in MAJOR_EVENTS_2016_2025.items():
        assert set(groups) == {"global", "taiwan"}
        for scope, events in groups.items():
            assert len(events) == 3
            for event in events:
                assert event["id"] not in ids
                ids.add(event["id"])
                assert event["year"] == year and event["scope"] == scope
                start, end = map(date.fromisoformat, (event["start_date"], event["end_date"]))
                assert start <= end and start.year == end.year == year
                for key in ("category", "title", "summary", "status", "source_title", "source_agency", "relevance_tags", "date_note"):
                    assert event[key]
                parsed = urlparse(event["source_url"])
                assert parsed.scheme == "https" and parsed.netloc
    assert len(ids) == 60


@pytest.mark.parametrize("year", range(2016, 2026))
def test_api_returns_only_requested_year_with_both_scopes(year):
    response = CLIENT.get("/api/context/events", params={"year": year, "county": "臺中市"})
    assert response.status_code == 200
    events = response.json()["events"]
    assert len(events) == 6 and {event["year"] for event in events} == {year}
    assert {event["scope"] for event in events} == {"global", "taiwan"}
    assert all(event["causality_established"] is False for event in events)


def test_tariff_dates_administrations_and_policy_stages_are_distinct():
    events = {event["id"]: event for event in ContextService().events()}
    trump = events["global-trump-section301-tariffs-2018"]
    biden = events["global-biden-targeted-tariffs-2024"]
    reciprocal = events["global-trump-reciprocal-tariffs-2025"]
    assert trump["start_date"] == "2018-07-06" and trump["status"] == "implemented"
    assert "川普" in trump["title"] and "301" in trump["title"]
    assert biden["start_date"] == "2024-05-14" and biden["status"] == "announced"
    assert "拜登" in biden["title"] and "分批" in biden["summary"]
    assert reciprocal["start_date"] == "2025-04-02" and reciprocal["status"] == "announced"
    assert "川普" in reciprocal["title"] and "對等關稅" in reciprocal["title"]


def test_noncausal_catalog_and_no_dynamic_pipeline():
    text = json.dumps(MAJOR_EVENTS_2016_2025, ensure_ascii=False)
    for phrase in ("因此造成犯罪增加", "證明治安變差", "證明不是治安變差"):
        assert phrase not in text
    source = (ROOT / "app/services/context_service.py").read_text(encoding="utf-8")
    assert "MAJOR_EVENTS_2016_2025" in source
    assert not any(fragment in source for fragment in ("requests.", "httpx.", "urlopen", "read_text", "json.loads"))
    assert not (ROOT / "data/context/major_events.json").exists()


def test_ui_groups_selected_years_and_scopes_with_dates_counts_and_sources():
    script = r'''
const fs=require('fs'),vm=require('vm');
const context={CrimeSelectionState:require(process.argv[1]),DistrictSelectionState:require(process.argv[2]),DashboardLayoutState:{create:()=>({})},MapNavigation:{},MapProjection:{},Intl,URLSearchParams,document:{addEventListener:()=>{}}};
vm.createContext(context);vm.runInContext(fs.readFileSync(process.argv[3],'utf8'),context);
context.events=JSON.parse(fs.readFileSync(0,'utf8'));
const single=vm.runInContext('eventCatalogMarkup(events,[2021])',context);
const multi=vm.runInContext('eventCatalogMarkup(events,[2025,2018,2024,2024])',context);
const empty=vm.runInContext('eventCatalogMarkup([],[2020])',context);
process.stdout.write(JSON.stringify({single,multi,empty}));
'''
    result = subprocess.run(
        ["node", "-e", script, *(str(ROOT / "app/static" / name) for name in ("crime_selection.js", "selection_state.js", "app.js"))],
        input=json.dumps(ContextService().events(), ensure_ascii=False), text=True, encoding="utf-8", capture_output=True, check=True,
    )
    html = json.loads(result.stdout)
    assert html["single"].count('data-event-year="2021"') == 1
    assert html["single"].count('data-event-id=') == 6
    assert "全球重大事件（3）" in html["single"] and "台灣重大事件（3）" in html["single"]
    assert "2021-05-19–2021-07-26" in html["single"]
    assert "cdc.gov.tw" in html["single"] and "who.int" in html["single"]
    assert "時間重疊不代表因果關係" in html["single"]
    assert "2024" not in html["single"]
    assert html["multi"].count('data-event-year=') == 3
    assert html["multi"].count('data-event-id=') == 18
    assert html["multi"].index('data-event-year="2018"') < html["multi"].index('data-event-year="2024"') < html["multi"].index('data-event-year="2025"')
    assert "川普" in html["multi"] and "拜登" in html["multi"]
    assert "這不表示沒有事件發生" in html["empty"]
