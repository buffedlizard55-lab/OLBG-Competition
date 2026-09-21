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
from datetime import timedelta
from typing import Dict, List, Optional

from .. import models, timeutil
from ..db import Store
from ..models import (
    EVENT_STATUS_FINISHED, EVENT_STATUS_POSTPONED, EVENT_STATUS_SCHEDULED,
    Event, Result,
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


def fetch_url(url: str) -> str:
    """Generic policy-gated GET against the OpenLigaDB API base.

    Refuses any URL outside ``api.openligadb.de`` (the only endpoint the
    registered policy covers) and any run when the automated-API mode is
    not permitted.  Used by CI capture (network) and injectable in tests.
    """
    get_policy("openligadb").assert_permitted(MODE_AUTO_API)
    if not url.startswith(API_BASE + "/"):
        raise PolicyError(f"refusing non-OpenLigaDB URL: {url}")
    req = urllib.request.Request(url, headers={"User-Agent":
                                               "NorthstarLab/0.3 (paper-trading research)"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return resp.read().decode("utf-8")


def fetch_matchdata(league_shortcut: str, league_season: int,
                    group_order: Optional[int] = None) -> str:
    """Live fetch (used in CI / environments with network). Refuses to run
    unless the source policy permits automated API collection."""
    return fetch_url(league_url(league_shortcut, league_season, group_order))


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

# How the "available to the desk" timestamp is derived per sport. The
# football pilot uses the source's lastUpdateDateTime (post-match data-entry
# timestamps that sit between kickoff and settlement there). DEL community
# rows were batch-edited at end of season (e.g. 2025-04-07 for September
# games), which would wrongly erase all walk-forward history; instead the
# result becomes visible a fixed INFERRED_GAME_DURATION after start. This is
# an explicit conservative construction (a desk cannot know a game is final
# before it ends), never a claim the source timestamps results at that
# second. It is documented in docs/STATUS.md.
INFERRED_GAME_DURATION = {
    "ice_hockey": timedelta(hours=3),
    # Darts: audit of the three committed 2025 PDC events (141 matches,
    # docs/DARTS-AUDIT.md) measured same-day result entry lag of 1.2h-10.5h
    # (median 1.7h-3.0h; some weekend sessions batch-entered days later),
    # and an evening session's individual match can start late and run long.
    # +12h is conservative against every observed same-day entry and against
    # match end, while still releasing a round before the next day's first
    # decision cutoff (same documented construction as hockey).
    "darts": timedelta(hours=12),
}


def availability_for(sport: Optional[str], start_utc,
                     source_version) -> "models.datetime":
    """officially_final_at_utc per sport (see INFERRED_GAME_DURATION)."""
    dur = INFERRED_GAME_DURATION.get(sport or "")
    if dur is not None:
        return start_utc + dur
    if source_version and _is_iso(source_version):
        return parse_utc(source_version)
    return start_utc


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
        # Irregularity flag: OT/shootout entries are only possible after a
        # *drawn* regulation. A decisive "after regulation" entry together
        # with an OT/SO entry is a contradiction in the community-entered
        # source. The priority final is still used, but the conflict is
        # recorded for review instead of silently smoothed over.
        kinds = {r.get("resultTypeKind") for r in m.get("matchResults", [])}
        reg_entry = next((r for r in m.get("matchResults", [])
                          if r.get("resultTypeKind") == RESULT_KIND_AFTER_90),
                         None)
        has_post_reg = bool({RESULT_KIND_AFTER_EXTRA,
                             RESULT_KIND_AFTER_PENALTIES} & kinds)
        # Audit 2026-09-20 (PDCPCF 2025 matchID 79962, Price v Littler):
        # the same result kind can appear several times with conflicting
        # scores (a real 8-11 plus two stale 0-0 duplicates with
        # consecutive resultIDs). The first entry is retained, but the
        # conflict is flagged for the review queue instead of silently
        # resolved.
        duplicate_conflict = False
        if final is not None:
            duplicate_conflict = any(
                (r.get("pointsTeam1"), r.get("pointsTeam2"))
                != (final.get("pointsTeam1"), final.get("pointsTeam2"))
                for r in m.get("matchResults", [])
                if r.get("resultTypeKind") == final.get("resultTypeKind"))
        kind_inconsistent = bool(duplicate_conflict or (
            reg_entry is not None and has_post_reg
            and reg_entry.get("pointsTeam1") != reg_entry.get("pointsTeam2")))
        inconsistency_reason = (
            "duplicate_conflict" if duplicate_conflict
            else "impossible_layering" if kind_inconsistent else None)
        out.append({
            "match_id": m["matchID"],
            "league_shortcut": m.get("leagueShortcut"),
            "league_season": m.get("leagueSeason"),
            "league_name": m.get("leagueName"),
            "start_utc": parse_utc(m["matchDateTimeUTC"]),
            # Local/UTC consistency: matchDateTime must equal
            # matchDateTimeUTC + CET/CEST.  None when the local field is
            # absent (nothing to check), False = TIME_CONFLICT.
            "local_time_consistent": (
                timeutil.openligadb_local_matches_utc(
                    m["matchDateTime"], m["matchDateTimeUTC"])
                if m.get("matchDateTime") else None),
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
            "kind_inconsistent": kind_inconsistent,
            "inconsistency_reason": inconsistency_reason,
            "source_version": m.get("lastUpdateDateTime"),
            "raw_match": m,
        })
    return out


def ingest_matchday(store: Store, text: str,
                    verify_identity: bool = True,
                    sport: Optional[str] = SPORT_FOOTBALL,
                    as_of=None) -> Dict:
    """Ingest one matchday payload: events + primary results.

    ``verify_identity``: when True, events start at ``probable`` identity
    confidence; the cross-check step (ingest_pilot in the pipeline) upgrades
    to ``verified`` once an independent source agrees.

    ``as_of`` (aware datetime, optional): the capture instant. Unfinished
    matches whose scheduled start is *after* ``as_of`` are ``scheduled``
    (upcoming fixtures, forward-test candidates); unfinished matches at or
    before ``as_of`` are unresolved -> ``postponed`` (review queue), the
    pre-existing behaviour which remains the default when ``as_of`` is None.
    """
    policy = get_policy("openligadb")
    policy.assert_permitted(MODE_AUTO_API)  # documents the mode even offline
    if as_of is not None and as_of.tzinfo is None:
        raise ValueError("as_of must be a timezone-aware datetime")
    matches = parse_matchday(text, sport=sport)
    stats = {"events": 0, "results": 0, "anomalies": 0, "event_ids": []}
    # Source-metadata repair: a match row with leagueSeason null (seen live
    # on del/2024 matchday 40, matchID 76412) would otherwise leak "None"
    # into ids and URLs. Normalise to the *modal* season of unambiguous rows
    # in the same payload and flag the repair for review - never silently.
    seasons = {}
    for m in matches:
        if m["league_season"] is not None and m["league_shortcut"]:
            key = m["league_shortcut"]
            seasons[key] = seasons.get(key, {})
            seasons[key][m["league_season"]] = \
                seasons[key].get(m["league_season"], 0) + 1
    modal_season = {k: max(v, key=v.get) for k, v in seasons.items()}
    for m in matches:
        season = m["league_season"]
        if season is None:
            season = modal_season.get(m["league_shortcut"], "unknown")
        eid = event_id_for({"leagueShortcut": m["league_shortcut"],
                            "leagueSeason": season,
                            "matchID": m["match_id"]})
        url = f"{API_BASE}/getmatchdata/{m['league_shortcut']}/" \
              f"{season}/{m['match_id']}"
        if m["league_season"] is None:
            aid = stable_id("an", models.ANOMALY_MISSING_METADATA, eid)
            if not store.anomaly_exists(aid):
                stats["anomalies"] += 1
            store.add_anomaly(models.Anomaly(
                anomaly_id=aid,
                kind=models.ANOMALY_MISSING_METADATA,
                entity_type="event", entity_id=eid,
                detected_at_utc=models.utcnow(),
                detail=(f"source left leagueSeason null for matchID "
                        f"{m['match_id']} ({m['league_name']}); normalised "
                        f"to {season} from the payload's unambiguous rows "
                        "and flagged for manual review"),
                source_urls=[url]))
        if m["local_time_consistent"] is False:
            aid = stable_id("an", models.ANOMALY_TIME_CONFLICT, eid,
                            "openligadb-local-vs-utc")
            if not store.anomaly_exists(aid):
                stats["anomalies"] += 1
            store.add_anomaly(models.Anomaly(
                anomaly_id=aid,
                kind=models.ANOMALY_TIME_CONFLICT,
                entity_type="event", entity_id=eid,
                detected_at_utc=models.utcnow(),
                detail=(f"matchDateTime {m['raw_match'].get('matchDateTime')} "
                        f"is not matchDateTimeUTC "
                        f"{m['raw_match'].get('matchDateTimeUTC')} + "
                        "CET/CEST; UTC field used, local field distrusted"),
                source_urls=[url]))
        if m["finished"]:
            status = EVENT_STATUS_FINISHED
        elif as_of is not None and m["start_utc"] > as_of:
            status = EVENT_STATUS_SCHEDULED  # genuine upcoming fixture
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
        stats["event_ids"].append(eid)
        if m["finished"] and m["home_goals"] is not None:
            final_at = availability_for(sport, m["start_utc"],
                                        m["source_version"])
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
        if m.get("kind_inconsistent"):
            aid = stable_id("an", models.ANOMALY_RESULT_KIND_INCONSISTENT,
                            eid)
            if not store.anomaly_exists(aid):
                stats["anomalies"] += 1
            if m.get("inconsistency_reason") == "duplicate_conflict":
                detail = (
                    "the same result kind appears more than once with "
                    f"conflicting scores ({m['league_name']} matchID="
                    f"{m['match_id']}; pattern first seen in the 2026-09-20 "
                    "darts audit: one real entry plus stale 0-0 duplicates "
                    "with consecutive resultIDs; seen again on pl/2026 "
                    "matchday 4 on 2026-09-21). The first entry is kept but "
                    "NOT trusted silently: flagged for manual review against "
                    "the official source, outcome kept "
                    f"{m['home_goals']}-{m['away_goals']} ({m['final_kind']})")
            else:
                detail = (
                    "decisive 'after regulation' entry coexists with an "
                    "overtime/shootout entry (impossible layering in "
                    f"community-entered source; matchID={m['match_id']}). "
                    "Final read via hockey priority AfterPenalties > "
                    "AfterExtraTime > After90Minutes; flagged for manual "
                    "review, outcome kept "
                    f"{m['home_goals']}-{m['away_goals']} "
                    f"({m['final_kind']})")
            store.add_anomaly(models.Anomaly(
                anomaly_id=aid,
                kind=models.ANOMALY_RESULT_KIND_INCONSISTENT,
                entity_type="result", entity_id=eid,
                detected_at_utc=models.utcnow(),
                detail=detail,
                source_urls=[url]))
    store.commit()
    return stats


def _is_iso(value) -> bool:
    try:
        parse_utc(str(value))
        return True
    except (ValueError, TypeError):
        return False
