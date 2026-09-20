"""Adapter tests against the *committed pilot fixtures* (real, verified data).

Requirement coverage: "build one official-result adapter" + the dual-source
cross-check that upgrades event identity to ``verified``. These tests load the
actual fixtures so a regression in parsing or reconciliation is caught.
"""
from __future__ import annotations

import json

import pytest

from northstar.adapters import football_data, olbg, openligadb
from northstar.db import Store
from northstar.timeutil import odds_collection_window_utc
from northstar.models import parse_utc

from conftest import RAW, read_fixture


OLDB_FILES = [
    "openligadb_bl1_2024_sd1.json",
    "openligadb_bl1_2024_sd10.json",
    "openligadb_bl1_2024_sd20.json",
]


@pytest.fixture(scope="module")
def pilot_store(tmp_path_factory):
    """A store with the full pilot ingested (OLDB + football-data CSV)."""
    s = Store(str(tmp_path_factory.mktemp("pilot") / "pilot.db"))
    for name in OLDB_FILES:
        openligadb.ingest_matchday(s, read_fixture(name))
    stats = football_data.ingest_csv_text(s, read_fixture(
        "football_data_d1_2425_pilot.csv"))
    s.commit()
    yield s, stats
    s.close()


class TestOpenLigaDb:
    def test_fixture_row_counts(self):
        total = 0
        for name in OLDB_FILES:
            payload = json.loads(read_fixture(name))
            assert len(payload) == 9, name
            total += len(payload)
        assert total == 27

    def test_parse_extracts_after90_result(self):
        matches = openligadb.parse_matchday(read_fixture(OLDB_FILES[0]))
        assert len(matches) == 9
        for m in matches:
            assert m["finished"] is True
            assert m["home_goals"] is not None
            assert m["away_goals"] is not None
            assert m["start_utc"].tzinfo is not None

    def test_ingest_creates_events_and_results(self, pilot_store):
        s, _ = pilot_store
        events = [e for e in s.events() if e["source_provider"] == "openligadb"]
        results = [r for r in s.results() if r["provider"] == "openligadb"]
        assert len(events) == 27
        assert len(results) == 27

    def test_event_id_is_stable(self):
        payload = json.loads(read_fixture(OLDB_FILES[0]))
        m = payload[0]
        eid1 = openligadb.event_id_for(m)
        eid2 = openligadb.event_id_for(m)
        assert eid1 == eid2
        assert eid1.startswith("ev-")


class TestFootballDataCrossCheck:
    def test_rows_parsed(self, pilot_store):
        s, stats = pilot_store
        assert stats["rows"] == 27

    def test_dual_source_agreement_27_of_27(self, pilot_store):
        """The core verification claim: every pilot FT result agrees across
        the two independent sources."""
        s, stats = pilot_store
        assert stats["cross_checked"] == 27
        assert stats["cross_checked_agree"] == 27

    def test_events_upgraded_to_verified(self, pilot_store):
        s, _ = pilot_store
        events = [e for e in s.events() if e["source_provider"] == "openligadb"]
        assert all(e["identity_confidence"] == "verified" for e in events)

    def test_all_five_provider_snapshots_present(self, pilot_store):
        """27 matches x 3 selections x 5 providers = 405 snapshots (Pinnacle
        excluded per the source's 2025-07-23 notice)."""
        s, stats = pilot_store
        assert stats["odds_snapshots"] == 405
        by_provider = {}
        for snap in s.odds_snapshots():
            by_provider[snap["provider"]] = by_provider.get(
                snap["provider"], 0) + 1
        for p in ("b365", "betfair", "williamhill", "market_avg",
                  "betfair_exchange"):
            assert by_provider.get(p) == 81, p
        # Pinnacle must be absent (source notice: unreliable, excluded)
        assert "pinacle" not in by_provider
        assert "pinnacle" not in by_provider

    def test_snapshots_are_pre_start(self, pilot_store):
        s, _ = pilot_store
        for e in s.events():
            if e["source_provider"] != "openligadb":
                continue
            start = parse_utc(e["scheduled_start_utc"])
            for snap in s.odds_snapshots(e["event_id"]):
                assert parse_utc(snap["observed_at_utc"]) < start
            assert all(snap["timestamp_precision"] == "window_close_inferred"
                       for snap in s.odds_snapshots(e["event_id"]))

    def test_unmatched_row_is_flagged(self, store):
        """A CSV row with no matching stored event must be flagged, not
        silently dropped."""
        from northstar.adapters.football_data import parse_csv_text
        rows = parse_csv_text(read_fixture("football_data_d1_2425_pilot.csv"))
        # fabricate a row for a team that is not in the store
        fake = dict(rows[0])
        fake["raw"] = dict(rows[0]["raw"], HomeTeam="Ghost FC",
                           AwayTeam="Phantom FC")
        fake["home"], fake["away"] = "Ghost FC", "Phantom FC"
        found = football_data._find_event(store, fake)
        assert "anomaly" in found
        assert found["anomaly"] == "EVENT_UNMATCHED"


class TestHockeyFinalResult:
    """Hockey has no 'regulation' settlement: a finished match decided in
    extra time must carry the final score, not the regulation draw."""

    @staticmethod
    def _payload(kind, points, finished=True):
        return json.dumps([{
            "matchID": 1001, "leagueShortcut": "del", "leagueSeason": 2024,
            "leagueName": "DEL", "matchDateTimeUTC": "2024-10-04T16:30:00Z",
            "group": {"groupOrderID": 1, "groupName": "Spieltag 1"},
            "team1": {"teamId": 1, "teamName": "Team A"},
            "team2": {"teamId": 2, "teamName": "Team B"},
            "matchIsFinished": finished,
            "matchResults": [{"resultTypeKind": "HalfTime",
                              "pointsTeam1": 1, "pointsTeam2": 1},
                             {"resultTypeKind": kind,
                              "pointsTeam1": points[0],
                              "pointsTeam2": points[1]}],
            "lastUpdateDateTime": "2024-10-04T18:45:00Z",
        }])

    def test_extra_time_result_wins_over_regulation_draw(self):
        text = self._payload("After90Minutes", (2, 2))
        # add an AfterExtraTime result to the same match
        payload = json.loads(text)
        payload[0]["matchResults"].append(
            {"resultTypeKind": "AfterExtraTime", "pointsTeam1": 2,
             "pointsTeam2": 3})
        matches = openligadb.parse_matchday(
            json.dumps(payload), sport="ice_hockey")
        assert matches[0]["home_goals"] == 2
        assert matches[0]["away_goals"] == 3
        assert matches[0]["final_kind"] == "AfterExtraTime"

    def test_football_ignores_extra_time(self):
        """Football settles on 90 minutes even if extra time is recorded
        (cups): the After90 result is the full-time result."""
        payload = json.loads(self._payload("After90Minutes", (1, 1)))
        payload[0]["leagueShortcut"] = "bl1"
        payload[0]["matchResults"].append(
            {"resultTypeKind": "AfterExtraTime", "pointsTeam1": 1,
             "pointsTeam2": 2})
        matches = openligadb.parse_matchday(
            json.dumps(payload), sport="football")
        assert (matches[0]["home_goals"], matches[0]["away_goals"]) == (1, 1)
        assert matches[0]["final_kind"] == "After90Minutes"

    def test_penalties_result_wins_for_hockey(self):
        payload = json.loads(self._payload("After90Minutes", (2, 2)))
        payload[0]["matchResults"].extend([
            {"resultTypeKind": "AfterExtraTime", "pointsTeam1": 2,
             "pointsTeam2": 2},
            {"resultTypeKind": "AfterPenalties", "pointsTeam1": 4,
             "pointsTeam2": 3},
        ])
        matches = openligadb.parse_matchday(
            json.dumps(payload), sport="ice_hockey")
        assert (matches[0]["home_goals"], matches[0]["away_goals"]) == (4, 3)
        assert matches[0]["final_kind"] == "AfterPenalties"

    def test_ingest_stores_sport_and_kind(self, store):
        payload = json.loads(self._payload("After90Minutes", (1, 1)))
        payload[0]["matchResults"].append(
            {"resultTypeKind": "AfterExtraTime", "pointsTeam1": 1,
             "pointsTeam2": 2})
        openligadb.ingest_matchday(store, json.dumps(payload),
                                   sport="ice_hockey")
        events = store.events()
        assert len(events) == 1
        assert events[0]["sport"] == "ice_hockey"
        results = store.results()
        assert len(results) == 1
        assert results[0]["result_type_kind"] == "AfterExtraTime"
        assert (results[0]["home_goals"], results[0]["away_goals"]) == (1, 2)


class TestOlbGParse:
    def test_index_snapshot_parses_12_cards(self):
        path = RAW + "/olbg_betting_tips_index_2026-09-19.md"
        cards = olbg.parse_index_snapshot(path)
        assert len(cards) == 12
        for c in cards:
            assert c["event_name"]
            assert c["selection"]
            assert c["url"].startswith("https://www.olbg.com/betting-tips/")
            assert c["source_event_id"]
            assert c["sport"] in {
                "Football", "Rugby_Union", "Boxing", "Darts",
                "Horse_Racing", "Baseball", "American_Football",
                "Motor_Racing", "Greyhounds"}

    def test_consensus_counts_present(self):
        path = RAW + "/olbg_betting_tips_index_2026-09-19.md"
        cards = olbg.parse_index_snapshot(path)
        with_consensus = [c for c in cards if c["consensus_wins"] is not None]
        assert len(with_consensus) >= 10
        for c in with_consensus:
            assert 0 <= c["consensus_wins"] <= c["consensus_total"]

    def test_time_labels_are_parsable(self):
        path = RAW + "/olbg_betting_tips_index_2026-09-19.md"
        cards = olbg.parse_index_snapshot(path)
        parsed = [c for c in cards
                  if olbg._parse_olbg_time_label(
                      c["time_label"], parse_utc("2026-09-19T10:00:00Z"))]
        # The pilot capture: every card carries Today/Tomorrow HH:MM
        assert len(parsed) == len(cards)

    def test_replay_uses_snapshot_header_for_relative_dates(self):
        path = RAW + "/olbg_betting_tips_index_2026-09-19.md"
        captured = olbg._captured_at_from_header(path)
        assert captured == parse_utc("2026-09-19T00:00:00Z")
        card = next(c for c in olbg.parse_index_snapshot(path)
                     if c["time_label"].startswith("Today"))
        start = olbg._parse_olbg_time_label(card["time_label"], captured)
        assert start.date().isoformat() == "2026-09-19"

    def test_event_snapshot_parses_consensus_table(self):
        path = RAW + "/olbg_event_mancity_sunderland_2026-09-19.md"
        parsed = olbg.parse_event_snapshot(path)
        assert parsed["event_name"] == "Man City v Sunderland"
        assert len(parsed["consensus"]) >= 1
        for row in parsed["consensus"]:
            assert row["selection"]
            assert 0 <= row["wins"] <= row["total"]

    def test_auto_fetch_is_policy_blocked(self):
        from northstar.policy import PolicyError
        with pytest.raises(PolicyError):
            olbg.auto_fetch("https://www.olbg.com/betting-tips")

    def test_footballdata_auto_mode_blocked(self):
        """football-data permits manual import but NOT automated retrieval."""
        from northstar.policy import (MODE_AUTO_API, PolicyError, get_policy)
        with pytest.raises(PolicyError):
            get_policy("football_data").assert_permitted(MODE_AUTO_API)


class TestOddsWindowInference:
    def test_weekend_fixture_closes_friday(self):
        # Saturday 14:30 UK kickoff (BST) -> Friday 17:00 UK close
        kickoff = parse_utc("2024-08-24T13:30:00Z")  # = 14:30 BST
        window = odds_collection_window_utc(kickoff)
        assert window == parse_utc("2024-08-23T16:00:00Z")  # 17:00 BST

    def test_midweek_fixture_closes_tuesday(self):
        # Thursday 19:30 UK kickoff (GMT) -> Tuesday 13:00 UK close
        kickoff = parse_utc("2024-11-07T19:30:00Z")
        window = odds_collection_window_utc(kickoff)
        assert window == parse_utc("2024-11-05T13:00:00Z")

    def test_window_always_before_kickoff(self):
        for kickoff in (
            parse_utc("2024-08-23T18:30:00Z"),  # Fri 19:30 BST
            parse_utc("2024-08-24T13:30:00Z"),  # Sat 14:30 BST
            parse_utc("2024-11-08T14:30:00Z"),  # Fri 14:30 GMT
            parse_utc("2024-11-09T14:30:00Z"),  # Sat 14:30 GMT
            parse_utc("2025-02-01T14:30:00Z"),  # Sat 14:30 GMT
        ):
            window = odds_collection_window_utc(kickoff)
            assert window < kickoff, kickoff.isoformat()
