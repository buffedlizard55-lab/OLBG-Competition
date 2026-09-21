"""Cross-check manually snapshotted OLBG events against permitted fixtures.

OLBG snapshots are review evidence only (manual, ToS-compliant); they carry
short team names and relative kickoff labels ("Today 15:00").  Once the
same fixture exists in an OpenLigaDB capture, the two can be compared:

- team identity via the curated table ``data/aliases/football_olbg.json``
  (evidence-linked, no heuristics - see northstar.aliases);
- kickoff: OLBG-derived UTC vs OpenLigaDB ``matchDateTimeUTC``.

A match on teams + calendar day with a different kickoff instant is a
``TIME_CONFLICT`` anomaly on the OLBG event (the permitted source's UTC is
authoritative; the OLBG row is *not* edited).  Found 2026-09-21: all five
matchable OLBG football cards were exactly 5 h earlier than OpenLigaDB -
consistent with the manual snapshot's labels having been rendered in a
UTC-5 locale rather than UK time.  The anomaly makes that visible instead
of leaving wrong kickoffs in the upcoming-bets view.
"""
from __future__ import annotations

from datetime import timedelta
from typing import Any, Dict, List

from . import models
from .aliases import alias_version, canonical_name
from .db import Store
from .models import parse_utc, stable_id, utcnow

ALIAS_SPORT = "football_olbg"


def reconcile_olbg_events(store: Store) -> Dict[str, Any]:
    """Return {"checked", "matched", "time_conflicts", "unmatched", "rows"}."""
    olbg = [e for e in store.events()
            if e["source_provider"] == "olbg" and e["sport"] == "football"]
    official = [e for e in store.events()
                if e["source_provider"] == "openligadb"
                and e["sport"] == "football"]
    by_key: Dict[Any, List[Dict[str, Any]]] = {}
    for e in official:
        day = parse_utc(e["scheduled_start_utc"]).date()
        by_key.setdefault((e["home_team"], e["away_team"]), []).append(e)
    out = {"checked": 0, "matched": 0, "time_conflicts": 0, "unmatched": 0,
           "alias_table": alias_version(ALIAS_SPORT), "rows": []}
    for e in olbg:
        out["checked"] += 1
        home = canonical_name(ALIAS_SPORT, e["home_team"])
        away = canonical_name(ALIAS_SPORT, e["away_team"])
        start = parse_utc(e["scheduled_start_utc"])
        candidates = [o for o in by_key.get((home, away), [])
                      if abs(parse_utc(o["scheduled_start_utc"]) - start)
                      <= timedelta(hours=36)]
        row = {"olbg_event_id": e["event_id"], "event": f"{home} v {away}",
               "olbg_start_utc": e["scheduled_start_utc"],
               "official_event_id": None, "official_start_utc": None,
               "status": "unmatched"}
        if not candidates:
            out["unmatched"] += 1
            out["rows"].append(row)
            continue
        o = min(candidates, key=lambda c: abs(
            parse_utc(c["scheduled_start_utc"]) - start))
        out["matched"] += 1
        row.update({"official_event_id": o["event_id"],
                    "official_start_utc": o["scheduled_start_utc"],
                    "official_source_url": o["source_url"]})
        delta = parse_utc(o["scheduled_start_utc"]) - start
        if delta == timedelta(0):
            row["status"] = "agree"
        else:
            row["status"] = "time_conflict"
            row["delta_hours"] = delta.total_seconds() / 3600.0
            out["time_conflicts"] += 1
            aid = stable_id("an", models.ANOMALY_TIME_CONFLICT,
                            e["event_id"], "olbg-vs-openligadb")
            store.add_anomaly(models.Anomaly(
                anomaly_id=aid,
                kind=models.ANOMALY_TIME_CONFLICT,
                entity_type="event", entity_id=e["event_id"],
                detected_at_utc=utcnow(),
                detail=(f"OLBG snapshot kickoff {e['scheduled_start_utc']} "
                        f"differs from OpenLigaDB {o['scheduled_start_utc']} "
                        f"for {home} v {away} by {row['delta_hours']:+.1f} h; "
                        "the manual snapshot's relative time label was "
                        "parsed as UK local time - the permitted source's "
                        "UTC is authoritative, the OLBG row is left as "
                        "captured and flagged for review"),
                source_urls=[e["source_url"] or "", o["source_url"] or ""]))
        out["rows"].append(row)
    store.commit()
    return out
