"""New strategy family: value probes, no-market Elo desks, darts Elo.

Every strategy must: decide only from pre-cutoff features (the engine
audits reads), state a model trail, and pass walk-forward without leak
violations on synthetic stores.
"""
from __future__ import annotations

from datetime import timedelta

import pytest

from northstar import models
from northstar.backtest import run_walk_forward
from northstar.models import parse_utc
from northstar.strategies import REGISTRY, build
from northstar.strategies.darts import DartsElo
from northstar.strategies.elo import EloFavourite3Way, elo_three_way
from northstar.strategies.value import DrawValue, FormValue, HomeEdge

from conftest import mk_event, mk_odds, mk_result


def _three_way_prices(store, event_id, home, draw, away,
                      observed="2026-01-09T12:00:00Z"):
    for sel, odds in (("home", home), ("draw", draw), ("away", away)):
        mk_odds(store, event_id, selection_key=sel, odds=odds,
                observed=observed)


class TestDrawValue:
    def test_bets_draw_when_model_edge_clears_threshold(self, store):
        ev = mk_event(store, event_id="ev-dv1")
        # fair draw ~ .2105 vs equal-rating model draw .25 -> edge ~ .04
        _three_way_prices(store, "ev-dv1", home=2.0, draw=5.0, away=4.0)
        mk_result(store, event_id="ev-dv1", home_goals=1, away_goals=1)
        rep = run_walk_forward(store, [ev], build("draw-value-v1"),
                               "draw-value-v1", label="t")
        assert rep["leak_violations"] == []
        assert len(rep["bets"]) == 1
        assert rep["bets"][0]["selection"] == "draw"
        model = rep["bets"][0]["model"]
        assert model["edge"]["draw"] >= 0.03
        assert model["model_prob"] and model["fair_prob"]

    def test_passes_when_market_draw_is_fair_or_short(self, store):
        ev = mk_event(store, event_id="ev-dv2")
        # fair draw ~ .31 > model .25 -> negative edge -> no bet
        _three_way_prices(store, "ev-dv2", home=2.4, draw=3.0, away=3.0)
        mk_result(store, event_id="ev-dv2")
        rep = run_walk_forward(store, [ev], build("draw-value-v1"),
                               "draw-value-v1", label="t")
        assert rep["bets"] == []
        assert rep["skipped"][0]["reason"] == "strategy passed"

    def test_no_market_price_is_no_bet(self, store):
        ev = mk_event(store, event_id="ev-dv3")
        mk_result(store, event_id="ev-dv3")
        rep = run_walk_forward(store, [ev], build("draw-value-v1"),
                               "draw-value-v1", label="t")
        assert rep["bets"] == []
        assert rep["skipped"][0]["reason"] == "no pre-cutoff odds" or \
            rep["skipped"][0]["reason"] == "strategy passed"


class TestHomeEdge:
    def test_bets_home_only_on_large_edge(self, store):
        ev = mk_event(store, event_id="ev-he1")
        # market leans away (fair home ~.279) vs equal-rating model home
        # ~.44 -> edge ~.16 >= .05
        _three_way_prices(store, "ev-he1", home=3.5, draw=3.8, away=2.1)
        mk_result(store, event_id="ev-he1", home_goals=2, away_goals=0)
        rep = run_walk_forward(store, [ev], build("home-edge-v1"),
                              "home-edge-v1", label="t")
        assert rep["leak_violations"] == []
        assert len(rep["bets"]) == 1
        assert rep["bets"][0]["selection"] == "home"

    def test_passes_when_home_is_market_favourite(self, store):
        ev = mk_event(store, event_id="ev-he2")
        # market home ~.62 fair > model .44 -> negative edge
        _three_way_prices(store, "ev-he2", home=1.5, draw=4.5, away=6.0)
        mk_result(store, event_id="ev-he2")
        rep = run_walk_forward(store, [ev], build("home-edge-v1"),
                              "home-edge-v1", label="t")
        assert rep["bets"] == []


class TestFormValue:
    def _season(self, store):
        # Two released wins for Alpha, two losses for Beta, then the bet
        # event.  Results release even on passed events (engine fix).
        e1 = mk_event(store, event_id="ev-f1", home="Alpha", away="Beta",
                      start="2026-01-01T15:00:00Z")
        store.conn.execute(
            "UPDATE events SET group_order=1 WHERE event_id='ev-f1'")
        mk_result(store, event_id="ev-f1", home_goals=2, away_goals=0,
                  final_at="2026-01-01T17:00:00Z")
        e2 = mk_event(store, event_id="ev-f2", home="Beta", away="Alpha",
                      start="2026-01-05T15:00:00Z")
        store.conn.execute(
            "UPDATE events SET group_order=2 WHERE event_id='ev-f2'")
        mk_result(store, event_id="ev-f2", home_goals=0, away_goals=1,
                  final_at="2026-01-05T17:00:00Z")
        e3 = mk_event(store, event_id="ev-f3", home="Alpha", away="Beta",
                      start="2026-01-10T15:00:00Z")
        store.conn.execute(
            "UPDATE events SET group_order=3 WHERE event_id='ev-f3'")
        _three_way_prices(store, "ev-f3", home=2.2, draw=3.4, away=3.2)
        mk_result(store, event_id="ev-f3", home_goals=1, away_goals=0,
                  final_at="2026-01-10T17:00:00Z")
        return [e1, e2, e3]

    def test_backs_better_form_at_valid_price(self, store):
        events = self._season(store)
        rep = run_walk_forward(store, events, build("form-value-v1"),
                               "form-value-v1", label="t")
        assert rep["leak_violations"] == []
        bets = [b for b in rep["bets"] if b["event_id"] == "ev-f3"]
        assert len(bets) == 1
        assert bets[0]["selection"] == "home"  # Alpha (home) has the form
        assert bets[0]["model"]["form_points_per_match"]["home"] == 3.0
        assert bets[0]["model"]["form_points_per_match"]["away"] == 0.0

    def test_insufficient_history_is_no_bet(self, store):
        # Only the first two events (no released form yet at their cutoffs)
        ev = mk_event(store, event_id="ev-f0", home="Alpha", away="Beta",
                      start="2026-01-01T15:00:00Z")
        _three_way_prices(store, "ev-f0", home=2.2, draw=3.4, away=3.2,
                          observed="2025-12-31T12:00:00Z")
        mk_result(store, event_id="ev-f0", final_at="2026-01-01T17:00:00Z")
        rep = run_walk_forward(store, [ev], build("form-value-v1"),
                               "form-value-v1", label="t")
        assert rep["bets"] == []
        assert rep["skipped"][0]["model"]["reason"] == \
            "insufficient released form history"

    def test_price_floor_refuses_short_favourite(self, store):
        events = self._season(store)
        # Alpha form is real but the price is below the 1.80 floor
        store.conn.execute(
            "UPDATE odds_snapshots SET decimal_odds=1.4 "
            "WHERE event_id='ev-f3' AND selection_key='home'")
        rep = run_walk_forward(store, events, build("form-value-v1"),
                               "form-value-v1", label="t")
        bets = [b for b in rep["bets"] if b["event_id"] == "ev-f3"]
        assert bets == []
        skip = [s for s in rep["skipped"] if s["event_id"] == "ev-f3"][0]
        assert "below floor" in skip["model"]["reason"]


class TestEloFavourite3Way:
    def test_selects_argmax_above_threshold_in_forward_mode(self, store):
        from northstar.backtest import TimeBoundedStore
        s = build("elo-favourite-3way-v1")
        tbs = TimeBoundedStore()
        start = parse_utc("2026-02-01T15:00:00Z")
        ev = {"event_id": "ev-x", "home_team": "A", "away_team": "B",
              "scheduled_start_utc": "2026-02-01T15:00:00Z"}
        tbs.register_event(ev)
        tbs.update_ratings({"A": 1650.0, "B": 1400.0},
                           available_at=start - timedelta(days=1))
        as_of = start - timedelta(hours=24)
        out = s.predict(ev, tbs, start, as_of=as_of)
        assert out["selection_key"] == "home"
        assert out["cutoff_utc"] == as_of
        assert out["model"]["model_prob"]["home"] >= s.min_prob

    def test_passes_below_selectivity_threshold(self, store):
        from northstar.backtest import TimeBoundedStore
        s = build("elo-favourite-3way-v1")
        tbs = TimeBoundedStore()
        start = parse_utc("2026-02-01T15:00:00Z")
        ev = {"event_id": "ev-y", "home_team": "A", "away_team": "B",
              "scheduled_start_utc": "2026-02-01T15:00:00Z"}
        tbs.register_event(ev)
        out = s.predict(ev, tbs, start, as_of=start - timedelta(hours=24))
        assert out["selection_key"] == "none"
        assert "below selectivity" in out["model"]["reason"]

    def test_three_way_mapping_sums_to_one(self):
        p = elo_three_way(1550.0, 1480.0)
        assert sum(p.values()) == pytest.approx(1.0)
        assert 0.15 <= p["draw"] <= 0.32


class TestDartsElo:
    def test_neutral_ratings_never_select(self):
        from northstar.backtest import TimeBoundedStore
        s = DartsElo()
        tbs = TimeBoundedStore()
        start = parse_utc("2026-02-01T19:00:00Z")
        ev = {"event_id": "ev-d", "home_team": "Player1",
              "away_team": "Player2",
              "scheduled_start_utc": "2026-02-01T19:00:00Z"}
        tbs.register_event(ev)
        out = s.predict(ev, tbs, start, as_of=start - timedelta(hours=2))
        # 1500 v 1500, no venue edge -> 0.5/0.5 < min_prob 0.60
        assert out["selection_key"] == "none"

    def test_stronger_player_selected_after_history(self):
        from northstar.backtest import TimeBoundedStore
        s = DartsElo()
        tbs = TimeBoundedStore()
        tbs.update_ratings({"Player1": 1620.0, "Player2": 1410.0},
                           available_at=parse_utc("2026-01-20T00:00:00Z"))
        start = parse_utc("2026-02-01T19:00:00Z")
        ev = {"event_id": "ev-d2", "home_team": "Player1",
              "away_team": "Player2",
              "scheduled_start_utc": "2026-02-01T19:00:00Z"}
        tbs.register_event(ev)
        out = s.predict(ev, tbs, start, as_of=start - timedelta(hours=2))
        assert out["selection_key"] == "home"
        assert out["selection_text"] == "Player1"
        assert out["model"]["model_prob"]["draw"] == 0.0
        assert out["cutoff_utc"] == start - timedelta(hours=2)

    def test_drawn_row_updates_as_half_and_never_guesses(self):
        from northstar.backtest import TimeBoundedStore
        s = DartsElo()
        tbs = TimeBoundedStore()
        ev = {"event_id": "ev-d3", "home_team": "P", "away_team": "Q",
              "scheduled_start_utc": "2026-02-01T19:00:00Z"}
        out = s.ratings_after(ev, 3, 3, tbs,
                              parse_utc("2026-02-01T22:00:00Z"))
        # equal ratings + draw -> no movement
        assert out["P"] == pytest.approx(1500.0)
        assert out["Q"] == pytest.approx(1500.0)

    def test_walk_forward_prediction_only_and_graded(self, store):
        # Five finished darts events, P1 outscores P2 throughout: the
        # 0.60 selectivity floor is cleared only once ratings separate,
        # and every decision is prediction-only (allow_no_odds), never
        # settled, never PnL.
        events = []
        for i in range(1, 6):
            eid = f"ev-dp{i}"
            ev = mk_event(store, event_id=eid, sport="darts",
                          home="P1", away="P2",
                          start=f"2026-01-0{i}T19:00:00Z")
            store.conn.execute(
                f"UPDATE events SET group_order={i} WHERE event_id=?",
                (eid,))
            mk_result(store, event_id=eid, home_goals=6, away_goals=6 - i,
                      final_at=f"2026-01-0{i}T23:00:00Z")
            events.append(ev)
        rep = run_walk_forward(store, events, build("darts-elo-v1"),
                               "darts-elo-v1", label="darts-t",
                               allow_no_odds=True)
        assert rep["leak_violations"] == []
        assert rep["bets"], "ratings should clear the 0.60 floor by match 5"
        assert all(b["outcome_action"] == "prediction_only"
                   for b in rep["bets"])
        assert all(b["selection"] == "home" for b in rep["bets"])
        assert store.all_settlements() == []
        tips = store.tips(tipster_id="darts-elo-v1")
        assert tips and all(t["status"] == models.TIP_STATUS_UNSETTLEABLE
                            for t in tips)
        assert all(t["market"] == models.MARKET_MATCH_WINNER_3WAY
                   for t in tips)  # engine constant; label handled in UI


class TestRegistryCoverage:
    def test_all_registered_strategies_build(self):
        for sid in REGISTRY:
            s = build(sid)
            assert s.name and s.description

    def test_new_ids_present(self):
        for sid in ("draw-value-v1", "home-edge-v1", "form-value-v1",
                    "darts-elo-v1", "elo-favourite-3way-v1"):
            assert sid in REGISTRY
