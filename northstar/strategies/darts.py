"""Darts Elo strategy (prediction-only; no permissioned odds path).

Sport rules (from the PDC schema audit, docs/DARTS-AUDIT.md):
- OpenLigaDB darts rows are player-vs-player; ``pointsTeam1/2`` are a
  decisive leg/set count - legs in the committed 2025 ProTour/EuroTour
  events and the 2026 World Series Finals (audit-verified), **sets** in
  World Championship events (e.g. PDCWM 2026: 7-1, 6-3 scorelines). The
  model only compares the counts, so both encodings are valid inputs;
  never a draw at full time;
- there is no home/away advantage concept comparable to team sports: the
  listed-first player is a presentation order, so HOME_ADV = 0 (research
  prior, documented - not fitted);
- walkovers/retirements would surface as finished rows with lopsided or
  missing set counts; the parser keeps whatever the source recorded and the
  audit flags irregularities instead of guessing.

Player identity: rating lookups/updates key on the *canonical* player
name from the curated, evidence-linked table ``data/aliases/darts.json``
(northstar.aliases).  Only three verified splits are merged (abbreviated
BSDO spellings + the Mansell nickname split); unknown names stay raw.  The
applied aliases are written into the model trail so a reviewer sees them.

Calibration honesty: K=24 and MIN_PROB are *research priors* for an
individual-sport Elo, stated before any grading, not fitted on the pilot.
There is no permissioned historical darts odds path in this repository, so
this strategy produces predictions only (``allow_no_odds`` walk-forward):
graded on accuracy/Brier by northstar.evaluation, never on PnL.
"""
from __future__ import annotations

from datetime import timedelta
from typing import Any, Dict

from ..aliases import applied_aliases, alias_version, canonical_name
from ..models import SPORT_DARTS, fmt_utc
from .base import Strategy, no_bet

INITIAL = 1500.0
K = 24.0
HOME_ADV = 0.0          # listed-first player is presentation order only
MIN_PROB = 0.60
DECISION_LAG = timedelta(minutes=30)


def _expected_first(r_first: float, r_second: float) -> float:
    return 1.0 / (1.0 + 10.0 ** ((r_second - (r_first + HOME_ADV)) / 400.0))


class DartsElo(Strategy):
    def __init__(self, min_prob: float = MIN_PROB):
        super().__init__(
            name="Darts Elo favourite (no-market pilot)",
            description=(f"2-way player Elo (K={K:.0f}, no venue adjustment; "
                         f"research priors) on sets won; selects the model "
                         f"favourite when win prob >= {min_prob:.0%}. "
                         "Prediction-only: no permissioned darts odds path "
                         "exists in this build, so graded on accuracy, "
                         "never on PnL."),
            odds_provider=None,
            sport=SPORT_DARTS)
        self.min_prob = min_prob

    def predict(self, event, tbs, start, market_odds=None,
                odds_observed_at=None, as_of=None) -> Dict[str, Any]:
        # Forward mode reads at the capture instant; backtest mode uses a
        # fixed pre-start lag (see hockey.HockeyElo for the rationale).
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
            "model_prob": {"home": e_home, "draw": 0.0, "away": 1.0 - e_home},
            "ratings": {"home": round(rh, 1), "away": round(ra, 1)},
            "decision_time": fmt_utc(at),
            "odds": "none (no permissioned odds path)",
            "identity": {
                "alias_table": alias_version(SPORT_DARTS),
                "applied": applied_aliases(
                    SPORT_DARTS, [event["home_team"], event["away_team"]])},
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
            # A drawn darts row would be a source irregularity (matches are
            # played to a winner); treat as 0.5 rather than guess, and the
            # ingest flags it for review.
            s_home = 0.5
        delta = K * (s_home - e_home)
        return {home: rh + delta, away: ra - delta}
