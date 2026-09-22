"""Asian-handicap strategies on the football pilot (third settleable market).

Market: ``asian_handicap`` — the line is per-event (``AHh`` in the
football-data file: "Market size of handicap (home team)", verified against
the source's notes.txt 2026-09-22). A negative line handicaps the home
team. Integer lines push; quarter lines split the stake half/half across
the two neighbouring component lines (settlement:
``settlement.match_outcome_asian_handicap`` — win+push = ``half_won``,
lose+push = ``half_lost``).

The value desk reuses the totals module's independent-Poisson goal model
(Maher 1982 / Dixon-Coles 1997 family; league rates + shrunk attack/defence
multipliers from *released* matches only). From (lambda_home, lambda_away)
it builds the full margin distribution D = H - A and, for the priced line,
the model's P(win)/P(push)/P(lose) for each side — blended across the two
half-stakes on a quarter line, which is exactly how the bet settles.

Value definition (pre-registered, stated before any grading):

    model_ev  = P_model(win) * (odds - 1) - P_model(lose)
    market_ev = fair_win * (odds - 1) - fair_lose
    edge      = model_ev - market_ev

where ``fair_*`` are the margin-removed (proportional) probabilities from
the two quoted prices — the standard de-marging approximation; it folds the
push probability proportionally into win/lose (documented simplification,
same family as the O/U fair-value method). The desk bets the side with the
larger ``edge`` only when ``edge >= EDGE_THRESHOLD`` (0.03, the same 3%
prior as the other value desks) *and* the model EV is positive.

Both strategies settle real paper PnL on the verified pilot and join the
Holm family. Nothing here is a claimed edge; the pilot sample is 27
matches.
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional

from ..models import MARKET_ASIAN_HANDICAP, SPORT_FOOTBALL
from ..settlement import asian_handicap_components
from .base import Strategy, no_bet
from .totals import expected_goals

EDGE_THRESHOLD = 0.03
# Poisson support for the score grid. Pilot goal rates are ~1.6/1.3 per
# match; P(X > 15) < 1e-9 there, and the grid is renormalized so the
# margin probabilities sum to exactly 1 regardless of truncation.
MAX_GOALS = 15


def margin_distribution(lam_home: float, lam_away: float,
                        max_goals: int = MAX_GOALS
                        ) -> Dict[int, float]:
    """P(home margin D = H - A) under independent Poissons.

    Renormalized over the truncated grid so the probabilities sum to 1.
    """
    def pois(lam: float) -> List[float]:
        # P(X = k) for k in 0..max_goals, via recurrence (stable for small
        # lambda; exp(-lam) underflow is impossible for league goal rates).
        out = [1.0]
        for k in range(1, max_goals + 1):
            out.append(out[-1] * lam / k)
        e = math.exp(-lam)
        return [p * e for p in out]

    ph, pa = pois(lam_home), pois(lam_away)
    dist: Dict[int, float] = {}
    total = 0.0
    for h in range(max_goals + 1):
        for a in range(max_goals + 1):
            d = h - a
            p = ph[h] * pa[a]
            dist[d] = dist.get(d, 0.0) + p
            total += p
    return {d: p / total for d, p in dist.items()}


def ah_probabilities(margin_dist: Dict[int, float], line: float
                     ) -> Dict[str, float]:
    """P(win)/P(push)/P(lose) for the HOME side at ``line`` (blended over
    quarter-line components). The AWAY side is the mirror: away wins when
    home loses and pushes on the same scores."""
    components = asian_handicap_components(line)
    win = push = lose = 0.0
    for comp in components:
        for d, p in margin_dist.items():
            adjusted = d + comp
            if adjusted > 0:
                win += p
            elif adjusted == 0:
                push += p
            else:
                lose += p
    n = len(components)
    return {"win": win / n, "push": push / n, "lose": lose / n}


def side_probabilities(margin_dist: Dict[int, float], line: float,
                       selection_key: str) -> Dict[str, float]:
    home = ah_probabilities(margin_dist, line)
    if selection_key == "home":
        return home
    if selection_key == "away":
        return {"win": home["lose"], "push": home["push"],
                "lose": home["win"]}
    raise ValueError(f"unknown Asian-handicap selection: {selection_key}")


def ah_fair(odds: Dict[str, Optional[float]]
            ) -> Optional[Dict[str, float]]:
    """Margin-removed AH win probabilities (proportional method). The
    push probability is folded proportionally into win/lose — the standard
    two-way de-marging approximation, documented above."""
    o_h, o_a = odds.get("home"), odds.get("away")
    if o_h is None or o_a is None or o_h <= 1.0 or o_a <= 1.0:
        return None
    i_h, i_a = 1.0 / o_h, 1.0 / o_a
    tot = i_h + i_a
    return {"home": i_h / tot, "away": i_a / tot}


def expected_value(prob: Dict[str, float], odds: float) -> float:
    """EV per 1 unit staked (push contributes 0: stake refunded)."""
    return prob["win"] * (odds - 1.0) - prob["lose"]


def line_from_market(market_odds: Optional[Dict[str, Any]]
                     ) -> Optional[float]:
    """The priced line, as offered by the walk-forward engine."""
    line = (market_odds or {}).get("line")
    if line is None:
        return None
    try:
        asian_handicap_components(line)   # validates the quarter grid
    except ValueError:
        return None
    return float(line)


class AsianHandicapValue(Strategy):
    """Back the side whose Poisson-model EV beats the de-margined market
    EV by >= 3 points, with a positive model EV."""

    def __init__(self, edge_threshold: float = EDGE_THRESHOLD,
                 odds_provider: str = "market_avg"):
        super().__init__(
            name="Poisson Asian-handicap value",
            description=(f"Independent-Poisson goal model (same priors as "
                         f"the totals desk) evaluated on the priced AH line "
                         f"(quarter lines split half/half); bets the side "
                         f"whose model EV beats the margin-removed market "
                         f"EV by >= {edge_threshold:.0%} per unit staked, "
                         f"and only when the model EV itself is positive. "
                         f"Pre-registered priors, not fitted."),
            odds_provider=odds_provider, sport=SPORT_FOOTBALL,
            market=MARKET_ASIAN_HANDICAP)
        self.edge_threshold = edge_threshold

    def predict(self, event, tbs, start, market_odds=None,
                odds_observed_at=None, as_of=None) -> Dict[str, Any]:
        if odds_observed_at is None or not market_odds:
            return no_bet(odds_observed_at,
                          {"reason": "no pre-start AH price"})
        line = line_from_market(market_odds)
        if line is None:
            return no_bet(odds_observed_at,
                          {"reason": "no usable quarter-grid AH line"})
        fair = ah_fair(market_odds)
        if fair is None:
            return no_bet(odds_observed_at,
                          {"reason": "incomplete AH prices"})
        xg = expected_goals(tbs, event["home_team"], event["away_team"],
                            odds_observed_at)
        margin_dist = margin_distribution(xg["lambda_home"],
                                          xg["lambda_away"])
        probs = {side: side_probabilities(margin_dist, line, side)
                 for side in ("home", "away")}
        evs, market_evs, edges = {}, {}, {}
        for side in ("home", "away"):
            evs[side] = expected_value(probs[side], market_odds[side])
            fair_p = {"win": fair[side], "lose": fair[_other(side)]}
            market_evs[side] = expected_value(fair_p, market_odds[side])
            edges[side] = evs[side] - market_evs[side]
        trail = {
            **xg, "line": line,
            "components": asian_handicap_components(line),
            "model_prob": probs,
            "fair_prob": fair,
            "model_ev": evs, "market_ev": market_evs, "edge_ev": edges,
        }
        side = max(edges, key=edges.get)
        if edges[side] < self.edge_threshold or evs[side] <= 0:
            return no_bet(odds_observed_at,
                          {**trail, "reason": "edge below threshold or "
                                             "non-positive model EV"})
        selection_text = (f"{event['home_team']} {line:+g} AH"
                          if side == "home"
                          else f"{event['away_team']} {-line:+g} AH")
        return {"cutoff_utc": odds_observed_at, "selection_key": side,
                "selection_text": selection_text, "line": line,
                "model": {**trail, "rule": "poisson AH EV edge >= "
                                          "threshold"}}


class AsianHandicapFavourite(Strategy):
    """Baseline: always back the market's more-likely side of the AH line."""

    def __init__(self, odds_provider: str = "market_avg"):
        super().__init__(
            name="Market AH favourite (baseline)",
            description=("Always backs the margin-removed market favourite "
                         "side of the priced Asian handicap. Baseline "
                         "reference for the AH family, not a claimed edge."),
            odds_provider=odds_provider, sport=SPORT_FOOTBALL,
            market=MARKET_ASIAN_HANDICAP)

    def predict(self, event, tbs, start, market_odds=None,
                odds_observed_at=None, as_of=None) -> Dict[str, Any]:
        if odds_observed_at is None or not market_odds:
            return no_bet(odds_observed_at,
                          {"reason": "no pre-start AH price"})
        line = line_from_market(market_odds)
        if line is None:
            return no_bet(odds_observed_at,
                          {"reason": "no usable quarter-grid AH line"})
        fair = ah_fair(market_odds)
        if fair is None:
            return no_bet(odds_observed_at,
                          {"reason": "incomplete AH prices"})
        side = max(fair, key=fair.get)
        selection_text = (f"{event['home_team']} {line:+g} AH"
                          if side == "home"
                          else f"{event['away_team']} {-line:+g} AH")
        return {"cutoff_utc": odds_observed_at, "selection_key": side,
                "selection_text": selection_text, "line": line,
                "model": {"fair_prob": fair, "line": line,
                          "rule": "argmax fair AH probability"}}


def _other(side: str) -> str:
    return "away" if side == "home" else "home"
