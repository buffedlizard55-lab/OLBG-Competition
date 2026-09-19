"""Event-state handling: postponements, cancellations/voids, disputes.

Requirement coverage: "automated tests for postponements, voids, ...
disputed results". The governing rule: uncertainty is never converted into
a loss - postponed = pending, cancelled = void (stake refunded), disputed =
withheld for review.
"""
from __future__ import annotations

import pytest

from northstar import models
from northstar.models import (
    ANOMALY_RESULT_NOT_FINAL, TIP_STATUS_DISPUTED, TIP_STATUS_PENDING,
    TIP_STATUS_VOID,
)
from northstar.settlement import settle_tip

from conftest import START, mk_event, mk_result, mk_tip


class TestPostponement:
    def test_postponed_event_keeps_tip_pending(self, store):
        mk_event(store, status=models.EVENT_STATUS_POSTPONED)
        mk_tip(store)
        out = settle_tip(store, "tip-t1")
        assert out["action"] == "pending"
        assert out["settlement_id"] is None
        assert store.get_tip("tip-t1")["status"] == TIP_STATUS_PENDING

    def test_postponement_is_never_a_loss(self, store):
        mk_event(store, status=models.EVENT_STATUS_POSTPONED)
        mk_tip(store, odds=10.0, stake=5.0)
        settle_tip(store, "tip-t1")
        assert store.latest_settlement("tip-t1") is None  # no PnL row at all

    def test_postponed_then_rescheduled_settles_later(self, store):
        """Postponed now, finished with a result later -> settles normally."""
        ev = mk_event(store, status=models.EVENT_STATUS_POSTPONED)
        mk_tip(store)
        assert settle_tip(store, "tip-t1")["action"] == "pending"
        # source resolves: event finished 2-1 (home)
        mk_event(store, event_id="ev-t1",
                 status=models.EVENT_STATUS_FINISHED)
        mk_result(store, home_goals=2, away_goals=1)
        out = settle_tip(store, "tip-t1")
        assert out["action"] == "settled"
        assert out["gates"]["identity"] == "pass"
        assert store.latest_settlement("tip-t1")["outcome"] == "won"


class TestCancellationVoids:
    def test_cancelled_event_voids_tip(self, store):
        mk_event(store, status=models.EVENT_STATUS_CANCELLED)
        mk_tip(store, odds=2.0, stake=3.0)
        out = settle_tip(store, "tip-t1")
        assert out["action"] == "void"
        s = store.latest_settlement("tip-t1")
        assert s["outcome"] == "void"
        assert s["pnl_units"] == 0.0
        assert s["stake_units"] == 3.0
        assert store.get_tip("tip-t1")["status"] == TIP_STATUS_VOID

    def test_abandoned_event_voids_tip(self, store):
        mk_event(store, status=models.EVENT_STATUS_ABANDONED)
        mk_tip(store)
        assert settle_tip(store, "tip-t1")["action"] == "void"
        assert store.latest_settlement("tip-t1")["pnl_units"] == 0.0

    def test_void_excluded_from_turnover(self, store):
        """Void stakes must not enter turnover or the PnL sequence."""
        from northstar.leaderboard import entrant_metrics
        mk_event(store, event_id="ev-v1",
                 status=models.EVENT_STATUS_CANCELLED)
        mk_event(store, event_id="ev-w1")  # finished
        mk_tip(store, tip_id="tip-v1", event_id="ev-v1", stake=2.0)
        mk_tip(store, tip_id="tip-w1", event_id="ev-w1", odds=2.0)
        mk_result(store, event_id="ev-w1", home_goals=1, away_goals=0)
        settle_tip(store, "tip-v1")
        settle_tip(store, "tip-w1")
        m = entrant_metrics(store, "tester")
        assert m["voids"] == 1
        assert m["settled_bets"] == 1          # only the counted win
        assert m["turnover_units"] == pytest.approx(1.0)  # void stake excluded
        assert m["profit_units"] == pytest.approx(1.0)


class TestDisputed:
    def test_disputed_event_withholds_settlement(self, store):
        mk_event(store, status=models.EVENT_STATUS_DISPUTED)
        mk_tip(store)
        out = settle_tip(store, "tip-t1")
        assert out["action"] == "disputed"
        assert out["settlement_id"] is None
        assert store.get_tip("tip-t1")["status"] == TIP_STATUS_DISPUTED
        assert store.latest_settlement("tip-t1") is None

    def test_disputed_event_raises_review_anomaly(self, store):
        mk_event(store, status=models.EVENT_STATUS_DISPUTED)
        mk_tip(store)
        out = settle_tip(store, "tip-t1")
        kinds = {a["kind"] for a in store.anomalies()}
        assert ANOMALY_RESULT_NOT_FINAL in kinds
        assert len(out["anomalies"]) == 1

    def test_conflicting_providers_dispute_tip(self, store):
        """Two result providers disagree -> disputed, no settlement."""
        from northstar.models import ANOMALY_RESULT_SOURCE_CONFLICT
        mk_event(store)
        mk_tip(store)
        mk_result(store, provider="openligadb", home_goals=2, away_goals=1)
        mk_result(store, provider="other", home_goals=1, away_goals=1)
        out = settle_tip(store, "tip-t1")
        assert out["action"] == "disputed"
        assert out["gates"]["reconciliation"] == "fail:providers disagree"
        assert store.get_tip("tip-t1")["status"] == TIP_STATUS_DISPUTED
        assert store.latest_settlement("tip-t1") is None
        kinds = {a["kind"] for a in store.anomalies()}
        assert ANOMALY_RESULT_SOURCE_CONFLICT in kinds

    def test_agreeing_providers_settle_verified(self, store):
        """Two independent providers agreeing strengthens, not blocks."""
        mk_event(store)
        mk_tip(store)
        mk_result(store, provider="openligadb", home_goals=2, away_goals=1)
        mk_result(store, provider="other", home_goals=2, away_goals=1)
        out = settle_tip(store, "tip-t1")
        assert out["action"] == "settled"
        assert out["gates"]["reconciliation"].startswith("pass:2")
        assert store.latest_settlement("tip-t1")[
            "verification_state"] == "verified"


class TestLifecycleEdgeCases:
    def test_scheduled_event_stays_pending(self, store):
        mk_event(store, status=models.EVENT_STATUS_SCHEDULED)
        mk_tip(store)
        assert settle_tip(store, "tip-t1")["action"] == "pending"

    def test_result_timestamp_before_start_is_blocked(self, store):
        """A 'final' result stamped before kickoff cannot settle anything."""
        mk_event(store)
        mk_tip(store)
        mk_result(store, final_at="2026-01-10T14:00:00Z")  # 1h before start
        out = settle_tip(store, "tip-t1")
        assert out["action"] == "blocked"
        assert out["gates"]["result"] == "fail:result timestamp before start"

    def test_missing_raw_hash_downgrades_to_review(self, store):
        mk_event(store)
        mk_tip(store)
        mk_result(store, raw_hash=None)
        out = settle_tip(store, "tip-t1")
        assert out["action"] == "review"
        assert out["gates"]["integrity"].startswith("fail:no raw hash")
        assert "openligadb" in out["gates"]["integrity"]
        assert store.latest_settlement("tip-t1")[
            "verification_state"] == "review"

    def test_agreeing_providers_one_missing_hash_downgrades(self, store):
        """Integrity gate: if ANY agreeing provider lacks a raw payload
        hash, the settlement cannot be verified."""
        mk_event(store)
        mk_tip(store)
        mk_result(store, provider="openligadb", home_goals=2, away_goals=1)
        mk_result(store, provider="other", home_goals=2, away_goals=1,
                  raw_hash=None)
        out = settle_tip(store, "tip-t1")
        assert out["action"] == "review"
        assert out["gates"]["integrity"].startswith("fail:no raw hash")
        assert "other" in out["gates"]["integrity"]

    def test_unverified_identity_downgrades_to_review(self, store):
        mk_event(store, identity="unmatched")
        mk_tip(store)
        mk_result(store)
        out = settle_tip(store, "tip-t1")
        assert out["action"] == "review"
        assert out["gates"]["identity"] == "fail:unmatched"

    def test_odds_after_start_fails_time_gate(self, store):
        mk_event(store)
        mk_tip(store, published="2026-01-10T16:00:00Z",
                cutoff="2026-01-10T16:00:00Z")  # post-start
        mk_result(store)
        out = settle_tip(store, "tip-t1")
        assert out["gates"]["time"] == "fail:post-start input"
        assert out["action"] == "review"
        kinds = {a["kind"] for a in store.anomalies()}
        assert models.ANOMALY_ODDS_AFTER_START in kinds
