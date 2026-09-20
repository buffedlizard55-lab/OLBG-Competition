"""Second-pass integrity regressions for immutable source evidence."""
from __future__ import annotations

import math

import pytest

from northstar import models
from northstar.models import OddsSnapshot, parse_utc
from northstar.settlement import implied_probabilities, settle_tip

from conftest import mk_event, mk_result, mk_tip


def test_odds_source_event_edit_is_flagged_and_original_is_retained(store):
    mk_event(store)
    first = OddsSnapshot(
        snapshot_id="snapshot-fixed",
        event_id="ev-t1",
        observed_at_utc=parse_utc("2026-01-09T12:00:00Z"),
        provider="licensed_book",
        market_key=models.MARKET_MATCH_WINNER_3WAY,
        selection_key="home",
        decimal_odds=2.1,
        source_event_id="provider-event-v1",
        timestamp_precision="provider_snapshot",
        raw_row_hash="hash-v1",
    )
    store.add_odds_snapshot(first)
    edited = OddsSnapshot(
        snapshot_id="snapshot-fixed",
        event_id="ev-t1",
        observed_at_utc=first.observed_at_utc,
        provider=first.provider,
        market_key=first.market_key,
        selection_key=first.selection_key,
        decimal_odds=2.1,
        source_event_id="provider-event-v2",
        timestamp_precision="provider_snapshot",
        raw_row_hash="hash-v1",
    )
    store.add_odds_snapshot(edited)
    row = store.odds_snapshots("ev-t1")[0]
    assert row["source_event_id"] == "provider-event-v1"
    assert models.ANOMALY_SOURCE_EDITED in {
        anomaly["kind"] for anomaly in store.anomalies()
    }


def test_tip_storage_rejects_nonfinite_or_invalid_prices(store):
    mk_event(store)
    with pytest.raises(ValueError, match="finite"):
        mk_tip(store, odds=math.nan)
    with pytest.raises(ValueError, match="greater than|> 1"):
        mk_tip(store, tip_id="bad-price", odds=1.0)
    with pytest.raises(ValueError, match="finite"):
        mk_tip(store, tip_id="bad-stake", stake=math.inf)


def test_changed_result_creates_auditable_settlement_revision(store):
    mk_event(store)
    mk_tip(store)
    mk_result(store, home_goals=2, away_goals=1)
    first = settle_tip(store, "tip-t1")
    assert first["action"] == "settled"

    # The provider corrects the score under the same event/provider key.  The
    # old settlement remains; the new one explicitly supersedes it.
    mk_result(store, home_goals=0, away_goals=1)
    second = settle_tip(store, "tip-t1")
    assert second["action"] == "settled"
    rows = store.settlements_for_tip("tip-t1")
    assert len(rows) == 2
    assert rows[-1]["supersedes_id"] == rows[0]["settlement_id"]
    assert models.ANOMALY_SOURCE_EDITED in {
        anomaly["kind"] for anomaly in store.anomalies()
    }


def test_implied_probabilities_reject_nonfinite_prices():
    with pytest.raises(ValueError, match="finite"):
        implied_probabilities([2.0, float("inf"), 3.0])
    with pytest.raises(ValueError, match="finite"):
        implied_probabilities([2.0, float("nan"), 3.0])


def test_flagged_result_is_excluded_from_grading_and_ratings(store):
    """Audit 2026-09-20 (PDCPCF matchID 79962, Price v Littler): an event
    with an open RESULT_KIND_INCONSISTENT anomaly must neither update
    walk-forward ratings nor be graded on - the review queue owns it."""
    from northstar.backtest import run_walk_forward
    from northstar.evaluation import prediction_accuracy
    from northstar.strategies import build

    mk_event(store)
    mk_result(store, home_goals=8, away_goals=11)
    store.add_anomaly(models.Anomaly(
        anomaly_id="an-dup-test",
        kind=models.ANOMALY_RESULT_KIND_INCONSISTENT,
        entity_type="result", entity_id="ev-t1",
        detected_at_utc=models.utcnow(),
        detail="conflicting duplicate result entries",
        source_urls=["https://example.org/result"]))
    store.commit()

    rep = run_walk_forward(store, [store.get_event("ev-t1")],
                           build("elo-edge-v1"), "elo-edge-v1",
                           label="flag-test", allow_no_odds=True)
    assert rep["bets"] == []
    assert any("flagged" in s.get("reason", "") for s in rep["skipped"])

    acc = prediction_accuracy(store, [{
        "event_id": "ev-t1", "selection_key": "home",
        "model": {"model_prob": {"home": 0.6, "draw": 0.2, "away": 0.2}},
    }])
    assert acc["n_graded"] == 0
    assert any("flagged" in u.get("reason", "") for u in acc["ungraded"])
