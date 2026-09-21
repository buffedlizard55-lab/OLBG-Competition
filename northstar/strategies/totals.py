"""Total-goals (over/under 2.5) strategies on the football pilot.

Market: ``total_goals_over_under_2_5`` - settled on the 90-minute score
(``settlement.match_outcome_totals``; a half-goal line never pushes).

Research lineage (verified references in docs/STRATEGIES.md): Maher (1982)
introduced independent-Poisson attack/defence goal models; Dixon & Coles
(1997, JRSS-C 46(2) 265-280) built the betting-market version.  This module
implements the *simplest honest member* of that family so every input is a
released, time-bounded statistic:

    lambda_home = league_home_rate * attack(home) * defence(away)
    lambda_away = league_away_rate * attack(away) * defence(home)

where ``attack`` = goals scored per match / league mean scored per match and
``defence`` = goals conceded per match / league mean conceded per match, all
computed from matches *released* at the cutoff (TimeBoundedStore).  P(total
>= 3) is the Poisson complement of P(0..2 goals) for the sum (a Poisson with
rate lambda_home + lambda_away under independence).

Pre-registered priors (stated before grading; NOT fitted on the pilot):
- PRIOR_MATCHES = 6: a Bayesian-style shrink toward league rates; each
  team's attack/defence multiplier is (goals + prior*league_mean) /
  (matches + prior) so early-season rates are not driven by one match;
- LEAGUE_PRIOR_HOME / AWAY = 1.60 / 1.30 goals per match: the 2023/24
  Bundesliga per-match averages rounded to one decimal are NOT used - that
  would be a look-ahead unless the season is fully released; instead a
  generic top-flight prior (documented literature range ~1.5/1.2) is used
  until the walk-forward has >= MIN_LEAGUE_MATCHES released matches, after
  which the league rates come from released data only;
- EDGE_THRESHOLD = 0.03 for the value probe; the baseline probe has none.

Both strategies are prediction+price desks on the verified pilot: they bet
the stored ``market_avg`` over/under price at the collection-window close,
so they settle real paper PnL and enter the Holm family.
"""
from __future__ import annotations

import math
from typing import Any, Dict, Optional

from ..models import MARKET_TOTALS_2_5, SPORT_FOOTBALL
from .base import Strategy, no_bet

PRIOR_MATCHES = 6
LEAGUE_PRIOR_HOME = 1.60
LEAGUE_PRIOR_AWAY = 1.30
MIN_LEAGUE_MATCHES = 10
EDGE_THRESHOLD = 0.03
LINE = 2.5


def poisson_cdf(k: int, lam: float) -> float:
    """P(X <= k) for X ~ Poisson(lam)."""
    if lam <= 0:
        return 1.0
    return math.exp(-lam) * sum(lam ** i / math.factorial(i)
                                for i in range(k + 1))


def totals_fair(odds: Dict[str, Optional[float]]
                ) -> Optional[Dict[str, float]]:
    """Margin-removed over/under probabilities (proportional method)."""
    o, u = odds.get("over"), odds.get("under")
    if o is None or u is None or o <= 1.0 or u <= 1.0:
        return None
    io, iu = 1.0 / o, 1.0 / u
    tot = io + iu
    return {"over": io / tot, "under": iu / tot}


def expected_goals(tbs, home: str, away: str, at) -> Dict[str, Any]:
    """Time-bounded Poisson rates for one fixture (read-audited)."""
    released = tbs.released_matches(at)
    n = len(released)
    if n >= MIN_LEAGUE_MATCHES:
        league_home = sum(m["home_goals"] for m in released) / n
        league_away = sum(m["away_goals"] for m in released) / n
        league_source = f"released ({n} matches)"
    else:
        league_home, league_away = LEAGUE_PRIOR_HOME, LEAGUE_PRIOR_AWAY
        league_source = f"prior (only {n} released matches)"
    mean_scored = (league_home + league_away) / 2.0
    mean_conceded = mean_scored

    def multipliers(team: str) -> Dict[str, float]:
        rows = tbs.goal_record(team, at)
        m = len(rows)
        scored = sum(r["goals"] for r in rows)
        conceded = sum(r["opponent_goals"] for r in rows)
        attack = ((scored + PRIOR_MATCHES * mean_scored)
                  / ((m + PRIOR_MATCHES) * mean_scored))
        defence = ((conceded + PRIOR_MATCHES * mean_conceded)
                   / ((m + PRIOR_MATCHES) * mean_conceded))
        return {"matches": m, "attack": attack, "defence": defence}

    h, a = multipliers(home), multipliers(away)
    lam_h = league_home * h["attack"] * a["defence"]
    lam_a = league_away * a["attack"] * h["defence"]
    p_under = poisson_cdf(int(LINE), lam_h + lam_a)   # P(total <= 2)
    return {
        "lambda_home": round(lam_h, 4), "lambda_away": round(lam_a, 4),
        "league_rates": {"home": round(league_home, 4),
                         "away": round(league_away, 4),
                         "source": league_source},
        "team_multipliers": {"home": {k: round(v, 4) if isinstance(v, float)
                                      else v for k, v in h.items()},
                             "away": {k: round(v, 4) if isinstance(v, float)
                                      else v for k, v in a.items()}},
        "model_prob": {"over": 1.0 - p_under, "under": p_under},
        "line": LINE,
    }


class PoissonTotalsValue(Strategy):
    """Back over/under 2.5 when the Poisson model beats the fair price by
    >= EDGE_THRESHOLD."""

    def __init__(self, edge_threshold: float = EDGE_THRESHOLD,
                 odds_provider: str = "market_avg"):
        super().__init__(
            name="Poisson totals value (O/U 2.5)",
            description=(f"Independent-Poisson goal model (Maher/Dixon-Coles "
                         f"family; league rates + shrunk attack/defence "
                         f"multipliers from released matches only, prior "
                         f"weight {PRIOR_MATCHES} matches) vs the "
                         f"margin-removed market over/under 2.5 price; bets "
                         f"the side with a >= {edge_threshold:.0%} edge. "
                         "Pre-registered priors, not fitted."),
            odds_provider=odds_provider, sport=SPORT_FOOTBALL,
            market=MARKET_TOTALS_2_5)
        self.edge_threshold = edge_threshold

    def predict(self, event, tbs, start, market_odds=None,
                odds_observed_at=None, as_of=None) -> Dict[str, Any]:
        if odds_observed_at is None or not market_odds:
            return no_bet(odds_observed_at,
                          {"reason": "no pre-start totals price"})
        fair = totals_fair(market_odds)
        if fair is None:
            return no_bet(odds_observed_at,
                          {"reason": "incomplete totals prices"})
        xg = expected_goals(tbs, event["home_team"], event["away_team"],
                            odds_observed_at)
        edge = {k: xg["model_prob"][k] - fair[k] for k in fair}
        trail = {**xg, "fair_prob": fair, "edge": edge}
        side = max(edge, key=edge.get)
        if edge[side] >= self.edge_threshold:
            return {"cutoff_utc": odds_observed_at, "selection_key": side,
                    "selection_text": f"{side} 2.5 goals",
                    "model": {**trail,
                              "rule": "poisson edge >= threshold"}}
        return no_bet(odds_observed_at,
                      {**trail, "reason": "edge below threshold"})


class MarketTotalsFavourite(Strategy):
    """Baseline: always back the market's more-likely side of O/U 2.5."""

    def __init__(self, odds_provider: str = "market_avg"):
        super().__init__(
            name="Market totals favourite (O/U 2.5 baseline)",
            description=("Always backs the margin-removed market favourite "
                         "side of the over/under 2.5 goals market. Baseline "
                         "reference for the totals family, not a claimed "
                         "edge."),
            odds_provider=odds_provider, sport=SPORT_FOOTBALL,
            market=MARKET_TOTALS_2_5)

    def predict(self, event, tbs, start, market_odds=None,
                odds_observed_at=None, as_of=None) -> Dict[str, Any]:
        if odds_observed_at is None or not market_odds:
            return no_bet(odds_observed_at,
                          {"reason": "no pre-start totals price"})
        fair = totals_fair(market_odds)
        if fair is None:
            return no_bet(odds_observed_at,
                          {"reason": "incomplete totals prices"})
        side = max(fair, key=fair.get)
        return {"cutoff_utc": odds_observed_at, "selection_key": side,
                "selection_text": f"{side} 2.5 goals",
                "model": {"fair_prob": fair,
                          "rule": "argmax fair totals probability"}}
