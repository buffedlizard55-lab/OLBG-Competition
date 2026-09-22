"""Strategy registry.

Sport-specific strategies live here. Only sports whose source path has
passed verification get runnable strategies; others stay documented-but-
blocked so the UI can show an explicit "not-covered / verification-blocked"
state instead of invented numbers.

Football pilot strategies settle real PnL (permissioned odds path exists
for the 2024/25 pilot) on three markets: 1X2, over/under 2.5 goals and
(since 2026-09-22) the Asian handicap. Ice-hockey and darts strategies are
prediction-only: their sports have verified *results* paths (OpenLigaDB,
ODbL) but no permissioned odds path, so they are graded on accuracy/Brier
by northstar.evaluation, never on profit — the naive baselines
(home-ice / listed-first) exist to give those accuracy numbers a reference
point. The forward-test desks (northstar/forward.py) reuse the no-market
strategies on current-season fixtures; predictions are frozen in the
append-only forward ledger.
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
from .asian import AsianHandicapValue, AsianHandicapFavourite
from .baselines import DartsListedFirstBaseline, HockeyHomeBaseline

REGISTRY = {
    "market-favourite-v1": MarketFavourite,
    "market-longshot-v1": MarketLongshot,
    "elo-edge-v1": EloEdge,
    "draw-no-bet-v1": DrawNoBet,
    "draw-value-v1": DrawValue,
    "home-edge-v1": HomeEdge,
    "form-value-v1": FormValue,
    "hockey-elo-v1": HockeyElo,
    "hockey-home-v1": HockeyHomeBaseline,
    "darts-elo-v1": DartsElo,
    "darts-listed-first-v1": DartsListedFirstBaseline,
    "elo-favourite-3way-v1": EloFavourite3Way,
    "poisson-totals-value-v1": PoissonTotalsValue,
    "market-totals-favourite-v1": MarketTotalsFavourite,
    "ah-poisson-value-v1": AsianHandicapValue,
    "ah-market-favourite-v1": AsianHandicapFavourite,
}

# Backtested on the verified football pilot (permissioned odds exist).
# 1X2 family, O/U 2.5 family, Asian-handicap family (added 2026-09-22).
FOOTBALL_STRATEGIES = [
    "market-favourite-v1", "market-longshot-v1",
    "elo-edge-v1", "draw-no-bet-v1",
    "draw-value-v1", "home-edge-v1", "form-value-v1",
    # Second market on the same verified pilot: over/under 2.5 goals.
    "poisson-totals-value-v1", "market-totals-favourite-v1",
    # Third market on the same verified pilot: Asian handicap (the AHh /
    # AvgAHH / AvgAHA columns of the same manual-import file).
    "ah-poisson-value-v1", "ah-market-favourite-v1",
]
# Prediction-only desks on verified results paths without odds.
# Each sport carries its Elo model plus a naive baseline for reference.
HOCKEY_STRATEGIES = ["hockey-elo-v1", "hockey-home-v1"]
DARTS_STRATEGIES = ["darts-elo-v1", "darts-listed-first-v1"]

# Strategies whose source path lacks permissioned odds: run prediction-only.
PREDICTION_ONLY_STRATEGIES = HOCKEY_STRATEGIES + DARTS_STRATEGIES

# Forward-test desks by sport (no-market models; predictions frozen in the
# ledger at capture time). The football forward desk cannot use the market
# strategies: the current season has no permissioned odds path.
FORWARD_STRATEGIES = {
    "football": ["elo-favourite-3way-v1"],
    "ice_hockey": ["hockey-elo-v1", "hockey-home-v1"],
    "darts": ["darts-elo-v1", "darts-listed-first-v1"],
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
    "AsianHandicapValue", "AsianHandicapFavourite",
    "HockeyHomeBaseline", "DartsListedFirstBaseline",
    "REGISTRY", "FOOTBALL_STRATEGIES", "HOCKEY_STRATEGIES",
    "DARTS_STRATEGIES", "PREDICTION_ONLY_STRATEGIES", "FORWARD_STRATEGIES",
    "build",
]
