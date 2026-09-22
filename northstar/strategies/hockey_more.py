"""Second-generation ice-hockey desks (prediction-only, no market).

Three new pre-registered hypotheses on the SAME verified ODbL result path
(OpenLigaDB DEL 2024/25, single source, identity ``probable``):

1. ``hockey-elo-mov-v1`` - margin-of-victory Elo.  Research question: does
   the *size* of a win carry information the plain W/L Elo update throws
   away?  Prior: rating systems that scale the update by the margin are a
   standard Elo refinement; the World-Football-Elo convention is quoted
   verbatim below.  Rule (pre-registered before grading, not fitted): the
   same expected-score function and home advantage as ``hockey-elo-v1``,
   but the K factor scales with the goal margin, ``K * g`` with ``g = 1``
   for a 1-goal game, ``1.5`` for 2 goals and ``(11 + margin) / 8`` beyond
   that.

2. ``hockey-totals-poisson-v1`` + ``hockey-totals-over-v1`` - the second
   market for this sport: TOTAL GOALS over/under 5.5 on the final score.
   Research question: does the independent-Poisson goal model that already
   runs on football totals (Maher 1982 -> Dixon & Coles 1997 lineage)
   transfer to DEL total goals?  Prior: the same lineage, explicitly a
   cross-sport transfer test, so nothing hockey-specific is claimed.  Rule
   (pre-registered, not fitted): league home/away goal rates from matches
   released at the cutoff (generic prior 3.1/2.9 until >= 10 released
   matches), team multipliers shrunk with a 6-match prior weight, then
   P(total >= 6) vs P(total <= 5) on the independent-Poisson double sum.
   The desk states the more likely side for EVERY match (no selectivity),
   which is exactly what makes it comparable to the always-over baseline
   ``hockey-totals-over-v1``.

Honesty rules (identical to every other prediction-only desk here):

* prediction-only: DEL has **no permissioned odds path** in this
  repository, so there is no entry price, no stake and NO PnL.  These
  desks are graded on accuracy/Brier by :mod:`northstar.evaluation` and are
  excluded from the PnL family and the Holm correction;
* every prior above is a research prior stated before grading, never
  fitted on the graded sample;
* the pool is the same single-source DEL result set, so the identity is
  ``probable``, never ``verified``;
* baselines exist so no accuracy number is quoted alone:
  ``hockey-home-v1`` for the MoV Elo desk (2-way final) and
  ``hockey-totals-over-v1`` for the totals desk (always over).
"""
from __future__ import annotations

from datetime import timedelta
from typing import Any, Dict

from ..models import SPORT_ICE_HOCKEY
from .base import Strategy, no_bet
from .hockey import HOME_ADV, INITIAL, K as PLAIN_K, _expected_home
from .hockey_reg import (LEAGUE_PRIOR_AWAY, LEAGUE_PRIOR_HOME, MAX_GOALS,
                         MIN_LEAGUE_MATCHES, PRIOR_MATCHES, poisson_pmf)

DECISION_LAG = timedelta(minutes=30)
SPORT = SPORT_ICE_HOCKEY
TOTALS_LINE = 5.5
MOV_MIN_PROB = 0.55


def mov_multiplier(margin: int) -> float:
    """Pre-registered margin weight (World-Football-Elo convention).

    "It is increased by half if a game is won by two goals, by 3/4 if a
    game is won by three goals, and by 3/4 + (N-3)/8 if the game is won by
    four or more goals, where N is the goal difference."
    (World Football Elo Ratings, https://www.eloratings.net/about, fetched
    2026-09-22; the multiplier is expressed relative to the base update, so
    the quoted fractions are added to 1.)
    """
    if margin <= 1:
        return 1.0
    if margin == 2:
        return 1.5
    return (11.0 + margin) / 8.0


def totals_probabilities(lambda_home: float, lambda_away: float
                         ) -> Dict[str, float]:
    """P(total > 5.5) / P(total < 5.5) from independent Poisson goals."""
    p_over = 0.0
    for gh in range(MAX_GOALS + 1):
        mass_h = poisson_pmf(gh, lambda_home)
        for ga in range(MAX_GOALS + 1):
            if gh + ga > TOTALS_LINE:
                p_over += mass_h * poisson_pmf(ga, lambda_away)
    return {"over": p_over, "under": 1.0 - p_over}


def total_goals_rates(tbs, home: str, away: str, at) -> Dict[str, Any]:
    """Time-bounded Poisson total-goals rates (read-audited, not fitted).

    Same construction as :func:`northstar.strategies.hockey_reg
    .reg_expected_goals`, with hockey priors; only matches released at
    ``at`` are read (the store raises on any later read).
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
        "lambda_home": round(lam_h, 4),
        "lambda_away": round(lam_a, 4),
        "expected_total": round(lam_h + lam_a, 4),
        "line": TOTALS_LINE,
        "league_rates": {"home": round(league_home, 4),
                         "away": round(league_away, 4),
                         "source": league_source},
        "team_multipliers": {
            "home": {k: (round(v, 4) if isinstance(v, float) else v)
                     for k, v in h.items()},
            "away": {k: (round(v, 4) if isinstance(v, float) else v)
                     for k, v in a.items()}},
        "model_prob": totals_probabilities(lam_h, lam_a),
        "market": f"total goals over/under {TOTALS_LINE} (final score)",
    }


class HockeyEloMov(Strategy):
    """Margin-of-victory Elo, 2-way final (no-market, prediction-only)."""

    def __init__(self, min_prob: float = MOV_MIN_PROB):
        super().__init__(
            name="Hockey Elo margin-of-victory (no-market pilot)",
            description=(f"2-way Elo on the OT/SO-aware final with the "
                         f"update scaled by the goal margin "
                         f"(K={PLAIN_K:.0f} x g, home adv {HOME_ADV:.0f} Elo "
                         f"pts; research priors, not fitted); backs the "
                         f"model favourite when win prob >= {min_prob:.0%}. "
                         "Control for hockey-elo-v1 - prediction-only "
                         "(no permissioned odds path), graded on "
                         "accuracy/Brier, never PnL."),
            odds_provider=None, sport=SPORT)
        self.min_prob = min_prob

    def predict(self, event, tbs, start, market_odds=None,
                odds_observed_at=None, as_of=None) -> Dict[str, Any]:
        at = as_of if as_of is not None else start - DECISION_LAG
        if at >= start:
            return no_bet(start - DECISION_LAG,
                          {"reason": "decision time not before start"})
        rh = tbs.team_rating(event["home_team"], at) or INITIAL
        ra = tbs.team_rating(event["away_team"], at) or INITIAL
        e_home = _expected_home(rh, ra)
        model = {
            "model_prob": {"home": e_home, "draw": 0.0,
                           "away": 1.0 - e_home},
            "ratings": {"home": round(rh, 1), "away": round(ra, 1)},
            "decision_lag": "start-30min",
            "mov_rule": "K x g, g = 1 / 1.5 / (11 + margin) / 8",
            "odds": "none (no permissioned odds path)",
        }
        if max(e_home, 1.0 - e_home) < self.min_prob:
            return no_bet(at, {**model,
                               "reason": "below selectivity threshold"})
        pick = "home" if e_home >= 0.5 else "away"
        return {"cutoff_utc": at, "selection_key": pick,
                "selection_text": (event["home_team"] if pick == "home"
                                   else event["away_team"]),
                "model": model}

    def ratings_after(self, event, home_goals, away_goals, tbs,
                      final_at) -> Dict[str, float]:
        rh = tbs.team_rating(event["home_team"], final_at) or INITIAL
        ra = tbs.team_rating(event["away_team"], final_at) or INITIAL
        e_home = _expected_home(rh, ra)
        if home_goals > away_goals:
            s_home = 1.0
        elif home_goals < away_goals:
            s_home = 0.0
        else:
            # Unreachable for a decisive hockey final; a drawn row is a
            # source irregularity that the ingest flags for review.  Never
            # guess a winner: treat as 0.5 exactly as the plain desk does.
            s_home = 0.5
        g = mov_multiplier(abs(int(home_goals) - int(away_goals)))
        delta = PLAIN_K * g * (s_home - e_home)
        return {event["home_team"]: rh + delta,
                event["away_team"]: ra - delta}


class HockeyTotalsPoisson(Strategy):
    """Poisson total-goals desk, over/under 5.5 (prediction-only)."""

    def __init__(self):
        super().__init__(
            name="Poisson total goals O/U 5.5 (hockey)",
            description=(f"Independent-Poisson goal model "
                         f"(Maher/Dixon-Coles lineage) on the DEL final "
                         f"score: league rates + shrunk attack/defence "
                         f"multipliers from released matches only (prior "
                         f"weight {PRIOR_MATCHES}); generic prior "
                         f"{LEAGUE_PRIOR_HOME}/{LEAGUE_PRIOR_AWAY} until "
                         f">= {MIN_LEAGUE_MATCHES} released matches. "
                         f"States the more likely side of the "
                         f"{TOTALS_LINE} line for EVERY match (no "
                         f"selectivity - comparable to its always-over "
                         f"baseline). Pre-registered, not fitted. "
                         "Prediction-only: no permissioned DEL odds path "
                         "- accuracy/Brier, never PnL."),
            odds_provider=None, sport=SPORT,
            market_outcome="total_goals_over_under_5_5")

    def predict(self, event, tbs, start, market_odds=None,
                odds_observed_at=None, as_of=None) -> Dict[str, Any]:
        at = as_of if as_of is not None else start - DECISION_LAG
        if at >= start:
            return no_bet(start - DECISION_LAG,
                          {"reason": "decision time not before start"})
        xg = total_goals_rates(tbs, event["home_team"],
                               event["away_team"], at)
        probs = xg["model_prob"]
        pick = "over" if probs["over"] >= probs["under"] else "under"
        return {"cutoff_utc": at, "selection_key": pick,
                "selection_text": f"{pick} {TOTALS_LINE} total goals",
                "model": {**xg,
                          "rule": f"argmax P(total > {TOTALS_LINE})",
                          "odds": "none (no permissioned odds path)"}}

    def ratings_after(self, event, home_goals, away_goals, tbs, final_at):
        # Reads released results directly; no rating state of its own.
        return {}


class HockeyTotalsOverBaseline(Strategy):
    """Always-over baseline for the DEL totals market (naive reference).

    Flat 0.5/0.5 prior (uninformative by design, so its Brier is 0.5 by
    construction); the hit rate is the reference point.  A totals desk that
    does not beat the share of over-5.5 games in the same pool has shown no
    information.
    """

    def __init__(self):
        super().__init__(
            name="Always-over naive baseline (hockey totals)",
            description=(f"Always predicts OVER {TOTALS_LINE} total goals. "
                         "Flat 0.5/0.5 prior (uninformative by design: "
                         "Brier stays 0.5; the hit rate is the reference "
                         "point). Baseline for the DEL totals desk - "
                         "prediction-only, never PnL."),
            odds_provider=None, sport=SPORT,
            market_outcome="total_goals_over_under_5_5")

    def predict(self, event, tbs, start, market_odds=None,
                odds_observed_at=None, as_of=None) -> Dict[str, Any]:
        at = as_of if as_of is not None else start - DECISION_LAG
        if at >= start:
            return no_bet(start - DECISION_LAG,
                          {"reason": "decision time not before start"})
        return {"cutoff_utc": at, "selection_key": "over",
                "selection_text": f"over {TOTALS_LINE} total goals",
                "model": {
                    "model_prob": {"over": 0.5, "under": 0.5},
                    "prior": "flat 0.5/0.5 (uninformative by design)",
                    "rule": f"always over {TOTALS_LINE}",
                    "line": TOTALS_LINE,
                    "odds": "none (no permissioned odds path)",
                }}
