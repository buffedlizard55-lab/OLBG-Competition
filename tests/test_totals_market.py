"""Over/under 2.5 market: settlement rule, market gate, strategies.

The second market on the verified football pilot.  Every branch of the
rule set is pinned here so a settlement change cannot slip in silently.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from northstar import models
from northstar.models import MARKET_TOTALS_2_5, MARKET_MATCH_WINNER_3WAY
from northstar.settlement import (MARKET_RULES, match_outcome_totals,
                                  settle_tip)
from northstar.strategies import (FOOTBALL_STRATEGIES, REGISTRY, build)
from northstar.strategies.totals import (LEAGUE_PRIOR_AWAY,
                                         LEAGUE_PRIOR_HOME, expected_goals,
                                         poisson_cdf, totals_fair)

from conftest import mk_event, mk_result, mk_tip


class TestTotalsRule:
    @pytest.mark.parametrize("hg,ag,sel,exp", [
        (2, 1, "over", "won"), (2, 1, "under", "lost"),
        (1, 1, "over", "lost"), (1, 1, "under", "won"),
        (0, 0, "under", "won"), (5, 0, "over", "won"),
        (0, 3, "over", "won"), (2, 0, "under", "won"),
    ])
    def test_grading(self, hg, ag, sel, exp):
        assert match_outcome_totals(sel, hg, ag) == exp

    def test_unknown_selection_rejected(self):
        with pytest.raises(ValueError):
            match_outcome_totals("home", 2, 1)

    @pytest.mark.parametrize("hg,ag", [(-1, 0), (1.5, 0), (True, 0),
                                       (None, 1), ("2", 1)])
    def test_invalid_score_rejected(self, hg, ag):
        with pytest.raises(ValueError):
            match_outcome_totals("over", hg, ag)

    def test_integer_line_refused_no_guessed_push_rule(self):
        with pytest.raises(ValueError):
            match_outcome_totals("over", 2, 1, line=3.0)

    def test_rule_table(self):
        assert set(MARKET_RULES) == {MARKET_MATCH_WINNER_3WAY,
                                     MARKET_TOTALS_2_5}
        assert MARKET_RULES[MARKET_TOTALS_2_5][0] == ("over", "under")


class TestTotalsSettlement:
    def test_over_tip_settles_won(self, store):
        mk_event(store)
        mk_tip(store, market=MARKET_TOTALS_2_5, selection_key="over",
               odds=1.9, stake=1.0)
        mk_result(store, home_goals=2, away_goals=1)
        out = settle_tip(store, "tip-t1")
        assert out["action"] == "settled"
        assert out["gates"]["market"] == "pass"
        s = store.latest_settlement("tip-t1")
        assert s["outcome"] == "won"
        assert s["pnl_units"] == pytest.approx(0.9)
        assert s["rule_version"] == models.SETTLEMENT_RULE_VERSION

    def test_under_tip_settles_lost(self, store):
        mk_event(store)
        mk_tip(store, market=MARKET_TOTALS_2_5, selection_key="under",
               odds=2.1)
        mk_result(store, home_goals=2, away_goals=1)
        settle_tip(store, "tip-t1")
        s = store.latest_settlement("tip-t1")
        assert s["outcome"] == "lost"
        assert s["pnl_units"] == pytest.approx(-1.0)

    def test_extra_time_result_kind_blocks_totals(self, store):
        """O/U 2.5 is a 90-minute market: an AfterExtraTime final must not
        be graded (blocked, not lost)."""
        from northstar.models import Result, parse_utc, utcnow, stable_id
        from conftest import FINAL_AT
        mk_event(store)
        mk_tip(store, market=MARKET_TOTALS_2_5, selection_key="over",
               odds=1.9)
        store.add_result(Result(
            result_id=stable_id("res", "ev-t1", "openligadb", 2, 1, "aet"),
            event_id="ev-t1", provider="openligadb",
            retrieved_at_utc=utcnow(), source_url="https://example.org/r",
            raw_payload_hash="cafe", final_status="finished",
            officially_final_at_utc=parse_utc(FINAL_AT),
            home_goals=2, away_goals=1,
            result_type_kind=models.RESULT_KIND_AFTER_EXTRA, version="v1"))
        store.commit()
        out = settle_tip(store, "tip-t1")
        assert out["action"] == "blocked"
        assert "90-minute" in out["gates"]["arithmetic"]
        assert store.latest_settlement("tip-t1") is None
        # the same score as a 90-minute row settles normally
        mk_tip(store, tip_id="tip-t2", market=MARKET_MATCH_WINNER_3WAY,
               selection_key="home", odds=1.9)
        assert settle_tip(store, "tip-t2")["action"] == "settled"

    def test_wrong_selection_for_market_is_blocked(self, store):
        mk_event(store)
        mk_tip(store, market=MARKET_TOTALS_2_5, selection_key="home")
        mk_result(store)
        out = settle_tip(store, "tip-t1")
        assert out["gates"]["market"].startswith("fail")
        assert out["action"] != "settled"
        assert store.latest_settlement("tip-t1") is None

    def test_unknown_market_still_blocked(self, store):
        mk_event(store)
        mk_tip(store, market="asian_handicap", selection_key="home")
        mk_result(store)
        out = settle_tip(store, "tip-t1")
        assert out["gates"]["market"].startswith("fail")
        assert store.latest_settlement("tip-t1") is None


class TestPoissonModel:
    def test_poisson_cdf_matches_closed_form(self):
        import math
        lam = 2.7
        exp = math.exp(-lam) * (1 + lam + lam ** 2 / 2)
        assert poisson_cdf(2, lam) == pytest.approx(exp)
        assert poisson_cdf(0, 0.0) == 1.0

    def test_totals_fair_removes_margin(self):
        f = totals_fair({"over": 1.9, "under": 1.9})
        assert f == pytest.approx({"over": 0.5, "under": 0.5})
        assert totals_fair({"over": 1.9, "under": None}) is None
        assert totals_fair({"over": 1.0, "under": 1.9}) is None

    def test_cold_start_uses_stated_priors_and_neutral_multipliers(self):
        from northstar.backtest import TimeBoundedStore
        tbs = TimeBoundedStore()
        at = datetime(2026, 1, 1, tzinfo=timezone.utc)
        xg = expected_goals(tbs, "A", "B", at)
        assert xg["league_rates"]["home"] == LEAGUE_PRIOR_HOME
        assert xg["league_rates"]["away"] == LEAGUE_PRIOR_AWAY
        assert xg["team_multipliers"]["home"]["attack"] == 1.0
        assert xg["lambda_home"] == pytest.approx(LEAGUE_PRIOR_HOME)
        p = xg["model_prob"]
        assert p["over"] + p["under"] == pytest.approx(1.0)
        # lambda 2.9 -> P(<=2) = e^-2.9 (1 + 2.9 + 4.205) ~ 0.4460
        assert p["under"] == pytest.approx(0.4460, abs=1e-3)

    def test_multipliers_move_with_released_goals_only(self):
        from northstar.backtest import TimeBoundedStore
        tbs = TimeBoundedStore()
        ev = {"event_id": "e1", "home_team": "A", "away_team": "B",
              "scheduled_start_utc": "2026-01-01T15:00:00Z"}
        rel = datetime(2026, 1, 1, 17, tzinfo=timezone.utc)
        tbs.add_result(ev, 5, 0, rel)
        before = expected_goals(tbs, "A", "B",
                                datetime(2026, 1, 1, 16, tzinfo=timezone.utc))
        after = expected_goals(tbs, "A", "B",
                               datetime(2026, 1, 2, tzinfo=timezone.utc))
        assert before["team_multipliers"]["home"]["matches"] == 0
        assert after["team_multipliers"]["home"]["matches"] == 1
        assert after["team_multipliers"]["home"]["attack"] > 1.0
        assert after["team_multipliers"]["away"]["defence"] > 1.0
        assert after["lambda_home"] > before["lambda_home"]


class TestTotalsStrategies:
    def test_registered_and_market_tagged(self):
        for sid in ("poisson-totals-value-v1", "market-totals-favourite-v1"):
            assert sid in REGISTRY and sid in FOOTBALL_STRATEGIES
            st = build(sid)
            assert st.market == MARKET_TOTALS_2_5
            assert st.sport == "football"

    def test_no_price_means_no_bet(self):
        from northstar.backtest import TimeBoundedStore
        ev = {"event_id": "e1", "home_team": "A", "away_team": "B",
              "scheduled_start_utc": "2026-01-01T15:00:00Z"}
        for sid in ("poisson-totals-value-v1", "market-totals-favourite-v1"):
            d = build(sid).predict(ev, TimeBoundedStore(),
                                   datetime(2026, 1, 1, 15,
                                            tzinfo=timezone.utc))
            assert d["selection_key"] == "none"

    def test_favourite_baseline_picks_market_side(self):
        from northstar.backtest import TimeBoundedStore
        ev = {"event_id": "e1", "home_team": "A", "away_team": "B",
              "scheduled_start_utc": "2026-01-01T15:00:00Z"}
        at = datetime(2026, 1, 1, 12, tzinfo=timezone.utc)
        d = build("market-totals-favourite-v1").predict(
            ev, TimeBoundedStore(), datetime(2026, 1, 1, 15,
                                             tzinfo=timezone.utc),
            market_odds={"over": 1.5, "under": 2.6}, odds_observed_at=at)
        assert d["selection_key"] == "over"
        assert d["cutoff_utc"] == at

    def test_value_desk_respects_threshold(self):
        from northstar.backtest import TimeBoundedStore
        ev = {"event_id": "e1", "home_team": "A", "away_team": "B",
              "scheduled_start_utc": "2026-01-01T15:00:00Z"}
        at = datetime(2026, 1, 1, 12, tzinfo=timezone.utc)
        start = datetime(2026, 1, 1, 15, tzinfo=timezone.utc)
        st = build("poisson-totals-value-v1")
        # cold model: P(over) ~ 0.554. Fair over at 1.9/1.9 = 0.50 -> edge
        # 0.054 >= 0.03 -> over.
        d = st.predict(ev, TimeBoundedStore(), start,
                       market_odds={"over": 1.9, "under": 1.9},
                       odds_observed_at=at)
        assert d["selection_key"] == "over"
        # market already at 0.56 over -> no edge either side
        d = st.predict(ev, TimeBoundedStore(), start,
                       market_odds={"over": 1.70, "under": 2.15},
                       odds_observed_at=at)
        assert d["selection_key"] == "none"
        assert d["model"]["reason"] == "edge below threshold"


class TestTotalsPredictionCopy:
    """Tipster copy for O/U 2.5 trails must be rendered from the Poisson
    trail, never from the 1X2 template (regression: renderer crashed on
    ``ratings: None`` when a totals bet reached the picker)."""

    def _event(self):
        return {"home_team": "Eintracht Frankfurt", "away_team": "Wolfsburg",
                "scheduled_start_utc": "2025-02-02T14:30:00Z"}

    def test_totals_trail_renders_over_under_sentences(self):
        from northstar.predictor import render_prediction
        out = render_prediction(
            self._event(),
            model={"ratings": None, "lambda_home": 1.9, "lambda_away": 1.3,
                   "model_prob": {"over": 0.66, "under": 0.34}},
            fair={"over": 0.62, "under": 0.38},
            edge={"over": 0.04},
            selection="over", odds=1.52,
            source_links=["https://api.openligadb.de/getmatchdata/bl1/2024/20"])
        assert out["evidence_ok"] is True
        assert "OVER 2.5 GOALS" in out["headline"]
        assert "66%" in out["body"] and "34%" in out["body"]
        assert "62%" in out["body"]
        assert "1.52" in out["body"]

    def test_renderer_refuses_partial_totals_trail(self):
        from northstar.predictor import render_prediction
        out = render_prediction(
            self._event(),
            model={"ratings": None, "model_prob": {"over": 0.6}},
            fair=None, edge=None, selection="over", odds=1.5)
        assert out["evidence_ok"] is False
        assert "No call" in out["body"]
