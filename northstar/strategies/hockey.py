"""Ice hockey Elo strategy (no market odds — prediction-only).

Sport rule explained in the module it feeds: DEL results on OpenLigaDB are
decisive (final score includes overtime/shootout), so this is a 2-way W/L
model; `draw` is emitted with probability 0 and is never selected.

Calibration honesty: K, HOME_ADV and MIN_PROB are *research priors*, not
fitted parameters. HOME_ADV=35 Elo points corresponds to a ~55% home win
share at equal ratings (400*log10(0.55/0.45) ~= 35), a documented league
prior; it is explicitly NOT fitted on this sample (that would be in-sample).
There is no permissioned historical odds path for DEL hockey in this
repository, so this strategy produces predictions only: the walk-forward
engine records them with ``allow_no_odds`` and the desk grades them on
accuracy/Brier (never PnL). Do not convert these to profit units.
"""
from __future__ import annotations

from datetime import timedelta
from typing import Any, Dict

from .base import Strategy, no_bet

INITIAL = 1500.0
K = 32.0
HOME_ADV = 35.0
MIN_PROB = 0.55
DECISION_LAG = timedelta(minutes=30)

SPORT = "ice_hockey"


def _expected_home(r_home: float, r_away: float) -> float:
    return 1.0 / (1.0 + 10.0 ** ((r_away - (r_home + HOME_ADV)) / 400.0))


class HockeyElo(Strategy):
    def __init__(self, min_prob: float = MIN_PROB):
        super().__init__(
            name="Hockey Elo favourite (no-market pilot)",
            description=(f"2-way Elo incl. OT/SO (K={K:.0f}, home adv "
                         f"{HOME_ADV:.0f} Elo pts, research priors); backs "
                         f"the model favourite when win prob >= {min_prob:.0%}. "
                         "Prediction-only: DEL has no permissioned odds path "
                         "in this build, so graded on accuracy, not PnL."),
            odds_provider=None,
            sport=SPORT)
        self.min_prob = min_prob

    def predict(self, event, tbs, start, market_odds=None,
                odds_observed_at=None) -> Dict[str, Any]:
        # Hockey has no market input here: the decision moment is a fixed
        # pre-start lag, and every rating read happens at that moment (the
        # TimeBoundedStore raises if a feature would only exist later).
        at = start - DECISION_LAG
        rh = tbs.team_rating(event["home_team"], at) or INITIAL
        ra = tbs.team_rating(event["away_team"], at) or INITIAL
        e_home = _expected_home(rh, ra)
        model = {
            "model_prob": {"home": e_home, "draw": 0.0, "away": 1.0 - e_home},
            "ratings": {"home": rh, "away": ra},
            "decision_lag": "start-30min",
            "odds": "none (no permissioned odds path)",
        }
        if max(e_home, 1.0 - e_home) < self.min_prob:
            return no_bet(at, {**model, "reason": "below selectivity "
                                                "threshold"})
        pick = "home" if e_home >= 0.5 else "away"
        return {"cutoff_utc": at, "selection_key": pick,
                "selection_text": (event["home_team"] if pick == "home"
                                   else event["away_team"]),
                "model": model}

    def ratings_after(self, event, home_goals, away_goals, tbs,
                      final_at) -> Dict[str, float]:
        # Latest released rating at/behind final_at is the pre-update rating;
        # this game's own update is only stored after we return.
        rh = tbs.team_rating(event["home_team"], final_at) or INITIAL
        ra = tbs.team_rating(event["away_team"], final_at) or INITIAL
        e_home = _expected_home(rh, ra)
        if home_goals > away_goals:
            s_home = 1.0
        elif home_goals < away_goals:
            s_home = 0.0
        else:
            # A regulation-drawn row leaking through parse would otherwise
            # corrupt ratings; treat exactly as 0.5 and flag loudly upstream
            # (RESULT_KIND_INCONSISTENT) rather than guessing a winner.
            s_home = 0.5
        delta = K * (s_home - e_home)
        return {event["home_team"]: rh + delta,
                event["away_team"]: ra - delta}
