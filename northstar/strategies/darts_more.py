"""Second-generation darts desk (prediction-only, no permissioned odds).

``darts-mov-elo-v1`` - margin-of-victory Elo.  Research question: the same
one Q2 asks for hockey - does the *size* of a win carry information the
plain W/L Elo update throws away?  Prior: margin-scaled Elo updates are a
standard refinement; the weight used here is the World-Football-Elo
convention quoted verbatim in :mod:`northstar.strategies.hockey_more`
(``g = 1 / 1.5 / (11 + margin)/8``), applied with the darts Elo constants
(K=24, no venue adjustment).

Stated weakness (never hidden): the stored darts margin unit differs by
event format - legs in ProTour/EuroTour events, sets in World Championship
events - and the source does not label which unit a row carries.  The desk
therefore uses the raw stored count difference as the margin, and records
that fact in every prediction's model trail.  A future capture that labels
the unit can split the desks; until then this is the honest version.

Honesty rules: prediction-only (no odds path), graded on accuracy/Brier by
:mod:`northstar.evaluation`, excluded from the PnL family and the Holm
correction; player identity goes through the curated alias table exactly as
``darts-elo-v1`` does; the comparison desk is ``darts-elo-v1`` itself and
the naive reference is ``darts-listed-first-v1``.
"""
from __future__ import annotations

from datetime import timedelta
from typing import Any, Dict

from ..aliases import applied_aliases, alias_version, canonical_name
from ..models import SPORT_DARTS, fmt_utc
from .base import Strategy, no_bet
from .darts import HOME_ADV, INITIAL, K, MIN_PROB, _expected_first

DECISION_LAG = timedelta(minutes=30)


def mov_multiplier(margin: int) -> float:
    """Pre-registered margin weight (identical constants to the hockey desk)."""
    if margin <= 1:
        return 1.0
    if margin == 2:
        return 1.5
    return (11.0 + margin) / 8.0


class DartsEloMov(Strategy):
    """Margin-of-victory Elo on the stored leg/set counts (no-market)."""

    def __init__(self, min_prob: float = MIN_PROB):
        super().__init__(
            name="Darts Elo margin-of-victory (no-market pilot)",
            description=(f"Player Elo with the update scaled by the stored "
                         f"leg/set margin (K={K:.0f} x g, no venue "
                         f"adjustment; research priors, not fitted); "
                         f"selects the model favourite when win prob "
                         f">= {min_prob:.0%}. Control for darts-elo-v1 - "
                         "prediction-only (no permissioned odds path), "
                         "graded on accuracy/Brier, never PnL."),
            odds_provider=None, sport=SPORT_DARTS)
        self.min_prob = min_prob

    def predict(self, event, tbs, start, market_odds=None,
                odds_observed_at=None, as_of=None) -> Dict[str, Any]:
        at = as_of if as_of is not None else start - DECISION_LAG
        if at >= start:
            return no_bet(start - DECISION_LAG,
                          {"reason": "decision time not before start"})
        home = canonical_name(SPORT_DARTS, event["home_team"])
        away = canonical_name(SPORT_DARTS, event["away_team"])
        rh = tbs.team_rating(home, at) or INITIAL
        ra = tbs.team_rating(away, at) or INITIAL
        e_home = _expected_first(rh, ra)
        model = {
            "model_prob": {"home": e_home, "draw": 0.0,
                           "away": 1.0 - e_home},
            "ratings": {"home": round(rh, 1), "away": round(ra, 1)},
            "decision_time": fmt_utc(at),
            "mov_rule": "K x g, g = 1 / 1.5 / (11 + margin) / 8",
            "mov_margin_unit": ("raw stored count difference: legs in "
                                "ProTour/EuroTour events, sets in World "
                                "Championship events (source does not label "
                                "the unit per row - stated weakness)"),
            "odds": "none (no permissioned odds path)",
            "identity": {
                "alias_table": alias_version(SPORT_DARTS),
                "applied": applied_aliases(
                    SPORT_DARTS, [event["home_team"], event["away_team"]])},
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
        home = canonical_name(SPORT_DARTS, event["home_team"])
        away = canonical_name(SPORT_DARTS, event["away_team"])
        rh = tbs.team_rating(home, final_at) or INITIAL
        ra = tbs.team_rating(away, final_at) or INITIAL
        e_home = _expected_first(rh, ra)
        if home_goals > away_goals:
            s_home = 1.0
        elif home_goals < away_goals:
            s_home = 0.0
        else:
            # A drawn darts row is a source irregularity (the ingest flags
            # it); never guess a winner - 0.5, exactly as the plain desk.
            s_home = 0.5
        g = mov_multiplier(abs(int(home_goals) - int(away_goals)))
        delta = K * g * (s_home - e_home)
        return {home: rh + delta, away: ra - delta}
