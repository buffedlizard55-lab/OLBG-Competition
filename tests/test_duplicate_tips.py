"""Duplicate-tip handling: idempotency + explicit anomaly.

Requirement coverage: "automated tests for ... duplicate tips".
"""
from __future__ import annotations

from northstar import models
from northstar.models import ANOMALY_DUPLICATE_TIP, Tip
from northstar.settlement import settle_tip

from conftest import mk_event, mk_result, mk_tip


def test_same_tip_id_twice_is_noop(store):
    """Re-adding an identical tip (e.g. re-run of an importer) must not
    duplicate rows and must not create a DUPLICATE_TIP anomaly."""
    mk_event(store)
    mk_tip(store)
    out = store.add_tip(Tip(
        tip_id="tip-t1", tipster_id="tester", strategy_id="test-strategy",
        event_id="ev-t1", market=models.MARKET_MATCH_WINNER_3WAY,
        selection="home", selection_key="home",
        published_at_utc=models.parse_utc("2026-01-09T12:00:00Z"),
        collected_at_utc=models.utcnow(),
        cutoff_at_utc=models.parse_utc("2026-01-09T12:00:00Z"),
        odds_decimal=2.0, odds_source="testbook", stake_units=1.0,
        raw_payload_hash="deadbeef",  # same payload -> pure re-run
        status=models.TIP_STATUS_OPEN,
    ))
    assert out["created"] is False
    assert len(store.tips()) == 1
    assert {a["kind"] for a in store.anomalies()} == set()


def test_recaptured_payload_hash_flags_source_edited(store):
    """Same tip re-captured with a *different* payload hash = source edit."""
    mk_event(store)
    mk_tip(store)
    out = store.add_tip(Tip(
        tip_id="tip-t1", tipster_id="tester", strategy_id="test-strategy",
        event_id="ev-t1", market=models.MARKET_MATCH_WINNER_3WAY,
        selection="home", selection_key="home",
        published_at_utc=models.parse_utc("2026-01-09T12:00:00Z"),
        collected_at_utc=models.utcnow(),
        cutoff_at_utc=models.parse_utc("2026-01-09T12:00:00Z"),
        odds_decimal=2.0, odds_source="testbook", stake_units=1.0,
        raw_payload_hash="CHANGED",  # differs from the stored 'deadbeef'
        status=models.TIP_STATUS_OPEN,
    ))
    assert out["created"] is False
    assert models.ANOMALY_SOURCE_EDITED in {
        a["kind"] for a in store.anomalies()}


def test_same_selection_different_tip_id_flags_duplicate(store):
    """Same event + market + selection via a *different* tip id is a
    duplicate bet: allowed to store (audit trail) but flagged."""
    mk_event(store)
    mk_tip(store, tip_id="tip-a")
    out = store.add_tip(Tip(
        tip_id="tip-b", tipster_id="tester", strategy_id="test-strategy",
        event_id="ev-t1", market=models.MARKET_MATCH_WINNER_3WAY,
        selection="home", selection_key="home",
        published_at_utc=models.parse_utc("2026-01-09T12:30:00Z"),
        collected_at_utc=models.utcnow(),
        cutoff_at_utc=models.parse_utc("2026-01-09T12:30:00Z"),
        odds_decimal=2.0, odds_source="testbook", stake_units=1.0,
        status=models.TIP_STATUS_OPEN,
    ))
    assert out["created"] is True
    assert len(store.tips()) == 2
    assert ANOMALY_DUPLICATE_TIP in {a["kind"] for a in store.anomalies()}


def test_different_selections_are_not_duplicates(store):
    mk_event(store)
    mk_tip(store, tip_id="tip-a", selection_key="home")
    mk_tip(store, tip_id="tip-b", selection_key="away")
    assert len(store.tips()) == 2
    assert {a["kind"] for a in store.anomalies()} == set()


def test_duplicate_tips_settle_independently(store):
    """Two distinct tips on the same selection (different publish times ->
    DUPLICATE_TIP flagged) are separate bets; each settles with its own PnL
    row and they never cross-contaminate."""
    from northstar.models import ANOMALY_DUPLICATE_TIP
    mk_event(store)
    mk_tip(store, tip_id="tip-a", odds=2.0)
    mk_tip(store, tip_id="tip-b", odds=2.5,
           published="2026-01-09T12:30:00Z")
    assert ANOMALY_DUPLICATE_TIP in {a["kind"] for a in store.anomalies()}
    mk_result(store, home_goals=2, away_goals=1)  # home wins
    out_a = settle_tip(store, "tip-a")
    out_b = settle_tip(store, "tip-b")
    assert out_a["action"] == "settled"
    assert out_b["action"] == "settled"
    s_a = store.latest_settlement("tip-a")
    s_b = store.latest_settlement("tip-b")
    assert s_a["pnl_units"] == 1.0      # 1.0 * (2.0 - 1)
    assert s_b["pnl_units"] == 1.5      # 1.0 * (2.5 - 1)


def test_backtest_resettlement_is_idempotent(store):
    """Re-running settlement of an already-settled tip returns the same
    settlement id and appends nothing (no double-counted PnL)."""
    mk_event(store)
    mk_tip(store)
    mk_result(store, home_goals=2, away_goals=1)
    first = settle_tip(store, "tip-t1")
    second = settle_tip(store, "tip-t1")
    assert first["action"] == "settled"
    assert second["action"] == "already_settled"
    assert second["settlement_id"] == first["settlement_id"]
    assert len(store.settlements_for_tip("tip-t1")) == 1
