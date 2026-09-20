"""Value-probe strategies on the football 1X2 market (backtestable).

Each strategy states a *falsifiable pricing hypothesis* from the academic
literature and turns it into one auditable rule.  References (verified
links) live in docs/STRATEGIES.md; the parameters below are research priors
stated up front - none is fitted on the pilot sample (fitting on 27 matches
would be in-sample selection, the exact bias docs/STATUS.md warns about).

- DrawValue: the draw is a systematically *longshot-ish* outcome in 1X2
  prices (retail bettors under-buy draws; the favourite-longshot bias
  literature predicts longshot prices pay less than fair).  Probe: back the
  draw when our model's draw probability exceeds the margin-removed market
  draw probability by a fixed edge threshold.
- HomeEdge: home advantage is the most over-discussed edge in football
  tipping.  Probe: back the home side only when the model's home edge over
  the fair market price clears a deliberately high threshold.
- FormValue: "back the team in better recent form, but only at a price" -
  the classic tipster rule.  Probe: form points per match over the last
  (<=) 3 released matches, a minimum form gap, and a minimum price floor so
  the bet is not a hopeless longshot.
"""
from __future__ import annotations

from typing import Any, Dict

from .base import Strategy, market_implied, no_bet
from .elo import INITIAL, elo_three_way, elo_update

DRAW_EDGE_THRESHOLD = 0.03
HOME_EDGE_THRESHOLD = 0.05
FORM_MATCHES = 3
FORM_GAP_POINTS_PER_MATCH = 1.0
FORM_PRICE_FLOOR = 1.80


class DrawValue(Strategy):
    """Back the draw when model p_draw - fair p_draw >= threshold."""

    def __init__(self, edge_threshold: float = DRAW_EDGE_THRESHOLD,
                 odds_provider: str = "market_avg"):
        super().__init__(
            name="Draw value probe",
            description=(f"Draw mispricing probe: back DRAW when the Elo "
                         f"3-way model's draw probability exceeds the "
                         f"margin-removed market draw probability by >= "
                         f"{edge_threshold:.0%}. Research prior, not fitted."),
            odds_provider=odds_provider)
        self.edge_threshold = edge_threshold

    def predict(self, event, tbs, start, market_odds=None,
                odds_observed_at=None, as_of=None) -> Dict[str, Any]:
        if odds_observed_at is None or not market_odds:
            return no_bet(odds_observed_at,
                          {"reason": "no pre-start market price"})
        rh = tbs.team_rating(event["home_team"], odds_observed_at) or INITIAL
        ra = tbs.team_rating(event["away_team"], odds_observed_at) or INITIAL
        model = elo_three_way(rh, ra)
        fair = market_implied(market_odds)
        if fair is None:
            return no_bet(odds_observed_at,
                          {"reason": "incomplete market prices"})
        edge = {k: model[k] - fair[k] for k in model}
        trail = {"ratings": {"home": round(rh, 1), "away": round(ra, 1)},
                 "model_prob": model, "fair_prob": fair, "edge": edge}
        if edge["draw"] >= self.edge_threshold:
            return {"cutoff_utc": odds_observed_at,
                    "selection_key": "draw",
                    "selection_text": "draw",
                    "model": {**trail,
                              "rule": "model draw edge >= threshold"}}
        return no_bet(odds_observed_at,
                      {**trail, "reason": "draw edge below threshold"})

    def ratings_after(self, event, home_goals, away_goals, tbs,
                      final_at) -> Dict[str, float]:
        return elo_update(event, home_goals, away_goals, tbs, final_at)


class HomeEdge(Strategy):
    """Back home when model p_home - fair p_home >= a high threshold."""

    def __init__(self, edge_threshold: float = HOME_EDGE_THRESHOLD,
                 odds_provider: str = "market_avg"):
        super().__init__(
            name="Home-advantage value probe",
            description=(f"Home bias probe: back HOME only when the Elo "
                         f"model's home probability exceeds the "
                         f"margin-removed market price by >= "
                         f"{edge_threshold:.0%} (deliberately selective). "
                         "Research prior, not fitted."),
            odds_provider=odds_provider)
        self.edge_threshold = edge_threshold

    def predict(self, event, tbs, start, market_odds=None,
                odds_observed_at=None, as_of=None) -> Dict[str, Any]:
        if odds_observed_at is None or not market_odds:
            return no_bet(odds_observed_at,
                          {"reason": "no pre-start market price"})
        rh = tbs.team_rating(event["home_team"], odds_observed_at) or INITIAL
        ra = tbs.team_rating(event["away_team"], odds_observed_at) or INITIAL
        model = elo_three_way(rh, ra)
        fair = market_implied(market_odds)
        if fair is None:
            return no_bet(odds_observed_at,
                          {"reason": "incomplete market prices"})
        edge = {k: model[k] - fair[k] for k in model}
        trail = {"ratings": {"home": round(rh, 1), "away": round(ra, 1)},
                 "model_prob": model, "fair_prob": fair, "edge": edge}
        if edge["home"] >= self.edge_threshold:
            return {"cutoff_utc": odds_observed_at,
                    "selection_key": "home",
                    "selection_text": "home",
                    "model": {**trail,
                              "rule": "model home edge >= threshold"}}
        return no_bet(odds_observed_at,
                      {**trail, "reason": "home edge below threshold"})

    def ratings_after(self, event, home_goals, away_goals, tbs,
                      final_at) -> Dict[str, float]:
        return elo_update(event, home_goals, away_goals, tbs, final_at)


class FormValue(Strategy):
    """Recent-form gap + price floor (classic tipster rule, made auditable).

    Form = mean points per match (W3/D1/L0) over the last ``n`` released
    matches at the cutoff.  Back the higher-form side when the per-match
    form gap is >= ``form_gap`` AND its stored price is >= ``price_floor``
    (never back a hopeless longshot on form alone).  Teams with fewer than
    2 released matches: no bet (insufficient evidence, stated in the model
    trail).
    """

    def __init__(self, n: int = FORM_MATCHES,
                 form_gap: float = FORM_GAP_POINTS_PER_MATCH,
                 price_floor: float = FORM_PRICE_FLOOR,
                 odds_provider: str = "market_avg"):
        super().__init__(
            name="Form + price value",
            description=(f"Back the better recent-form side (mean points per "
                         f"match over last {n} released matches) when the "
                         f"gap >= {form_gap:.1f} pts/match and the stored "
                         f"price >= {price_floor:.2f}. Tipster-style rule, "
                         "fully auditable, no fitted parameters."),
            odds_provider=odds_provider)
        self.n = n
        self.form_gap = form_gap
        self.price_floor = price_floor

    def predict(self, event, tbs, start, market_odds=None,
                odds_observed_at=None, as_of=None) -> Dict[str, Any]:
        if odds_observed_at is None or not market_odds:
            return no_bet(odds_observed_at,
                          {"reason": "no pre-start market price"})
        fh = tbs.recent_form(event["home_team"], odds_observed_at, self.n)
        fa = tbs.recent_form(event["away_team"], odds_observed_at, self.n)
        if len(fh) < 2 or len(fa) < 2:
            return no_bet(odds_observed_at,
                          {"reason": "insufficient released form history",
                           "home_matches": len(fh), "away_matches": len(fa)})
        pph_h = sum(r["points"] for r in fh) / len(fh)
        pph_a = sum(r["points"] for r in fa) / len(fa)
        trail = {"form_points_per_match": {"home": round(pph_h, 4),
                                           "away": round(pph_a, 4)},
                 "form_matches_used": {"home": len(fh), "away": len(fa)},
                 "fair_prob": market_implied(market_odds)}
        if abs(pph_h - pph_a) < self.form_gap:
            return no_bet(odds_observed_at,
                          {**trail, "reason": "form gap below threshold"})
        side = "home" if pph_h > pph_a else "away"
        price = market_odds.get(side)
        if price is None or price < self.price_floor:
            return no_bet(odds_observed_at,
                          {**trail, "reason": f"{side} price below floor "
                                              f"({price})",
                           "form_side": side})
        return {"cutoff_utc": odds_observed_at,
                "selection_key": side,
                "selection_text": f"form {side}",
                "model": {**trail, "form_side": side, "price": price,
                          "rule": "form gap + price floor"}}

    def ratings_after(self, event, home_goals, away_goals, tbs,
                      final_at) -> Dict[str, float]:
        # Carries the shared Elo ratings so draw/home-edge style desks keep
        # a consistent released-rating timeline for cross-checks.
        return elo_update(event, home_goals, away_goals, tbs, final_at)
