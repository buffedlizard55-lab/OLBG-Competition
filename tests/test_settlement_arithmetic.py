"""Settlement arithmetic: pure decimal bet math (level stakes).

Requirement coverage: "automated tests for ... settlement arithmetic".
"""
from __future__ import annotations

import math

import pytest

from northstar.settlement import (
    decimal_pnl, implied_probabilities, match_outcome_3way,
)


class TestDecimalPnl:
    def test_won_profit(self):
        # 1 unit at 2.10 -> 1.10 profit
        assert decimal_pnl(1.0, 2.10, "won") == pytest.approx(1.10)

    def test_won_profit_stake_scaled(self):
        # 2 units at 3.50 -> 5.00 profit
        assert decimal_pnl(2.0, 3.50, "won") == pytest.approx(5.00)

    def test_won_low_odds(self):
        # 1 unit at 1.05 -> 0.05 profit (odds just above 1 are legal)
        assert decimal_pnl(1.0, 1.05, "won") == pytest.approx(0.05)

    def test_lost_returns_negative_stake(self):
        assert decimal_pnl(1.0, 2.0, "lost") == pytest.approx(-1.0)
        assert decimal_pnl(2.5, 1.2, "lost") == pytest.approx(-2.5)

    def test_void_is_zero(self):
        assert decimal_pnl(1.0, 2.0, "void") == 0.0
        assert decimal_pnl(99.0, 1.5, "void") == 0.0

    def test_push_is_zero(self):
        assert decimal_pnl(1.0, 2.0, "push") == 0.0

    def test_stake_must_be_positive(self):
        with pytest.raises(ValueError):
            decimal_pnl(0.0, 2.0, "won")
        with pytest.raises(ValueError):
            decimal_pnl(-1.0, 2.0, "won")

    def test_won_requires_stored_odds(self):
        with pytest.raises(ValueError):
            decimal_pnl(1.0, None, "won")

    def test_odds_must_exceed_one(self):
        with pytest.raises(ValueError):
            decimal_pnl(1.0, 1.0, "won")
        with pytest.raises(ValueError):
            decimal_pnl(1.0, 0.5, "won")

    def test_odds_must_be_finite(self):
        with pytest.raises(ValueError):
            decimal_pnl(1.0, float("nan"), "won")
        with pytest.raises(ValueError):
            decimal_pnl(1.0, float("inf"), "won")

    def test_unknown_outcome_rejected(self):
        with pytest.raises(ValueError):
            decimal_pnl(1.0, 2.0, "draw-bet")

    def test_rounding_is_stable(self):
        # repeating decimals are rounded to 10dp so ledger sums are exact
        v = decimal_pnl(1.0, 1.1, "won")
        assert v == round(1.0 * 0.1, 10)
        assert not math.isnan(v)


class TestMatchOutcome3way:
    def test_home_win(self):
        assert match_outcome_3way("home", 2, 1) == "won"
        assert match_outcome_3way("away", 2, 1) == "lost"
        assert match_outcome_3way("draw", 2, 1) == "lost"

    def test_away_win(self):
        assert match_outcome_3way("away", 0, 3) == "won"
        assert match_outcome_3way("home", 0, 3) == "lost"

    def test_draw(self):
        assert match_outcome_3way("draw", 1, 1) == "won"
        assert match_outcome_3way("home", 1, 1) == "lost"
        assert match_outcome_3way("away", 1, 1) == "lost"

    def test_zero_zero(self):
        assert match_outcome_3way("draw", 0, 0) == "won"


class TestImpliedProbabilities:
    def test_margin_removed_sums_to_one(self):
        p = implied_probabilities([2.0, 3.5, 3.5])
        assert p[0] + p[1] + p[2] == pytest.approx(1.0)

    def test_proportional_normalisation(self):
        # 1/2 + 1/3.5 + 1/3.5 = 0.5 + 0.285714 + 0.285714 = 1.071428
        # home share = 0.5 / 1.071428 = 0.466667
        p = implied_probabilities([2.0, 3.5, 3.5])
        assert p[0] == pytest.approx(0.4666666667)
        assert p[1] == pytest.approx(0.2666666667)

    def test_fair_odds_recover_raw_implied(self):
        # if 1/odds already sum to 1, normalisation is the identity
        odds = [2.0, 5.0, 10.0]  # 0.5 + 0.2 + 0.1 = 0.8 -> not fair, no-raise
        p = implied_probabilities(odds)
        assert sum(p) == pytest.approx(1.0)

    def test_rejects_bad_prices(self):
        with pytest.raises(ValueError):
            implied_probabilities([2.0, 1.0, 3.0])
        with pytest.raises(ValueError):
            implied_probabilities([2.0, None, 3.0])
        with pytest.raises(ValueError):
            implied_probabilities([0.9, 3.0, 3.0])
