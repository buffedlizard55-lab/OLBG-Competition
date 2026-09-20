"""Ice hockey (DEL) pilot: fixtures, availability inference, irregularity
flags, prediction-only walk-forward, and accuracy grading.

Everything is offline and uses the committed ODbL OpenLigaDB fixtures. The
core honesty guarantees under test:

- OT/shootout finals are taken from AfterPenalties > AfterExtraTime >
  After90Minutes (never the regulation draw);
- results become visible at start+3h (inferred), never before a game could
  be final, never when the source was batch-edited months later;
- impossible source layering (decisive regulation + OT/SO entry) is flagged
  as RESULT_KIND_INCONSISTENT, not smoothed over;
- hockey bets are prediction-only: zero settlements, zero PnL, tips stay
  'unsettleable';
- the football pilot is unchanged by the hockey path.
"""
from __future__ import annotations

import json
import os

import pytest

from northstar import models
from northstar.adapters import openligadb
from northstar.backtest import run_walk_forward
from northstar.db import Store
from northstar.evaluation import brier_three, outcome_key, prediction_accuracy
from northstar.leaderboard import build_leaderboard
from northstar.models import parse_utc
from northstar.strategies import build as build_strategy

FIXTURES = os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "data", "fixtures")

SD1 = os.path.join(FIXTURES, "openligadb_del_2024_sd1.json")
SD20 = os.path.join(FIXTURES, "openligadb_del_2024_sd20.json")
SD40 = os.path.join(FIXTURES, "openligadb_del_2024_sd40.json")

# Hand-audited truths from the committed fixtures (checked against the raw
# payload bytes during fixture review, 2026-09-20):
# - 76100: regulation 3-2 AND an Overtime 3-2 entry -> AfterExtraTime final
# - 76414: 3.Drittel 5-6 listed + Penalty 5-6 entry -> AfterPenalties final
OT_MATCHES = {76100: (3, 2), 76273: (2, 1), 76409: (1, 2)}
SO_MATCHES = {76414: (5, 6)}
INCONSISTENT_IDS = {76100, 76273, 76409, 76414}
ALL_IDS_MD = {
    1: {76100, 76101, 76102, 76103, 76104, 76105, 76106},
    20: {76269, 76270, 76271, 76272, 76273, 76274, 76275},
    40: {76409, 76410, 76411, 76412, 76413, 76414, 76415},
}


def _read(path: str) -> str:
    with open(path, encoding="utf-8") as fh:
        return fh.read()


@pytest.fixture()
def hockey_store(tmp_path) -> Store:
    s = Store(str(tmp_path / "hockey.db"))
    for path in (SD1, SD20, SD40):
        openligadb.ingest_matchday(s, _read(path), sport="ice_hockey")
    yield s
    s.close()


# -------------------------------------------------------------- parse layer

def test_fixtures_cover_expected_matchdays():
    for md, path in ((1, SD1), (20, SD20), (40, SD40)):
        rows = openligadb.parse_matchday(_read(path), sport="ice_hockey")
        assert {r["match_id"] for r in rows} == ALL_IDS_MD[md]
        assert all(r["league_shortcut"] == "del" for r in rows)
        assert all(r["finished"] for r in rows)
        assert all(r["home_goals"] is not None for r in rows)
        # DEL finals are decisive after OT/SO resolution: no draws survive
        assert all(r["home_goals"] != r["away_goals"] for r in rows)
    # source fidelity: the parse layer preserves the null leagueSeason of
    # matchID 76412 exactly as served; normalization happens at ingest,
    # with a MISSING_METADATA flag (tested below).
    rows40 = openligadb.parse_matchday(_read(SD40), sport="ice_hockey")
    nulls = [r["match_id"] for r in rows40 if r["league_season"] is None]
    assert nulls == [76412]
    assert sum(1 for r in rows40 if r["league_season"] == 2024) == 6


def test_null_season_normalized_and_flagged_at_ingest(hockey_store):
    anoms = [a for a in hockey_store.anomalies()
             if a["kind"] == "MISSING_METADATA"]
    assert len(anoms) == 1
    assert "76412" in anoms[0]["detail"]
    event = hockey_store.get_event(anoms[0]["entity_id"])
    assert "None" not in (event["source_url"] or "")
    assert event["source_url"].endswith("/getmatchdata/del/2024/76412")
    # result for the repaired event carries full provenance
    res = hockey_store.results(anoms[0]["entity_id"])
    assert len(res) == 1 and res[0]["final_status"] == "finished"


def test_ot_and_shootout_final_kind_selection():
    rows = {}
    for path in (SD1, SD20, SD40):
        for r in openligadb.parse_matchday(_read(path), sport="ice_hockey"):
            rows[r["match_id"]] = r
    for mid, score in OT_MATCHES.items():
        assert rows[mid]["final_kind"] == "AfterExtraTime"
        assert (rows[mid]["home_goals"], rows[mid]["away_goals"]) == score
    for mid, score in SO_MATCHES.items():
        assert rows[mid]["final_kind"] == "AfterPenalties"
        assert (rows[mid]["home_goals"], rows[mid]["away_goals"]) == score
    # The shootout game is NOT settled as the regulation draw: 76414's
    # stored regulation-kind entry says 5-6 (source inconsistent, flagged),
    # and the engine took the AfterPenalties entry, never a 5-5 guess.
    assert rows[76414]["kind_inconsistent"] is True


def test_source_layering_irregularities_flagged_not_silent(hockey_store):
    kinds = {a["kind"] for a in hockey_store.anomalies()}
    assert "RESULT_KIND_INCONSISTENT" in kinds
    flagged = {a["entity_id"]
               for a in hockey_store.anomalies()
               if a["kind"] == "RESULT_KIND_INCONSISTENT"}
    events = {e["source_event_id"]: e["event_id"]
              for e in hockey_store.events()}
    assert flagged == {events[str(mid)] for mid in INCONSISTENT_IDS}
    # one anomaly per irregular event (idempotent on re-ingest)
    again = openligadb.ingest_matchday(hockey_store, _read(SD40),
                                       sport="ice_hockey")
    assert again["anomalies"] == 0


# ----------------------------------------------------------- availability

def test_results_available_start_plus_3h_not_batch_timestamp(hockey_store):
    for e in hockey_store.events():
        res = hockey_store.results(e["event_id"])
        assert len(res) == 1
        r = res[0]
        start = parse_utc(e["scheduled_start_utc"])
        final_at = parse_utc(r["officially_final_at_utc"])
        # inferred construction: exactly start+3h
        assert (final_at - start).total_seconds() == 3 * 3600
        # and GATE: strictly after start (never before a game could end)
        assert final_at > start
        # the raw batch-edit timestamp is preserved as retrieval evidence,
        # not mistaken for availability
        assert r["version"] and r["version"] != r["officially_final_at_utc"]


def test_hockey_events_never_verified_identity(hockey_store):
    # single source: cross-check gate keeps DEL at 'probable' - never
    # silently upgraded without an independent compilation
    assert all(e["identity_confidence"] == "probable"
               for e in hockey_store.events())


# -------------------------------------------------- prediction-only engine

@pytest.fixture()
def hockey_report(hockey_store):
    events = [e for e in hockey_store.events() if e["status"] == "finished"]
    strategy = build_strategy("hockey-elo-v1")
    rep = run_walk_forward(hockey_store, events, strategy, "hockey-elo-v1",
                           label="hockey-pilot", allow_no_odds=True)
    return rep


def test_prediction_only_never_settles(hockey_store, hockey_report):
    preds = [b for b in hockey_report["bets"]
             if b["outcome_action"] == "prediction_only"]
    assert preds, "expected at least one prediction in the pilot"
    # zero settlements anywhere for hockey tips
    assert hockey_store.all_settlements() == []
    tips = hockey_store.tips(tipster_id="hockey-elo-v1")
    assert len(tips) == len(preds)
    assert all(t["status"] == "unsettleable" for t in tips)
    assert all(t["odds_decimal"] is None for t in tips)
    assert all("no permissioned odds path" in (t["notes"] or "")
               for t in tips)


def test_cutoffs_strictly_pre_start_and_no_leaks(hockey_store, hockey_report):
    assert hockey_report["leak_violations"] == []
    for b in hockey_report["bets"]:
        event = hockey_store.get_event(b["event_id"])
        assert event["sport"] == "ice_hockey"
        assert parse_utc(b["cutoff"]) < parse_utc(
            event["scheduled_start_utc"])


def test_hockey_strategy_ignores_football_events(hockey_store):
    # a football event in the store must never enter the hockey walk-forward
    from conftest import mk_event  # reuse builder
    football_ev = mk_event(hockey_store, event_id="ev-football-cross",
                           sport="football")
    strategy = build_strategy("hockey-elo-v1")
    rep = run_walk_forward(hockey_store, [football_ev], strategy,
                           "hockey-elo-v1", allow_no_odds=True)
    assert rep["bets"] == [] and rep["skipped"] == [] and \
        rep["leak_violations"] == []


def test_prediction_only_desk_excluded_from_pnl_leaderboard(hockey_store,
                                                            hockey_report):
    assert hockey_report["bets"]
    lb = build_leaderboard(hockey_store)
    assert all(r["entrant_id"] != "hockey-elo-v1" for r in lb)


def test_walk_forward_ordering_invariance(hockey_store):
    events = [e for e in hockey_store.events() if e["status"] == "finished"]
    shuffled = list(reversed(events))

    def run(evs):
        rep = run_walk_forward(hockey_store, evs,
                               build_strategy("hockey-elo-v1"),
                               "hockey-elo-v1", allow_no_odds=True)
        return [(b["event_id"], b["selection"], b["cutoff"])
                for b in rep["bets"]]

    assert run(events) == run(shuffled)


# ------------------------------------------------------------- evaluation

def test_accuracy_matches_hand_computation(hockey_store, hockey_report):
    ev = prediction_accuracy(hockey_store, hockey_report["bets"],
                             sport="ice_hockey")
    preds = [b for b in hockey_report["bets"]
             if b["outcome_action"] == "prediction_only"]
    # graded == all predictions (pilot results are finished & consistent)
    assert ev["n_graded"] == len(preds)
    assert ev["ungraded"] == []
    # independent recount straight from stored results
    hits = 0
    for b in preds:
        r = hockey_store.results(b["event_id"])[0]
        actual = outcome_key(r["home_goals"], r["away_goals"])
        hits += 1 if b["selection"] == actual else 0
    assert ev["hits"] == hits
    assert ev["accuracy"] == pytest.approx(hits / len(preds))
    assert sum(d["n"] for d in ev["by_matchday"].values()) == len(preds)
    assert "not PnL" in ev["note"] or "Not PnL" in ev["note"]


def test_evaluation_refuses_conflicting_results(store):
    from conftest import mk_event, mk_result
    mk_event(store, event_id="ev-conflict", sport="ice_hockey")
    mk_result(store, "ev-conflict", provider="a", home_goals=3, away_goals=2)
    mk_result(store, "ev-conflict", provider="b", home_goals=2, away_goals=3)
    out = prediction_accuracy(
        store, [{"event_id": "ev-conflict", "selection": "home",
                 "model": {}}])
    assert out["n_graded"] == 0
    assert out["ungraded"][0]["reason"] == "conflicting or incomplete result"


def test_brier_and_outcome_helpers():
    assert outcome_key(3, 2) == "home"
    assert outcome_key(2, 3) == "away"
    assert outcome_key(2, 2) == "draw"
    probs = {"home": 0.6, "draw": 0.0, "away": 0.4}
    assert brier_three(probs, "home") == pytest.approx(
        (0.6 - 1) ** 2 + 0.0 + 0.4 ** 2)
    assert brier_three(probs, "away") == pytest.approx(
        0.6 ** 2 + 0.0 + (0.4 - 1) ** 2)
    with pytest.raises(ValueError):
        brier_three(probs, "postponed")


def test_synthetic_accuracy_exact_numbers(store):
    from conftest import mk_event, mk_result
    for i in (1, 2, 3):
        mk_event(store, event_id=f"ev-acc-{i}", sport="ice_hockey",
                 start="2026-01-1%dT15:00:00Z" % i)
    mk_result(store, "ev-acc-1", provider="p", home_goals=4, away_goals=1)
    mk_result(store, "ev-acc-2", provider="p", home_goals=2, away_goals=3)
    mk_result(store, "ev-acc-3", provider="p", home_goals=1, away_goals=0)
    bets = [
        {"event_id": "ev-acc-1", "selection": "home", "model": {}},
        {"event_id": "ev-acc-2", "selection": "home", "model": {}},
        {"event_id": "ev-acc-3", "selection": "away", "model": {}},
    ]
    out = prediction_accuracy(store, bets)
    assert (out["n_graded"], out["hits"]) == (3, 1)
    assert out["accuracy"] == pytest.approx(1 / 3)


# --------------------------------------- football pilot isolation guarantees

def test_hockey_ingest_does_not_touch_football_tables(hockey_store):
    assert all(e["sport"] == "ice_hockey" for e in hockey_store.events())
    assert hockey_store.odds_snapshots() == []
