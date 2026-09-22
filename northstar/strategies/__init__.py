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
from .decay import EloDecay
from .dixon_coles import DixonColesValue
from .draw import DrawNoBet
from .value import DrawValue, FormValue, HomeEdge
from .hockey import HockeyElo
from .hockey_reg import HockeyRegPoisson, HockeyRegHomeBaseline
from .hockey_more import (HockeyEloMov, HockeyTotalsOverBaseline,
                          HockeyTotalsPoisson)
from .darts import DartsElo
from .darts_more import DartsEloMov
from .totals import (MarketTotalsFavourite, PoissonTotalsArgmax,
                     PoissonTotalsValue)
from .asian import AsianHandicapValue, AsianHandicapFavourite
from .baselines import (DartsListedFirstBaseline,
                        FootballHomeBaseline, FootballTotalsOverBaseline,
                        HockeyHomeBaseline)

REGISTRY = {
    "market-favourite-v1": MarketFavourite,
    "market-longshot-v1": MarketLongshot,
    "elo-edge-v1": EloEdge,
    "elo-decay-v1": EloDecay,
    "dixon-coles-v1": DixonColesValue,
    "draw-no-bet-v1": DrawNoBet,
    "draw-value-v1": DrawValue,
    "home-edge-v1": HomeEdge,
    "form-value-v1": FormValue,
    "hockey-elo-v1": HockeyElo,
    "hockey-home-v1": HockeyHomeBaseline,
    "hockey-reg-poisson-v1": HockeyRegPoisson,
    "hockey-reg-home-v1": HockeyRegHomeBaseline,
    "hockey-elo-mov-v1": HockeyEloMov,
    "hockey-totals-poisson-v1": HockeyTotalsPoisson,
    "hockey-totals-over-v1": HockeyTotalsOverBaseline,
    "darts-elo-v1": DartsElo,
    "darts-mov-elo-v1": DartsEloMov,
    "darts-listed-first-v1": DartsListedFirstBaseline,
    "elo-favourite-3way-v1": EloFavourite3Way,
    "poisson-totals-value-v1": PoissonTotalsValue,
    "market-totals-favourite-v1": MarketTotalsFavourite,
    "ah-poisson-value-v1": AsianHandicapValue,
    "ah-market-favourite-v1": AsianHandicapFavourite,
    # Full-season football accuracy pair (added 2026-09-22, pass 3): the
    # 2024/25 Bundesliga season is committed in full (306 finished
    # matches), so the no-market desks can be graded on a sample 11x the
    # frozen 27-match PnL pilot - real results, no odds, no PnL claim.
    "football-home-baseline-v1": FootballHomeBaseline,
    "football-totals-poisson-v1": PoissonTotalsArgmax,
    "football-totals-over-v1": FootballTotalsOverBaseline,
}

# Backtested on the verified football pilot (permissioned odds exist).
# 1X2 family, O/U 2.5 family, Asian-handicap family (added 2026-09-22),
# goal-model lineage controls (elo-decay-v1, dixon-coles-v1, added
# 2026-09-22 - pre-registered, part of the Holm PnL family).
FOOTBALL_STRATEGIES = [
    "market-favourite-v1", "market-longshot-v1",
    "elo-edge-v1", "elo-decay-v1", "dixon-coles-v1",
    "draw-no-bet-v1",
    "draw-value-v1", "home-edge-v1", "form-value-v1",
    # Second market on the same verified pilot: over/under 2.5 goals.
    "poisson-totals-value-v1", "market-totals-favourite-v1",
    # Third market on the same verified pilot: Asian handicap (the AHh /
    # AvgAHH / AvgAHA columns of the same manual-import file).
    "ah-poisson-value-v1", "ah-market-favourite-v1",
]
# Football no-market desks graded on the WHOLE committed 2024/25
# Bundesliga season (306 finished results).  elo-favourite-3way-v1 is the
# same pre-registered desk the forward test already issues; this block
# gives its walk-forward accuracy a real out-of-sample-sized sample on
# committed verified results instead of the 27-match PnL pilot.
FOOTBALL_ACCURACY_STRATEGIES = [
    "elo-favourite-3way-v1", "football-home-baseline-v1",
    "football-totals-poisson-v1", "football-totals-over-v1",
]

# Prediction-only desks on verified results paths without odds.
# Each sport carries its model(s) plus a naive baseline for reference.
# The regulation-time 3-way pair (added 2026-09-22) is graded on the
# 3-period outcome, not the OT/SO-aware final (market_outcome=
# "regulation_3way" in the strategy + evaluation/forward grading).
HOCKEY_STRATEGIES = [
    "hockey-elo-v1", "hockey-home-v1",
    "hockey-reg-poisson-v1", "hockey-reg-home-v1",
    # Added 2026-09-22: margin-of-victory Elo (2-way final) and the second
    # prediction-only market, total goals over/under 5.5 (with its naive
    # always-over baseline).  Same verified ODbL result path, same rules.
    "hockey-elo-mov-v1", "hockey-totals-poisson-v1", "hockey-totals-over-v1",
]
DARTS_STRATEGIES = ["darts-elo-v1", "darts-mov-elo-v1",
                    "darts-listed-first-v1"]

# Which naive baseline each accuracy desk must be quoted against (site
# "beats its naive baseline?" flag; cli attaches the comparison to the
# backtest card).  A model desk without its baseline in the payload is a
# wiring bug, not a missing number - the site renders no flag rather than
# comparing against nothing.
NAIVE_BASELINE_FOR = {
    "hockey-elo-v1": "hockey-home-v1",
    "hockey-reg-poisson-v1": "hockey-reg-home-v1",
    "hockey-elo-mov-v1": "hockey-home-v1",
    "hockey-totals-poisson-v1": "hockey-totals-over-v1",
    "darts-elo-v1": "darts-listed-first-v1",
    "darts-mov-elo-v1": "darts-listed-first-v1",
    "elo-favourite-3way-v1": "football-home-baseline-v1",
    "football-totals-poisson-v1": "football-totals-over-v1",
}

# Strategies whose source path lacks permissioned odds: run prediction-only.
PREDICTION_ONLY_STRATEGIES = (HOCKEY_STRATEGIES + DARTS_STRATEGIES
                              + FOOTBALL_ACCURACY_STRATEGIES)

# Forward-test desks by sport (no-market models; predictions frozen in the
# ledger at capture time). The football forward desk cannot use the market
# strategies: the current season has no permissioned odds path.
FORWARD_STRATEGIES = {
    "football": ["elo-favourite-3way-v1"],
    "ice_hockey": ["hockey-elo-v1", "hockey-home-v1",
                   "hockey-elo-mov-v1",
                   "hockey-reg-poisson-v1", "hockey-reg-home-v1",
                   "hockey-totals-poisson-v1", "hockey-totals-over-v1"],
    "darts": ["darts-elo-v1", "darts-listed-first-v1"],
}


def build(strategy_id: str, **kwargs):
    if strategy_id not in REGISTRY:
        raise KeyError(f"unknown strategy '{strategy_id}'")
    return REGISTRY[strategy_id](**kwargs)


__all__ = [
    "Strategy", "market_implied", "remove_margin", "no_bet",
    "MarketFavourite", "MarketLongshot", "EloEdge", "EloFavourite3Way",
    "EloDecay", "DixonColesValue",
    "DrawNoBet", "DrawValue", "HomeEdge", "FormValue",
    "HockeyElo", "HockeyRegPoisson", "HockeyRegHomeBaseline",
    "PoissonTotalsArgmax", "FootballHomeBaseline", "FootballTotalsOverBaseline",
    "HockeyEloMov", "HockeyTotalsPoisson", "HockeyTotalsOverBaseline",
    "DartsElo", "DartsEloMov", "PoissonTotalsValue", "MarketTotalsFavourite",
    "AsianHandicapValue", "AsianHandicapFavourite",
    "HockeyHomeBaseline", "DartsListedFirstBaseline",
    "REGISTRY", "FOOTBALL_STRATEGIES", "FOOTBALL_ACCURACY_STRATEGIES",
    "HOCKEY_STRATEGIES",
    "DARTS_STRATEGIES", "PREDICTION_ONLY_STRATEGIES", "FORWARD_STRATEGIES",
    "NAIVE_BASELINE_FOR",
    "build",
]
