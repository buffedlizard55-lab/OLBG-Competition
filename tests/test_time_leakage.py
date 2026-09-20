"""Time-leakage prevention: the walk-forward engine must never let a model
see a feature before its availability time, or a result before the bet.

Requirement coverage: "automated tests for ... time leakage".
"""
from __future__ import annotations

from datetime import timedelta

import pytest

from northstar import models
from northstar.backtest import (
    BacktestResult, TimeBoundedStore, TimeLeakageError,
    bootstrap_ci, run_walk_forward,
)
from northstar.models import parse_utc
from northstar.strategies import build

from conftest import START, mk_event, mk_odds, mk_result, mk_tip


def make_tbs_with_history():
    """A TimeBoundedStore whose event starts in the future and which has a
    result/rating that becomes available at a known time."""
    tbs = TimeBoundedStore()
    start = parse_utc(START)
    ev = {
        "event_id": "ev-x", "sport": "football", "competition": "T",
        "home_team": "A", "away_team": "B",
        "scheduled_start_utc": START, "status": "finished",
        "group_order": 1,
    }
    tbs.register_event(ev)
    final_at = start + timedelta(hours=2)
    tbs.add_result(ev, 1, 0, available_at=final_at)
    tbs.update_ratings({"A": 1550.0, "B": 1450.0}, available_at=final_at)
    return tbs, start, final_at


class TestTimeBoundedStore:
    def test_rating_not_visible_before_release(self):
        tbs, start, final_at = make_tbs_with_history()
        assert tbs.team_rating("A", final_at - timedelta(seconds=1)) is None
        assert tbs.team_rating("A", final_at) == 1550.0

    def test_last_result_not_visible_before_release(self):
        tbs, start, final_at = make_tbs_with_history()
        assert tbs.last_result("A", final_at - timedelta(seconds=1)) is None
        r = tbs.last_result("A", final_at)
        assert r["goals"] == 1

    def test_reading_event_at_or_after_start_raises(self):
        tbs, start, final_at = make_tbs_with_history()
        # strictly before start: allowed
        tbs.event("ev-x", start - timedelta(seconds=1))
        with pytest.raises(TimeLeakageError):
            tbs.event("ev-x", start)
        with pytest.raises(TimeLeakageError):
            tbs.event("ev-x", final_at)

    def test_unknown_event_raises(self):
        tbs, start, _ = make_tbs_with_history()
        with pytest.raises(TimeLeakageError):
            tbs.event("ev-nope", start - timedelta(seconds=1))


class TestWalkForward:
    def test_cutoff_not_before_start_is_a_leak_violation(self, store):
        """A strategy whose declared cutoff is at/after kickoff must be
        refused and recorded as a leakage violation, not settled."""
        class BadCutoff:
            name = "bad cutoff"
            description = "deliberately broken"
            odds_provider = "market_avg"

            def predict(self, event, tbs, start, market_odds=None,
                        odds_observed_at=None, as_of=None):
                return {"cutoff_utc": start + timedelta(minutes=5),
                        "selection_key": "home", "selection_text": "home",
                        "model": {}}

            def ratings_after(self, event, hg, ag, tbs, final_at):
                return {}

        ev = mk_event(store, event_id="ev-l1")
        mk_odds(store, "ev-l1", observed="2026-01-09T12:00:00Z")
        mk_result(store, event_id="ev-l1", home_goals=2, away_goals=1)
        rep = run_walk_forward(store, [ev], BadCutoff(), "bad-cutoff-v1")
        assert rep["bets"] == []
        assert len(rep["leak_violations"]) == 1
        assert store.tips(tipster_id="bad-cutoff-v1") == []

    def test_read_after_declared_cutoff_is_refused(self, store):
        class FalseCutoff:
            name = "false cutoff"
            description = "reads a feature after the declared cutoff"
            odds_provider = "market_avg"

            def predict(self, event, tbs, start, market_odds=None,
                        odds_observed_at=None, as_of=None):
                tbs.last_result(event["home_team"],
                                odds_observed_at + timedelta(minutes=1))
                return {"cutoff_utc": odds_observed_at,
                        "selection_key": "home", "selection_text": "home",
                        "model": {}}

            def ratings_after(self, event, hg, ag, tbs, final_at):
                return {}

        ev = mk_event(store, event_id="ev-read-cutoff")
        for sel, odds in (("home", 2.0), ("draw", 3.0), ("away", 4.0)):
            mk_odds(store, ev["event_id"], selection_key=sel, odds=odds,
                    observed="2026-01-09T12:00:00Z")
        mk_result(store, event_id=ev["event_id"])
        rep = run_walk_forward(store, [ev], FalseCutoff(), "false-cutoff-v1")
        assert rep["bets"] == []
        assert len(rep["leak_violations"]) == 1

    def test_no_leak_violations_for_honest_strategies(self, store):
        mk_event(store, event_id="ev-l2")
        store.conn.execute(
            "UPDATE events SET group_order=1 WHERE event_id='ev-l2'")
        store.commit()
        for sel, o in (("home", 2.2), ("draw", 3.4), ("away", 3.1)):
            mk_odds(store, "ev-l2", selection_key=sel, odds=o,
                    observed="2026-01-09T12:00:00Z")
        mk_result(store, event_id="ev-l2", home_goals=2, away_goals=1)
        events = [store.get_event("ev-l2")]
        for sid in ("market-favourite-v1", "market-longshot-v1",
                    "elo-edge-v1", "draw-no-bet-v1"):
            rep = run_walk_forward(store, events, build(sid), sid)
            assert rep["leak_violations"] == [], sid

    def test_result_not_visible_to_later_event_until_after_bet(self, store):
        """Ordering guarantee: event 2's model must not see event 1's
        result before event 1's bet has been made. We verify the release
        ordering by checking that a strategy reading team history at the
        cutoff of event 2 sees only pre-event-2 data."""

        class Recorder:
            name = "recorder"
            description = "records what is visible at cutoff"
            odds_provider = "market_avg"

            def __init__(self):
                self.seen = {}

            def predict(self, event, tbs, start, market_odds=None,
                        odds_observed_at=None):
                # read the home team's history at the declared cutoff
                self.seen[event["event_id"]] = tbs.last_result(
                    event["home_team"], odds_observed_at)
                return {"cutoff_utc": odds_observed_at,
                        "selection_key": "none", "selection_text": "no bet",
                        "model": {}}

            def ratings_after(self, event, hg, ag, tbs, final_at):
                return {}

        ev1 = mk_event(store, event_id="ev-e1", home="A", away="B",
                       start="2026-01-10T15:00:00Z")
        ev2 = mk_event(store, event_id="ev-e2", home="A", away="C",
                       start="2026-01-11T15:00:00Z")
        store.conn.execute(
            "UPDATE events SET group_order=1 WHERE event_id='ev-e1'")
        store.conn.execute(
            "UPDATE events SET group_order=2 WHERE event_id='ev-e2'")
        store.commit()
        for eid in ("ev-e1", "ev-e2"):
            for sel, o in (("home", 2.2), ("draw", 3.4), ("away", 3.1)):
                mk_odds(store, eid, selection_key=sel, odds=o,
                        observed="2026-01-09T12:00:00Z")
        mk_result(store, event_id="ev-e1", home_goals=1, away_goals=0,
                  final_at="2026-01-10T17:00:00Z")
        mk_result(store, event_id="ev-e2", home_goals=0, away_goals=2,
                  final_at="2026-01-11T17:00:00Z")
        strat = Recorder()
        run_walk_forward(store, [ev1, ev2], strat, "recorder-v1")
        # At ev1's cutoff (2026-01-09T12:00Z) nothing has happened yet:
        assert strat.seen["ev-e1"] is None
        # At ev2's cutoff (also 2026-01-09T12:00Z) ev1's result (released
        # at 2026-01-10T17:00Z) must still be invisible:
        assert strat.seen["ev-e2"] is None

    def test_ordering_invariance(self, store):
        """Shuffling the input event list must not change any bet,
        skip, or settlement outcome."""
        starts = ["2026-01-10T15:00:00Z", "2026-01-12T15:00:00Z",
                  "2026-01-14T15:00:00Z"]
        for i, st in enumerate(starts):
            mk_event(store, event_id=f"ev-o{i}", home=f"T{i}", away=f"U{i}",
                     start=st)
            store.conn.execute(
                f"UPDATE events SET group_order={i + 1} "
                f"WHERE event_id='ev-o{i}'")
            for sel, o in (("home", 2.2), ("draw", 3.4), ("away", 3.1)):
                mk_odds(store, f"ev-o{i}", selection_key=sel, odds=o,
                        observed="2026-01-09T12:00:00Z")
            mk_result(store, event_id=f"ev-o{i}",
                      home_goals=(1, 0, 2)[i], away_goals=(0, 2, 1)[i],
                      final_at=st.replace("T15:00:00Z", "T17:00:00Z"))
        store.commit()
        events = [store.get_event(f"ev-o{i}") for i in range(3)]
        rev = events[::-1]
        a = run_walk_forward(store, events, build("market-favourite-v1"),
                             "mf-a")
        # Distinct strategy_id -> distinct tip ids, so the second run is a
        # clean comparison over the same underlying events.
        b = run_walk_forward(store, rev, build("market-favourite-v1"),
                             "mf-b")
        key = lambda rep: [(x["event_id"], x["selection"], x["odds"])
                           for x in rep["bets"]]
        assert key(a) == key(b)


class TestBootstrapCi:
    def test_deterministic_with_seed(self):
        seq = [1.0, -1.0, 0.5, -0.5, 2.0]
        a = bootstrap_ci(seq)
        b = bootstrap_ci(seq)
        assert a == b

    def test_ci_brackets_mean(self):
        seq = [1.0, -1.0, 0.5, -0.5, 2.0, -2.0, 1.0]
        ci = bootstrap_ci(seq)
        assert ci["lo"] <= ci["mean"] <= ci["hi"]
        assert ci["n"] == len(seq)

    def test_empty_sequence(self):
        ci = bootstrap_ci([])
        assert ci["n"] == 0
        assert ci["mean"] == 0.0
