"""Pilot scope pinning: the frozen 27-match PnL pilot must never widen.

The whole-season bl1/2024 payload (capture-pilot) ingests the SAME event
ids as the three hand-audited matchday files plus the other matches of the
season.  The PnL pilot scope is therefore pinned to the frozen matchdays
1/10/20 (cli.FOOTBALL_PILOT_MATCHDAYS); the hockey pilot is deliberately
NOT pinned (it should grow with the full season).
"""
from __future__ import annotations

import copy
import json
import os

from northstar import cli
from northstar.adapters import openligadb
from northstar.db import Store
from conftest import read_fixture

FIXTURES = os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "data", "fixtures")


def _synthetic_full_season(name: str, extra_group: int = 2,
                           extra_days: int = 7) -> str:
    """Real pilot file + one extra finished match in another matchday.

    The extra row is a deep copy of the first row with a new matchID and a
    later date in the same season - enough to prove the scope filter, no
    network, no invented scores (the score is the row's own real score).
    """
    payload = json.loads(read_fixture(name))
    extra = copy.deepcopy(payload[0])
    extra["matchID"] = payload[0]["matchID"] + 500000
    extra["group"]["groupOrderID"] = extra_group
    extra["group"]["groupID"] = 999000 + extra_group
    # shift the kickoff 7 days later (same season)
    base = extra["matchDateTimeUTC"][:10].split("-")
    month = int(base[1])
    day = int(base[2]) + extra_days
    if day > 28:
        day -= 28
        month += 1
    extra["matchDateTimeUTC"] = (f"{base[0]}-{month:02d}-{day:02d}"
                                 + extra["matchDateTimeUTC"][10:])
    extra["matchDateTime"] = extra["matchDateTimeUTC"].replace("Z", "")
    payload.append(extra)
    return json.dumps(payload)


class TestPilotScopePinning:
    def _football_store(self, tmp_path, full_season: bool) -> Store:
        s = Store(str(tmp_path / "t.db"))
        openligadb.ingest_matchday(s, read_fixture(
            "openligadb_bl1_2024_sd1.json"))
        if full_season:
            openligadb.ingest_matchday(s,
                                       _synthetic_full_season(
                                           "openligadb_bl1_2024_sd1.json"))
        s.commit()
        return s

    def test_frozen_pilot_scope_pinned_to_matchdays(self, tmp_path):
        s = self._football_store(tmp_path, full_season=True)
        finished = [e for e in s.events() if e["status"] == "finished"]
        pinned = cli._pilot_scope(finished, "football", "/bl1/2024/",
                                  matchdays=cli.FOOTBALL_PILOT_MATCHDAYS)
        unpinned = cli._pilot_scope(finished, "football", "/bl1/2024/")
        # the synthetic extra matchday-2 match exists in the store ...
        assert len(unpinned) == len(pinned) + 1
        # ... but the PnL pilot scope stays on the frozen matchdays only
        assert {e["group_order"] for e in pinned} <= cli.FOOTBALL_PILOT_MATCHDAYS
        assert len(pinned) == 9  # matchday 1 of the real pilot file

    def test_scope_without_full_season_file_unchanged(self, tmp_path):
        s = self._football_store(tmp_path, full_season=False)
        finished = [e for e in s.events() if e["status"] == "finished"]
        pinned = cli._pilot_scope(finished, "football", "/bl1/2024/",
                                  matchdays=cli.FOOTBALL_PILOT_MATCHDAYS)
        assert len(pinned) == 9

    def test_hockey_scope_is_not_pinned(self, tmp_path):
        s = Store(str(tmp_path / "h.db"))
        openligadb.ingest_matchday(s, read_fixture(
            "openligadb_del_2024_sd1.json"), sport="ice_hockey")
        openligadb.ingest_matchday(s,
                                   _synthetic_full_season(
                                       "openligadb_del_2024_sd1.json"),
                                   sport="ice_hockey")
        s.commit()
        finished = [e for e in s.events() if e["status"] == "finished"]
        hockey = cli._pilot_scope(finished, "ice_hockey", "/del/2024/")
        # hockey grows with the full season (no matchday pin)
        assert len(hockey) == 8
        groups = {e["group_order"] for e in hockey}
        assert 2 in groups and 1 in groups


class TestBl1WarmupIngest:
    def test_warmup_ingests_full_season_with_sidecar(self, tmp_path,
                                                     monkeypatch):
        text = _synthetic_full_season("openligadb_bl1_2024_sd1.json")
        fixture = tmp_path / "openligadb_bl1_2024.json"
        fixture.write_text(text + "\n", encoding="utf-8")
        from northstar import models
        import hashlib
        meta = {
            "source_id": "openligadb", "license_id": "odbl-1.0",
            "collection_mode": "automated_api",
            "url": "https://api.openligadb.de/getmatchdata/bl1/2024",
            "captured_at_utc": "2026-09-22T05:00:00Z",
            "sha256": hashlib.sha256(text.encode()).hexdigest(),
            "fixture": fixture.name, "league_shortcut": "bl1",
            "league_season": 2024, "league_name": "Bundesliga",
            "sport": "football", "n_matches": 10, "n_finished": 10,
        }
        (tmp_path / (fixture.name + ".meta.json")).write_text(
            json.dumps(meta, indent=2) + "\n", encoding="utf-8")
        monkeypatch.setattr(cli, "FIXTURES", str(tmp_path))
        s = Store(str(tmp_path / "warm.db"))
        stats = cli.ingest_pilot_warmup(s)
        assert stats["events"] == 10
        assert stats["results"] == 10
        # the events carry the bl1/2024 per-match URLs (history filter)
        urls = [e["source_url"] for e in s.events()]
        assert all("/getmatchdata/bl1/2024/" in u for u in urls)

    def test_warmup_refuses_payload_without_sidecar(self, tmp_path,
                                                    monkeypatch):
        text = _synthetic_full_season("openligadb_bl1_2024_sd1.json")
        (tmp_path / "openligadb_bl1_2024.json").write_text(
            text + "\n", encoding="utf-8")
        monkeypatch.setattr(cli, "FIXTURES", str(tmp_path))
        s = Store(str(tmp_path / "warm.db"))
        stats = cli.ingest_pilot_warmup(s)
        assert stats["events"] == 0  # no provenance, no ingest

    def test_warmup_noop_without_file(self, tmp_path, monkeypatch):
        monkeypatch.setattr(cli, "FIXTURES", str(tmp_path / "missing"))
        s = Store(str(tmp_path / "warm.db"))
        stats = cli.ingest_pilot_warmup(s)
        assert stats["events"] == 0
