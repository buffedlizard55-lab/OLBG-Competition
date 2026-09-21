"""Strategy registry.

Sport-specific strategies live here. Only sports whose source path has
passed verification get runnable strategies; others stay documented-but-
blocked so the UI can show an explicit "not-covered / verification-blocked"
state instead of invented numbers.

Football pilot strategies settle real PnL (permissioned odds path exists
for the 2024/25 pilot). Ice-hockey and darts strategies are
prediction-only: their sports have verified *results* paths (OpenLigaDB,
ODbL) but no permissioned odds path, so they are graded on accuracy/Brier
by northstar.evaluation, never on profit. The forward-test desks
(northstar/forward.py) reuse the no-market strategies on current-season
fixtures; predictions are frozen in the append-only forward ledger.
"""
from .base import (Strategy, market_implied, remove_margin,
                   no_bet)
from .market import MarketFavourite, MarketLongshot
from .elo import EloEdge, EloFavourite3Way
from .draw import DrawNoBet
from .value import DrawValue, FormValue, HomeEdge
from .hockey import HockeyElo
from .darts import DartsElo
from .totals import MarketTotalsFavourite, PoissonTotalsValue

REGISTRY = {
    "market-favourite-v1": MarketFavourite,
    "market-longshot-v1": MarketLongshot,
    "elo-edge-v1": EloEdge,
    "draw-no-bet-v1": DrawNoBet,
    "draw-value-v1": DrawValue,
    "home-edge-v1": HomeEdge,
    "form-value-v1": FormValue,
    "hockey-elo-v1": HockeyElo,
    "darts-elo-v1": DartsElo,
    "elo-favourite-3way-v1": EloFavourite3Way,
    "poisson-totals-value-v1": PoissonTotalsValue,
    "market-totals-favourite-v1": MarketTotalsFavourite,
}

# Backtested on the verified football pilot (permissioned odds exist).
FOOTBALL_STRATEGIES = [
    "market-favourite-v1", "market-longshot-v1",
    "elo-edge-v1", "draw-no-bet-v1",
    "draw-value-v1", "home-edge-v1", "form-value-v1",
    # Second market on the same verified pilot: over/under 2.5 goals.
    "poisson-totals-value-v1", "market-totals-favourite-v1",
]
# Prediction-only desks on verified results paths without odds.
HOCKEY_STRATEGIES = ["hockey-elo-v1"]
DARTS_STRATEGIES = ["darts-elo-v1"]

# Strategies whose source path lacks permissioned odds: run prediction-only.
PREDICTION_ONLY_STRATEGIES = HOCKEY_STRATEGIES + DARTS_STRATEGIES

# Forward-test desks by sport (no-market models; predictions frozen in the
# ledger at capture time). The football forward desk cannot use the market
# strategies: the current season has no permissioned odds path.
FORWARD_STRATEGIES = {
    "football": ["elo-favourite-3way-v1"],
    "ice_hockey": ["hockey-elo-v1"],
    "darts": ["darts-elo-v1"],
}


def build(strategy_id: str, **kwargs):
    if strategy_id not in REGISTRY:
        raise KeyError(f"unknown strategy '{strategy_id}'")
    return REGISTRY[strategy_id](**kwargs)


__all__ = [
    "Strategy", "market_implied", "remove_margin", "no_bet",
    "MarketFavourite", "MarketLongshot", "EloEdge", "EloFavourite3Way",
    "DrawNoBet", "DrawValue", "HomeEdge", "FormValue",
    "HockeyElo", "DartsElo", "PoissonTotalsValue", "MarketTotalsFavourite",
    "REGISTRY", "FOOTBALL_STRATEGIES", "HOCKEY_STRATEGIES",
    "DARTS_STRATEGIES", "PREDICTION_ONLY_STRATEGIES", "FORWARD_STRATEGIES",
    "build",
]
