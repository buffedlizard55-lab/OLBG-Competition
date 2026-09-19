"""Strategy registry.

Sport-specific strategies live here. Only the sports whose source path has
passed verification (football - Bundesliga pilot) get runnable strategies;
others stay documented-but-blocked so the UI can show an explicit
"not-covered / verification-blocked" state instead of invented numbers.
"""
from .base import (Strategy, market_implied, remove_margin,
                   no_bet)
from .market import MarketFavourite, MarketLongshot
from .elo import EloEdge
from .draw import DrawNoBet

REGISTRY = {
    "market-favourite-v1": MarketFavourite,
    "market-longshot-v1": MarketLongshot,
    "elo-edge-v1": EloEdge,
    "draw-no-bet-v1": DrawNoBet,
}

FOOTBALL_STRATEGIES = list(REGISTRY)


def build(strategy_id: str, **kwargs):
    if strategy_id not in REGISTRY:
        raise KeyError(f"unknown strategy '{strategy_id}'")
    return REGISTRY[strategy_id](**kwargs)


__all__ = [
    "Strategy", "market_implied", "remove_margin", "no_bet",
    "MarketFavourite", "MarketLongshot", "EloEdge", "DrawNoBet",
    "REGISTRY", "FOOTBALL_STRATEGIES", "build",
]
