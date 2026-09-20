"""Draw-No-Bet style strategy (football, 3-way settlement).

A "decisive match" probe: the Elo model is used only to flag games where a
draw looks unlikely (p_draw < 0.30) and one team clearly leads the 2-way
max(p_home, p_away) >= 0.55. The stronger side is backed in the 3-way
market; if the game is a draw the bet loses (standard DNB behaviour).
No model confidence -> no bet.
"""
from __future__ import annotations

from typing import Any, Dict

from .base import Strategy, no_bet
from .elo import _draw_rate, _expected_home, INITIAL


class DrawNoBet(Strategy):
    def __init__(self, draw_max: float = 0.30, two_way_min: float = 0.55,
                 odds_provider: str = "market_avg"):
        super().__init__(
            name="Draw-No-Bet decisive",
            description=(f"Elo-based: back the 2-way leader when "
                         f"p_draw < {draw_max:.2f} and max(p_home,p_away) "
                         f">= {two_way_min:.2f}; a draw loses (DNB rule)."),
            odds_provider=odds_provider)
        self.draw_max = draw_max
        self.two_way_min = two_way_min

    def predict(self, event, tbs, start, market_odds=None,
                odds_observed_at=None, as_of=None) -> Dict[str, Any]:
        if odds_observed_at is None or not market_odds:
            return no_bet(odds_observed_at,
                          {"reason": "no pre-start market price"})
        rh = tbs.team_rating(event["home_team"], odds_observed_at) or INITIAL
        ra = tbs.team_rating(event["away_team"], odds_observed_at) or INITIAL
        e_home = _expected_home(rh, ra)
        p_home, p_away = e_home, 1.0 - e_home
        p_draw = _draw_rate(rh + 60.0, ra)
        if p_draw < self.draw_max and max(p_home, p_away) >= self.two_way_min:
            choice = "home" if p_home >= p_away else "away"
            return {"cutoff_utc": odds_observed_at,
                    "selection_key": choice,
                    "selection_text": f"DNB {choice}",
                    "model": {"p_home": round(p_home, 4),
                              "p_draw": round(p_draw, 4),
                              "p_away": round(p_away, 4),
                              "ratings": {"home": round(rh, 1),
                                          "away": round(ra, 1)},
                              "rule": "decisive-match DNB"}}
        return no_bet(odds_observed_at,
                      {"reason": "not a decisive match",
                       "p_home": round(p_home, 4),
                       "p_draw": round(p_draw, 4),
                       "p_away": round(p_away, 4)})

    def ratings_after(self, event, home_goals, away_goals, tbs, final_at):
        from .elo import EloEdge
        return EloEdge().ratings_after(event, home_goals, away_goals, tbs,
                                       final_at)
