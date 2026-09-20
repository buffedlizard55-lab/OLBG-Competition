"""Multiple-comparisons statistics for the strategy family.

The desk tests several strategies on the same small pilot sample.  Without a
correction, "the best of m results" is biased upwards (selection effect).
This module adds the honest family-wise view required by docs/STATUS.md
limitation #8:

- ``bootstrap_p_two_sided``: a deterministic centered-bootstrap p-value for
  H0: mean per-bet PnL = 0 (the same resampling scheme/seed family as
  ``backtest.bootstrap_ci``, so numbers are reproducible offline);
- ``holm_bonferroni``: step-down adjusted p-values across the tested family
  (Holm 1979).  Adjusted p-values are monotone and clipped at 1.0.

Nothing here claims significance for the pilot; it exists so the site can
show that nothing *survives* correction either.
"""
from __future__ import annotations

import random
from typing import Dict, List, Optional, Sequence


def bootstrap_p_two_sided(pnl_sequence: Sequence[float],
                          n_resamples: int = 2000,
                          seed: int = 54321) -> Optional[float]:
    """Two-sided bootstrap p-value for H0: mean(PnL) = 0.

    Centered bootstrap: resample from (x - mean(x)) so the null holds by
    construction, then measure how extreme the observed mean is relative to
    the null distribution of the mean.  Deterministic for a fixed seed.
    Returns None for an empty sequence.
    """
    n = len(pnl_sequence)
    if n == 0:
        return None
    mean = sum(pnl_sequence) / n
    centered = [x - mean for x in pnl_sequence]
    rng = random.Random(seed)
    extreme = 0
    abs_mean = abs(mean)
    for _ in range(n_resamples):
        s = 0.0
        for _ in range(n):
            s += centered[rng.randrange(n)]
        if abs(s / n) >= abs_mean - 1e-12:
            extreme += 1
    return min(1.0, extreme / n_resamples)


def holm_bonferroni(p_values: Dict[str, Optional[float]]
                    ) -> Dict[str, Dict[str, Optional[object]]]:
    """Holm step-down adjusted p-values over a family of tests.

    Input maps strategy_id -> raw p (None allowed: untestable, e.g. no
    settled bets; such members are excluded from the family size and get
    ``adjusted: None``).  Output maps strategy_id ->
    {"p_raw", "p_adjusted", "family_size", "significant_05"}.

    Holm (1979): with ordered raw p_(1) <= ... <= p_(m),
    adjusted p_(i) = max_{j<=i} min(1, (m - j + 1) * p_(j)).
    """
    testable = {k: v for k, v in p_values.items() if v is not None}
    m = len(testable)
    out: Dict[str, Dict[str, Optional[object]]] = {
        k: {"p_raw": v, "p_adjusted": None, "family_size": m,
            "significant_05": None}
        for k, v in p_values.items()
    }
    if not m:
        return out
    order: List[str] = sorted(testable, key=lambda k: (testable[k], k))
    running = 0.0
    for i, sid in enumerate(order):
        adj = min(1.0, (m - i) * testable[sid])
        running = max(running, adj)  # enforce monotonicity
        out[sid]["p_adjusted"] = round(running, 6)
        out[sid]["significant_05"] = bool(running < 0.05)
    for sid in out:
        if out[sid]["p_raw"] is not None:
            out[sid]["p_raw"] = round(float(out[sid]["p_raw"]), 6)
    return out
