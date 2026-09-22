"""Shared fixtures + builders for the Northstar test suite.

Everything here is offline: it builds a temporary SQLite store and synthetic
entities, plus loads the committed pilot fixtures for adapter tests. The suite
must pass with no network access.
"""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

import pytest

from northstar import models
from northstar.db import Store
from northstar.models import (
    Event, OddsSnapshot, Result, Tip, parse_utc, utcnow,
)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIXTURES = os.path.join(ROOT, "data", "fixtures")
RAW = os.path.join(ROOT, "data", "raw")

# A fixed, consistent timeline used across settlement tests (UTC).
START = "2026-01-10T15:00:00Z"          # event kickoff
PUBLISHED = "2026-01-09T12:00:00Z"       # tip publish/cutoff (pre-start)
FINAL_AT = "2026-01-10T17:00:00Z"        # result officially final (post-start)


@pytest.fixture()
def store(tmp_path) -> Store:
    s = Store(str(tmp_path / "test.db"))
    yield s
    s.close()


def mk_event(store: Store, event_id: str = "ev-t1", *,
             status: str = models.EVENT_STATUS_FINISHED,
             identity: str = "verified",
             start: str = START,
             home: str = "Home FC", away: str = "Away FC",
             sport: str = "football",
             competition: str = "Test League") -> Dict[str, Any]:
    ev = Event(
        event_id=event_id,
        sport=sport,
        competition=competition,
        home_team_id="h", home_team=home,
        away_team_id="a", away_team=away,
        scheduled_start_utc=parse_utc(start),
        status=status,
        identity_confidence=identity,
        source_provider="test",
        source_url="https://example.org/event",
        source_version="v1",
    )
    store.upsert_event(ev)
    store.commit()
    return store.get_event(event_id)


def mk_tip(store: Store, tip_id: str = "tip-t1", *,
           event_id: str = "ev-t1",
           selection_key: str = "home",
           selection: Optional[str] = None,
           market: str = models.MARKET_MATCH_WINNER_3WAY,
           odds: Optional[float] = 2.0,
           stake: float = 1.0,
           published: str = PUBLISHED,
           cutoff: Optional[str] = None,
           status: str = models.TIP_STATUS_OPEN,
           tipster: str = "tester",
           line: Optional[float] = None) -> Dict[str, Any]:
    tip = Tip(
        tip_id=tip_id,
        tipster_id=tipster,
        strategy_id="test-strategy",
        event_id=event_id,
        market=market,
        selection=selection or selection_key,
        selection_key=selection_key,
        published_at_utc=parse_utc(published),
        collected_at_utc=utcnow(),
        cutoff_at_utc=parse_utc(cutoff or published),
        odds_decimal=odds,
        odds_source="testbook",
        stake_units=stake,
        line=line,
        source_url="https://example.org/tip",
        raw_payload_hash="deadbeef",
        status=status,
    )
    store.add_tip(tip)
    store.commit()
    return store.get_tip(tip_id)


def mk_result(store: Store, event_id: str = "ev-t1", *,
              provider: str = "openligadb",
              home_goals: int = 2, away_goals: int = 1,
              final_status: str = "finished",
              final_at: str = FINAL_AT,
              raw_hash: Optional[str] = "cafe0123") -> List[Dict[str, Any]]:
    r = Result(
        result_id=models.stable_id("res", event_id, provider,
                                   home_goals, away_goals, final_status),
        event_id=event_id,
        provider=provider,
        retrieved_at_utc=utcnow(),
        source_url="https://example.org/result",
        raw_payload_hash=raw_hash,
        final_status=final_status,
        officially_final_at_utc=parse_utc(final_at),
        home_goals=home_goals,
        away_goals=away_goals,
        result_type_kind=models.RESULT_KIND_AFTER_90,
        version="v1",
    )
    store.add_result(r)
    store.commit()
    return store.results(event_id)


def mk_odds(store: Store, event_id: str = "ev-t1", *,
            provider: str = "market_avg",
            selection_key: str = "home",
            odds: float = 2.0,
            observed: str = PUBLISHED) -> None:
    snap = OddsSnapshot(
        snapshot_id=models.stable_id("os", event_id, provider, selection_key,
                                     observed),
        event_id=event_id,
        observed_at_utc=parse_utc(observed),
        provider=provider,
        market_key="match_winner_3way",
        selection_key=selection_key,
        decimal_odds=odds,
        timestamp_precision="exact",
    )
    store.add_odds_snapshot(snap)
    store.commit()


def read_fixture(name: str) -> str:
    with open(os.path.join(FIXTURES, name), "r", encoding="utf-8") as fh:
        return fh.read()


PILOT_OLDB_FILES = [
    "openligadb_bl1_2024_sd1.json",
    "openligadb_bl1_2024_sd10.json",
    "openligadb_bl1_2024_sd20.json",
]


@pytest.fixture(scope="module")
def pilot_store(tmp_path_factory):
    """A store with the full football pilot ingested (OpenLigaDB matchdays
    1/10/20 + the football-data manual-import CSV excerpt).  Shared by the
    adapter tests and the Asian-handicap walk-forward tests."""
    from northstar.adapters import football_data, openligadb
    s = Store(str(tmp_path_factory.mktemp("pilot") / "pilot.db"))
    for name in PILOT_OLDB_FILES:
        openligadb.ingest_matchday(s, read_fixture(name))
    stats = football_data.ingest_csv_text(s, read_fixture(
        "football_data_d1_2425_pilot.csv"))
    s.commit()
    yield s, stats
    s.close()


DEL_SD1 = os.path.join(FIXTURES, "openligadb_del_2024_sd1.json")
DEL_SD20 = os.path.join(FIXTURES, "openligadb_del_2024_sd20.json")
DEL_SD40 = os.path.join(FIXTURES, "openligadb_del_2024_sd40.json")


@pytest.fixture()
def hockey_store(tmp_path) -> Store:
    """A store with the DEL 2024/25 pilot ingested (matchdays 1/20/40)."""
    from northstar.adapters import openligadb
    s = Store(str(tmp_path / "hockey.db"))
    for path in (DEL_SD1, DEL_SD20, DEL_SD40):
        with open(path, encoding="utf-8") as fh:
            openligadb.ingest_matchday(s, fh.read(), sport="ice_hockey")
    yield s
    s.close()
