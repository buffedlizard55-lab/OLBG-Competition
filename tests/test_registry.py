"""Hypothesis registry consistency + dynamic sport coverage.

The registry is the single source of truth for the strategy lab; the site
must never show a "tested" hypothesis that the engine cannot build, and a
sport row must never claim a pilot that the store does not contain.
"""
from __future__ import annotations

from northstar import models
from northstar.registry import HYPOTHESES, REGISTRY_VERSION, registry_payload
from northstar.report import build_coverage
from northstar.strategies import (
    DARTS_STRATEGIES, FOOTBALL_STRATEGIES, FORWARD_STRATEGIES,
    HOCKEY_STRATEGIES, PREDICTION_ONLY_STRATEGIES, REGISTRY,
)

from conftest import mk_event


class TestHypothesisRegistry:
    def test_every_tested_id_is_buildable(self):
        for h in HYPOTHESES:
            if h.get("tested"):
                assert h["tested"] in REGISTRY, h["name"]

    def test_every_runnable_strategy_is_registered(self):
        listed = {h.get("tested") for h in HYPOTHESES}
        for sid in (FOOTBALL_STRATEGIES + HOCKEY_STRATEGIES
                    + DARTS_STRATEGIES):
            assert sid in listed, sid
        for sids in FORWARD_STRATEGIES.values():
            for sid in sids:
                assert sid in listed, sid

    def test_statuses_are_from_the_controlled_vocabulary(self):
        allowed = {"Pilot-tested", "Forward-live", "Ready to source",
                   "Blocked"}
        for h in HYPOTHESES:
            assert h["status"] in allowed, h["name"]

    def test_payload_shape(self):
        p = registry_payload()
        assert p["version"] == REGISTRY_VERSION
        assert isinstance(p["hypotheses"], list) and p["hypotheses"]

    def test_prediction_only_strategies_never_claim_pnl(self):
        for sid in PREDICTION_ONLY_STRATEGIES:
            s = REGISTRY[sid]()
            assert s.odds_provider is None

    def test_forward_desks_exist_for_live_sports(self):
        assert set(FORWARD_STRATEGIES) == {"football", "ice_hockey",
                                           "darts"}


class TestCoveragePromotion:
    def test_darts_row_pending_without_data(self, store):
        cov = build_coverage(store)
        darts = next(c for c in cov if c["sport"] == "Darts")
        assert darts["status"] == "results_path_available"
        assert "empty" in darts["results_path"]  # discovery finding shown

    def test_darts_row_promotes_only_with_finished_events(self, store):
        mk_event(store, event_id="ev-dart-1", sport="darts",
                 status=models.EVENT_STATUS_SCHEDULED,
                 identity="probable")
        cov = build_coverage(store)
        darts = next(c for c in cov if c["sport"] == "Darts")
        assert darts["status"] == "results_path_available"

        mk_event(store, event_id="ev-dart-2", sport="darts",
                 status=models.EVENT_STATUS_FINISHED,
                 identity="probable")
        cov = build_coverage(store)
        darts = next(c for c in cov if c["sport"] == "Darts")
        assert darts["status"] == "results_pilot"
        assert "2 events" in darts["results_path"]

    def test_all_21_olbg_sport_families_present(self, store):
        cov = build_coverage(store)
        names = {c["sport"] for c in cov if c["scope"] == "olbg"}
        expected = {
            "Horse Racing", "Football", "Tennis", "Golf",
            "American Football", "Baseball", "Basketball", "Boxing",
            "Cricket", "Cycling", "Darts", "Gaelic Football",
            "Greyhounds", "Handball", "Hurling", "Ice Hockey",
            "Motor Racing", "Rugby Union", "Rugby League", "Snooker",
            "Volleyball",
        }
        assert names == expected
        blocked = [c for c in cov if c["status"] == "verification_blocked"]
        assert len(blocked) == 18
