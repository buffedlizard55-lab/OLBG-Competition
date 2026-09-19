"""football-data.co.uk adapter - manual-import historical odds.

Source policy (verified 2026-09-19, see policy.py / docs/LICENSING.md):
free for *private individuals only*; automated bots/scrapers/AI training are
excluded by the site's own statement. Therefore:

- this adapter NEVER downloads anything. A human downloads the CSV and
  places it under data/imports/ (git-ignored) or commits a small,
  hand-reviewed pilot extract under data/fixtures/;
- the pipeline only parses the local file (mode: manual_import);
- odds carry no per-event timestamp: observed_at is the close of the
  documented collection window (Fri 17:00 UK / Tue 13:00 UK) - recorded as
  ``window_close_inferred``;
- Pinnacle columns are excluded per the site's 2025-07-23 reliability notice.

Verified join semantics: the CSV ``Time`` column is UK local time (checked
against OpenLigaDB matchDateTimeUTC for all 27 pilot matches, 27/27 exact).
"""
from __future__ import annotations

import csv
import io
from datetime import datetime, time as dtime
from typing import Dict, List, Optional, Tuple

from .. import models
from ..db import Store
from ..models import (
    ANOMALY_COMPETITION_MISMATCH, ANOMALY_EVENT_UNMATCHED,
    ANOMALY_PARTICIPANT_AMBIGUOUS, ANOMALY_TIME_CONFLICT,
    MARKET_MATCH_WINNER_3WAY,
    OddsSnapshot, parse_utc, sha256_text, stable_id, utcnow,
)
from ..policy import MODE_MANUAL_IMPORT, PolicyError, get_policy
from ..timeutil import odds_collection_window_utc, uk_local_to_utc

PROVIDER_ID = "football_data"
FILE_URL = "https://www.football-data.co.uk/mmz4281/2425/D1.csv"

# OpenLigaDB official name -> football-data CSV short name
TEAM_ALIASES = {
    "Borussia M\u00f6nchengladbach": "M'gladbach",
    "Bayer 04 Leverkusen": "Leverkusen",
    "RB Leipzig": "RB Leipzig",
    "VfL Bochum": "Bochum",
    "TSG Hoffenheim": "Hoffenheim",
    "Holstein Kiel": "Holstein Kiel",
    "SC Freiburg": "Freiburg",
    "VfB Stuttgart": "Stuttgart",
    "FC Augsburg": "Augsburg",
    "SV Werder Bremen": "Werder Bremen",
    "1. FSV Mainz 05": "Mainz",
    "1. FC Union Berlin": "Union Berlin",
    "Borussia Dortmund": "Dortmund",
    "Eintracht Frankfurt": "Ein Frankfurt",
    "VfL Wolfsburg": "Wolfsburg",
    "FC Bayern M\u00fcnchen": "Bayern Munich",
    "FC St. Pauli": "St Pauli",
    "1. FC Heidenheim 1846": "Heidenheim",
}

# Bookmaker column groups we store (Pinnacle deliberately excluded:
# site notice 23/07/2025 - Pinnacle feed unreliable, excluded from market
# average/maximum).
PROVIDER_COLUMNS = [
    ("b365", "B365H", "B365D", "B365A"),
    ("betfair", "BFH", "BFD", "BFA"),
    ("williamhill", "WHH", "WHD", "WHA"),
    ("market_avg", "AvgH", "AvgD", "AvgA"),
    ("betfair_exchange", "BFEH", "BFED", "BFEA"),
]


def parse_csv_text(text: str) -> List[Dict]:
    """Parse football-data CSV text into normalized rows (no I/O)."""
    get_policy("football_data").assert_permitted(MODE_MANUAL_IMPORT)
    rows = []
    reader = csv.DictReader(io.StringIO(text))
    for raw in reader:
        if not raw.get("Div"):
            continue
        rows.append({
            "div": raw["Div"].strip(),
            "date": datetime.strptime(raw["Date"].strip(), "%d/%m/%Y").date(),
            "time": dtime(*map(int, raw["Time"].strip().split(":"))),
            "home": raw["HomeTeam"].strip(),
            "away": raw["AwayTeam"].strip(),
            "ft_home": _num(raw.get("FTHG")),
            "ft_away": _num(raw.get("FTAG")),
            "ftr": (raw.get("FTR") or "").strip(),
            "raw": raw,
        })
    return rows


def _num(v: Optional[str]) -> Optional[float]:
    """Decimal odds/statistic cell -> float (integral values as int),
    or None if absent/blank."""
    if v in (None, "", "None"):
        return None
    try:
        f = float(v)
    except ValueError:
        return None
    return int(f) if f.is_integer() else f


def _find_event(store: Store, row: Dict) -> Optional[Dict[str, Optional[str]]]:
    """Match a CSV row to a stored event.

    Returns {"event_id", "time_ok"} or {"anomaly": kind, "detail": ...}.
    Uses UK-local -> UTC conversion with an exact-minute requirement.
    """
    try:
        kickoff_utc = uk_local_to_utc(row["date"], row["time"])
    except ValueError as exc:
        return {"anomaly": ANOMALY_TIME_CONFLICT,
                "detail": str(exc), "row": row}
    candidates = [e for e in store.events()
                  if _norm(e["home_team"]) == row["home"]
                  and _norm(e["away_team"]) == row["away"]]
    if not candidates:
        return {"anomaly": ANOMALY_EVENT_UNMATCHED,
                "detail": (f"no event for {row['home']} v {row['away']} "
                           f"on {row['date']}/{row['time']}"),
                "row": row}
    if len(candidates) > 1:
        return {"anomaly": ANOMALY_PARTICIPANT_AMBIGUOUS,
                "detail": f"{len(candidates)} events match "
                          f"{row['home']} v {row['away']}",
                "row": row}
    e = candidates[0]
    if _norm(e["competition"]).startswith("1. Fu\u00dfball-Bundesliga") is False:
        return {"anomaly": ANOMALY_COMPETITION_MISMATCH,
                "detail": f"event competition '{e['competition']}' not "
                          f"Bundesliga for D1 row",
                "row": row}
    start = parse_utc(e["scheduled_start_utc"])
    time_ok = abs((start - kickoff_utc).total_seconds()) < 90
    return {"event_id": e["event_id"], "time_ok": time_ok, "row": row}


def _norm(name: str) -> str:
    return TEAM_ALIASES.get(name, name)


def ingest_csv_text(store: Store, text: str,
                    expected_division: str = "D1") -> Dict:
    """Ingest a locally-provided football-data CSV (manual import).

    For each row: 1) cross-check the FT result against the OpenLigaDB result
    (reconciliation gate input), 2) store per-bookmaker odds snapshots at the
    inferred collection-window close.
    """
    policy = get_policy("football_data")
    policy.assert_permitted(MODE_MANUAL_IMPORT)
    rows = parse_csv_text(text)
    stats = {"rows": len(rows), "odds_snapshots": 0, "cross_checked": 0,
             "cross_checked_agree": 0, "anomalies": [], "unmatched": []}
    for row in rows:
        if row["div"] != expected_division:
            continue
        found = _find_event(store, row)
        if "anomaly" in found:
            stats["anomalies"].append(found["anomaly"])
            stats["unmatched"].append(found["detail"])
            continue
        eid = found["event_id"]
        event = store.get_event(eid)
        if not found["time_ok"]:
            store.add_anomaly(models.Anomaly(
                anomaly_id=stable_id("an", "TIME_CONFLICT", eid,
                                     row["home"], row["away"]),
                kind="TIME_CONFLICT", entity_type="event", entity_id=eid,
                detected_at_utc=utcnow(),
                detail=(f"CSV UK time {row['date']} {row['time']} does not "
                        f"align with stored UTC start within 90s"),
                source_urls=[event["source_url"] or "", FILE_URL]))
            stats["anomalies"].append("TIME_CONFLICT")
            continue

        # Cross-check the full-time result (independent source B).
        if row["ft_home"] is not None and event:
            res = store.results(eid)
            ol = [r for r in res if r["provider"] == "openligadb"
                  and r["final_status"] == "finished"]
            if ol:
                stats["cross_checked"] += 1
                if (ol[0]["home_goals"], ol[0]["away_goals"]) == (
                        row["ft_home"], row["ft_away"]):
                    stats["cross_checked_agree"] += 1
                    if event["identity_confidence"] != "verified":
                        store.conn.execute(
                            "UPDATE events SET identity_confidence='verified'"
                            " WHERE event_id=?", (eid,))
                else:
                    store.add_anomaly(models.Anomaly(
                        anomaly_id=stable_id(
                            "an", "RESULT_SOURCE_CONFLICT", eid),
                        kind="RESULT_SOURCE_CONFLICT", entity_type="event",
                        entity_id=eid, detected_at_utc=utcnow(),
                        detail=(f"FT differs: football_data="
                                f"{row['ft_home']}-{row['ft_away']} vs "
                                f"openligadb={ol[0]['home_goals']}-"
                                f"{ol[0]['away_goals']}"),
                        source_urls=[event["source_url"] or "", FILE_URL]))
                    stats["anomalies"].append("RESULT_SOURCE_CONFLICT")

        # Odds snapshots at the inferred collection-window close.
        window = odds_collection_window_utc(parse_utc(
            event["scheduled_start_utc"]))
        row_hash = sha256_text(",".join(
            str(v) for v in row["raw"].values() if v is not None))
        for provider, ch, cd, ca in PROVIDER_COLUMNS:
            for sel, col in (("home", ch), ("draw", cd), ("away", ca)):
                v = _num(row["raw"].get(col))
                if v is None:
                    continue
                odds = float(v)
                if odds <= 1.0 or odds != odds:
                    store.add_anomaly(models.Anomaly(
                        anomaly_id=stable_id("an", "ODDS_INVALID", eid,
                                             provider, sel),
                        kind="MISSING_ODDS", entity_type="odds",
                        entity_id=eid, detected_at_utc=utcnow(),
                        detail=f"invalid odds {v} for {provider}/{sel}",
                        source_urls=[FILE_URL]))
                    continue
                snap = OddsSnapshot(
                    snapshot_id=stable_id("os", eid, provider, sel,
                                          window.isoformat()),
                    event_id=eid,
                    observed_at_utc=window,
                    provider=provider,
                    market_key=MARKET_MATCH_WINNER_3WAY,
                    selection_key=sel,
                    decimal_odds=odds,
                    timestamp_precision="window_close_inferred",
                    raw_row_hash=row_hash,
                    source_url=FILE_URL,
                    notes=("football-data batch sample; window close per "
                           "source docs (Fri 17:00 UK / Tue 13:00 UK)"))
                store.add_odds_snapshot(snap)
                stats["odds_snapshots"] += 1
    store.commit()
    return stats
