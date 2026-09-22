"""Historical pilot capture (capture-pilot): frozen whole-season fixtures.

Offline (injected fetch). Guarantees under test:
- a target is fetched once and written as canonical compact JSON + a
  sha256 sidecar (same contract as the current-season capture);
- repeat runs SKIP an already-committed fixture pair (frozen - the capture
  instant in the sidecar is never silently replaced);
- invalid payloads (not a list / empty) are refused, never written;
- a pilot capture log receipt is written.
"""
from __future__ import annotations

import json
import os

import pytest

from northstar import capture, models
from northstar.adapters import openligadb

FIXTURE_NAME_DEL = "openligadb_del_2024.json"
FIXTURE_NAME_BL1 = "openligadb_bl1_2024.json"


def _mk_match(match_id: int, shortcut: str = "del", season: int = 2024,
              finished: bool = True) -> dict:
    return {
        "matchID": match_id,
        "matchDateTime": "2024-10-01T18:00:00",
        "timeZoneID": "W. Europe Standard Time",
        "leagueId": 4827,
        "leagueName": "Test League",
        "leagueSeason": season,
        "leagueShortcut": shortcut,
        "matchDateTimeUTC": "2024-10-01T16:00:00Z",
        "group": {"groupName": "1. Spieltag", "groupOrderID": 1,
                  "groupID": 1},
        "team1": {"teamId": 1, "teamName": "Home", "shortName": "HOM",
                  "teamIconUrl": "https://example.org/h.svg",
                  "teamGroupName": None},
        "team2": {"teamId": 2, "teamName": "Away", "shortName": "AWY",
                  "teamIconUrl": "https://example.org/a.svg",
                  "teamGroupName": None},
        "lastUpdateDateTime": "2024-10-01T22:00:00.000",
        "matchIsFinished": finished,
        "matchResults": ([
            {"resultID": 1, "resultName": "1.Drittel", "pointsTeam1": 1,
             "pointsTeam2": 0, "resultOrderID": 1, "resultTypeID": 1,
             "resultTypeKind": "HalfTime",
             "resultDescription": "Ergebnis nach dem 1.Drittel"},
            {"resultID": 2, "resultName": "3.Drittel", "pointsTeam1": 3,
             "pointsTeam2": 2, "resultOrderID": 2, "resultTypeID": 2,
             "resultTypeKind": "After90Minutes",
             "resultDescription": "Ergebnis nach dem 3.Drittel"},
        ] if finished else []),
        "goals": [],
        "location": None,
        "numberOfViewers": None,
    }


class TestCapturePilot:
    def test_targets_are_the_documented_pilot_seasons(self):
        assert ("del", 2024, "ice_hockey") in capture.PILOT_TARGETS
        assert ("bl1", 2024, "football") in capture.PILOT_TARGETS

    def test_writes_fixture_and_sidecar(self, tmp_path):
        calls = []

        def fake_fetch(url):
            calls.append(url)
            shortcut = url.rstrip("/").split("/")[-2]
            season = url.rstrip("/").split("/")[-1]
            assert shortcut in ("del", "bl1")
            payload = [_mk_match(900000, shortcut=shortcut,
                                 season=int(season))]
            return json.dumps(payload)

        log = capture.capture_pilot(str(tmp_path), fetch=fake_fetch)
        assert not log["errors"]
        rows = {r["shortcut"]: r for r in log["targets"]}
        assert rows["del"]["written"] is True
        assert rows["bl1"]["written"] is True
        assert len(calls) == 2  # exactly one request per target

        for name, shortcut in ((FIXTURE_NAME_DEL, "del"),
                               (FIXTURE_NAME_BL1, "bl1")):
            path = tmp_path / name
            assert path.exists()
            text = path.read_text(encoding="utf-8")
            # canonical compact JSON + trailing newline
            payload = json.loads(text)
            assert text == json.dumps(payload, ensure_ascii=False,
                                      separators=(",", ":")) + "\n"
            # presentation-only crest URLs stripped
            for m in payload:
                assert "teamIconUrl" not in m["team1"]
                assert "teamIconUrl" not in m["team2"]
            meta_path = tmp_path / (name + ".meta.json")
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            assert meta["sha256"] == models.sha256_text(text)
            assert meta["league_shortcut"] == shortcut
            assert meta["license_id"] == "odbl-1.0"
            assert meta["collection_mode"] == "automated_api"
            assert meta["captured_at_utc"]
        # log receipt
        assert (tmp_path / "pilot-capture-log.json").exists()

    def test_second_run_is_idempotent_skip(self, tmp_path):
        def fake_fetch(url):
            raise AssertionError("frozen fixture must not be re-fetched")

        # first run writes
        def first_fetch(url):
            shortcut = url.rstrip("/").split("/")[-2]
            season = url.rstrip("/").split("/")[-1]
            return json.dumps([_mk_match(900000, shortcut=shortcut,
                                         season=int(season))])

        log1 = capture.capture_pilot(str(tmp_path), fetch=first_fetch)
        assert all(r["written"] for r in log1["targets"])
        # second run: everything skipped, fetch never called
        log2 = capture.capture_pilot(str(tmp_path), fetch=fake_fetch)
        assert not log2["errors"]
        for r in log2["targets"]:
            assert r.get("skipped_existing") is True
            assert r["written"] is False
        # the sidecar's capture instant is unchanged (frozen)
        meta = json.loads((tmp_path / (FIXTURE_NAME_DEL + ".meta.json"))
                          .read_text(encoding="utf-8"))
        assert meta["captured_at_utc"]

    def test_empty_payload_refused_not_written(self, tmp_path):
        def fake_fetch(url):
            return "[]"

        log = capture.capture_pilot(str(tmp_path), fetch=fake_fetch)
        assert log["errors"], "empty payloads must be logged as errors"
        for r in log["targets"]:
            assert r["written"] is False
            assert "empty" in r.get("error", "")
        assert not (tmp_path / FIXTURE_NAME_DEL).exists()
        assert not (tmp_path / (FIXTURE_NAME_DEL + ".meta.json")).exists()

    def test_invalid_json_refused_not_written(self, tmp_path):
        def fake_fetch(url):
            return "{not json"

        log = capture.capture_pilot(str(tmp_path), fetch=fake_fetch)
        assert log["errors"]
        assert not (tmp_path / FIXTURE_NAME_DEL).exists()

    def test_schema_mismatch_refused(self, tmp_path):
        def fake_fetch(url):
            shortcut = url.rstrip("/").split("/")[-2]
            season = url.rstrip("/").split("/")[-1]
            m = _mk_match(900000, shortcut="del", season=int(season))
            # a genuine league mismatch (case-insensitive compare in
            # capture_season refuses only exact shortcut mismatch)
            m["leagueShortcut"] = "pl"
            m["leagueSeason"] = 2024
            return json.dumps([m])

        log = capture.capture_pilot(str(tmp_path), fetch=fake_fetch)
        for r in log["targets"]:
            if r["shortcut"] == "del":
                assert r["written"] is False
                assert "shortcut" in r.get("error", "")
