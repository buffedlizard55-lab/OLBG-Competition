"""End-to-end pipeline invariants (offline, committed fixtures only).

Requirement coverage: the full collect->store->compile->analyze->track chain
must reproduce the headline numbers deterministically: 27 events, 27 results,
27/27 dual-source agreement, 405 odds snapshots, four strategies that settle
with *verified* state and produce reviewable placed/upcoming bets.
"""
from __future__ import annotations

import pytest

from northstar.adapters import football_data, openligadb
from northstar.backtest import run_walk_forward
from northstar.db import Store
from northstar.leaderboard import build_leaderboard, placed_bets, upcoming_bets
from northstar.strategies import FOOTBALL_STRATEGIES, build
from northstar.timeutil import odds_collection_window_utc
from northstar.models import parse_utc

from conftest import read_fixture

OLDB_FILES = [
    "openligadb_bl1_2024_sd1.json",
    "openligadb_bl1_2024_sd10.json",
    "openligadb_bl1_2024_sd20.json",
]


@pytest.fixture(scope="module")
def pipeline_store(tmp_path_factory):
    s = Store(str(tmp_path_factory.mktemp("e2e") / "e2e.db"))
    for name in OLDB_FILES:
        openligadb.ingest_matchday(s, read_fixture(name))
    csv_stats = football_data.ingest_csv_text(
        s, read_fixture("football_data_d1_2425_pilot.csv"))
    s.commit()
    yield s, csv_stats
    s.close()


def test_headline_counts(pipeline_store):
    s, stats = pipeline_store
    events = [e for e in s.events() if e["source_provider"] == "openligadb"]
    assert len(events) == 27
    results = [r for r in s.results() if r["provider"] == "openligadb"]
    assert len(results) == 27
    assert stats["cross_checked"] == 27
    assert stats["cross_checked_agree"] == 27
    assert stats["odds_snapshots"] == 405


def test_every_event_is_verified(pipeline_store):
    s, _ = pipeline_store
    for e in s.events():
        if e["source_provider"] == "openligadb":
            assert e["identity_confidence"] == "verified", e["event_id"]


def test_all_snapshots_pre_start_and_inferred(pipeline_store):
    s, _ = pipeline_store
    n = 0
    for e in s.events():
        if e["source_provider"] != "openligadb":
            continue
        start = parse_utc(e["scheduled_start_utc"])
        for snap in s.odds_snapshots(e["event_id"]):
            assert parse_utc(snap["observed_at_utc"]) < start
            assert snap["timestamp_precision"] == "window_close_inferred"
            n += 1
    assert n == 405


def test_all_strategies_settle_verified_no_leaks(pipeline_store):
    s, _ = pipeline_store
    events = [e for e in s.events()
              if e["status"] == "finished"
              and e["source_provider"] == "openligadb"]
    for sid in FOOTBALL_STRATEGIES:
        rep = run_walk_forward(s, events, build(sid), sid, label="e2e")
        assert rep["leak_violations"] == [], sid
        tips = [t for t in s.tips(tipster_id=sid)
                if t["status"] in ("won", "lost")]
        for t in tips:
            st = s.latest_settlement(t["tip_id"])
            assert st["verification_state"] == "verified", (sid, t["tip_id"])


def test_backtest_is_idempotent_on_rerun(pipeline_store):
    """Re-running the same backtest must not create duplicate settlements
    or double-count PnL (idempotency guard)."""
    s, _ = pipeline_store
    events = [e for e in s.events()
              if e["status"] == "finished"
              and e["source_provider"] == "openligadb"]
    sid = "market-favourite-v1"
    a = run_walk_forward(s, events, build(sid), sid, label="e2e")
    n_settlements = len(s.all_settlements())
    n_tips = len(s.tips(tipster_id=sid))
    b = run_walk_forward(s, events, build(sid), sid, label="e2e")
    assert len(s.all_settlements()) == n_settlements
    assert len(s.tips(tipster_id=sid)) == n_tips
    # and the bet sets match
    ka = {(x["event_id"], x["selection"]) for x in a["bets"]}
    kb = {(x["event_id"], x["selection"]) for x in b["bets"]}
    assert ka == kb


def test_leaderboard_and_bet_views_populated(pipeline_store):
    s, _ = pipeline_store
    lb = build_leaderboard(s)
    assert lb, "leaderboard must not be empty after backtests"
    assert all("rank" in r for r in lb)
    # at least one strategy entrant exists and has settled bets
    strat_rows = [r for r in lb if r["kind"] == "strategy"]
    assert any(r["settled_bets"] > 0 for r in strat_rows)
    assert placed_bets(s)
    # OLBG imports (if any) would surface here; the pilot store has none, so
    # upcoming may be empty - just assert the call works and lists are sane.
    assert isinstance(upcoming_bets(s), list)


def test_odds_window_matches_snapshot_observation(pipeline_store):
    """For each event, the stored snapshot observed_at must equal the
    inferred collection-window close for that kickoff (consistency check)."""
    s, _ = pipeline_store
    checked = 0
    for e in s.events():
        if e["source_provider"] != "openligadb":
            continue
        snaps = s.odds_snapshots(e["event_id"])
        if not snaps:
            continue
        window = odds_collection_window_utc(
            parse_utc(e["scheduled_start_utc"]))
        for snap in snaps:
            assert parse_utc(snap["observed_at_utc"]) == window
        checked += 1
    assert checked == 27
