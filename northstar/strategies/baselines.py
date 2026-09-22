"""Naive baselines for the prediction-only sports (hockey, darts).

Why these exist: the Elo desks report accuracy/Brier with no market to
compare against (no permissioned odds path). A naive baseline gives that
comparison point for free from the same stored results: if the model does
not beat "always home" / "always the listed-first player", its hit rate is
not evidence of information.

Honesty rules (mirrored from the Elo desks):
- the probabilities are a flat 0.5/0.5 prior — deliberately uninformative,
  stated before grading, not fitted on anything. The baseline's Brier is
  therefore 0.5 by construction and *uninformative*; the hit rate is the
  only meaningful number;
- no selectivity threshold: a naive baseline bets every eligible match
  (that is what makes it the reference);
- prediction-only: no odds path exists for DEL or PDC in this repository,
  so these desks never touch PnL and never enter the Holm PnL family.
"""
from __future__ import annotations

from datetime import timedelta
from typing import Any, Dict

from ..models import SPORT_DARTS, SPORT_ICE_HOCKEY
from .base import Strategy

DECISION_LAG = timedelta(minutes=30)


class HockeyHomeBaseline(Strategy):
    """Always predict the home side (home-ice naive baseline)."""

    def __init__(self):
        super().__init__(
            name="Home-ice naive baseline (hockey)",
            description=("Always predicts HOME. Flat 0.5/0.5 prior "
                         "(uninformative by design: Brier stays 0.5; the "
                         "hit rate is the reference point). Baseline for "
                         "the hockey accuracy desks — prediction-only, "
                         "never PnL."),
            odds_provider=None, sport=SPORT_ICE_HOCKEY)

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
                    "prior": "flat 0.5/0.5 (uninformative by design)",
                    "rule": "always the home side",
                }}


class DartsListedFirstBaseline(Strategy):
    """Always predict the listed-first player (presentation-order probe).

    The PDC schema audit (docs/DARTS-AUDIT.md) found the listed-first
    player is a presentation order with no home-advantage meaning; this
    baseline measures whether any residual order signal exists in the
    stored results — a sanity check on the pool, not a betting idea."""

    def __init__(self):
        super().__init__(
            name="Listed-first naive baseline (darts)",
            description=("Always predicts the listed-first player. Flat "
                         "0.5/0.5 prior (uninformative by design: Brier "
                         "stays 0.5; the hit rate is the reference point). "
                         "The PDC audit found listing order carries no "
                         "home-advantage meaning — a hit rate far from 50% "
                         "would itself be a data finding. Prediction-only, "
                         "never PnL."),
            odds_provider=None, sport=SPORT_DARTS)

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
                    "prior": "flat 0.5/0.5 (uninformative by design)",
                    "rule": "always the listed-first player",
                }}
