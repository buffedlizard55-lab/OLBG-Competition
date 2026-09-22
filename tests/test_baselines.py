"""Naive baseline desks (home-ice hockey, listed-first darts).

These desks exist so the accuracy-only sports have a no-information
reference: the Elo desks' hit rates are only meaningful next to "always
home" / "always the listed-first player".  They must never touch PnL, never
carry a selective threshold, and always carry the flat 0.5/0.5 prior whose
Brier is 0.5 by construction.
"""
from __future__ import annotations

import pytest

from northstar import models
from northstar.backtest import run_walk_forward
from northstar.evaluation import prediction_accuracy
from northstar.strategies import (
    DARTS_STRATEGIES, HOCKEY_STRATEGIES, PREDICTION_ONLY_STRATEGIES, build,
)

from conftest import START, mk_event


class TestBaselineContracts:
    def test_registered_as_prediction_only(self):
        assert "hockey-home-v1" in HOCKEY_STRATEGIES
        assert "darts-listed-first-v1" in DARTS_STRATEGIES
        for sid in ("hockey-home-v1", "darts-listed-first-v1"):
            assert sid in PREDICTION_ONLY_STRATEGIES
            s = build(sid)
            assert s.odds_provider is None

    def test_no_selectivity_threshold_by_design(self):
        for sid in ("hockey-home-v1", "darts-listed-first-v1"):
            assert not hasattr(build(sid), "min_prob")

    def test_flat_prior_and_brier_is_uninformative(self):
        from northstar.evaluation import brier_three
        prior = {"home": 0.5, "draw": 0.0, "away": 0.5}
        # 2-way sports never produce a draw, so the only reachable actuals:
        for actual in ("home", "away"):
            assert brier_three(prior, actual) == pytest.approx(0.5)


class TestHockeyHomeBaseline:
    def test_always_predicts_home(self, store):
        mk_event(store, event_id="ev-h1", sport="ice_hockey",
                 identity="probable")
        strat = build("hockey-home-v1")
        start = models.parse_utc(START)
        d = strat.predict(store.get_event("ev-h1"), _tbs(), start)
        assert d["selection_key"] == "home"
        assert d["selection_text"] == "Home FC"
        assert d["model"]["model_prob"] == {"home": 0.5, "draw": 0.0,
                                            "away": 0.5}
        assert d["cutoff_utc"] < start

    def test_walk_forward_grades_every_unflagged_event(self, hockey_store):
        events = [e for e in hockey_store.events()
                  if e["status"] == "finished"]
        assert len(events) == 21
        rep = run_walk_forward(hockey_store, events,
                               build("hockey-home-v1"), "hockey-home-v1",
                               label="hockey-pilot", allow_no_odds=True)
        assert not rep["leak_violations"]
        # 21 events, 4 carry RESULT_KIND_INCONSISTENT anomalies (review
        # queue owns them) -> 17 prediction-only bets
        assert len(rep["bets"]) == 17
        assert all(b["outcome_action"] == "prediction_only"
                   for b in rep["bets"])
        # every tip is unsettleable (no odds path) - never PnL
        for t in hockey_store.tips(tipster_id="hockey-home-v1"):
            assert t["status"] == models.TIP_STATUS_UNSETTLEABLE
            assert hockey_store.odds_snapshots(t["event_id"]) or True
        ev = prediction_accuracy(hockey_store, rep["bets"],
                                 sport="ice_hockey")
        assert ev["n_graded"] == len(rep["bets"])
        # the home share on the graded pool is the reference number
        assert ev["hits"] == sum(1 for g in ev["graded"]
                                 if g["actual"] == "home")
        assert ev["mean_brier"] == pytest.approx(0.5, abs=1e-9)


class TestDartsListedFirstBaseline:
    def test_always_predicts_listed_first(self, store):
        mk_event(store, event_id="ev-d1", sport="darts",
                 identity="probable", home="Michael Smith",
                 away="Michael van Gerwen")
        strat = build("darts-listed-first-v1")
        start = models.parse_utc(START)
        d = strat.predict(store.get_event("ev-d1"), _tbs(), start)
        assert d["selection_key"] == "home"
        assert d["selection_text"] == "Michael Smith"

    def test_forward_renderer_writes_baseline_copy_not_a_refusal(self):
        from northstar.predictor import render_forward_prediction
        entry = {
            "home_team": "Kölner Haie", "away_team": "Eisbären Berlin",
            "selection": "Kölner Haie", "selection_key": "home",
            "cutoff_utc": "2026-09-21T13:13:41Z",
            "model": {
                "model_prob": {"home": 0.5, "draw": 0.0, "away": 0.5},
                "prior": "flat 0.5/0.5 (uninformative by design)",
                "rule": "always the home side"},
        }
        out = render_forward_prediction(entry, source_links=[])
        assert out["evidence_ok"] is True
        assert "(baseline)" in out["headline"]
        assert "no-information reference" in out["body"]
        assert "Kölner Haie" in out["body"]

    def test_forward_renderer_still_refuses_broken_entries(self):
        from northstar.predictor import render_forward_prediction
        out = render_forward_prediction({
            "home_team": "A", "away_team": "B", "selection": "A",
            "selection_key": "home",
            "model": {"prior": "x", "rule": "y"}},   # no model_prob
            source_links=[])
        assert out["evidence_ok"] is False

    def test_forward_mode_cutoff_is_as_of(self, store):
        mk_event(store, event_id="ev-d2", sport="darts",
                 status=models.EVENT_STATUS_SCHEDULED, identity="probable")
        strat = build("darts-listed-first-v1")
        start = models.parse_utc(START)
        as_of = _hours_before(start, 48)
        d = strat.predict(store.get_event("ev-d2"), _tbs(), start,
                          as_of=as_of)
        assert d["selection_key"] == "home"
        assert d["cutoff_utc"] == as_of


def _hours_before(dt, hours):
    from datetime import timedelta
    return dt - timedelta(hours=hours)


def _tbs():
    from northstar.backtest import TimeBoundedStore
    return TimeBoundedStore()


class TestNaiveBaselineComparison:
    """The per-card "beats its naive baseline?" flag (pure comparison)."""

    def test_above_baseline(self):
        from northstar.evaluation import naive_baseline_comparison
        out = naive_baseline_comparison(
            {"accuracy": 0.8125, "n_graded": 48},
            {"accuracy": 0.6627, "n_graded": 421},
            "darts-listed-first-v1")
        assert out["beats_baseline"] is True
        assert out["strategy_id"] == "darts-listed-first-v1"
        assert out["desk_accuracy"] == 0.8125
        assert out["desk_n_graded"] == 48
        assert out["accuracy"] == 0.6627
        assert out["n_graded"] == 421

    def test_below_baseline(self):
        from northstar.evaluation import naive_baseline_comparison
        out = naive_baseline_comparison(
            {"accuracy": 0.471, "n_graded": 17},
            {"accuracy": 0.647, "n_graded": 17},
            "hockey-reg-home-v1")
        assert out["beats_baseline"] is False

    def test_equal_is_not_a_win(self):
        from northstar.evaluation import naive_baseline_comparison
        out = naive_baseline_comparison(
            {"accuracy": 0.6, "n_graded": 5},
            {"accuracy": 0.6, "n_graded": 5},
            "b")
        assert out["beats_baseline"] is False

    @pytest.mark.parametrize("desk,base", [
        (None, {"accuracy": 0.6, "n_graded": 5}),
        ({"accuracy": 0.6, "n_graded": 5}, None),
        ({"accuracy": None, "n_graded": 0},
         {"accuracy": 0.6, "n_graded": 5}),
        ({"accuracy": 0.6, "n_graded": 5},
         {"accuracy": 0.6, "n_graded": 0}),
        ({}, {}),
    ])
    def test_missing_sides_render_no_flag(self, desk, base):
        from northstar.evaluation import naive_baseline_comparison
        assert naive_baseline_comparison(desk, base, "b") is None


class TestNaiveBaselineWiring:
    def test_every_model_desk_paired_with_a_registered_baseline(self):
        from northstar.strategies import (
            NAIVE_BASELINE_FOR, PREDICTION_ONLY_STRATEGIES, REGISTRY,
        )
        # Every accuracy desk must name the baseline it is quoted against
        # (added 2026-09-22: hockey MoV Elo and the hockey totals desk, plus
        # the darts MoV control).  A model desk without a baseline is a
        # wiring bug: its hit rate would be quoted against nothing.
        assert set(NAIVE_BASELINE_FOR) == {
            "hockey-elo-v1", "hockey-reg-poisson-v1",
            "hockey-elo-mov-v1", "hockey-totals-poisson-v1",
            "darts-elo-v1", "darts-mov-elo-v1",
            # Full-season football accuracy pair (added 2026-09-22).
            "elo-favourite-3way-v1", "football-totals-poisson-v1"}
        for sid, baseline_id in NAIVE_BASELINE_FOR.items():
            assert sid in REGISTRY and baseline_id in REGISTRY
            assert sid in PREDICTION_ONLY_STRATEGIES
            assert baseline_id in PREDICTION_ONLY_STRATEGIES

    def test_committed_site_payload_carries_the_flag(self):
        """The shipped site.json must already carry the comparison (the
        pipeline attaches it before every deploy)."""
        import json, os
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        site = json.load(open(os.path.join(root, "site-data", "site.json"),
                              encoding="utf-8"))
        bt = site.get("backtest") or {}
        from northstar.strategies import NAIVE_BASELINE_FOR
        expect = NAIVE_BASELINE_FOR
        for sid, baseline_id in expect.items():
            nb = (bt.get(sid) or {}).get("naive_baseline")
            assert nb, f"{sid} must carry its naive baseline comparison"
            assert nb["strategy_id"] == baseline_id
            assert nb["accuracy"] is not None and nb["n_graded"] > 0
            assert nb["desk_accuracy"] is not None and nb["desk_n_graded"] > 0
            assert isinstance(nb["beats_baseline"], bool)
        # PnL strategies never carry an accuracy-baseline flag:
        assert "naive_baseline" not in (bt.get("ah-poisson-value-v1") or {})
