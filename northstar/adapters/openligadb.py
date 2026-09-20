"""OpenLigaDB adapter - the open-licensed reference-result path.

Why OpenLigaDB for the pilot:
- data are published under ODbL 1.0 (open, share-alike) - a permissioned
  source, unlike scraped feeds;
- a real HTTP JSON API with a documented rate limit (60 req/min/IP), no key;
- machine-readable result types (HalfTime / After90Minutes /
  AfterExtraTime / AfterPenalties) which map cleanly onto settlement rules.

Honesty caveat (also in policy.py): OpenLigaDB is community-entered. It is an
open-licensed *reference* source, not a DFL official feed. The identity gate
requires ``verified`` confidence, which we grant after an independent
cross-check (here: the football-data.co.uk FT result, a second, independent
compilation) has agreed; until then events stay ``probable``/``unmatched``.
"""
from __future__ import annotations

import json
import urllib.request
from typing import Dict, List, Optional

from .. import models
from ..db import Store
from ..models import (
    EVENT_STATUS_FINISHED, EVENT_STATUS_POSTPONED, Event, Result,
    RESULT_KIND_AFTER_90, RESULT_KIND_AFTER_EXTRA,
    RESULT_KIND_AFTER_PENALTIES, SPORT_FOOTBALL,
    parse_utc, sha256_text, stable_id,
)
from ..policy import MODE_AUTO_API, PolicyError, get_policy

PROVIDER_ID = "openligadb"
API_BASE = "https://api.openligadb.de"


def league_url(league_shortcut: str, league_season: int,
               group_order: Optional[int] = None) -> str:
    if group_order is None:
        return f"{API_BASE}/getmatchdata/{league_shortcut}/{league_season}"
    return (f"{API_BASE}/getmatchdata/{league_shortcut}/{league_season}/"
            f"{group_order}")


def fetch_matchdata(league_shortcut: str, league_season: int,
                    group_order: Optional[int] = None) -> str:
    """Live fetch (used in CI / environments with network). Refuses to run
    unless the source policy permits automated API collection."""
    get_policy("openligadb").assert_permitted(MODE_AUTO_API)
    url = league_url(league_shortcut, league_season, group_order)
    req = urllib.request.Request(url, headers={"User-Agent":
                                               "NorthstarLab/0.2 (paper-trading research)"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return resp.read().decode("utf-8")


def event_id_for(match: Dict) -> str:
    return stable_id("ev", "bl1" if match.get("leagueShortcut") == "bl1"
                     else match.get("leagueShortcut", "ol"),
                     match["leagueSeason"], match["matchID"])


# Which resultTypeKind is the "final" for a sport. Football settles on
# 90 minutes (cups: extra time/penalties are separate markets). Hockey has
# no such split - the source's final score is the settled score, so a finished
# DEL/CHL match that went to extra time (or a shootout in some formats)
# must be read from AfterExtraTime / AfterPenalties, not the regulation
# draw. Darts: fall back through the list if a series is recorded under a
# non-standard kind.
FINAL_KIND_PRIORITY = {
    "football": [RESULT_KIND_AFTER_90],
    "ice_hockey": [RESULT_KIND_AFTER_PENALTIES,
                   RESULT_KIND_AFTER_EXTRA, RESULT_KIND_AFTER_90],
}
DEFAULT_FINAL_KIND_PRIORITY = [RESULT_KIND_AFTER_90,
                               RESULT_KIND_AFTER_EXTRA,
                               RESULT_KIND_AFTER_PENALTIES]


def parse_matchday(text: str, sport: Optional[str] = None) -> List[Dict]:
    """Parse an OpenLigaDB matchdata JSON payload into normalized match dicts.

    Accepts the full-season list and single-matchday lists alike; only
    finished/unfinished flag, UTC start, participants and the sport-appropriate
    final result are carried forward (see FINAL_KIND_PRIORITY).
    """
    priority = FINAL_KIND_PRIORITY.get(sport or "",
                                       DEFAULT_FINAL_KIND_PRIORITY)
    payload = json.loads(text)
    out: List[Dict] = []
    for m in payload:
        final = None
        for kind in priority:
            for r in m.get("matchResults", []):
                if r.get("resultTypeKind") == kind:
                    final = r
                    break
            if final is not None:
                break
        if m.get("matchIsFinished") and final is None:
            # Finished but no final result of a recognised kind recorded -
            # do not guess; keep the match without a final result.
            final = None
        out.append({
            "match_id": m["matchID"],
            "league_shortcut": m.get("leagueShortcut"),
            "league_season": m.get("leagueSeason"),
            "league_name": m.get("leagueName"),
            "start_utc": parse_utc(m["matchDateTimeUTC"]),
            "group_order": (m.get("group") or {}).get("groupOrderID"),
            "group_name": (m.get("group") or {}).get("groupName"),
            "home_team_id": str(m["team1"]["teamId"]),
            "home_team": m["team1"]["teamName"],
            "away_team_id": str(m["team2"]["teamId"]),
            "away_team": m["team2"]["teamName"],
            "finished": bool(m.get("matchIsFinished")),
            "home_goals": final["pointsTeam1"] if final else None,
            "away_goals": final["pointsTeam2"] if final else None,
            "final_kind": final["resultTypeKind"] if final else None,
            "source_version": m.get("lastUpdateDateTime"),
            "raw_match": m,
        })
    return out


def ingest_matchday(store: Store, text: str,
                    verify_identity: bool = True,
                    sport: Optional[str] = SPORT_FOOTBALL) -> Dict:
    """Ingest one matchday payload: events + primary results.

    ``verify_identity``: when True, events start at ``probable`` identity
    confidence; the cross-check step (ingest_pilot in the pipeline) upgrades
    to ``verified`` once an independent source agrees.
    """
    policy = get_policy("openligadb")
    policy.assert_permitted(MODE_AUTO_API)  # documents the mode even offline
    matches = parse_matchday(text, sport=sport)
    stats = {"events": 0, "results": 0, "anomalies": 0}
    for m in matches:
        eid = event_id_for({"leagueShortcut": m["league_shortcut"],
                            "leagueSeason": m["league_season"],
                            "matchID": m["match_id"]})
        url = f"{API_BASE}/getmatchdata/{m['league_shortcut']}/" \
              f"{m['league_season']}/{m['match_id']}"
        if m["finished"]:
            status = EVENT_STATUS_FINISHED
        else:
            status = EVENT_STATUS_POSTPONED  # unresolved state; review queue
        event = Event(
            event_id=eid,
            sport=sport,
            competition=m["league_name"] or "unknown",
            home_team_id=m["home_team_id"],
            home_team=m["home_team"],
            away_team_id=m["away_team_id"],
            away_team=m["away_team"],
            scheduled_start_utc=m["start_utc"],
            status=status,
            group_order=m["group_order"],
            group_name=m["group_name"],
            source_event_id=str(m["match_id"]),
            source_provider=PROVIDER_ID,
            source_url=url,
            source_version=m["source_version"],
            identity_confidence=("probable" if verify_identity
                                 else "verified"))
        anomalies = store.upsert_event(event)
        stats["anomalies"] += len(anomalies)
        stats["events"] += 1
        if m["finished"] and m["home_goals"] is not None:
            final_at = (m["source_version"] and
                        parse_utc(m["source_version"])
                        if _is_iso(m["source_version"]) else m["start_utc"])
            result = Result(
                result_id=stable_id("res", PROVIDER_ID, eid,
                                    m["source_version"] or "v0"),
                event_id=eid,
                provider=PROVIDER_ID,
                retrieved_at_utc=parse_utc(m["source_version"])
                if _is_iso(m["source_version"]) else m["start_utc"],
                source_url=url,
                raw_payload_hash=sha256_text(
                    json.dumps(m["raw_match"], sort_keys=True)),
                final_status="finished",
                officially_final_at_utc=final_at,
                home_goals=m["home_goals"],
                away_goals=m["away_goals"],
                result_type_kind=m["final_kind"],
                version=m["source_version"],
            )
            stats["anomalies"] += len(store.add_result(result))
            stats["results"] += 1
    store.commit()
    return stats


def _is_iso(value) -> bool:
    try:
        parse_utc(str(value))
        return True
    except (ValueError, TypeError):
        return False
