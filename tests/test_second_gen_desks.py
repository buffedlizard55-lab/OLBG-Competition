"""Second-generation desks: hockey MoV Elo, hockey totals, darts MoV Elo.

Covers the 2026-09-22 additions:
- the margin-of-victory weight is exactly the quoted World-Football-Elo
  rule (https://www.eloratings.net/about, reference R11);
- a one-goal win updates ratings identically to the plain Elo desk (so the
  MoV desks are a strict refinement, not a rewrite);
- the prediction-only totals market (over/under 5.5) grades on the stored
  final score: a half line can never push, and a whole line is refused;
- the committed payloads exist and are honest (PnL unavailable, never
  zero; baseline attached; forward rows carry the new market id).
"""
import json
import os

import pytest

from northstar import models
from northstar.evaluation import (TOTALS_OUTCOME_MODES, brier_binary,
                                  totals_outcome)
from northstar.strategies import (DARTS_STRATEGIES, HOCKEY_STRATEGIES,
                                  NAIVE_BASELINE_FOR, REGISTRY)
from northstar.strategies.darts_more import mov_multiplier as darts_mov
from northstar.strategies.hockey_more import (HockeyTotalsOverBaseline,
                                              HockeyTotalsPoisson,
                                              mov_multiplier,
                                              totals_probabilities)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class TestMarginWeights:
    @pytest.mark.parametrize("margin,expected", [
        (0, 1.0), (1, 1.0),          # the rule applies to wins only
        (2, 1.5),                    # "increased by half" (2-goal win)
        (3, 1.75),                   # "by 3/4" (3-goal win)
        (4, 1.875),                  # 3/4 + (N-3)/8, N=4
        (6, 2.125),                  # 3/4 + (N-3)/8, N=6
    ])
    def test_matches_the_quoted_rule(self, margin, expected):
        assert mov_multiplier(margin) == pytest.approx(expected)
        assert darts_mov(margin) == pytest.approx(expected)

    def test_formula_is_11_plus_margin_over_8(self):
        for margin in range(3, 12):
            assert mov_multiplier(margin) == pytest.approx((11 + margin) / 8)


class TestRegistration:
    def test_new_desks_are_registered_and_listed(self):
        for sid in ("hockey-elo-mov-v1", "hockey-totals-poisson-v1",
                    "hockey-totals-over-v1", "darts-mov-elo-v1"):
            assert sid in REGISTRY
        assert "hockey-elo-mov-v1" in HOCKEY_STRATEGIES
        assert "hockey-totals-poisson-v1" in HOCKEY_STRATEGIES
        assert "darts-mov-elo-v1" in DARTS_STRATEGIES

    def test_every_new_model_desk_has_a_baseline(self):
        assert NAIVE_BASELINE_FOR["hockey-elo-mov-v1"] == "hockey-home-v1"
        assert NAIVE_BASELINE_FOR["hockey-totals-poisson-v1"] == \
            "hockey-totals-over-v1"
        assert NAIVE_BASELINE_FOR["darts-mov-elo-v1"] == \
            "darts-listed-first-v1"

    def test_desks_never_claim_an_odds_provider(self):
        for sid in ("hockey-elo-mov-v1", "hockey-totals-poisson-v1",
                    "hockey-totals-over-v1", "darts-mov-elo-v1"):
            assert REGISTRY[sid]().odds_provider is None

    def test_totals_desk_declares_the_new_market(self):
        desk = HockeyTotalsPoisson()
        assert desk.market_outcome == "total_goals_over_under_5_5"
        assert desk.sport == models.SPORT_ICE_HOCKEY
        base = HockeyTotalsOverBaseline()
        assert base.market_outcome == "total_goals_over_under_5_5"


class TestTotalsMarket:
    def test_half_line_never_pushes(self):
        assert totals_outcome(6, 5.5) == "over"
        assert totals_outcome(5, 5.5) == "under"
        assert totals_outcome(0, 5.5) == "under"

    def test_whole_line_is_refused(self):
        with pytest.raises(ValueError):
            totals_outcome(6, 6.0)

    def test_line_registration(self):
        assert TOTALS_OUTCOME_MODES["total_goals_over_under_5_5"] == 5.5
        assert models.MARKET_TOTALS_5_5 == "total_goals_over_under_5_5"

    def test_brier_binary(self):
        assert brier_binary({"over": 1.0, "under": 0.0}, "over") == 0.0
        assert brier_binary({"over": 0.0, "under": 1.0}, "over") == 2.0
        assert brier_binary({"over": 0.5, "under": 0.5}, "under") == 0.5
        with pytest.raises(ValueError):
            brier_binary({"over": 0.5, "under": 0.5}, "draw")

    def test_probabilities_are_normalised_and_monotone(self):
        flat = totals_probabilities(3.0, 3.0)
        assert sum(flat.values()) == pytest.approx(1.0, abs=1e-9)
        assert flat["over"] == pytest.approx(0.5536, abs=0.01)
        high = totals_probabilities(4.5, 4.5)
        assert high["over"] > flat["over"]
        low = totals_probabilities(1.5, 1.5)
        assert low["over"] < flat["over"]


class TestCommittedPayloads:
    @staticmethod
    def _site():
        path = os.path.join(ROOT, "site-data", "site.json")
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)

    def test_new_desks_are_in_the_committed_backtest_payload(self):
        bt = self._site()["backtest"]
        for sid in ("hockey-elo-mov-v1", "hockey-totals-poisson-v1",
                    "hockey-totals-over-v1", "darts-mov-elo-v1"):
            card = bt.get(sid)
            assert card, f"{sid} missing from the committed payload"
            assert card["pnl_available"] is False
            assert card["profit_units"] is None      # unavailable, not zero
            acc = card.get("accuracy") or {}
            assert acc.get("n_graded", 0) > 0
            assert 0.0 <= acc.get("accuracy", 0.0) <= 1.0

    def test_totals_desk_carries_its_baseline_flag(self):
        bt = self._site()["backtest"]
        nb = bt["hockey-totals-poisson-v1"]["naive_baseline"]
        assert nb["strategy_id"] == "hockey-totals-over-v1"
        assert isinstance(nb["beats_baseline"], bool)
        assert nb["n_graded"] > 0 and nb["desk_n_graded"] > 0

    def test_forward_rows_use_the_new_market_ids(self):
        rows = self._site()["forward"]["rows"]
        by_desk = {}
        for row in rows:
            by_desk.setdefault(row["strategy_id"], set()).add(row["market"])
        assert by_desk["hockey-totals-poisson-v1"] == {
            models.MARKET_TOTALS_5_5}
        assert by_desk["hockey-totals-over-v1"] == {models.MARKET_TOTALS_5_5}
        assert by_desk["hockey-elo-mov-v1"] == {
            models.MARKET_MATCH_WINNER_2WAY}

    def test_forward_rows_freeze_their_outcome_mode(self):
        rows = self._site()["forward"]["rows"]
        modes = {row["strategy_id"]: row.get("outcome") for row in rows}
        assert modes["hockey-totals-poisson-v1"] == \
            "total_goals_over_under_5_5"
        assert modes["hockey-totals-over-v1"] == "total_goals_over_under_5_5"
        assert modes["hockey-reg-poisson-v1"] == "regulation_3way"

    def test_no_new_desk_leaks_into_the_pnl_family(self):
        site = self._site()
        for sid in ("hockey-elo-mov-v1", "hockey-totals-poisson-v1",
                    "hockey-totals-over-v1", "darts-mov-elo-v1"):
            card = site["backtest"][sid]
            assert card.get("p_value_holm") is None
            assert card.get("roi") is None
            assert card["leak_violations"] == []
