"""Period-row schema rules (docs/HOCKEY-SCHEMA-AUDIT.md).

Hockey rows on OpenLigaDB are period rows wearing football-era
``resultTypeKind`` labels (1./2./3.Drittel -> HalfTime/HalfTime/
After90Minutes).  The goal list is the second representation of the same
final score and the two representations disagree in real committed data
(del/2024 matchID 76236: rows say 0-0, the goal list says 4-2).  These
tests pin the ``goals_vs_results`` anomaly rule on REAL fixture rows
(committed pilot + the 2026-09-22 DEL2/CHL probe slices) and the edge
cases that make the goal-list final the running-score MAXIMUM (goal rows
are community-entered out of chronological order), never the last row.
"""
from __future__ import annotations

import json
import os
from datetime import timedelta

import pytest

from northstar import models
from northstar.adapters import openligadb
from northstar.models import parse_utc

from conftest import FIXTURES, read_fixture


def parse(name: str, sport: str = "ice_hockey"):
    return {r["match_id"]: r for r in openligadb.parse_matchday(
        read_fixture(name), sport=sport)}


def by_id(rows, match_id):
    return rows[match_id]


class TestGoalListFinalIsTheRunningMaximum:
    def test_out_of_order_goal_rows_take_the_max_not_the_last_row(self):
        # Real entry-order defect (bl1/2024 matchID 72363): the last goal
        # ROW is (1,0); the running-score maximum (5,1) is the final.
        rows = parse("openligadb_bl1_2024.json", sport="football")
        r = by_id(rows, 72363)
        assert r["goal_list_final"] == (5, 1)
        assert not r["goals_vs_results"]
        assert r["home_goals"] == 5 and r["away_goals"] == 1

    def test_missing_goal_scores_means_unknown_not_disagreement(self):
        # The hand-assembled bl1 pilot slices carry no goal running
        # scores: the check is skipped silently, never flagged.
        rows = parse("openligadb_bl1_2024_sd1.json", sport="football")
        assert rows
        for r in rows.values():
            assert r["goal_list_final"] is None
            assert not r["goals_vs_results"]


class TestRealCommittedDefects:
    def test_del_76236_rows_disagree_with_goal_list(self):
        # The one committed rows-vs-goals defect: Adler Mannheim v
        # Nürnberg Ice Tigers, del/2024 matchID 76236.  Period rows read
        # 1.Drittel 0-0, 2.Drittel 4-2, 3.Drittel 0-0; the goal list runs
        # to 4-2.  The priority row (3.Drittel 0-0) is contradicted by
        # the goal list and must be quarantined, not graded.
        rows = parse("openligadb_del_2024.json")
        r = by_id(rows, 76236)
        assert r["goal_list_final"] == (4, 2)
        assert r["goals_vs_results"] is True
        assert r["inconsistency_reason"] == "goals_vs_results"
        assert r["kind_inconsistent"] is True
        # The priority row's score is kept (flag, never repair):
        assert (r["home_goals"], r["away_goals"]) == (0, 0)

    def test_clean_del_matches_are_not_flagged_by_the_goal_rule(self):
        rows = parse("openligadb_del_2024.json")
        flagged = [m for m, r in rows.items()
                   if r["inconsistency_reason"] == "goals_vs_results"]
        assert flagged == [76236]

    def test_extra_time_match_with_drawn_regulation_stays_clean(self):
        # del/2024 matchID 76234: regulation row 0-0 (a draw) + OT row
        # 3-4 agreeing with the goal list - correct hockey layering.
        rows = parse("openligadb_del_2024.json")
        r = by_id(rows, 76234)
        assert r["goal_list_final"] == (3, 4)
        assert r["goals_vs_results"] is False
        assert r["kind_inconsistent"] is False
        assert r["final_kind"] == models.RESULT_KIND_AFTER_EXTRA


class TestDel2ProbeSlice:
    """The 2026-09-22 DEL2 Hauptrunde matchday-1 probe (leagueId 5962)."""

    @pytest.fixture(scope="class")
    def rows(self):
        return parse("openligadb_del2_2026_sd1.json")

    def test_probe_has_the_seven_documented_matches(self, rows):
        assert sorted(rows) == [84079, 84080, 84081, 84082, 84083, 84084,
                                84085]

    def test_five_matches_disagree_rows_vs_goal_list(self, rows):
        flagged = sorted(m for m, r in rows.items()
                         if r["inconsistency_reason"] == "goals_vs_results")
        assert flagged == [84079, 84080, 84082, 84083, 84084]
        assert rows[84079]["goal_list_final"] == (2, 3)
        assert rows[84080]["goal_list_final"] == (4, 3)
        assert rows[84082]["goal_list_final"] == (3, 7)
        assert rows[84083]["goal_list_final"] == (1, 3)
        assert rows[84084]["goal_list_final"] == (4, 1)

    def test_one_match_has_impossible_ot_layering(self, rows):
        # 84085: 3.Drittel row 3-2 is decisive yet an Overtime row 3-4
        # exists (the goal list shows the 3-3 equaliser at 59').
        r = rows[84085]
        assert r["inconsistency_reason"] == "impossible_layering"
        assert r["goals_vs_results"] is False
        assert r["goal_list_final"] == (3, 4)
        assert r["final_kind"] == models.RESULT_KIND_AFTER_EXTRA

    def test_exactly_one_match_is_clean(self, rows):
        clean = sorted(m for m, r in rows.items() if not r["kind_inconsistent"])
        assert clean == [84081]
        assert rows[84081]["home_goals"] == 1
        assert rows[84081]["away_goals"] == 4


class TestChlProbeSlice:
    """The 2026-09-22 Champions Hockey League matchday-1 probe
    (leagueId 4951) - the clean control: 12/12 rows agree with the goal
    lists and both overtime games show drawn regulation rows."""

    @pytest.fixture(scope="class")
    def rows(self):
        return parse("openligadb_chl_2026_sd1.json")

    def test_twelve_matches_and_nothing_flagged(self, rows):
        assert len(rows) == 12
        assert all(not r["kind_inconsistent"] for r in rows.values())

    def test_overtime_games_have_drawn_regulation_rows(self, rows):
        for match_id in (81928, 81935):
            r = rows[match_id]
            assert r["final_kind"] == models.RESULT_KIND_AFTER_EXTRA
            assert r["goal_list_final"] == (r["home_goals"], r["away_goals"])

    def test_entry_order_robustness_on_real_rows(self, rows):
        # 81929: the two 17' goals are entered out of order ((0,2) before
        # (0,1)) - the maximum rule still resolves the 2-5 final.
        r = rows[81929]
        assert r["goal_list_final"] == (2, 5)
        assert r["home_goals"] == 2 and r["away_goals"] == 5


class TestSyntheticEdges:
    def _match(self, goals, results):
        return [{
            "matchID": 1, "leagueShortcut": "DEL2", "leagueSeason": 2026,
            "leagueName": "DEL2 Hauptrunde",
            "matchDateTime": "2026-09-18T19:30:00",
            "matchDateTimeUTC": "2026-09-18T17:30:00Z",
            "team1": {"teamId": 1, "teamName": "A"},
            "team2": {"teamId": 2, "teamName": "B"},
            "lastUpdateDateTime": "2026-09-18T22:45:34.03",
            "matchIsFinished": True,
            "matchResults": results, "goals": goals,
        }]

    def _rows(self, goals, results):
        return openligadb.parse_matchday(
            json.dumps(self._match(goals, results)), sport="ice_hockey")[0]

    def test_empty_goal_list_is_skipped(self):
        r = self._rows([], [{"resultTypeKind": "After90Minutes",
                             "pointsTeam1": 2, "pointsTeam2": 1}])
        assert r["goal_list_final"] is None
        assert r["goals_vs_results"] is False

    def test_goal_rows_without_running_scores_are_skipped(self):
        r = self._rows([{"goalID": 1, "matchMinute": 5}],
                       [{"resultTypeKind": "After90Minutes",
                         "pointsTeam1": 2, "pointsTeam2": 1}])
        assert r["goal_list_final"] is None
        assert r["goals_vs_results"] is False

    def test_agreeing_final_is_not_flagged(self):
        r = self._rows([{"goalID": 1, "scoreTeam1": 1, "scoreTeam2": 0},
                        {"goalID": 2, "scoreTeam1": 2, "scoreTeam2": 1}],
                       [{"resultTypeKind": "After90Minutes",
                         "pointsTeam1": 2, "pointsTeam2": 1}])
        assert r["goal_list_final"] == (2, 1)
        assert r["goals_vs_results"] is False

    def test_disagreement_keeps_the_row_score_and_flags(self):
        r = self._rows([{"goalID": 1, "scoreTeam1": 1, "scoreTeam2": 0},
                        {"goalID": 2, "scoreTeam1": 2, "scoreTeam2": 1}],
                       [{"resultTypeKind": "After90Minutes",
                         "pointsTeam1": 0, "pointsTeam2": 0}])
        assert r["goals_vs_results"] is True
        assert (r["home_goals"], r["away_goals"]) == (0, 0)


class TestIngestQuarantines:
    def test_ingest_flags_the_anomaly_and_keeps_the_row_score(self, store):
        payload = read_fixture("openligadb_del_2024.json")
        matches = json.loads(payload)
        one = json.dumps([m for m in matches if m["matchID"] == 76236])
        stats = openligadb.ingest_matchday(store, one, sport="ice_hockey")
        store.commit()
        assert stats["anomalies"] >= 1
        flags = [a for a in store.anomalies(status="open")
                 if a["kind"] == models.ANOMALY_RESULT_KIND_INCONSISTENT]
        assert len(flags) == 1
        assert "4-2" in flags[0]["detail"] and "goal list" in flags[0]["detail"]
        results = store.results(stats["event_ids"][0])
        assert (results[0]["home_goals"], results[0]["away_goals"]) == (0, 0)

    def test_duplicate_conflict_keeps_priority_but_carries_goal_evidence(
            self, store):
        # pl/2026 matchID 86559: duplicate After90 rows AND a goal list
        # that contradicts the kept row - the reason stays
        # duplicate_conflict (most specific pattern) but the goal-list
        # evidence is appended to the detail.
        with open(os.path.join(FIXTURES, "current",
                               "openligadb_pl_2026.json"),
                  encoding="utf-8") as fh:
            payload = fh.read()
        matches = json.loads(payload)
        one = json.dumps([m for m in matches if m["matchID"] == 86559])
        openligadb.ingest_matchday(store, one, sport="football")
        store.commit()
        flags = [a for a in store.anomalies(status="open")
                 if a["kind"] == models.ANOMALY_RESULT_KIND_INCONSISTENT]
        assert len(flags) == 1
        assert "conflicting scores" in flags[0]["detail"]
        assert "goal list's running-score maximum 1-1" in flags[0]["detail"]

    def test_retrieved_at_utc_is_converted_from_german_local_time(
            self, store):
        # lastUpdateDateTime 2025-04-07T21:30:19.807 is CEST: the stored
        # retrieval instant must be 19:30:19Z, not the UTC-as-written
        # 21:30 (docs/HOCKEY-SCHEMA-AUDIT.md, STATUS limitation #11).
        payload = read_fixture("openligadb_del_2024.json")
        matches = json.loads(payload)
        one = json.dumps([m for m in matches if m["matchID"] == 76100])
        stats = openligadb.ingest_matchday(store, one, sport="ice_hockey")
        store.commit()
        result = store.results(stats["event_ids"][0])[0]
        assert result["retrieved_at_utc"].endswith("2025-04-07T19:30:19Z")
        # Hockey availability is the conservative start+3h inference,
        # untouched by the stamp conversion:
        assert result["officially_final_at_utc"] == \
            models.fmt_utc(parse_utc("2024-09-19T17:30:00Z")
                           + timedelta(hours=3))
