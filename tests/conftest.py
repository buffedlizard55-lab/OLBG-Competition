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
           tipster: str = "tester") -> Dict[str, Any]:
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
