"""Regulation-time 3-way hockey desks + grading resolver.

Offline, on the committed DEL 2024/25 pilot fixtures. Guarantees:
- the 3-way model probabilities are a proper distribution;
- the regulation outcome resolver maps the stored FINAL row's kind to the
  3-period outcome (After90 -> stored scoreline; AfterExtra/AfterPenalties
  -> regulation draw; unknown kind -> None, never guessed);
- the walk-forward issues for every non-flagged match, is leak-free, and
  grades on regulation outcomes (a regulation draw that loses in OT/SO is
  a hit for the desk, not a 2-way miss);
- the always-home baseline issues every match with the flat prior.
"""
from __future__ import annotations

import math

import pytest

from northstar import models
from northstar.backtest import run_walk_forward
from northstar.evaluation import (prediction_accuracy, regulation_outcome)
from northstar.strategies import build
from northstar.strategies.hockey_reg import reg_three_way


class TestRegThreeWay:
    def test_is_a_probability_distribution(self):
        for lam_h in (1.5, 3.1, 5.0):
            for lam_a in (1.5, 2.9, 4.0):
                p = reg_three_way(lam_h, lam_a)
                assert set(p) == {"home", "draw", "away"}
                assert all(v >= 0 for v in p.values())
                assert abs(sum(p.values()) - 1.0) < 1e-9

    def test_symmetry_and_monotonicity(self):
        p = reg_three_way(3.0, 3.0)
        assert abs(p["home"] - p["away"]) < 1e-9
        assert 0 < p["draw"] < 1
        p_up = reg_three_way(4.5, 2.0)
        p_down = reg_three_way(2.0, 4.5)
        assert p_up["home"] > p["home"] > p_down["home"]
        assert p_up["away"] < p["away"] < p_down["away"]


class TestRegulationOutcomeResolver:
    def test_after_90_final_gives_stored_scoreline(self):
        row = {"result_type_kind": models.RESULT_KIND_AFTER_90}
        assert regulation_outcome(row, 3, 1) == "home"
        assert regulation_outcome(row, 1, 3) == "away"

    def test_after_90_draw_is_defensive_draw(self):
        # A finished DECISIVE final with kind After90 cannot be a draw in
        # hockey (OT would follow) - but the resolver handles it without
        # crashing (defensive; such rows would be flagged upstream).
        row = {"result_type_kind": models.RESULT_KIND_AFTER_90}
        assert regulation_outcome(row, 2, 2) == "draw"

    def test_ot_or_so_final_means_drawn_regulation(self):
        assert regulation_outcome(
            {"result_type_kind": models.RESULT_KIND_AFTER_EXTRA}, 3, 3
        ) == "draw"
        assert regulation_outcome(
            {"result_type_kind": models.RESULT_KIND_AFTER_PENALTIES}, 5, 6
        ) == "draw"

    def test_unknown_kind_refused(self):
        assert regulation_outcome({"result_type_kind": None}, 3, 1) is None
        assert regulation_outcome({}, 3, 1) is None
        assert regulation_outcome(
            {"result_type_kind": "HalfTime"}, 3, 1) is None


class TestRegWalkForward:
    @pytest.fixture(scope="class")
    def hockey_store(self, tmp_path_factory):
        from conftest import DEL_SD1, DEL_SD20, DEL_SD40
        from northstar.adapters import openligadb
        from northstar.db import Store
        s = Store(str(tmp_path_factory.mktemp("reg") / "reg.db"))
        for path in (DEL_SD1, DEL_SD20, DEL_SD40):
            with open(path, encoding="utf-8") as fh:
                openligadb.ingest_matchday(s, fh.read(), sport="ice_hockey")
        yield s
        s.close()

    def test_poisson_reg_desk_leak_free_and_graded(self, hockey_store):
        finished = [e for e in hockey_store.events()
                    if e["status"] == models.EVENT_STATUS_FINISHED]
        strategy = build("hockey-reg-poisson-v1")
        assert strategy.market_outcome == "regulation_3way"
        rep = run_walk_forward(hockey_store, finished, strategy,
                               "hockey-reg-poisson-v1", label="reg-test",
                               allow_no_odds=True)
        assert rep["leak_violations"] == []
        # 21 pilot matches, 4 flagged (impossible layering) -> 17 decisions
        assert len(rep["bets"]) == 17
        assert all(b["outcome_action"] == "prediction_only"
                   for b in rep["bets"])
        assert not any(b["odds"] is not None for b in rep["bets"])
        # every issued model is a proper 3-way distribution
        for b in rep["bets"]:
            probs = b["model"]["model_prob"]
            assert abs(sum(probs.values()) - 1.0) < 1e-6
        evaln = prediction_accuracy(hockey_store, rep["bets"],
                                    sport="ice_hockey",
                                    outcome="regulation_3way")
        assert evaln["outcome_mode"] == "regulation_3way"
        assert evaln["n_graded"] == 17
        assert evaln["ungraded"] == []
        assert all(g["brier"] is not None for g in evaln["graded"])
        # internal consistency
        hits = sum(1 for g in evaln["graded"] if g["hit"])
        assert evaln["hits"] == hits
        assert abs(evaln["accuracy"] - hits / 17) < 1e-5

    def test_regulation_draw_is_a_hit_not_a_2way_miss(self, hockey_store):
        # Find a match that went to OT/SO (final kind != After90) and
        # check the resolver says regulation draw for it.
        ot_ids = []
        for e in hockey_store.events():
            if e["status"] != models.EVENT_STATUS_FINISHED:
                continue
            for r in hockey_store.results(e["event_id"]):
                if (r["final_status"] == "finished"
                        and r["result_type_kind"]
                        in (models.RESULT_KIND_AFTER_EXTRA,
                            models.RESULT_KIND_AFTER_PENALTIES)):
                    ot_ids.append(e["event_id"])
        assert ot_ids, "pilot must contain OT/SO games"
        for eid in ot_ids:
            row = hockey_store.results(eid)[0]
            assert regulation_outcome(row, row["home_goals"],
                                      row["away_goals"]) == "draw"

    def test_home_reg_baseline_issues_every_match(self, hockey_store):
        finished = [e for e in hockey_store.events()
                    if e["status"] == models.EVENT_STATUS_FINISHED]
        strategy = build("hockey-reg-home-v1")
        assert strategy.market_outcome == "regulation_3way"
        rep = run_walk_forward(hockey_store, finished, strategy,
                               "hockey-reg-home-v1", label="reg-test",
                               allow_no_odds=True)
        assert rep["leak_violations"] == []
        assert len(rep["bets"]) == 17
        assert all(b["selection"] == "home" for b in rep["bets"])
        evaln = prediction_accuracy(hockey_store, rep["bets"],
                                    sport="ice_hockey",
                                    outcome="regulation_3way")
        assert evaln["n_graded"] == 17
        # baseline accuracy = share of regulation home wins on the pool
        graded = evaln["graded"]
        home_wins = sum(1 for g in graded
                        if g["actual"] == "home")
        assert evaln["hits"] == home_wins

    def test_evaluation_refuses_unknown_outcome_mode(self, hockey_store):
        with pytest.raises(ValueError):
            prediction_accuracy(hockey_store, [], outcome="bogus")
