"""Leaderboard math + verification-state demotion.

Requirement coverage: "build competition leaderboard" with the project's
audit-first stance: only verified profit ranks at the top; review-state PnL
is shown but demoted and flagged.
"""
from __future__ import annotations

import pytest

from northstar import models
from northstar.leaderboard import (
    build_leaderboard, entrant_metrics, placed_bets, upcoming_bets,
)
from northstar.settlement import settle_tip

from conftest import mk_event, mk_result, mk_tip

# Staggered publish times keep the PnL sequence order deterministic.
T0 = "2026-01-01T10:00:00Z"
T1 = "2026-01-02T10:00:00Z"
T2 = "2026-01-03T10:00:00Z"
T3 = "2026-01-04T10:00:00Z"
T4 = "2026-01-05T10:00:00Z"


def _settled_bets(store, entrant, spec, tipster: str = "tester"):
    """spec: list of (suffix, selection, odds, home_goals, away_goals,
    published). Creates finished events, tips and results, settles them,
    and tags the tips with ``tipster``."""
    times = [T0, T1, T2, T3, T4]
    for i, (suffix, sel, odds, hg, ag) in enumerate(spec):
        eid = f"ev-{entrant}-{suffix}"
        mk_event(store, event_id=eid)
        mk_tip(store, tip_id=f"tip-{entrant}-{suffix}", event_id=eid,
               tipster=tipster, selection_key=sel, odds=odds,
               published=times[i % len(times)])
        mk_result(store, event_id=eid, home_goals=hg, away_goals=ag)
        settle_tip(store, tip_id=f"tip-{entrant}-{suffix}")


class TestMetrics:
    def test_profit_and_roi(self, store):
        _settled_bets(store, "a", [
            ("1", "home", 2.0, 2, 1),   # +1.00
            ("2", "away", 3.0, 0, 3),   # +2.00
            ("3", "home", 2.0, 1, 2),   # -1.00
        ])
        m = entrant_metrics(store, "tester")
        assert m["settled_bets"] == 3
        assert m["wins"] == 2 and m["losses"] == 1
        assert m["profit_units"] == pytest.approx(2.0)
        assert m["turnover_units"] == pytest.approx(3.0)
        assert m["roi"] == pytest.approx(2.0 / 3.0)
        assert m["strike_rate"] == pytest.approx(2 / 3)
        assert m["verification_state"] == "verified"

    def test_max_drawdown_with_stake(self, store):
        """PnL sequence +1, +1, -3, +1 (in publish-time order): peak 2,
        trough -1 -> max drawdown 3 units."""
        legs = [
            ("1", "home", 2.0, 1.0, 2, 0, T0),   # +1
            ("2", "away", 2.0, 1.0, 0, 2, T1),   # +1   (peak 2)
            ("3", "home", 4.0, 3.0, 0, 3, T2),   # -3   (trough -1)
            ("4", "home", 2.0, 1.0, 3, 0, T3),   # +1
        ]
        for suffix, sel, odds, stake, hg, ag, pub in legs:
            eid = f"ev-d2-{suffix}"
            mk_event(store, event_id=eid)
            mk_tip(store, tip_id=f"tip-d2-{suffix}", event_id=eid,
                   selection_key=sel, odds=odds, stake=stake,
                   published=pub)
            mk_result(store, event_id=eid, home_goals=hg, away_goals=ag)
            settle_tip(store, f"tip-d2-{suffix}")
        m = entrant_metrics(store, "tester")
        assert m["pnl_sequence"] == [1.0, 1.0, -3.0, 1.0]
        assert m["max_drawdown_units"] == pytest.approx(3.0)
        assert m["profit_units"] == pytest.approx(0.0)

    def test_strike_rate_ignores_voids(self, store):
        mk_event(store, event_id="ev-wv",
                 status=models.EVENT_STATUS_CANCELLED)
        mk_tip(store, tip_id="tip-v", event_id="ev-wv", published=T4)
        _settled_bets(store, "sv", [
            ("1", "home", 2.0, 2, 1),   # +1 win
            ("2", "home", 2.0, 0, 2),   # -1 loss
        ])
        settle_tip(store, "tip-v")  # void
        m = entrant_metrics(store, "tester")
        assert m["voids"] == 1
        assert m["settled_bets"] == 2
        assert m["strike_rate"] == pytest.approx(0.5)


class TestRanking:
    def test_rank_by_verified_profit(self, store):
        store.upsert_entrant("rich", "Rich", "strategy", "d")
        store.upsert_entrant("poor", "Poor", "strategy", "d")
        _settled_bets(store, "rich", [
            ("1", "home", 3.0, 2, 0),   # +2
            ("2", "away", 3.0, 0, 3),   # +2
        ], tipster="rich")
        _settled_bets(store, "poor", [
            ("1", "home", 2.0, 0, 1),   # -1
        ], tipster="poor")
        lb = build_leaderboard(store)
        by_id = {r["entrant_id"]: r for r in lb}
        assert by_id["rich"]["rank"] < by_id["poor"]["rank"]
        assert by_id["rich"]["profit_units"] == pytest.approx(4.0)
        assert by_id["poor"]["profit_units"] == pytest.approx(-1.0)
        assert by_id["rich"]["rank"] == 1

    def test_review_pnl_demoted_below_verified(self, store):
        """Review-state profit (even large) ranks below verified profit
        (even zero), because review numbers are not audited."""
        store.upsert_entrant("verif", "VerifiedZero", "strategy", "d")
        mk_event(store, event_id="ev-v1",
                 status=models.EVENT_STATUS_CANCELLED)
        mk_tip(store, tip_id="tip-v1", event_id="ev-v1", tipster="verif",
               published=T0)
        settle_tip(store, "tip-v1")  # void -> 0 verified profit

        store.upsert_entrant("rev", "ReviewFive", "strategy", "d")
        mk_event(store, event_id="ev-r1", identity="unmatched")
        mk_tip(store, tip_id="tip-r1", event_id="ev-r1", tipster="rev",
               odds=6.0, published=T1)
        mk_result(store, event_id="ev-r1", home_goals=3, away_goals=0)
        settle_tip(store, "tip-r1")   # +5 but review-state

        lb = build_leaderboard(store)
        by_id = {r["entrant_id"]: r for r in lb}
        assert by_id["rev"]["profit_units"] == pytest.approx(5.0)
        assert by_id["rev"]["verification_state"] == "review"
        assert by_id["verif"]["verification_state"] in ("verified", "none")
        assert by_id["verif"]["rank"] < by_id["rev"]["rank"]


class TestBetViews:
    def test_placed_and_upcoming_split(self, store):
        # settled bet (placed, not upcoming)
        _settled_bets(store, "pv", [("1", "home", 2.0, 2, 1)])
        # open bet on a scheduled event (upcoming)
        mk_event(store, event_id="ev-open",
                 status=models.EVENT_STATUS_SCHEDULED,
                 start="2026-02-01T15:00:00Z")
        mk_tip(store, tip_id="tip-open", event_id="ev-open",
               published=T4, status=models.TIP_STATUS_OPEN)
        placed = placed_bets(store)
        upcoming = upcoming_bets(store)
        assert {b["tip_id"] for b in placed} == {"tip-pv-1", "tip-open"}
        assert {b["tip_id"] for b in upcoming} == {"tip-open"}
        assert upcoming[0]["event"].startswith("Home FC")
        assert upcoming[0]["status"] == "open"

    def test_missing_event_shows_unmatched_label(self, store):
        """A tip whose event row is absent (e.g. an imported OLBG card with
        an unparsable kickoff) must still be reviewable."""
        from northstar.models import Tip
        store.add_tip(Tip(
            tip_id="tip-orphan", tipster_id="orphan", strategy_id="imported",
            event_id="ev-ghost", market="olbg:Full Time Result",
            selection="Draw", selection_key="crowd",
            published_at_utc=models.parse_utc(T0),
            collected_at_utc=models.utcnow(),
            cutoff_at_utc=models.parse_utc(T0), odds_decimal=None,
            status=models.TIP_STATUS_PENDING, notes="imported"))
        store.commit()
        placed = placed_bets(store, entrant_id="orphan")
        assert len(placed) == 1
        assert "not matched" in placed[0]["event"]
        assert placed[0]["odds"] is None
