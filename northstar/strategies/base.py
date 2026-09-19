"""Strategy base class + shared pure helpers."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, Optional

if TYPE_CHECKING:  # pragma: no cover
    from ..backtest import TimeBoundedStore


def remove_margin(odds: Dict[str, float]) -> Dict[str, float]:
    """Proportional normalisation -> fair (margin-removed) implied
    probabilities. Raises if any price is missing or <= 1."""
    if any(odds.get(k) is None or odds[k] <= 1.0
           for k in ("home", "draw", "away")):
        raise ValueError(f"prices missing or <= 1: {odds}")
    inv = {k: 1.0 / odds[k] for k in odds}
    total = sum(inv.values())
    return {k: v / total for k, v in inv.items()}


def market_implied(odds: Optional[Dict[str, Optional[float]]]
                   ) -> Optional[Dict[str, float]]:
    if not odds:
        return None
    try:
        return remove_margin({k: v for k, v in odds.items()})
    except (ValueError, TypeError):
        return None


def no_bet(cutoff_utc: Optional[datetime],
           model: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    return {"cutoff_utc": cutoff_utc, "selection_key": "none",
            "selection_text": "no bet", "model": model or {}}


@dataclass
class Strategy:
    name: str
    description: str
    odds_provider: str = "market_avg"

    def predict(self, event: Dict[str, Any], tbs: "TimeBoundedStore",
                start: datetime,
                market_odds: Optional[Dict[str, Optional[float]]] = None,
                odds_observed_at: Optional[datetime] = None
                ) -> Dict[str, Any]:
        """Return {"cutoff_utc", "selection_key" (home|draw|away|"none"),
        "selection_text", "model": {...}}.

        Contract:
        - every feature read through ``tbs`` uses an ``at`` <= the returned
          ``cutoff_utc``;
        - ``cutoff_utc`` is the latest time any used input (features and
          entry price) became available, strictly before ``start``;
        - reading the future raises TimeLeakageError from the store.
        """
        raise NotImplementedError

    def ratings_after(self, event: Dict[str, Any], home_goals: int,
                      away_goals: int, tbs: "TimeBoundedStore",
                      final_at: datetime) -> Dict[str, float]:
        """Optional absolute ratings to release at/after final_at."""
        return {}
