"""Capture tool: strict validation, sidecar metadata, discovery.

All tests inject a fake fetch - the suite stays offline.  The real network
path runs only in CI (capture.yml), where its output (capture-log.json +
fixtures) is committed for review.
"""
from __future__ import annotations

import json

import pytest

from northstar import capture
from northstar.models import sha256_text


def _match(mid=1, shortcut="bl1", finished=False, **over):
    m = {
        "matchID": mid,
        "matchDateTime": "2026-09-25T18:30:00",
        "matchDateTimeUTC": "2026-09-25T18:30:00Z",
        "leagueId": 1, "leagueName": "1. Fußball-Bundesliga 2026/2027",
        "leagueSeason": 2026, "leagueShortcut": shortcut,
        "team1": {"teamId": 1, "teamName": "A"},
        "team2": {"teamId": 2, "teamName": "B"},
        "matchIsFinished": finished,
        "matchResults": [],
        "lastUpdateDateTime": None,
    }
    m.update(over)
    return m


def fake_fetch(mapping):
    def fetch(url):
        if url not in mapping:
            raise AssertionError(f"unexpected URL {url}")
        value = mapping[url]
        if isinstance(value, Exception):
            raise value
        return value
    return fetch


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    monkeypatch.setattr(capture.time, "sleep", lambda s: None)


class TestCaptureSeason:
    def test_valid_payload_writes_fixture_and_meta(self, tmp_path):
        payload = [_match(1), _match(2, finished=True)]
        text = json.dumps(payload)
        url = capture.openligadb.league_url("bl1", 2026)
        row = capture.capture_season("bl1", 2026, "football",
                                     str(tmp_path),
                                     fetch=fake_fetch({url: text}))
        assert row["written"] is True
        assert row["matches"] == 2 and row["finished"] == 1
        fixture = tmp_path / "openligadb_bl1_2026.json"
        meta = json.loads((tmp_path / "openligadb_bl1_2026.json.meta.json")
                          .read_text())
        assert fixture.exists()
        stored = fixture.read_text()
        assert sha256_text(stored) == meta["sha256"]
        assert json.loads(stored) == payload
        assert meta["sport"] == "football"
        assert meta["collection_mode"] == "automated_api"
        assert meta["league_name"] == payload[0]["leagueName"]
        assert meta["captured_at_utc"].endswith("Z")

    def test_invalid_json_refused(self, tmp_path):
        url = capture.openligadb.league_url("bl1", 2026)
        row = capture.capture_season("bl1", 2026, "football", str(tmp_path),
                                     fetch=fake_fetch({url: "{not json"}))
        assert row["written"] is False and "invalid JSON" in row["error"]
        assert not list(tmp_path.glob("*.json"))

    def test_non_list_refused(self, tmp_path):
        url = capture.openligadb.league_url("bl1", 2026)
        row = capture.capture_season("bl1", 2026, "football", str(tmp_path),
                                     fetch=fake_fetch({url: '{"a": 1}'}))
        assert row["written"] is False

    def test_empty_list_recorded_not_written(self, tmp_path):
        # The PDCWSDF/2024 finding: an empty list is a discovery result,
        # never data.
        url = capture.openligadb.league_url("PDCWSDF", 2024)
        row = capture.capture_season("PDCWSDF", 2024, "darts", str(tmp_path),
                                     fetch=fake_fetch({url: "[]"}))
        assert row["written"] is False and row["matches"] == 0
        assert "empty" in row["error"]

    def test_missing_required_key_refused(self, tmp_path):
        bad = _match(1)
        del bad["matchIsFinished"]
        url = capture.openligadb.league_url("bl1", 2026)
        row = capture.capture_season("bl1", 2026, "football", str(tmp_path),
                                     fetch=fake_fetch(
                                         {url: json.dumps([bad])}))
        assert row["written"] is False and "matchIsFinished" in row["error"]

    def test_shortcut_mismatch_refused(self, tmp_path):
        url = capture.openligadb.league_url("bl1", 2026)
        row = capture.capture_season("bl1", 2026, "football", str(tmp_path),
                                     fetch=fake_fetch(
                                         {url: json.dumps(
                                             [_match(1, shortcut="del")])}))
        assert row["written"] is False and "!=" in row["error"]


class TestDiscovery:
    def test_discover_leagues_flags_darts(self):
        url = "https://api.openligadb.de/getavailableleagues"
        payload = [
            {"leagueId": 1, "leagueShortcut": "bl1",
             "leagueName": "1. Fußball-Bundesliga"},
            {"leagueId": 2, "leagueShortcut": "PDCWSDF",
             "leagueName": "PDC World Series of Darts Finals"},
            {"leagueId": 3, "leagueShortcut": "dddf",
             "leagueName": "Dart-Duisburg-Dartsdays"},
        ]
        rep = capture.discover_leagues(
            fetch=fake_fetch({url: json.dumps(payload)}))
        assert rep["n_leagues"] == 3
        shorts = {l["leagueShortcut"] for l in rep["darts_candidates"]}
        assert shorts == {"PDCWSDF", "dddf"}

    def test_discover_leagues_refuses_non_list(self):
        url = "https://api.openligadb.de/getavailableleagues"
        with pytest.raises(ValueError):
            capture.discover_leagues(fetch=fake_fetch({url: "{}"}))

    def test_discover_darts_seasons_reports_empty_shortcut(self):
        urls = {
            "https://api.openligadb.de/getavailableleagues": json.dumps([
                {"leagueId": 9, "leagueShortcut": "PDCX",
                 "leagueName": "PDC Something Darts"}]),
        }
        for shortcut in ("PDCX",) + tuple(
                capture.DARTS_SHORTCUT_CANDIDATES):
            urls[f"https://api.openligadb.de/getavailableseasons/{shortcut}"
                 ] = "[]" if shortcut != "PDCX" else json.dumps(
                [{"leagueSeason": 2025}, {"leagueSeason": 2026}])
        out = capture.discover_darts_seasons(fetch=fake_fetch(urls))
        pdcx = next(o for o in out if o["leagueShortcut"] == "PDCX")
        assert pdcx["latest_season"] == 2026
        empties = [o for o in out if o.get("seasons") == []]
        assert empties and all("empty" in o.get("note", "")
                               for o in empties)


class TestLoadCurrentFixtures:
    def _write(self, tmp_path, name, payload, meta):
        text = json.dumps(payload, ensure_ascii=False,
                          separators=(",", ":")) + "\n"
        (tmp_path / name).write_text(text)
        meta = {**meta, "sha256": sha256_text(text)}
        (tmp_path / (name + ".meta.json")).write_text(json.dumps(meta))
        return text

    def test_loads_valid_pairs(self, tmp_path):
        self._write(tmp_path, "openligadb_bl1_2026.json", [_match(1)],
                    {"url": "u", "captured_at_utc": "2026-09-20T12:00:00Z",
                     "sport": "football", "league_shortcut": "bl1",
                     "league_season": 2026})
        items = capture.load_current_fixtures(str(tmp_path))
        assert len(items) == 1
        assert items[0]["error"] is None if "error" in items[0] else True
        assert items[0]["meta"]["sport"] == "football"
        assert items[0]["text"]

    def test_missing_meta_refused(self, tmp_path):
        (tmp_path / "openligadb_bl1_2026.json").write_text("[]")
        items = capture.load_current_fixtures(str(tmp_path))
        assert items[0]["text"] is None
        assert "missing sidecar" in items[0]["error"]

    def test_tampered_fixture_refused(self, tmp_path):
        self._write(tmp_path, "openligadb_bl1_2026.json", [_match(1)],
                    {"url": "u", "captured_at_utc": "2026-09-20T12:00:00Z",
                     "sport": "football", "league_shortcut": "bl1",
                     "league_season": 2026})
        (tmp_path / "openligadb_bl1_2026.json").write_text("[{\"x\":1}]\n")
        items = capture.load_current_fixtures(str(tmp_path))
        assert "sha256 mismatch" in items[0]["error"]

    def test_missing_dir_is_empty(self, tmp_path):
        assert capture.load_current_fixtures(str(tmp_path / "nope")) == []
