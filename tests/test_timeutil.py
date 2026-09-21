"""UK civil time + odds-window inference.

The football-data Time column is UK local; odds are batch-collected on a
documented Fri/Tue schedule. These tests pin the conversions the cross-check
relies on, including the clock-change-day guard.
"""
from __future__ import annotations

from datetime import date, time as dtime

import pytest

from northstar.models import parse_utc
from northstar.timeutil import (
    odds_collection_window_utc, uk_dst_end, uk_dst_start, uk_local_to_utc,
)


class TestDstBoundaries:
    def test_2024_boundaries(self):
        # last Sunday of March 2024 = 31/03; last Sunday of October = 27/10
        assert uk_dst_start(2024).date() == date(2024, 3, 31)
        assert uk_dst_end(2024).date() == date(2024, 10, 27)

    def test_2025_boundaries(self):
        assert uk_dst_start(2025).date() == date(2025, 3, 30)
        assert uk_dst_end(2025).date() == date(2025, 10, 26)


class TestUkLocalToUtc:
    def test_summer_bst(self):
        # 23/08/2024 19:30 UK (BST) == 18:30 UTC
        assert uk_local_to_utc(date(2024, 8, 23), dtime(19, 30)) == \
            parse_utc("2024-08-23T18:30:00Z")

    def test_winter_gmt(self):
        # 09/11/2024 14:30 UK (GMT) == 14:30 UTC
        assert uk_local_to_utc(date(2024, 11, 9), dtime(14, 30)) == \
            parse_utc("2024-11-09T14:30:00Z")

    def test_boundary_days_2024(self):
        # 30/03/2024 23:00 UK (GMT, before change) == 23:00 UTC
        assert uk_local_to_utc(date(2024, 3, 30), dtime(23, 0)) == \
            parse_utc("2024-03-30T23:00:00Z")
        # 01/04/2024 01:30 UK (BST, after change) == 00:30 UTC
        assert uk_local_to_utc(date(2024, 4, 1), dtime(1, 30)) == \
            parse_utc("2024-04-01T00:30:00Z")

    def test_clock_change_day_refused(self):
        # 31/03/2024: 01:00-02:00 local is ambiguous/nonexistent -> refuse
        with pytest.raises(ValueError):
            uk_local_to_utc(date(2024, 3, 31), dtime(1, 30))
        with pytest.raises(ValueError):
            uk_local_to_utc(date(2024, 10, 27), dtime(1, 30))

    def test_accepts_datetime_input(self):
        # passing a datetime uses its date part
        assert uk_local_to_utc(parse_utc("2024-11-09T00:00:00Z"),
                               dtime(14, 30)) == \
            parse_utc("2024-11-09T14:30:00Z")


class TestOddsWindow:
    def test_pilot_matchdays(self):
        """The three pilot matchdays' windows, per the source schedule:
        SD1 (Fri 23/08 19:30 UK) -> Fri 17:00 UK;
        SD10 (Thu 07/11 19:30 UK) -> Tue 05/11 13:00 UK;
        SD20 (Sat 01/02 14:30 UK) -> Fri 31/01 17:00 UK."""
        assert odds_collection_window_utc(
            parse_utc("2024-08-23T18:30:00Z")) == \
            parse_utc("2024-08-23T16:00:00Z")
        assert odds_collection_window_utc(
            parse_utc("2024-11-07T19:30:00Z")) == \
            parse_utc("2024-11-05T13:00:00Z")
        assert odds_collection_window_utc(
            parse_utc("2025-02-01T14:30:00Z")) == \
            parse_utc("2025-01-31T17:00:00Z")

    def test_early_friday_falls_back_to_tuesday(self):
        # Fri 14:30 UK kickoff: Friday 17:00 close is NOT before it, so use
        # the earlier same-week Tuesday 13:00 window.
        kickoff = parse_utc("2024-11-08T14:30:00Z")  # Fri 14:30 GMT
        window = odds_collection_window_utc(kickoff)
        assert window == parse_utc("2024-11-05T13:00:00Z")
        assert window < kickoff


class TestCentralEuropeanOffset:
    """OpenLigaDB local/UTC cross-check (verified on all committed rows)."""

    def test_offsets_around_2026_changes(self):
        from datetime import datetime, timezone
        from northstar.timeutil import cet_offset_at_utc
        # EU summer time 2026: 29 March 01:00 UTC -> 25 October 01:00 UTC
        assert cet_offset_at_utc(datetime(2026, 3, 29, 0, 59,
                                          tzinfo=timezone.utc)) == 1
        assert cet_offset_at_utc(datetime(2026, 3, 29, 1, 0,
                                          tzinfo=timezone.utc)) == 2
        assert cet_offset_at_utc(datetime(2026, 10, 25, 0, 59,
                                          tzinfo=timezone.utc)) == 2
        assert cet_offset_at_utc(datetime(2026, 10, 25, 1, 0,
                                          tzinfo=timezone.utc)) == 1

    def test_pilot_rows_match(self):
        from northstar.timeutil import openligadb_local_matches_utc as ok
        # bl1 2024 md1 (CEST) and a January row (CET) from the pilot files
        assert ok("2024-08-23T20:30:00", "2024-08-23T18:30:00Z")
        assert ok("2025-02-01T15:30:00", "2025-02-01T14:30:00Z")
        assert not ok("2024-08-23T19:30:00", "2024-08-23T18:30:00Z")

    def test_all_committed_fixtures_consistent(self):
        import glob, json, os
        from northstar.timeutil import openligadb_local_matches_utc as ok
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        n = 0
        for f in glob.glob(os.path.join(root, "data", "fixtures", "**",
                                        "openligadb_*.json"), recursive=True):
            if f.endswith(".meta.json"):
                continue
            for m in json.load(open(f, encoding="utf-8")):
                if m.get("matchDateTime") and m.get("matchDateTimeUTC"):
                    assert ok(m["matchDateTime"], m["matchDateTimeUTC"]), \
                        (f, m["matchID"])
                    n += 1
        assert n >= 1000

    def test_ingest_flags_local_utc_mismatch(self, store):
        import json
        from northstar.adapters import openligadb
        m = {"matchID": 1, "matchDateTime": "2026-09-25T18:30:00",
             "matchDateTimeUTC": "2026-09-25T18:30:00Z",
             "leagueId": 1, "leagueName": "L 2026/2027", "leagueSeason": 2026,
             "leagueShortcut": "bl1", "team1": {"teamId": 1, "teamName": "A"},
             "team2": {"teamId": 2, "teamName": "B"},
             "matchIsFinished": False, "matchResults": [],
             "lastUpdateDateTime": None}
        out = openligadb.ingest_matchday(store, json.dumps([m]),
                                         verify_identity=False,
                                         sport="football")
        kinds = [a["kind"] for a in store.anomalies()]
        assert "TIME_CONFLICT" in kinds
        assert out["anomalies"] >= 1
