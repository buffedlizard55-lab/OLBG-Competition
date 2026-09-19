"""Market-basis strategies (baseline probes).

These do not claim an edge; they define the reference the model strategies
are compared against. The favourite baseline answers "what does the market
itself do?"; the longshot probe tests the favourite-longshot bias on the
pilot sample (does the cheap price over- or under-pay?).
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

from .base import Strategy, market_implied, no_bet


class MarketFavourite(Strategy):
    def __init__(self, odds_provider: str = "market_avg"):
        super().__init__(
            name="Market favourite (baseline)",
            description=("Always backs the margin-removed market favourite "
                         "(highest implied probability). Baseline reference, "
                         "not a claimed edge."),
            odds_provider=odds_provider)

    def predict(self, event, tbs, start, market_odds=None,
                odds_observed_at=None) -> Dict[str, Any]:
        if odds_observed_at is None or not market_odds:
            return no_bet(odds_observed_at,
                          {"reason": "no pre-start market price"})
        fair = market_implied(market_odds)
        if fair is None:
            return no_bet(odds_observed_at,
                          {"reason": "incomplete market prices"})
        best = max(fair, key=fair.get)
        return {"cutoff_utc": odds_observed_at,
                "selection_key": best,
                "selection_text": best,
                "model": {"fair": fair, "rule": "argmax fair probability"}}


class MarketLongshot(Strategy):
    def __init__(self, odds_provider: str = "market_avg"):
        super().__init__(
            name="Market longshot probe (baseline)",
            description=("Always backs the margin-removed least-favoured "
                         "team outcome (min of home/away implied "
                         "probabilities; draw excluded). Tests the "
                         "favourite-longshot bias on the pilot sample."),
            odds_provider=odds_provider)

    def predict(self, event, tbs, start, market_odds=None,
                odds_observed_at=None) -> Dict[str, Any]:
        if odds_observed_at is None or not market_odds:
            return no_bet(odds_observed_at,
                          {"reason": "no pre-start market price"})
        fair = market_implied(market_odds)
        if fair is None:
            return no_bet(odds_observed_at,
                          {"reason": "incomplete market prices"})
        teams = {"home": fair["home"], "away": fair["away"]}
        worst = min(teams, key=teams.get)
        return {"cutoff_utc": odds_observed_at,
                "selection_key": worst,
                "selection_text": worst,
                "model": {"fair": fair, "rule": "argmin team probability"}}
