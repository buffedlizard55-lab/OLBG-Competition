"""Strategy registry.

Sport-specific strategies live here. Only sports whose source path has
passed verification get runnable strategies; others stay documented-but-
blocked so the UI can show an explicit "not-covered / verification-blocked"
state instead of invented numbers.

Football strategies settle real PnL (permissioned odds path exists). The
ice-hockey strategy is prediction-only: DEL has a verified results path
(OpenLigaDB, ODbL) but no permissioned odds path, so it is graded on
accuracy/Brier by northstar.evaluation, never on profit.
"""
from .base import (Strategy, market_implied, remove_margin,
                   no_bet)
from .market import MarketFavourite, MarketLongshot
from .elo import EloEdge
from .draw import DrawNoBet
from .hockey import HockeyElo

REGISTRY = {
    "market-favourite-v1": MarketFavourite,
    "market-longshot-v1": MarketLongshot,
    "elo-edge-v1": EloEdge,
    "draw-no-bet-v1": DrawNoBet,
    "hockey-elo-v1": HockeyElo,
}

FOOTBALL_STRATEGIES = [
    "market-favourite-v1", "market-longshot-v1",
    "elo-edge-v1", "draw-no-bet-v1",
]
HOCKEY_STRATEGIES = ["hockey-elo-v1"]

# Strategies whose source path lacks permissioned odds: run prediction-only.
PREDICTION_ONLY_STRATEGIES = HOCKEY_STRATEGIES


def build(strategy_id: str, **kwargs):
    if strategy_id not in REGISTRY:
        raise KeyError(f"unknown strategy '{strategy_id}'")
    return REGISTRY[strategy_id](**kwargs)


__all__ = [
    "Strategy", "market_implied", "remove_margin", "no_bet",
    "MarketFavourite", "MarketLongshot", "EloEdge", "DrawNoBet", "HockeyElo",
    "REGISTRY", "FOOTBALL_STRATEGIES", "HOCKEY_STRATEGIES",
    "PREDICTION_ONLY_STRATEGIES", "build",
]
