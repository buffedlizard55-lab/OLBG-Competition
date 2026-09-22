"""Elo with time-based recency decay (football, 1X2 pilot).

Research question (pre-registered, docs/STRATEGIES.md): the frozen
``elo-edge-v1`` desk weights every past match forever once it has moved a
rating.  The standard extension lets a team's rating relax back toward
the seed between matches, so a team that has not played for months is not
rated as if its last result were fresh:

    r_eff(t) = SEED + (r - SEED) * 2 ** (-(t - t0) / HALF_LIFE)

where (r, t0) is the team's latest stored rating update at/before the
decision time.  PRE-REGISTERED HALF_LIFE_DAYS = 365 (one year), stated
before grading on the pilot and NOT tuned on pilot outcomes.  Ratings are
stored exactly like ``elo-edge-v1`` (shared ``elo.elo_update``); the decay
is applied at READ time only, so the two desks share one rating history
and differ only in the read model.

Same 3-way mapping (``elo.elo_three_way``), same edge rule (model-argmax
with >= 3 pt edge over the margin-removed market).  Enters the Holm PnL
family as a control for ``elo-edge-v1``.
"""
from __future__ import annotations

from typing import Any, Dict

from ..models import SPORT_FOOTBALL
from .base import Strategy, market_implied
from .elo import (EDGE_THRESHOLD, INITIAL, _draw_rate, _expected_home,
                  elo_update)

HALF_LIFE_DAYS = 365.0


def effective_rating(tbs, team: str, at, seed: float = INITIAL,
                     half_life_days: float = HALF_LIFE_DAYS) -> float:
    """Decayed reading of a team's latest stored rating at time ``at``.

    Reads the store through ``tbs.team_rating`` (read-audited like every
    other feature) and then applies the exponential relaxation to ``seed``
    over the gap since the last update.  No update -> the seed itself.
    """
    r = tbs.team_rating(team, at)
    if r is None:
        return seed
    updates = [u for u in tbs.rating_updates.get(team, [])
               if u["available_at"] <= at]
    if not updates:
        return seed
    t0 = max(u["available_at"] for u in updates)
    days = (at - t0).total_seconds() / 86400.0
    return seed + (r - seed) * (2.0 ** (-days / half_life_days))


class EloDecay(Strategy):
    """Elo value edge with time-decayed ratings (1X2)."""

    def __init__(self, edge_threshold: float = EDGE_THRESHOLD,
                 odds_provider: str = "market_avg"):
        super().__init__(
            name="Elo value edge (recency decay)",
            description=(f"Same Elo model as elo-edge-v1 (K=40, home adv 60, "
                         f"shared rating history) but ratings relax toward "
                         f"1500 with a pre-registered {HALF_LIFE_DAYS:.0f}-day "
                         f"half-life; backs the 3-way model-argmax when edge "
                         f"over the margin-removed market >= "
                         f"{edge_threshold:.0%}. Control for elo-edge-v1."),
            odds_provider=odds_provider, sport=SPORT_FOOTBALL)
        self.edge_threshold = edge_threshold

    def predict(self, event, tbs, start, market_odds=None,
                odds_observed_at=None, as_of=None) -> Dict[str, Any]:
        if odds_observed_at is None or not market_odds:
            from .base import no_bet
            return no_bet(odds_observed_at,
                          {"reason": "no pre-start market price"})
        at = odds_observed_at
        rh = effective_rating(tbs, event["home_team"], at)
        ra = effective_rating(tbs, event["away_team"], at)
        e_home = _expected_home(rh, ra)
        p_draw = _draw_rate(rh + 60.0, ra)
        model = {"home": e_home * (1 - p_draw),
                 "draw": p_draw,
                 "away": (1.0 - e_home) * (1 - p_draw)}
        fair = market_implied(market_odds)
        if fair is None:
            from .base import no_bet
            return no_bet(at, {"reason": "incomplete market prices"})
        edge = {k: model[k] - fair[k] for k in model}
        best_model = max(model, key=model.get)
        trail = {"ratings": {"home": round(rh, 1), "away": round(ra, 1)},
                 "decay": f"half_life={HALF_LIFE_DAYS:.0f}d",
                 "model_prob": model, "fair_prob": fair, "edge": edge}
        if edge[best_model] >= self.edge_threshold:
            return {"cutoff_utc": at, "selection_key": best_model,
                    "selection_text": best_model,
                    "model": {**trail,
                              "rule": "argmax decayed model with "
                                      "edge>=threshold"}}
        from .base import no_bet
        return no_bet(at, {**trail, "reason": "edge below threshold"})

    def ratings_after(self, event, home_goals, away_goals, tbs, final_at):
        # Identical rating history to elo-edge-v1 (shared update rule).
        return elo_update(event, home_goals, away_goals, tbs, final_at)
