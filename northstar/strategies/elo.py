"""Elo-ratings value strategy (football).

A small, auditable Elo model:
- each team seeded at 1500;
- expected home win (2-way): E = 1 / (1 + 10^((R_away - (R_home + home_adv))/400));
- result score S: home win 1.0 / draw 0.5 / away 0.0;
- update R += K*(S - E), K=40, home_adv=60 rating points.

3-way mapping (documented heuristic):
- 2-way p_home2 = E, p_away2 = 1 - E;
- draw rate p_draw = clamp(0.28 - 0.05*|R_home_eff - R_away|/100, 0.15, 0.32);
- p_home = p_home2*(1-p_draw), p_away = p_away2*(1-p_draw), p_draw.

Bet rule (edge): compare the model 3-way to the margin-removed market
3-way at the observed price; back the model-argmax only when its edge
(model - market) >= edge_threshold (default 3 points). No edge -> no bet.
This is the kind of rule a top tipster states: "we back X where the market
under-rates them."
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from ..models import SPORT_FOOTBALL, fmt_utc
from .base import Strategy, market_implied, no_bet

INITIAL = 1500.0
K = 40.0
HOME_ADV = 60.0
EDGE_THRESHOLD = 0.03


def _expected_home(r_home: float, r_away: float) -> float:
    return 1.0 / (1.0 + 10.0 ** ((r_away - (r_home + HOME_ADV)) / 400.0))


def _draw_rate(r_home_eff: float, r_away: float) -> float:
    d = abs(r_home_eff - r_away) / 100.0
    return max(0.15, min(0.32, 0.28 - 0.05 * d))


class EloEdge(Strategy):
    def __init__(self, edge_threshold: float = EDGE_THRESHOLD,
                 odds_provider: str = "market_avg"):
        super().__init__(
            name="Elo value edge",
            description=(f"Elo ratings (K={K:.0f}, home adv {HOME_ADV:.0f}); "
                         f"backs the model-argmax when edge over the "
                         f"margin-removed market >= {edge_threshold:.0%}. "
                         "No edge -> no bet."),
            odds_provider=odds_provider)
        self.edge_threshold = edge_threshold

    def _ratings_at(self, tbs, event, at):
        rh = tbs.team_rating(event["home_team"], at) or INITIAL
        ra = tbs.team_rating(event["away_team"], at) or INITIAL
        return rh, ra

    def predict(self, event, tbs, start, market_odds=None,
                odds_observed_at=None, as_of=None) -> Dict[str, Any]:
        if odds_observed_at is None or not market_odds:
            return no_bet(odds_observed_at,
                          {"reason": "no pre-start market price"})
        rh, ra = self._ratings_at(tbs, event, odds_observed_at)
        e_home = _expected_home(rh, ra)
        p_home2 = e_home
        p_away2 = 1.0 - e_home
        p_draw = _draw_rate(rh + HOME_ADV, ra)
        model = {"home": p_home2 * (1 - p_draw),
                 "draw": p_draw,
                 "away": p_away2 * (1 - p_draw)}
        fair = market_implied(market_odds)
        if fair is None:
            return no_bet(odds_observed_at,
                          {"reason": "incomplete market prices"})
        edge = {k: model[k] - fair[k] for k in model}
        best_model = max(model, key=model.get)
        if edge[best_model] >= self.edge_threshold and \
                model[best_model] == max(model.values()):
            return {"cutoff_utc": odds_observed_at,
                    "selection_key": best_model,
                    "selection_text": best_model,
                    "model": {"ratings": {"home": round(rh, 1),
                                          "away": round(ra, 1)},
                              "model_prob": model,
                              "fair_prob": fair,
                              "edge": edge,
                              "rule": "argmax model with edge>=threshold"}}
        return no_bet(odds_observed_at,
                      {"reason": "edge below threshold",
                       "model_prob": model, "fair_prob": fair,
                       "edge": edge,
                       "ratings": {"home": round(rh, 1),
                                   "away": round(ra, 1)}})

    def ratings_after(self, event, home_goals, away_goals, tbs,
                      final_at) -> Dict[str, float]:
        return elo_update(event, home_goals, away_goals, tbs, final_at)


def elo_update(event, home_goals, away_goals, tbs,
               final_at) -> Dict[str, float]:
    """Shared football Elo update (K, HOME_ADV as above).

    Reads each side's latest released rating at ``final_at`` and applies the
    standard Elo delta.  Used by every football strategy that carries
    ratings, so they cannot drift apart.
    """
    rh = tbs.team_rating(event["home_team"], final_at) or INITIAL
    ra = tbs.team_rating(event["away_team"], final_at) or INITIAL
    e_home = _expected_home(rh, ra)
    if home_goals > away_goals:
        s = 1.0
    elif home_goals < away_goals:
        s = 0.0
    else:
        s = 0.5
    return {event["home_team"]: rh + K * (s - e_home),
            event["away_team"]: ra + K * ((1 - s) - (1 - e_home))}


def elo_three_way(rh: float, ra: float) -> Dict[str, float]:
    """Shared 3-way mapping of the 2-way Elo expectation (documented
    heuristic, identical for every football Elo strategy)."""
    e_home = _expected_home(rh, ra)
    p_draw = _draw_rate(rh + HOME_ADV, ra)
    return {"home": e_home * (1 - p_draw),
            "draw": p_draw,
            "away": (1.0 - e_home) * (1 - p_draw)}


class EloFavourite3Way(Strategy):
    """No-market football model (forward-test desk).

    The current season has *no permissioned odds path* in this repo
    (football-data.co.uk may not be fetched automatically and no licensed
    provider key exists), so the forward desk cannot bet a price.  This
    strategy therefore issues predictions only: it backs the 3-way model
    argmax when that probability clears ``min_prob`` and is graded on
    accuracy/Brier exactly like the hockey desk - never on PnL.
    """

    MIN_PROB = 0.45
    DECISION_LAG = timedelta(minutes=30)

    def __init__(self, min_prob: float = MIN_PROB):
        super().__init__(
            name="Football Elo favourite (no-market forward desk)",
            description=(f"3-way Elo (K={K:.0f}, home adv {HOME_ADV:.0f}, "
                         "documented draw mapping); selects the model "
                         f"argmax when p >= {min_prob:.0%}. Prediction-only "
                         "forward desk: no permissioned odds path exists for "
                         "the current season, so graded on accuracy, never "
                         "on PnL."),
            odds_provider=None,
            sport=SPORT_FOOTBALL)
        self.min_prob = min_prob

    def predict(self, event, tbs, start, market_odds=None,
                odds_observed_at=None, as_of=None) -> Dict[str, Any]:
        # Forward mode: the decision instant is the capture time ``as_of``
        # (features can only be read there - a future pre-start lag would
        # claim inputs the desk did not have when it issued the ledger).
        at = as_of if as_of is not None else start - self.DECISION_LAG
        if at >= start:
            return no_bet(at if at < start else start - self.DECISION_LAG,
                          {"reason": "decision time not before start"})
        rh = tbs.team_rating(event["home_team"], at) or INITIAL
        ra = tbs.team_rating(event["away_team"], at) or INITIAL
        model = elo_three_way(rh, ra)
        trail = {"model_prob": model,
                 "ratings": {"home": round(rh, 1), "away": round(ra, 1)},
                 "decision_time": fmt_utc(at),
                 "odds": "none (no permissioned odds path)"}
        best = max(model, key=model.get)
        if model[best] < self.min_prob:
            return no_bet(at, {**trail, "reason": "below selectivity "
                                                 "threshold"})
        return {"cutoff_utc": at, "selection_key": best,
                "selection_text": best, "model": trail}

    def ratings_after(self, event, home_goals, away_goals, tbs,
                      final_at) -> Dict[str, float]:
        return elo_update(event, home_goals, away_goals, tbs, final_at)
