"""Elo recency decay + Dixon-Coles 1X2 desk (football pilot controls).

Offline: the decay math is unit-tested against a TimeBoundedStore; the
Dixon-Coles score matrix is checked against the plain-Poisson limit and
the negative-cell rejection; both desks run the real walk-forward on the
committed football pilot fixtures with zero leakage violations.
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

import pytest

from northstar import models
from northstar.backtest import TimeBoundedStore, run_walk_forward
from northstar.db import Store
from northstar.strategies import build
from northstar.strategies.decay import (HALF_LIFE_DAYS, EloDecay,
                                        effective_rating)
from northstar.strategies.dixon_coles import (dixon_coles_three_way, tau)
from conftest import PILOT_OLDB_FILES, read_fixture
from northstar.adapters import openligadb


class TestEffectiveRating:
    def _tbs_with_history(self, rating, updated_days_ago):
        tbs = TimeBoundedStore()
        at = datetime(2026, 1, 10, 12, 0, tzinfo=timezone.utc)
        t0 = at - timedelta(days=updated_days_ago)
        tbs.update_ratings({"Team": rating}, available_at=t0)
        return tbs, at

    def test_no_history_returns_seed(self):
        tbs = TimeBoundedStore()
        at = datetime(2026, 1, 10, 12, 0, tzinfo=timezone.utc)
        # team_rating must be called first to register the read audit
        assert tbs.team_rating("Nobody", at) is None
        assert effective_rating(tbs, "Nobody", at) == 1500.0

    def test_fresh_rating_unchanged(self):
        tbs, at = self._tbs_with_history(1700.0, 0.0)
        assert abs(effective_rating(tbs, "Team", at) - 1700.0) < 1e-9

    def test_half_life_relaxes_to_seed(self):
        tbs, at = self._tbs_with_history(1700.0, HALF_LIFE_DAYS)
        # one half-life -> exactly halfway back to the seed
        assert abs(effective_rating(tbs, "Team", at) - 1600.0) < 1e-6
        tbs2, at2 = self._tbs_with_history(1700.0, 2 * HALF_LIFE_DAYS)
        assert abs(effective_rating(tbs2, "Team", at2) - 1550.0) < 1e-6

    def test_below_seed_relaxes_upward(self):
        tbs, at = self._tbs_with_history(1300.0, HALF_LIFE_DAYS)
        assert abs(effective_rating(tbs, "Team", at) - 1400.0) < 1e-6

    def test_records_read_audit(self):
        tbs, at = self._tbs_with_history(1700.0, 10.0)
        assert tbs.team_rating("Team", at) == 1700.0
        effective_rating(tbs, "Team", at)
        assert tbs.latest_read_at == at


class TestDixonColes:
    def test_tau_values(self):
        assert tau(0, 0, 2.0, 1.5, -0.1) == 1.0 + 2.0 * 1.5 * 0.1
        assert tau(0, 1, 2.0, 1.5, -0.1) == 1.0 - 0.2
        assert tau(1, 0, 2.0, 1.5, -0.1) == 1.0 - 0.15
        assert tau(1, 1, 2.0, 1.5, -0.1) == 1.1
        assert tau(2, 3, 2.0, 1.5, -0.1) == 1.0

    def test_reduces_to_plain_poisson_at_rho_zero(self):
        lam_h, lam_a = 1.7, 1.2
        p = dixon_coles_three_way(lam_h, lam_a, rho=0.0)
        # plain independent Poisson 3-way (independent double sum)
        def pmf(k, lam):
            return math.exp(-lam) * lam ** k / math.factorial(k)
        h = d = a = 0.0
        for x in range(30):
            for y in range(30):
                cell = pmf(x, lam_h) * pmf(y, lam_a)
                h += cell if x > y else 0.0
                d += cell if x == y else 0.0
                a += cell if x < y else 0.0
        total = h + d + a
        assert abs(p["home"] - h / total) < 1e-6
        assert abs(p["draw"] - d / total) < 1e-6
        assert abs(p["away"] - a / total) < 1e-6

    def test_is_a_distribution(self):
        p = dixon_coles_three_way(1.7, 1.2)
        assert abs(sum(p.values()) - 1.0) < 1e-9
        assert all(v >= 0 for v in p.values())

    def test_negative_cell_rejects(self):
        # tau(0,1) = 1 + lam_h*rho = 1 - 1.1 < 0 at lam_h = 11, rho = -0.1
        with pytest.raises(ValueError, match="negative score cell"):
            dixon_coles_three_way(11.0, 3.0, rho=-0.1)


class TestWalkForward:
    @pytest.fixture(scope="class")
    def pilot_store(self, tmp_path_factory):
        s = Store(str(tmp_path_factory.mktemp("dec") / "dec.db"))
        for name in PILOT_OLDB_FILES:
            openligadb.ingest_matchday(s, read_fixture(name))
        yield s
        s.close()

    def test_elo_decay_runs_leak_free(self, pilot_store):
        finished = [e for e in pilot_store.events()
                    if e["status"] == models.EVENT_STATUS_FINISHED]
        rep = run_walk_forward(pilot_store, finished, build("elo-decay-v1"),
                               "elo-decay-v1", label="decay-test")
        assert rep["leak_violations"] == []
        # same rating history as elo-edge on a 7-month sample -> same bets
        rep_edge = run_walk_forward(pilot_store, finished,
                                    build("elo-edge-v1"), "elo-edge-v1",
                                    label="edge-test")
        assert rep["leak_violations"] == []
        assert [b["event_id"] for b in rep["bets"]] == \
               [b["event_id"] for b in rep_edge["bets"]]

    def test_dixon_coles_runs_leak_free(self, pilot_store):
        finished = [e for e in pilot_store.events()
                    if e["status"] == models.EVENT_STATUS_FINISHED]
        rep = run_walk_forward(pilot_store, finished,
                               build("dixon-coles-v1"), "dixon-coles-v1",
                               label="dc-test")
        assert rep["leak_violations"] == []
        for b in rep["bets"]:
            probs = b["model"]["model_prob"]
            assert set(probs) == {"home", "draw", "away"}
            assert abs(sum(probs.values()) - 1.0) < 1e-6
            assert b["model"]["rho"] == -0.1
        # settled bets have real PnL (permissioned pilot odds exist)
        assert all(b["outcome_action"] in ("settled", "already_settled",
                                           "review")
                   for b in rep["bets"])
