"""Multiple-comparisons statistics (docs/STATUS.md limitation #8)."""
from __future__ import annotations

import pytest

from northstar.stats import bootstrap_p_two_sided, holm_bonferroni


class TestBootstrapP:
    def test_empty_sequence_is_none(self):
        assert bootstrap_p_two_sided([]) is None

    def test_all_zero_pnl_is_not_extreme(self):
        # mean 0: every centered resample mean is 0, |0| >= |0| -> p = 1
        assert bootstrap_p_two_sided([0.0, 0.0, 0.0]) == pytest.approx(1.0)

    def test_constant_positive_pnl_rejects_null(self):
        # every bet +1: centered values are all 0, observed mean 1 -> no
        # resample is as extreme -> p is the floor 0.0
        assert bootstrap_p_two_sided([1.0] * 10) == pytest.approx(0.0)

    def test_noisy_sequence_has_middle_p(self):
        seq = [1.9, -0.5, -1.0, 2.0, 0.9, -1.0, 1.4, -0.5, 0.9, 1.2,
               -0.2, -1.0, 2.3, -0.5, 0.7, 0.9, -1.0, 1.5, 0.3, -0.6]
        p = bootstrap_p_two_sided(seq)
        assert p is not None and 0.0 < p < 1.0

    def test_deterministic_for_fixed_seed(self):
        seq = [0.9, -1.0, 1.7, -0.4, 0.2]
        assert (bootstrap_p_two_sided(seq, seed=7)
                == bootstrap_p_two_sided(seq, seed=7))

    def test_p_bounded_zero_one(self):
        for seq in ([1.0, -1.0], [2.0] * 5, [0.1, -0.2, 0.05]):
            p = bootstrap_p_two_sided(seq)
            assert p is None or 0.0 <= p <= 1.0


class TestHolmBonferroni:
    def test_known_vector(self):
        # Classic Holm example shape: m=3, raw p = .01, .04, .03
        out = holm_bonferroni({"a": 0.01, "b": 0.04, "c": 0.03})
        # ordered: a(.01)*3=.03, c(.03)*2=.06, b(.04)*1=.04 -> monotone
        # max: a=.03, c=.06, b=.06
        assert out["a"]["p_adjusted"] == pytest.approx(0.03)
        assert out["c"]["p_adjusted"] == pytest.approx(0.06)
        assert out["b"]["p_adjusted"] == pytest.approx(0.06)
        assert out["a"]["family_size"] == 3
        assert out["a"]["significant_05"] is True
        assert out["b"]["significant_05"] is False

    def test_adjusted_never_below_raw_and_capped(self):
        out = holm_bonferroni({"x": 0.6, "y": 0.8})
        for sid in ("x", "y"):
            assert out[sid]["p_adjusted"] >= out[sid]["p_raw"]
            assert out[sid]["p_adjusted"] <= 1.0

    def test_none_entries_excluded_from_family(self):
        out = holm_bonferroni({"a": 0.02, "b": None, "c": 0.4})
        assert out["b"]["p_adjusted"] is None
        assert out["b"]["significant_05"] is None
        assert out["a"]["family_size"] == 2
        # family m=2: a .02*2 = .04 significant; c .4*... not
        assert out["a"]["p_adjusted"] == pytest.approx(0.04)
        assert out["a"]["significant_05"] is True
        assert out["c"]["significant_05"] is False

    def test_all_none_family(self):
        out = holm_bonferroni({"a": None, "b": None})
        assert all(v["p_adjusted"] is None for v in out.values())
        assert all(v["family_size"] == 0 for v in out.values())

    def test_monotonicity_with_ties(self):
        out = holm_bonferroni({"a": 0.05, "b": 0.05, "c": 0.05})
        adj = sorted(v["p_adjusted"] for v in out.values())
        # m=3: .05*3=.15, then max(.15, .05*2)=.15, max(.15,.05)=.15
        assert adj == [pytest.approx(0.15)] * 3
