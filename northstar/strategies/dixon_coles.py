"""Dixon-Coles (1997) low-score correction, 1X2 value desk (football pilot).

Research question (pre-registered, docs/STRATEGIES.md): the independent
Poisson model (shared with the totals desk) mis-prices low-scoring scores
- it under-states the low-scoring draws (0-0, 1-1) and over-states the
low-scoring deciders (1-0, 0-1).  Dixon-Coles add the tau correction on
the score matrix (with rho < 0 it raises 0-0 and 1-1 and lowers 0-1 and
1-0, i.e. it raises the draw probability - the documented effect):

    tau(0,0) = 1 - lambda_h*lambda_a*rho
    tau(0,1) = 1 + lambda_h*rho
    tau(1,0) = 1 + lambda_a*rho
    tau(1,1) = 1 - rho
    tau(x,y) = 1  otherwise

PRE-REGISTERED RHO = -0.10 (the fitted values in the Dixon-Coles lineage
cluster near small negative values for modern top-flight data; stated
before grading, NOT tuned on the pilot).  The score matrix is truncated at
MAX_GOALS per side; a NEGATIVE cell rejects the parameters outright (the
bet is refused with the reason recorded - never clamped, never guessed).

Same league-rate/attack-defence construction as the totals desk (released
data only, shrunk multipliers), same edge rule as the Elo desk (model-argmax
with >= 3 pt edge over the margin-removed 1X2 market).  Enters the Holm PnL
family as a member of the goal-model lineage (Maher -> Dixon-Coles).
"""
from __future__ import annotations

import math
from typing import Any, Dict, Optional

from ..models import SPORT_FOOTBALL
from .base import Strategy, market_implied, no_bet
from .elo import EDGE_THRESHOLD
from .totals import expected_goals

RHO = -0.10
MAX_GOALS = 15
EDGE_THRESHOLD_DEFAULT = EDGE_THRESHOLD


def tau(x: int, y: int, lam_h: float, lam_a: float, rho: float) -> float:
    if x == 0 and y == 0:
        return 1.0 - lam_h * lam_a * rho
    if x == 0 and y == 1:
        return 1.0 + lam_h * rho
    if x == 1 and y == 0:
        return 1.0 + lam_a * rho
    if x == 1 and y == 1:
        return 1.0 - rho
    return 1.0


def _pmf(k: int, lam: float) -> float:
    if lam <= 0:
        return 1.0 if k == 0 else 0.0
    return math.exp(-lam) * lam ** k / math.factorial(k)


def dixon_coles_three_way(lam_h: float, lam_a: float,
                          rho: float = RHO) -> Dict[str, float]:
    """1X2 probabilities from the tau-corrected score matrix.

    Raises ValueError on a non-positive probability cell (the (rho, lambda)
    combination is rejected; callers refuse the bet instead of clamping).
    """
    p_home = p_draw = p_away = 0.0
    for x in range(MAX_GOALS + 1):
        mass_x = _pmf(x, lam_h)
        for y in range(MAX_GOALS + 1):
            cell = mass_x * _pmf(y, lam_a) * tau(x, y, lam_h, lam_a, rho)
            if cell < 0:
                raise ValueError(
                    f"negative score cell ({x},{y}) at lambda_h={lam_h}, "
                    f"lambda_a={lam_a}, rho={rho}")
            if x > y:
                p_home += cell
            elif x == y:
                p_draw += cell
            else:
                p_away += cell
    total = p_home + p_draw + p_away
    return {"home": p_home / total, "draw": p_draw / total,
            "away": p_away / total}


class DixonColesValue(Strategy):
    """1X2 value desk on the tau-corrected goal model (football pilot)."""

    def __init__(self, rho: float = RHO,
                 edge_threshold: float = EDGE_THRESHOLD_DEFAULT,
                 odds_provider: str = "market_avg"):
        super().__init__(
            name="Dixon-Coles 1X2 value",
            description=(f"Goal model with the Dixon-Coles tau low-score "
                         f"correction (pre-registered rho={rho:+.2f}, not "
                         f"fitted; negative cells reject the bet), same "
                         f"released-data league rates and shrunk team "
                         f"multipliers as the totals desk; backs the "
                         f"model-argmax when edge over the margin-removed "
                         f"1X2 market >= {edge_threshold:.0%}."),
            odds_provider=odds_provider, sport=SPORT_FOOTBALL)
        self.rho = rho
        self.edge_threshold = edge_threshold

    def predict(self, event, tbs, start, market_odds=None,
                odds_observed_at=None, as_of=None) -> Dict[str, Any]:
        if odds_observed_at is None or not market_odds:
            return no_bet(odds_observed_at,
                          {"reason": "no pre-start market price"})
        fair = market_implied(market_odds)
        if fair is None:
            return no_bet(odds_observed_at,
                          {"reason": "incomplete market prices"})
        xg = expected_goals(tbs, event["home_team"], event["away_team"],
                            odds_observed_at)
        try:
            model = dixon_coles_three_way(xg["lambda_home"],
                                          xg["lambda_away"], self.rho)
        except ValueError as exc:
            return no_bet(odds_observed_at,
                          {**xg, "reason": f"parameters rejected: {exc}"})
        edge = {k: model[k] - fair[k] for k in model}
        best_model = max(model, key=model.get)
        trail = {**xg, "model_prob": model, "fair_prob": fair,
                 "edge": edge, "rho": self.rho}
        if edge[best_model] >= self.edge_threshold:
            return {"cutoff_utc": odds_observed_at,
                    "selection_key": best_model,
                    "selection_text": best_model,
                    "model": {**trail,
                              "rule": "argmax DC model with "
                                      "edge>=threshold"}}
        return no_bet(odds_observed_at,
                      {**trail, "reason": "edge below threshold"})

    def ratings_after(self, event, home_goals, away_goals, tbs, final_at):
        # Goal-model desk: reads released results directly; no rating
        # state to release (keeps the Elo pool untouched).
        return {}
