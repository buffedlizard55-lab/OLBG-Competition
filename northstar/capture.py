"""Current-season capture tool (network; runs in CI, never in tests).

OpenLigaDB is the only source in this project whose license permits
automated API collection (ODbL-1.0; policy gate ``automated_api``).  This
module fetches *whole league seasons* in one request per league, validates
the payloads strictly, and writes canonical fixtures plus sidecar metadata
into ``data/fixtures/current/`` together with an append-only capture log.

Why CI: the sandbox/agent environment used for development has no direct
network egress, and manual transcription of payloads is exactly the kind of
unverifiable step this repo avoids.  GitHub Actions runners fetch with the
documented rate limit respected, commit the fixtures, and the offline
pipeline (pages/ci workflows, local runs) replays them deterministically.

Honesty rules:
- a payload that does not parse, is not a JSON list, or is empty is
  refused, never written (an empty list from a valid shortcut is recorded
  as a discovery finding, not as data);
- every written fixture records URL, capture instant, sha256, match counts
  and the league name reported by the source itself;
- darts leagues are *discovered* from getavailableleagues, not assumed:
  the 2026-09-20 development probe found that the previously documented
  shortcut/season pair (PDCWSDF/2024) returns an empty list, so hardcoded
  darts assumptions are treated as unverified until discovery confirms
  them (flagged in docs/DARTS-AUDIT.md and the discovery report).
"""
from __future__ import annotations

import json
import os
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from . import models
from .adapters import openligadb
from .models import parse_utc

# Whole-season targets for the forward-test desks. bl1 = Bundesliga
# (football), del = DEL (ice hockey).  Both verified live on 2026-09-20
# via getmatchdata probes.  Darts targets come from discovery (below).
CURRENT_TARGETS: List[Tuple[str, int, str]] = [
    ("bl1", 2026, "football"),
    ("del", 2026, "ice_hockey"),
]

# League shortcuts previously documented for darts; discovery decides
# whether they exist and which seasons carry data.
DARTS_SHORTCUT_CANDIDATES = ["PDCWSDF", "PDCWC", "pdc", "PDC", "darts"]

MIN_REQUEST_GAP_S = 1.1          # << 60 req/min documented limit
CANONICAL_SEPARATORS = (",", ":")


def _canonical(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False,
                      separators=CANONICAL_SEPARATORS) + "\n"


def discover_leagues(fetch=openligadb.fetch_url) -> Dict[str, Any]:
    """Enumerate the source's league index and extract darts candidates.

    ``fetch`` is injectable for tests.  Returns a report: all league
    shortcuts seen, and darts-related leagues with their names.
    """
    text = fetch("https://api.openligadb.de/getavailableleagues")
    payload = json.loads(text)
    if not isinstance(payload, list):
        raise ValueError("getavailableleagues did not return a JSON list")
    leagues = []
    for row in payload:
        shortcut = row.get("leagueShortcut") or ""
        name = row.get("leagueName") or ""
        blob = f"{shortcut} {name}".lower()
        is_darts = ("dart" in blob or shortcut.upper().startswith("PDC")
                    or "pdc" in shortcut.lower())
        leagues.append({"leagueId": row.get("leagueId"),
                        "leagueShortcut": shortcut,
                        "leagueName": name,
                        "darts_candidate": is_darts})
    return {
        "generated_utc": models.fmt_utc(models.utcnow()),
        "n_leagues": len(leagues),
        "darts_candidates": [l for l in leagues if l["darts_candidate"]],
        "shortcut_candidates_probed": DARTS_SHORTCUT_CANDIDATES,
        "leagues": leagues,
    }


def _probe_season_matches(fetch, shortcut: str, season: int) -> Optional[int]:
    """Return {"matches": n, "unfinished": u} for a shortcut/season, or None.

    Darts leagues on OpenLigaDB 404 on getavailableseasons (observed live
    2026-09-20), so the season list is probed directly through
    getmatchdata: an empty list means "no data for that season", a 404
    means the shortcut itself is unknown.
    """
    url = f"{openligadb.API_BASE}/getmatchdata/{shortcut}/{season}"
    try:
        payload = json.loads(fetch(url))
    except Exception:  # noqa: BLE001 - probe failures are findings
        return None
    if isinstance(payload, list):
        unfinished = sum(1 for m in payload
                         if isinstance(m, dict) and not m.get("matchIsFinished"))
        return {"matches": len(payload), "unfinished": unfinished}
    return None


def discover_darts_seasons(fetch=openligadb.fetch_url,
                           max_leagues: int = 4,
                           this_year: Optional[int] = None
                           ) -> List[Dict[str, Any]]:
    """For each discovered darts league, find seasons that carry data.

    Two-step discovery, everything recorded: getavailableseasons first; on
    failure/empty (the observed darts behaviour) probe getmatchdata for the
    last three seasons directly.  League names are kept so the capture log
    documents what each shortcut is.
    """
    report = discover_leagues(fetch)
    names = {l["leagueShortcut"]: l["leagueName"]
             for l in report["darts_candidates"]}
    out: List[Dict[str, Any]] = []
    seen = set()
    year = this_year or models.utcnow().year
    candidates = [l["leagueShortcut"] for l in report["darts_candidates"]]
    for extra in DARTS_SHORTCUT_CANDIDATES:
        if extra not in candidates:
            candidates.append(extra)   # probe documented-but-missing too
    for shortcut in candidates:
        if not shortcut or shortcut in seen:
            continue
        seen.add(shortcut)
        row: Dict[str, Any] = {"leagueShortcut": shortcut,
                               "leagueName": names.get(shortcut)}
        time.sleep(MIN_REQUEST_GAP_S)
        seasons = None
        try:
            seasons = json.loads(fetch(
                f"https://api.openligadb.de/getavailableseasons/{shortcut}"))
        except Exception as exc:  # noqa: BLE001 - report, don't crash
            row["seasons_endpoint_error"] = f"{type(exc).__name__}: {exc}"
        if isinstance(seasons, list) and seasons:
            digits = [int(s["leagueSeason"]) for s in seasons
                      if str(s.get("leagueSeason", "")).isdigit()]
            row["seasons"] = [s.get("leagueSeason") for s in seasons]
            row["latest_season"] = max(digits) if digits else None
            if row["latest_season"] is not None:
                time.sleep(MIN_REQUEST_GAP_S)
                probe = _probe_season_matches(fetch, shortcut,
                                              row["latest_season"])
                if probe:
                    row["unfinished_in_latest"] = probe["unfinished"]
        else:
            # Direct per-season probe (darts leagues 404 on the seasons
            # endpoint but answer getmatchdata - verified 2026-09-20).
            probes = {}
            for season in (year, year - 1, year - 2):
                time.sleep(MIN_REQUEST_GAP_S)
                probes[season] = _probe_season_matches(fetch, shortcut,
                                                       season)
            row["season_probes"] = probes
            with_data = [s for s, p in probes.items() if p and p["matches"]]
            row["seasons"] = sorted(with_data)
            row["latest_season"] = max(with_data) if with_data else None
            if row["latest_season"] is not None:
                probe = probes.get(row["latest_season"])
                if probe:
                    row["unfinished_in_latest"] = probe["unfinished"]
            if not with_data:
                row["note"] = ("no data for the last three seasons "
                               "(or shortcut unknown)")
        out.append(row)
    # Forward-test priority: a league whose latest season still carries
    # *unfinished* matches (upcoming fixtures) must never be crowded out by
    # all-finished historical events - the league index lists e.g. the
    # completed 2025 PDC events before "Darts WM 2026" (leagueId 4893),
    # which is exactly the payload the forward desk will need in December.
    out.sort(key=lambda o: (-(o.get("unfinished_in_latest") or 0),
                            -(o.get("latest_season") or 0)))
    kept = 0
    for row in out:
        if row.get("latest_season") is None:
            continue
        if kept >= max_leagues:
            row["trimmed"] = True
            row["note"] = ((row.get("note") + "; " if row.get("note") else "")
                           + f"beyond max_leagues={max_leagues} after "
                             "upcoming-first priority sort")
        else:
            kept += 1
    return out


def capture_season(shortcut: str, season: int, sport: str, out_dir: str,
                   fetch=openligadb.fetch_url) -> Dict[str, Any]:
    """Fetch one league-season, validate strictly, write fixture + meta.

    Returns a result row for the capture log.  Refusals (empty payload,
    bad JSON, schema mismatch) are recorded with ``written: False`` - the
    caller decides whether that is a finding (discovery) or a failure.
    """
    url = openligadb.league_url(shortcut, season)
    text = fetch(url)
    captured_at = models.utcnow()
    row: Dict[str, Any] = {
        "shortcut": shortcut, "season": season, "sport": sport, "url": url,
        "captured_at_utc": models.fmt_utc(captured_at),
    }
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        row.update({"written": False, "error": f"invalid JSON: {exc}"})
        return row
    if not isinstance(payload, list):
        row.update({"written": False, "error": "payload is not a JSON list"})
        return row
    if not payload:
        row.update({"written": False, "matches": 0,
                    "error": "empty list (shortcut/season carries no data)"})
        return row
    # Schema spot-checks before anything is written (fail loudly, never
    # store a half-understood payload).
    for m in payload:
        for key in ("matchID", "matchDateTimeUTC", "leagueShortcut",
                    "team1", "team2", "matchIsFinished"):
            if key not in m:
                row.update({"written": False,
                            "error": f"match row missing '{key}'"})
                return row
        if str(m.get("leagueShortcut")) != shortcut:
            row.update({"written": False,
                        "error": f"payload shortcut {m.get('leagueShortcut')}"
                                 f" != requested {shortcut}"})
            return row
    fixture_name = f"openligadb_{shortcut.lower()}_{season}.json"
    fixture_path = os.path.join(out_dir, fixture_name)
    os.makedirs(out_dir, exist_ok=True)
    canonical = _canonical(payload)
    with open(fixture_path, "w", encoding="utf-8") as fh:
        fh.write(canonical)
    sha = models.sha256_text(canonical)
    finished = sum(1 for m in payload if m.get("matchIsFinished"))
    league_name = payload[0].get("leagueName")
    meta = {
        "source_id": "openligadb",
        "license_id": "odbl-1.0",
        "collection_mode": "automated_api",
        "url": url,
        "captured_at_utc": models.fmt_utc(captured_at),
        "sha256": sha,
        "fixture": fixture_name,
        "league_shortcut": shortcut,
        "league_season": season,
        "league_name": league_name,
        "sport": sport,
        "n_matches": len(payload),
        "n_finished": finished,
        "note": ("whole-season payload fetched via the permitted automated "
                 "API (ODbL-1.0); canonical compact JSON, unmodified "
                 "content"),
    }
    with open(os.path.join(out_dir, fixture_name + ".meta.json"), "w",
              encoding="utf-8") as fh:
        json.dump(meta, fh, indent=2, ensure_ascii=False, sort_keys=True)
        fh.write("\n")
    row.update({"written": True, "matches": len(payload),
                "finished": finished, "league_name": league_name,
                "sha256": sha, "fixture": fixture_path})
    return row


def capture_current(out_dir: str, season: int = 2026,
                    fetch=openligadb.fetch_url) -> Dict[str, Any]:
    """Run the full capture pass and write the capture log.

    Log file: ``<out_dir>/capture-log.json`` (overwritten each run; the
    fixtures + forward ledger are the durable record, the log is the
    operational receipt kept next to them and committed for review).
    """
    log: Dict[str, Any] = {
        "started_utc": models.fmt_utc(models.utcnow()),
        "season": season, "targets": [], "darts_discovery": [],
        "errors": [],
    }
    for shortcut, seas, sport in CURRENT_TARGETS:
        row = capture_season(shortcut, seas, sport, out_dir, fetch=fetch)
        log["targets"].append(row)
        if not row.get("written"):
            log["errors"].append(row)
        time.sleep(MIN_REQUEST_GAP_S)
    # Darts: discovery-driven (the documented shortcut/season was found
    # empty on 2026-09-20; discovery decides what is capturable).
    try:
        index = discover_leagues(fetch=fetch)
        log["darts_league_index"] = index["darts_candidates"]
        time.sleep(MIN_REQUEST_GAP_S)
        darts = discover_darts_seasons(fetch=fetch)
        log["darts_discovery"] = darts
        for d in darts:
            latest = d.get("latest_season")
            if d.get("seasons") and latest and not d.get("trimmed"):
                row = capture_season(d["leagueShortcut"], int(latest),
                                     "darts", out_dir, fetch=fetch)
                log["targets"].append(row)
                if not row.get("written"):
                    log["errors"].append(row)
                time.sleep(MIN_REQUEST_GAP_S)
    except Exception as exc:  # noqa: BLE001 - discovery failure is a finding
        log["darts_discovery_error"] = f"{type(exc).__name__}: {exc}"
        log["errors"].append({"step": "darts_discovery",
                              "error": log["darts_discovery_error"]})
    log["finished_utc"] = models.fmt_utc(models.utcnow())
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "capture-log.json"), "w",
              encoding="utf-8") as fh:
        json.dump(log, fh, indent=2, ensure_ascii=False, sort_keys=True)
        fh.write("\n")
    return log


def load_current_fixtures(out_dir: str) -> List[Dict[str, Any]]:
    """Offline: read committed current fixtures + their sidecar metadata.

    Returns a list of {"path", "text", "meta"} ordered by fixture name.
    Fixtures without valid metadata are refused (an anomaly is flagged by
    the caller): capture instant is required for as_of classification.
    """
    out: List[Dict[str, Any]] = []
    if not os.path.isdir(out_dir):
        return out
    for name in sorted(os.listdir(out_dir)):
        if not name.startswith("openligadb_") or not name.endswith(".json"):
            continue
        if name.endswith(".meta.json"):
            continue
        path = os.path.join(out_dir, name)
        meta_path = path + ".meta.json"
        if not os.path.exists(meta_path):
            out.append({"path": path, "text": None, "meta": None,
                        "error": "missing sidecar metadata"})
            continue
        with open(meta_path, "r", encoding="utf-8") as fh:
            meta = json.load(fh)
        with open(path, "r", encoding="utf-8") as fh:
            text = fh.read()
        actual_sha = models.sha256_text(text)
        if meta.get("sha256") != actual_sha:
            out.append({"path": path, "text": None, "meta": meta,
                        "error": f"sha256 mismatch: meta says "
                                 f"{meta.get('sha256')}, file is {actual_sha}"})
            continue
        out.append({"path": path, "text": text, "meta": meta})
    return out
