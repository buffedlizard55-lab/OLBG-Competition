"""Capture tool: strict validation, sidecar metadata, discovery.

All tests inject a fake fetch - the suite stays offline.  The real network
path runs only in CI (capture.yml), where its output (capture-log.json +
fixtures) is committed for review.
"""
from __future__ import annotations

import json

import pytest

from northstar import capture
from northstar.models import parse_utc, sha256_text


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

    def test_shortcut_case_variant_accepted_and_recorded(self, tmp_path):
        """Live finding 2026-09-20: getmatchdata answers case-insensitively
        ("pdcfdt" -> payload leagueShortcut "PDCFDT"); a case variant is a
        recording, not a refusal."""
        url = capture.openligadb.league_url("pdcfdt", 2026)
        row = capture.capture_season("pdcfdt", 2026, "darts", str(tmp_path),
                                     fetch=fake_fetch(
                                         {url: json.dumps(
                                             [_match(1, shortcut="PDCFDT")])}))
        assert row["written"] is True
        assert row["payload_shortcut"] == "PDCFDT"
        assert (tmp_path / "openligadb_pdcfdt_2026.json").exists()


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
        shortcuts = ("PDCX",) + tuple(capture.DARTS_SHORTCUT_CANDIDATES)
        for shortcut in shortcuts:
            urls[f"https://api.openligadb.de/getavailableseasons/{shortcut}"
                 ] = "[]" if shortcut != "PDCX" else json.dumps(
                [{"leagueSeason": 2025}, {"leagueSeason": 2026}])
            # direct per-season probes (the darts fallback path)
            for season in (2026, 2025, 2024):
                urls[f"https://api.openligadb.de/getmatchdata/{shortcut}/"
                     f"{season}"] = "[]"
        out = capture.discover_darts_seasons(fetch=fake_fetch(urls),
                                             this_year=2026)
        pdcx = next(o for o in out if o["leagueShortcut"] == "PDCX")
        assert pdcx["latest_season"] == 2026
        assert pdcx["leagueName"] == "PDC Something Darts"
        empties = [o for o in out if o.get("latest_season") is None]
        assert empties and all("no data" in o.get("note", "")
                               for o in empties)
        assert all(o.get("season_probes") for o in empties)

    def test_upcoming_leagues_outrank_finished_history(self):
        """Discovery must prefer a league whose latest season still has
        *future* unfinished matches (the forward desk's payload, e.g. a
        starting World Championship) over all-finished events earlier in
        the index."""
        now = parse_utc("2026-09-20T19:30:00Z")
        finished = _match(1, shortcut="OLDDART25", finished=True,
                          matchDateTimeUTC="2025-07-11T11:00:00Z")
        upcoming = _match(2, shortcut="WMDART26", finished=False,
                          matchDateTimeUTC="2026-12-13T12:30:00Z")
        urls = {
            "https://api.openligadb.de/getavailableleagues": json.dumps([
                {"leagueId": 1, "leagueShortcut": "OLDDART25",
                 "leagueName": "Some Finished Darts Event 2025"},
                {"leagueId": 2, "leagueShortcut": "WMDART26",
                 "leagueName": "Darts WM 2026"}]),
        }
        for shortcut, body in (("OLDDART25", [finished] * 5),
                               ("WMDART26", [upcoming] * 5)):
            urls[f"https://api.openligadb.de/getavailableseasons/{shortcut}"
                 ] = "[]"
            urls[f"https://api.openligadb.de/getmatchdata/{shortcut}/2026"
                 ] = json.dumps(body)
            for season in (2025, 2024):
                urls[f"https://api.openligadb.de/getmatchdata/{shortcut}/"
                     f"{season}"] = "[]"
        out = capture.discover_darts_seasons(fetch=fake_fetch(urls),
                                             this_year=2026, max_leagues=1,
                                             now=now)
        wm = next(o for o in out if o["leagueShortcut"] == "WMDART26")
        old = next(o for o in out if o["leagueShortcut"] == "OLDDART25")
        assert wm["unfinished_in_latest"] == 5
        assert wm["future_unfinished_in_latest"] == 5
        assert old.get("future_unfinished_in_latest") == 0
        assert not wm.get("trimmed")
        assert old.get("trimmed") is True
        kept = [o for o in out
                if o.get("latest_season") and not o.get("trimmed")]
        assert [o["leagueShortcut"] for o in kept] == ["WMDART26"]

    def test_awaiting_refresh_league_outranks_finished_history(self):
        """Live finding 2026-09-20 (second capture): the WSDF final was in
        play, so its start was already past at probe time - a league with a
        few recent unfinished rows must still outrank fully-finished
        leagues, or the stale on-disk fixture freezes the result forever."""
        now = parse_utc("2026-09-20T20:05:00Z")
        inplay = _match(6, shortcut="LIVEDART", finished=False,
                        matchDateTimeUTC="2026-09-20T19:30:00Z")
        done = _match(7, shortcut="DONEDART", finished=True,
                      matchDateTimeUTC="2026-02-01T18:00:00Z")
        urls = {
            "https://api.openligadb.de/getavailableleagues": json.dumps([
                # finished league FIRST in index order - priority must
                # still pick the awaiting-refresh one
                {"leagueId": 1, "leagueShortcut": "DONEDART",
                 "leagueName": "Finished Darts Masters 2026"},
                {"leagueId": 2, "leagueShortcut": "LIVEDART",
                 "leagueName": "Live Darts Finals 2026"}]),
        }
        for shortcut, body in (("DONEDART", [done] * 5),
                               ("LIVEDART", [inplay])):
            urls[f"https://api.openligadb.de/getavailableseasons/{shortcut}"
                 ] = "[]"
            urls[f"https://api.openligadb.de/getmatchdata/{shortcut}/2026"
                 ] = json.dumps(body)
            for season in (2025, 2024):
                urls[f"https://api.openligadb.de/getmatchdata/{shortcut}/"
                     f"{season}"] = "[]"
        out = capture.discover_darts_seasons(fetch=fake_fetch(urls),
                                             this_year=2026, max_leagues=1,
                                             now=now)
        live = next(o for o in out if o["leagueShortcut"] == "LIVEDART")
        done_row = next(o for o in out if o["leagueShortcut"] == "DONEDART")
        assert live["future_unfinished_in_latest"] == 0
        assert not live.get("abandoned_pattern")
        assert not live.get("trimmed")
        assert done_row.get("trimmed") is True

    def test_case_variant_shortcuts_are_deduplicated(self):
        """Live index 2026-09-20 carries both 'pdcfdt' (4878) and 'PDCFDT'
        (6008); fixtures are written lowercase, so only one may be probed."""
        now = parse_utc("2026-09-20T19:30:00Z")
        m = _match(5, shortcut="PDCFDT", finished=True,
                   matchDateTimeUTC="2026-07-11T11:00:00Z")
        urls = {
            "https://api.openligadb.de/getavailableleagues": json.dumps([
                {"leagueId": 6008, "leagueShortcut": "PDCFDT",
                 "leagueName": "PDC Floorstuff Darts Trophy 2026"},
                {"leagueId": 4878, "leagueShortcut": "pdcfdt",
                 "leagueName": "PDC FDT 2026"}]),
        }
        for sc in ("PDCFDT", "pdcfdt"):
            urls[f"https://api.openligadb.de/getavailableseasons/{sc}"] = "[]"
            for season in (2026, 2025, 2024):
                urls[f"https://api.openligadb.de/getmatchdata/{sc}/{season}"
                     ] = json.dumps([m]) if season == 2026 else "[]"
        out = capture.discover_darts_seasons(fetch=fake_fetch(urls),
                                             this_year=2026, now=now)
        rows = [o for o in out
                if o["leagueShortcut"].lower() == "pdcfdt"]
        assert len(rows) == 1
        assert rows[0]["latest_season"] == 2026

    def test_abandoned_league_with_stale_unfinished_rows_is_demoted(self):
        """Live finding 2026-09-20: shortcut darts-wm-26 carried 52
        unfinished rows whose starts were 9 months old - an abandoned
        duplicate of the complete PDCWM league. Unfinished-but-past rows
        must NOT outrank cleanly-entered leagues."""
        now = parse_utc("2026-09-20T19:30:00Z")
        stale = _match(3, shortcut="DEADDART", finished=False,
                       matchDateTimeUTC="2025-12-13T12:30:00Z")
        done = _match(4, shortcut="CLEANDART", finished=True,
                      matchDateTimeUTC="2026-07-19T18:00:00Z")
        urls = {
            "https://api.openligadb.de/getavailableleagues": json.dumps([
                {"leagueId": 1, "leagueShortcut": "DEADDART",
                 "leagueName": "Abandoned Darts WM copy"},
                {"leagueId": 2, "leagueShortcut": "CLEANDART",
                 "leagueName": "Clean Darts Event 2026"}]),
        }
        for shortcut, body in (("DEADDART", [stale] * 12),
                               ("CLEANDART", [done] * 5)):
            urls[f"https://api.openligadb.de/getavailableseasons/{shortcut}"
                 ] = "[]"
            urls[f"https://api.openligadb.de/getmatchdata/{shortcut}/2026"
                 ] = json.dumps(body)
            for season in (2025, 2024):
                urls[f"https://api.openligadb.de/getmatchdata/{shortcut}/"
                     f"{season}"] = "[]"
        out = capture.discover_darts_seasons(fetch=fake_fetch(urls),
                                             this_year=2026, max_leagues=1,
                                             now=now)
        dead = next(o for o in out if o["leagueShortcut"] == "DEADDART")
        clean = next(o for o in out if o["leagueShortcut"] == "CLEANDART")
        assert dead["abandoned_pattern"] is True
        assert dead["future_unfinished_in_latest"] == 0
        assert not clean.get("abandoned_pattern")
        assert not clean.get("trimmed")
        assert dead.get("trimmed") is True



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
