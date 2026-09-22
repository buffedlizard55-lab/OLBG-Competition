"""Regulation-time 3-way hockey models (prediction-only, no-market).

Research question (pre-registered before grading, docs/STRATEGIES.md):
does an independent-Poisson goal model add information about the
REGULATION-TIME (3-period) 3-way outcome - home win / regulation draw /
away win - beyond the naive always-home baseline?

Why regulation: the decisive 2-way desks (hockey-elo-v1, hockey-home-v1)
grade on the OT/SO-aware final, where a regulation draw is indistinguishable
from a loss for the desk that called it.  The regulation 3-way is the
native outcome of the goal model (P(home goals > away goals) after 60
minutes) and its draws are observable: the adapter's stored final row
carries the result kind, so ``After90Minutes`` rows give the regulation
scoreline and ``AfterExtraTime``/``AfterPenalties`` finals are proof the
regulation ended level (docs/DARTS-AUDIT.md-style audit: 4 DEL matches
with impossible layering are flagged and excluded from grading by the
review queue, never smoothed over).

Model (Maher/Dixon-Coles lineage, same walk-forward construction as the
football totals desk - pre-registered priors, NOT fitted):

    lambda_home = league_home_rate * attack(home) * defence(away)
    lambda_away = league_away_rate * attack(away) * defence(home)

league rates from matches released in the pool at the cutoff (generic
prior LEAGUE_PRIOR_HOME/AWAY until >= MIN_LEAGUE_MATCHES released), team
multipliers shrunk with PRIOR_MATCHES.  P(regulation 3-way) is the
independent-Poisson mass of gh>ga / gh==ga / gh<ga.

Honesty rules: no selectivity threshold (the desk states a view for every
match, like the baselines it is compared against); prediction-only (no
permissioned DEL odds path - accuracy/Brier, never PnL); graded on
``regulation_3way`` outcomes, not on the OT/SO-aware final.
"""
from __future__ import annotations

import math
from datetime import timedelta
from typing import Any, Dict

from .base import Strategy, no_bet

PRIOR_MATCHES = 6
# Generic top-flight ice-hockey prior (~6.0 goals/match, mild home edge),
# stated before grading.  The walk-forward replaces it with released-data
# rates once the pool has >= MIN_LEAGUE_MATCHES released matches.
LEAGUE_PRIOR_HOME = 3.1
LEAGUE_PRIOR_AWAY = 2.9
MIN_LEAGUE_MATCHES = 10
# Truncation of the double sum; the lost Poisson mass at these rates is
# < 1e-6 and is renormalised (recorded, never guessed).
MAX_GOALS = 25

DECISION_LAG = timedelta(minutes=30)

SPORT = "ice_hockey"


def poisson_pmf(k: int, lam: float) -> float:
    if lam <= 0:
        return 1.0 if k == 0 else 0.0
    return math.exp(-lam) * lam ** k / math.factorial(k)


def reg_three_way(lambda_home: float, lambda_away: float
                  ) -> Dict[str, float]:
    """Regulation-time 3-way probabilities from independent Poisson goals."""
    p_home = p_draw = p_away = 0.0
    for gh in range(MAX_GOALS + 1):
        mass_h = poisson_pmf(gh, lambda_home)
        for ga in range(MAX_GOALS + 1):
            p = mass_h * poisson_pmf(ga, lambda_away)
            if gh > ga:
                p_home += p
            elif gh == ga:
                p_draw += p
            else:
                p_away += p
    total = p_home + p_draw + p_away
    return {"home": p_home / total, "draw": p_draw / total,
            "away": p_away / total}


def reg_expected_goals(tbs, home: str, away: str, at) -> Dict[str, Any]:
    """Time-bounded Poisson rates for one hockey fixture (read-audited).

    Same shrinkage construction as the football totals desk
    (``totals.expected_goals``), hockey priors.
    """
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
    return {
        "lambda_home": round(lam_h, 4), "lambda_away": round(lam_a, 4),
        "league_rates": {"home": round(league_home, 4),
                         "away": round(league_away, 4),
                         "source": league_source},
        "team_multipliers": {
            "home": {k: (round(v, 4) if isinstance(v, float) else v)
                     for k, v in h.items()},
            "away": {k: (round(v, 4) if isinstance(v, float) else v)
                     for k, v in a.items()}},
        "model_prob": reg_three_way(lam_h, lam_a),
        "market": "regulation-time 3-way (60 minutes)",
    }


class HockeyRegPoisson(Strategy):
    """Poisson goal model, regulation-time 3-way (no-market, prediction-only)."""

    def __init__(self):
        super().__init__(
            name="Poisson regulation 3-way (hockey)",
            description=(f"Independent-Poisson goal model (league rates + "
                         f"shrunk attack/defence multipliers from released "
                         f"matches only, prior weight {PRIOR_MATCHES}); "
                         f"states the regulation-time 3-way view for every "
                         f"match (no selectivity - comparable to the "
                         f"always-home baseline). Generic prior "
                         f"{LEAGUE_PRIOR_HOME}/{LEAGUE_PRIOR_AWAY} until "
                         f">= {MIN_LEAGUE_MATCHES} released matches, then "
                         f"released-data rates. Pre-registered, not fitted. "
                         "Prediction-only: no permissioned DEL odds path - "
                         "graded on regulation-time accuracy/Brier, never "
                         "PnL."),
            odds_provider=None, sport=SPORT,
            market_outcome="regulation_3way")

    def predict(self, event, tbs, start, market_odds=None,
                odds_observed_at=None, as_of=None) -> Dict[str, Any]:
        at = as_of if as_of is not None else start - DECISION_LAG
        if at >= start:
            return no_bet(start - DECISION_LAG,
                          {"reason": "decision time not before start"})
        xg = reg_expected_goals(tbs, event["home_team"], event["away_team"], at)
        probs = xg["model_prob"]
        pick = max(probs, key=probs.get)
        return {"cutoff_utc": at, "selection_key": pick,
                "selection_text": (event["home_team"] if pick == "home"
                                   else event["away_team"]
                                   if pick == "away" else "regulation draw"),
                "model": {**xg, "rule": "argmax regulation 3-way",
                          "odds": "none (no permissioned odds path)"}}

    def ratings_after(self, event, home_goals, away_goals, tbs, final_at):
        # No rating state of its own: the Poisson desk reads released
        # results directly.  (Keeping ratings in the store is the Elo
        # desks' job; this must not double-update their pool.)
        return {}


class HockeyRegHomeBaseline(Strategy):
    """Always-home baseline for the regulation 3-way (naive reference).

    The regulation analogue of hockey-home-v1: flat 0.5/0/0.5 prior
    (uninformative by design), picks HOME for every match.  If the Poisson
    desk does not beat the share of regulation home wins on the same
    pool, its 3-way numbers are not evidence of information.
    """

    def __init__(self):
        super().__init__(
            name="Regulation home naive baseline (hockey)",
            description=("Always predicts HOME in regulation time. Flat "
                         "0.5/0/0.5 prior (uninformative by design: Brier "
                         "against the 3-way actual is uninformative; the "
                         "hit rate is the reference point). Baseline for "
                         "the regulation 3-way desks - prediction-only, "
                         "never PnL."),
            odds_provider=None, sport=SPORT,
            market_outcome="regulation_3way")

    def predict(self, event, tbs, start, market_odds=None,
                odds_observed_at=None, as_of=None) -> Dict[str, Any]:
        at = as_of if as_of is not None else start - DECISION_LAG
        if at >= start:
            return {"cutoff_utc": start - DECISION_LAG,
                    "selection_key": "none", "selection_text": "no bet",
                    "model": {"reason": "decision time not before start"}}
        return {"cutoff_utc": at, "selection_key": "home",
                "selection_text": event["home_team"],
                "model": {
                    "model_prob": {"home": 0.5, "draw": 0.0, "away": 0.5},
                    "prior": "flat 0.5/0/0.5 (uninformative by design)",
                    "rule": "always the home side in regulation time",
                    "odds": "none (no permissioned odds path)",
                }}

    def ratings_after(self, event, home_goals, away_goals, tbs, final_at):
        return {}
