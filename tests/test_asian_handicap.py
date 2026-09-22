"""Asian-handicap market: settlement rules, adapter line storage, the two
strategies, and walk-forward engine integration.

Settlement convention (verified against the football-data.co.uk notes.txt
key, re-fetched 2026-09-22): "AHh = Market size of handicap (home team)" -
a negative line handicaps the HOME side, and the away side's handicap is
the mirror (-line). Both sides of a quote push on exactly the same scores.
"""
from __future__ import annotations

import pytest

from northstar import models
from northstar.leaderboard import entrant_metrics
from northstar.models import parse_utc
from northstar.settlement import (
    MARKET_RULES, asian_handicap_components, decimal_pnl,
    match_outcome_asian_handicap, settle_tip,
)
from northstar.strategies import (
    FOOTBALL_STRATEGIES, REGISTRY, build,
)
from northstar.strategies.asian import (
    AsianHandicapFavourite, AsianHandicapValue, ah_fair, ah_probabilities,
    expected_value, line_from_market, margin_distribution,
    side_probabilities,
)
from northstar.timeutil import odds_collection_window_utc

from conftest import FINAL_AT, PUBLISHED, START, mk_event, mk_result, mk_tip


# ---------------------------------------------------------------- rules

class TestAsianHandicapComponents:
    def test_whole_and_half_lines_are_single_components(self):
        assert asian_handicap_components(-1) == [-1.0]
        assert asian_handicap_components(0) == [0.0]
        assert asian_handicap_components(-0.5) == [-0.5]
        assert asian_handicap_components(1.5) == [1.5]

    def test_quarter_lines_split_into_neighbours(self):
        assert asian_handicap_components(-0.75) == [-1.0, -0.5]
        assert asian_handicap_components(0.25) == [0.0, 0.5]
        assert asian_handicap_components(1.75) == [1.5, 2.0]

    @pytest.mark.parametrize("bad", [-0.8, 0.3, 1.1, None, "−1", float("nan")])
    def test_off_grid_lines_are_refused(self, bad):
        with pytest.raises(ValueError):
            asian_handicap_components(bad)


class TestAsianHandicapGrading:
    """Every settleable shape, home and away, whole/half/quarter lines."""

    @pytest.mark.parametrize("line,home_goals,away_goals,expected", [
        # integer line home -1
        (-1, 2, 1, "push"),      # wins by exactly the line
        (-1, 3, 1, "won"),
        (-1, 1, 1, "lost"),
        (-1, 1, 2, "lost"),
        # integer line home +1 (away is the favourite giving a goal)
        (1, 1, 2, "push"),       # away wins by exactly 1: home +1 level
        (1, 1, 1, "won"),        # draw: home +1 wins
        (1, 1, 0, "won"),
        (1, 0, 1, "push"),       # away wins by exactly 1
        # half line home -0.5 (no push possible)
        (-0.5, 1, 0, "won"),
        (-0.5, 1, 1, "lost"),
        (-0.5, 0, 1, "lost"),
        # quarter line home -0.75 = (-1.0, -0.5) half stakes
        (-0.75, 2, 1, "half_won"),   # margin 1: -1.0 pushes, -0.5 wins
        (-0.75, 3, 1, "won"),        # margin 2: both win
        (-0.75, 1, 1, "lost"),       # margin 0: both lose
        # quarter line home +0.25 = (0.0, +0.5)
        (0.25, 1, 1, "half_won"),    # 0.0 pushes, +0.5 wins
        # level ball (0) is Draw No Bet
        (0, 1, 1, "push"),
        (0, 2, 2, "push"),
        (0, 0, 0, "push"),
    ])
    def test_home_side_matrix(self, line, home_goals, away_goals, expected):
        assert match_outcome_asian_handicap(
            "home", home_goals, away_goals, line) == expected

    def test_quarter_level_ball_correction(self):
        # margin -1 with line +0.25: 0.0 component -> -1 (lose);
        # +0.5 component -> -0.5 (lose) => both lose, not half_lost
        assert match_outcome_asian_handicap(
            "home", 0, 1, 0.25) == "lost"

    @pytest.mark.parametrize("line,home_goals,away_goals,expected", [
        # line is on the HOME team; away's handicap is the mirror
        (-1, 2, 1, "push"),      # home -1 pushes => away +1 pushes too
        (-1, 1, 1, "won"),       # away +1 wins on a draw
        (-1, 3, 1, "lost"),      # home wins by 2
        (-0.75, 2, 1, "half_lost"),  # away +0.75: (+1.0 pushes... mirror:
                                     # home -0.75 half_won for home)
        (-0.5, 1, 0, "lost"),
        (1, 0, 1, "push"),
    ])
    def test_away_side_mirror(self, line, home_goals, away_goals, expected):
        assert match_outcome_asian_handicap(
            "away", home_goals, away_goals, line) == expected

    def test_home_and_away_push_on_same_scores(self):
        # the defining symmetry of a two-way handicap quote
        for line in (-1, -0.75, 0, 0.25, 1):
            for hg, ag in ((2, 1), (1, 1), (3, 0), (0, 2)):
                h = match_outcome_asian_handicap("home", hg, ag, line)
                a = match_outcome_asian_handicap("away", hg, ag, line)
                assert (h == "push") == (a == "push"), (line, hg, ag)
                # and a half-stake outcome on one side mirrors the other
                mirror = {"won": "lost", "half_won": "half_lost",
                          "push": "push", "half_lost": "half_won",
                          "lost": "won"}
                assert a == mirror[h], (line, hg, ag)

    def test_invalid_inputs(self):
        with pytest.raises(ValueError):
            match_outcome_asian_handicap("draw", 2, 1, -1)
        with pytest.raises(ValueError):
            match_outcome_asian_handicap("over", 2, 1, -1)
        with pytest.raises(ValueError):
            match_outcome_asian_handicap("home", True, 1, -1)
        with pytest.raises(ValueError):
            match_outcome_asian_handicap("home", -1, 1, -1)
        with pytest.raises(ValueError):
            match_outcome_asian_handicap("home", 2, 1, None)
        with pytest.raises(ValueError):
            match_outcome_asian_handicap("home", 2, 1, -0.8)


class TestAsianHandicapArithmetic:
    def test_half_outcome_pnl(self):
        assert decimal_pnl(1.0, 2.0, "half_won") == 0.5
        assert decimal_pnl(2.0, 2.0, "half_won") == 1.0
        assert decimal_pnl(1.0, 2.0, "half_lost") == -0.5
        assert decimal_pnl(1.0, 2.0, "push") == 0.0
        assert decimal_pnl(1.0, 2.0, "won") == 1.0
        assert decimal_pnl(1.0, 2.0, "lost") == -1.0

    def test_unknown_outcome_refused(self):
        with pytest.raises(ValueError):
            decimal_pnl(1.0, 2.0, "quarter_won")


# ------------------------------------------------------------ settlement

class TestAsianHandicapSettlement:
    def _settle(self, store, *, line, hg, ag, selection="home",
                tipster="ah-desk"):
        mk_event(store, event_id="ev-ah")
        mk_tip(store, tip_id="tip-ah", event_id="ev-ah",
               selection_key=selection, market=models.MARKET_ASIAN_HANDICAP,
               odds=1.95, tipster=tipster, line=line)
        mk_result(store, event_id="ev-ah", home_goals=hg, away_goals=ag)
        return settle_tip(store, "tip-ah")

    def test_push_refunds_and_never_counts_as_loss(self, store):
        out = self._settle(store, line=-1, hg=2, ag=1)
        assert out["action"] == "settled"
        s = store.latest_settlement("tip-ah")
        assert s["outcome"] == "push"
        assert s["pnl_units"] == 0.0
        m = entrant_metrics(store, "ah-desk")
        assert m["settled_bets"] == 0     # push excluded from counted bets
        assert m["voids"] == 1
        assert m["profit_units"] == 0.0

    def test_half_won_settles_half_profit(self, store):
        out = self._settle(store, line=-0.75, hg=2, ag=1)
        assert out["action"] == "settled"
        s = store.latest_settlement("tip-ah")
        assert s["outcome"] == "half_won"
        assert s["pnl_units"] == pytest.approx(0.5 * 1.0 * 0.95)

    def test_away_side_of_quarter_line_settles_won(self, store):
        out = self._settle(store, line=0.25, hg=1, ag=2, selection="away")
        # home +0.25 with hg 1 ag 2: margin -1: the 0.0 component loses,
        # the +0.5 component loses => home lost => away (mirror) won.
        assert out["action"] == "settled"
        s = store.latest_settlement("tip-ah")
        assert s["outcome"] == "won"

    def test_half_lost_direct(self, store):
        self._settle(store, line=-0.75, hg=2, ag=1,
                     selection="away", tipster="ah-desk-2")
        # home half_won => away half_lost
        s = store.latest_settlement("tip-ah")
        assert s["outcome"] == "half_lost"
        assert s["pnl_units"] == pytest.approx(-0.5)
        m = entrant_metrics(store, "ah-desk-2")
        assert m["wins"] == 0.0 and m["losses"] == 0.5
        assert m["profit_units"] == pytest.approx(-0.5)

    def test_missing_line_is_blocked_not_guessed(self, store):
        mk_event(store, event_id="ev-ah")
        mk_tip(store, tip_id="tip-ah", event_id="ev-ah",
               market=models.MARKET_ASIAN_HANDICAP, odds=1.95,
               line=None)
        mk_result(store, event_id="ev-ah", home_goals=2, away_goals=1)
        out = settle_tip(store, "tip-ah")
        assert out["action"] == "blocked"
        assert out["gates"]["market"].startswith("fail:")

    def test_off_grid_line_is_blocked(self, store):
        out = self._settle(store, line=-0.8, hg=2, ag=1)
        assert out["action"] == "blocked"
        assert "quarter" in out["gates"]["market"]

    def test_extra_time_result_is_refused(self, store):
        mk_event(store, event_id="ev-ah")
        mk_tip(store, tip_id="tip-ah", event_id="ev-ah",
               market=models.MARKET_ASIAN_HANDICAP, odds=1.95, line=-1)
        from northstar.models import Result, utcnow
        r = Result(
            result_id="res-aet", event_id="ev-ah", provider="openligadb",
            retrieved_at_utc=utcnow(), source_url=None,
            raw_payload_hash="x", final_status="finished",
            officially_final_at_utc=parse_utc(FINAL_AT),
            home_goals=3, away_goals=1,
            result_type_kind="AfterExtraTime")
        store.add_result(r)
        out = settle_tip(store, "tip-ah")
        assert out["action"] == "blocked"
        assert "90-minute" in out["gates"]["arithmetic"]

    def test_half_outcomes_weight_leaderboard_wl(self, store):
        mk_event(store, event_id="ev-ah")
        mk_tip(store, tip_id="tip-ah", event_id="ev-ah",
               market=models.MARKET_ASIAN_HANDICAP, odds=2.0,
               line=-0.75, tipster="w-desk")
        mk_result(store, event_id="ev-ah", home_goals=2, away_goals=1)
        out = settle_tip(store, "tip-ah")
        assert out["action"] == "settled"
        m = entrant_metrics(store, "w-desk")
        assert m["settled_bets"] == 1
        assert m["wins"] == 0.5 and m["losses"] == 0.0
        assert m["strike_rate"] == 0.5
        assert m["profit_units"] == pytest.approx(0.5)
        assert m["turnover_units"] == 1.0


# ------------------------------------------------------------ math model

class TestAsianHandicapModelMath:
    def test_margin_distribution_sums_to_one_and_is_symmetric_for_equal_rates(
            self):
        dist = margin_distribution(1.4, 1.4)
        assert sum(dist.values()) == pytest.approx(1.0, abs=1e-12)
        # symmetric rates => symmetric margin distribution
        for d, p in dist.items():
            assert dist.get(-d, 0.0) == pytest.approx(p, abs=1e-12)

    def test_margin_distribution_matches_known_poisson_values(self):
        # hand check: lam_h = lam_a -> P(D=0) = sum_k P(H=k)^2
        import math
        lam = 1.0
        p0 = math.exp(-2 * lam) * sum(lam ** (2 * k) /
                                       (math.factorial(k) ** 2)
                                       for k in range(30))
        dist = margin_distribution(lam, lam)
        assert dist[0] == pytest.approx(p0, rel=1e-9)

    def test_ah_probabilities_sum_and_push_structure(self):
        dist = margin_distribution(1.6, 1.3)
        probs = ah_probabilities(dist, -1.0)
        assert probs["win"] + probs["push"] + probs["lose"] == \
            pytest.approx(1.0, abs=1e-9)
        # integer line has a real push probability; half line has none
        half = ah_probabilities(dist, -0.5)
        assert half["push"] == 0.0
        # quarter line push is the average of its components' pushes
        q = ah_probabilities(dist, -0.75)
        expected_push = 0.5 * (ah_probabilities(dist, -1.0)["push"] + 0.0)
        assert q["push"] == pytest.approx(expected_push, abs=1e-12)

    def test_away_side_is_mirror_of_home(self):
        dist = margin_distribution(1.6, 1.3)
        for line in (-1.0, -0.75, 0.0, 0.25, 1.5):
            h = side_probabilities(dist, line, "home")
            a = side_probabilities(dist, line, "away")
            assert a["win"] == pytest.approx(h["lose"], abs=1e-12)
            assert a["lose"] == pytest.approx(h["win"], abs=1e-12)
            assert a["push"] == pytest.approx(h["push"], abs=1e-12)

    def test_expected_value_math(self):
        # 50/30/20 at 2.10: EV = .5*(2.1-1) - .2 = 0.35 (push pays 0)
        assert expected_value({"win": 0.5, "push": 0.3, "lose": 0.2}, 2.1) \
            == pytest.approx(0.35)

    def test_fair_margin_removal(self):
        fair = ah_fair({"home": 1.95, "away": 1.95})
        assert fair == {"home": 0.5, "away": 0.5}
        fair2 = ah_fair({"home": 2.0, "away": 2.0})
        assert fair2 == {"home": 0.5, "away": 0.5}
        assert ah_fair({"home": 1.0, "away": 2.0}) is None
        assert ah_fair({"home": None, "away": 2.0}) is None

    def test_line_from_market_validates_grid(self):
        assert line_from_market({"line": -0.75}) == -0.75
        assert line_from_market({"line": -1}) == -1.0
        assert line_from_market({"line": -0.8}) is None
        assert line_from_market({}) is None
        assert line_from_market(None) is None


# ------------------------------------------------------------ strategies

class TestAsianHandicapStrategies:
    def _fake_tbs(self):
        from northstar.backtest import TimeBoundedStore

        class DummyTBS(TimeBoundedStore):
            """releases are irrelevant here; the AH desks only call
            expected_goals -> released_matches/goal_record."""

            def released_matches(self, at):
                return []

            def goal_record(self, team, at):
                return []
        return DummyTBS()

    def test_value_desk_requires_odds_and_line(self):
        strat = build("ah-poisson-value-v1")
        assert strat.sport == "football"
        assert strat.market == models.MARKET_ASIAN_HANDICAP
        d = strat.predict({"home_team": "H", "away_team": "A"},
                          self._fake_tbs(), parse_utc(START),
                          market_odds=None, odds_observed_at=None)
        assert d["selection_key"] == "none"

    def test_value_desk_no_bet_without_line(self):
        strat = build("ah-poisson-value-v1")
        d = strat.predict({"home_team": "H", "away_team": "A"},
                          self._fake_tbs(), parse_utc(START),
                          market_odds={"home": 1.95, "away": 1.95},
                          odds_observed_at=parse_utc(PUBLISHED))
        assert d["selection_key"] == "none"
        assert "line" in (d["model"].get("reason") or "")

    def test_value_desk_full_trail_when_it_bets(self):
        # heavily skewed prices force a detectable model-vs-market edge
        strat = build("ah-poisson-value-v1")
        d = strat.predict({"home_team": "H", "away_team": "A"},
                          self._fake_tbs(), parse_utc(START),
                          market_odds={"home": 3.2, "away": 1.4,
                                       "line": -0.5},
                          odds_observed_at=parse_utc(PUBLISHED))
        m = d["model"]
        assert set(m["model_prob"]) == {"home", "away"}
        for side in ("home", "away"):
            assert m["model_prob"][side]["win"] + \
                m["model_prob"][side]["push"] + \
                m["model_prob"][side]["lose"] == pytest.approx(1.0, abs=1e-9)
        assert m["fair_prob"]["home"] + m["fair_prob"]["away"] == \
            pytest.approx(1.0, abs=1e-9)
        assert set(m["model_ev"]) == set(m["market_ev"]) == \
            set(m["edge_ev"]) == {"home", "away"}
        assert m["line"] == -0.5
        if d["selection_key"] != "none":
            assert d["line"] == -0.5
            assert d["cutoff_utc"] == parse_utc(PUBLISHED)

    def test_baseline_always_bets_the_favourite_side(self):
        strat = build("ah-market-favourite-v1")
        d = strat.predict({"home_team": "H", "away_team": "A"},
                          self._fake_tbs(), parse_utc(START),
                          market_odds={"home": 1.8, "away": 2.1,
                                       "line": -0.25},
                          odds_observed_at=parse_utc(PUBLISHED))
        assert d["selection_key"] == "home"   # lower price = fair favourite
        assert d["line"] == -0.25
        assert "H -0.25 AH" in d["selection_text"]
        d2 = strat.predict({"home_team": "H", "away_team": "A"},
                           self._fake_tbs(), parse_utc(START),
                           market_odds={"home": 2.2, "away": 1.75,
                                        "line": 0.5},
                           odds_observed_at=parse_utc(PUBLISHED))
        assert d2["selection_key"] == "away"
        assert "A -0.5 AH" in d2["selection_text"]  # away +0.5 home line

    def test_both_ah_strategies_in_football_family_and_registry(self):
        assert "ah-poisson-value-v1" in FOOTBALL_STRATEGIES
        assert "ah-market-favourite-v1" in FOOTBALL_STRATEGIES
        assert REGISTRY["ah-poisson-value-v1"] is AsianHandicapValue
        assert REGISTRY["ah-market-favourite-v1"] is AsianHandicapFavourite

    def test_market_rule_registered(self):
        assert models.MARKET_ASIAN_HANDICAP in MARKET_RULES
        assert MARKET_RULES[models.MARKET_ASIAN_HANDICAP][0] == \
            ("home", "away")


# --------------------------------------------------------- tipster copy

class TestAsianHandicapPredictionCopy:
    EVENT = {"home_team": "Home FC", "away_team": "Away FC"}

    def _model(self):
        return {
            "ratings": None, "lambda_home": 1.7, "lambda_away": 1.2,
            "line": -0.75,
            "model_prob": {
                "home": {"win": 0.48, "push": 0.11, "lose": 0.41},
                "away": {"win": 0.41, "push": 0.11, "lose": 0.48}},
            "fair_prob": {"home": 0.52, "away": 0.48},
            "edge_ev": {"home": 0.052, "away": -0.02},
        }

    def test_ah_trail_renders_line_sentences(self):
        from northstar.predictor import render_prediction
        out = render_prediction(
            self.EVENT, model=self._model(),
            fair=self._model()["fair_prob"],
            edge=self._model()["edge_ev"],
            selection="home", odds=1.95,
            source_links=["https://api.openligadb.de/"])
        assert out["evidence_ok"] is True
        assert "AH" in out["headline"] and "-0.75" in out["headline"]
        assert "48%" in out["body"] and "11%" in out["body"]  # win/push
        assert "52%" in out["body"]                            # fair side
        assert "expected-value" in out["body"]                 # EV edge
        assert "1.95" in out["body"]

    def test_away_selection_headline_mirrors_the_line(self):
        from northstar.predictor import render_prediction
        model = self._model()
        model["line"] = 1.25          # home +1.25 -> away plays -1.25
        model["edge_ev"] = {"home": -0.03, "away": 0.061}
        out = render_prediction(
            self.EVENT, model=model, fair=model["fair_prob"],
            edge=model["edge_ev"], selection="away", odds=1.9)
        assert out["evidence_ok"] is True
        assert "AWAY FC -1.25 AH" in out["headline"]
        assert "(line +1.25 on the home side)" in out["body"]

    def test_renderer_refuses_partial_ah_trail(self):
        from northstar.predictor import render_prediction
        model = self._model()
        model["model_prob"] = {"home": {"win": 0.5}}   # broken distribution
        out = render_prediction(self.EVENT, model=model, fair=None,
                                edge=None, selection="home", odds=1.9)
        assert out["evidence_ok"] is False
        assert "No call" in out["body"]


# ------------------------------------------------------- walk-forward run

class TestAsianHandicapWalkForward:
    def test_pilot_run_produces_line_carrying_settled_tips(self, pilot_store):
        from northstar.backtest import run_walk_forward
        s, _ = pilot_store
        football = [e for e in s.events()
                    if e["sport"] == "football"
                    and "/bl1/2024/" in (e.get("source_url") or "")
                    and e["status"] == "finished"]
        assert len(football) == 27
        report = run_walk_forward(s, football, build("ah-market-favourite-v1"),
                                  "ah-market-favourite-v1", label="pilot")
        assert not report["leak_violations"]
        assert report["bets"], "baseline must bet every priced event"
        # every settled tip carries its line and settles to a valid outcome
        for b in report["bets"]:
            tip = s.get_tip(next(t["tip_id"] for t in s.tips(
                tipster_id="ah-market-favourite-v1")
                if t["event_id"] == b["event_id"]))
            assert tip["market"] == models.MARKET_ASIAN_HANDICAP
            assert tip["line"] is not None
            assert float(tip["line"] * 4).is_integer()
            if b["outcome_action"] in ("settled", "already_settled"):
                st = s.latest_settlement(tip["tip_id"])
                assert st["outcome"] in ("won", "half_won", "push",
                                         "half_lost", "lost")
        # the run settles at least one push or half outcome on 27 matches
        outcomes = {s.latest_settlement(t["tip_id"])["outcome"]
                    for t in s.tips(tipster_id="ah-market-favourite-v1")
                    if s.latest_settlement(t["tip_id"])}
        assert outcomes & {"won", "lost", "push", "half_won", "half_lost"}

    def test_engine_withholds_conflicting_line_market_view(self, store):
        """Two AH snapshots at the same window with different lines: the
        market view must be withheld (None) - a desk never guesses which
        line it traded."""
        from northstar.backtest import run_walk_forward
        mk_event(store, event_id="ev-conf", start=START)
        mk_result(store, event_id="ev-conf", home_goals=2, away_goals=1)
        window = odds_collection_window_utc(parse_utc(START))
        for line in (-1.0, -0.5):
            for sel in ("home", "away"):
                from northstar.models import OddsSnapshot
                store.add_odds_snapshot(OddsSnapshot(
                    snapshot_id=models.stable_id(
                        "os", "ev-conf", "asian_handicap", "market_avg",
                        sel, str(line)),
                    event_id="ev-conf", observed_at_utc=window,
                    provider="market_avg",
                    market_key=models.MARKET_ASIAN_HANDICAP,
                    selection_key=sel, decimal_odds=1.95, line=line,
                    timestamp_precision="window_close_inferred"))

        class Probe:
            sport = "football"
            market = models.MARKET_ASIAN_HANDICAP
            odds_provider = "market_avg"
            name = "probe"
            description = ""

            def predict(self, event, tbs, start, market_odds=None,
                        odds_observed_at=None, as_of=None):
                self.seen = market_odds
                if market_odds and "line" in market_odds:
                    return {"cutoff_utc": odds_observed_at,
                            "selection_key": "home",
                            "selection_text": "home", "line":
                                market_odds["line"], "model": {}}
                return {"cutoff_utc": odds_observed_at,
                        "selection_key": "none", "model": {}}

            def ratings_after(self, event, hg, ag, tbs, final_at):
                return {}

        probe = Probe()
        report = run_walk_forward(store, [store.get_event("ev-conf")],
                                  probe, "probe", label="t")
        assert probe.seen is None      # conflicting lines -> view withheld
        assert not report["bets"]
        assert any("strategy passed" in s["reason"]
                   for s in report["skipped"])
