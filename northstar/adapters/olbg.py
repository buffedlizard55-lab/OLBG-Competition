"""OLBG adapter - manual snapshots only.

POLICY: OLBG Terms of Use (Invendium Ltd, last updated 09 July 2025,
verified 2026-09-19) reserve all IP rights (9.1), restrict use to personal
non-commercial purposes (7.1, 13.3), prohibit copying/distribution without
written consent (9.2), and prohibit unconsented access (7.3). robots.txt
disallows /api/, /sports/, /tipster/.

Consequences, enforced here:
- ``auto_fetch()`` raises PolicyError unconditionally. There is no live
  collection path in this codebase.
- The only supported mode is ingesting *human-captured* snapshots stored in
  data/raw/olbg_*.md for review.
- Imported tips are ``pending``: they carry no permissioned odds and no
  official result path, so they can never enter verified PnL.
"""
from __future__ import annotations

import hashlib
import os
import re
from datetime import datetime
from typing import Dict, List, Optional

from .. import models
from ..db import Store
from ..models import (
    ANOMALY_CONSENSUS_DRIFT, TIP_STATUS_PENDING, Tip, stable_id, utcnow,
)
from ..policy import (MODE_AUTO_API, MODE_MANUAL_SNAPSHOT, PolicyError,
                      get_policy)

PROVIDER_ID = "olbg"

# URL pattern verified on the live site 2026-09-19:
# /betting-tips/{Sport}/{Region}/{League}/{Event}/{sport_num}?event_id={id}
EVENT_URL_RE = re.compile(
    r"https://www\.olbg\.com/betting-tips/([A-Za-z_]+)/([A-Za-z0-9_]+)/"
    r"([A-Za-z0-9_]+)/([A-Za-z0-9_@%& ]+?)/(\d+)\?event_id=(\d+)")
CONSENSUS_RE = re.compile(r"\*\*(\d+)\s*/\s*(\d+)\s*Win Tips\*\*")
CONSENSUS_TABLE_RE = re.compile(
    r"\|\s*•\s*\|\s*(.+?)\s*\|\s*\*\*(\d+)\*\*\s*/\s*(\d+)\s*\|\s*(\d+)%\s*\|")

SPORT_MAP = {
    "Football": "football", "Horse_Racing": "horse_racing",
    "Rugby_Union": "rugby_union", "American_Football": "american_football",
    "Baseball": "baseball", "Motor_Racing": "motor_racing",
    "Darts": "darts", "Boxing": "boxing", "Greyhounds": "greyhounds",
}


_CAPTURED_DATE_RE = re.compile(
    r"^\s*Captured:\s*(\d{4}-\d{2}-\d{2})(?:[T ]\d{2}:\d{2}:\d{2}Z)?",
    re.MULTILINE,
)


def _captured_at_from_header(path: str) -> Optional[datetime]:
    """Use the snapshot's own provenance date for relative labels.

    Replaying a historical manual capture on a later day must not turn
    ``Today`` into a different calendar date.  The header is provenance, not
    a network observation, so the fallback remains explicit when it is absent.
    """
    try:
        with open(path, "r", encoding="utf-8") as fh:
            match = _CAPTURED_DATE_RE.search(fh.read(4000))
    except OSError:
        return None
    if not match:
        return None
    try:
        return models.parse_utc(match.group(1) + "T00:00:00Z")
    except ValueError:
        return None


def _parse_olbg_time_label(label: str, captured_at: datetime
                           ) -> Optional[datetime]:
    """'Today 14:45' / 'Tomorrow 09:00' -> UTC kickoff (UK local time),
    relative to the capture instant. None if unparsable."""
    m = re.match(r"^(Today|Tomorrow)\s+(\d{1,2}):(\d{2})$", label or "")
    if not m:
        return None
    from ..timeutil import uk_local_to_utc
    from datetime import time as dtime, timedelta
    day = captured_at + timedelta(days=1 if m.group(1) == "Tomorrow" else 0)
    try:
        return uk_local_to_utc(day.date(),
                               dtime(hour=int(m.group(2)),
                                     minute=int(m.group(3))))
    except ValueError:
        return None


def auto_fetch(url: str) -> str:  # pragma: no cover - policy guard
    """Exists only to fail loudly. OLBG does not permit automated access."""
    get_policy("olbg").assert_permitted(MODE_AUTO_API)
    raise PolicyError("unreachable: auto fetch is policy-blocked for OLBG")


def _snapshot_hash(path: str) -> str:
    with open(path, "r", encoding="utf-8") as fh:
        return hashlib.sha256(fh.read().encode("utf-8")).hexdigest()


def parse_index_snapshot(path: str) -> List[Dict]:
    """Parse a manual /betting-tips index snapshot (markdown render).

    Returns tip-card dicts: event name/url, sport, league, time label,
    selection, market, consensus (wins/total), percentage, status.
    """
    get_policy("olbg").assert_permitted(MODE_MANUAL_SNAPSHOT)
    with open(path, "r", encoding="utf-8") as fh:
        text = fh.read()
    cards: List[Dict] = []
    # Split on event-link bullets, then walk the line blocks. The verified
    # structure per card (2026-09-19 capture) is:
    #   - [**Event**](event_url "")
    #   <blank> League <blank> (or Time for darts-style cards)
    #   Today|Tomorrow HH:MM
    #   [**Selection**](selection_url "")
    #   Market name
    #   **W/T Win Tips**  PCT%  N comments  [Expired]
    blocks = re.split(r"\n- \[", text)
    for block in blocks[1:]:
        m_url = re.match(r"\*\*([^*]+)\*\*\]\((https://[^)\s]+)", block)
        if not m_url:
            continue
        name, url = m_url.group(1), m_url.group(2)
        m_ev = EVENT_URL_RE.search(url)
        sport = m_ev.group(1) if m_ev else "unknown"
        event_id = m_ev.group(6) if m_ev else ""
        rest = block[m_url.end():]
        rest = rest.split("\n", 1)[1] if "\n" in rest else ""
        lines = [ln.strip() for ln in rest.splitlines()]
        lines = [ln for ln in lines if ln]
        league = ""
        time_label = ""
        selection = ""
        market = ""
        for i, ln in enumerate(lines):
            if re.match(r"^(\d{1,2}:\d{2})$", ln) or \
                    re.match(r"^(Today|Tomorrow|In \d+ days?)\s+\d{1,2}:\d{2}$", ln):
                time_label = ln
            elif (not league and not selection and not ln.startswith("[")
                  and not re.match(r"^\d{1,2}:\d{2}(\s|$)", ln)
                  and "Win Tips" not in ln and not ln.endswith("%")
                  and "comment" not in ln and ln != "Expired"
                  and ln != "Add" and not ln.startswith("**")
                  and i < 4):
                league = ln
            elif ln.startswith("[**") and not selection:
                sel_m = re.match(r"^\[\*\*([^*]+)\*\*\]", ln)
                if sel_m:
                    selection = sel_m.group(1)
            elif (selection and not market
                  and not ln.startswith("[") and not ln.startswith("**")
                  and not re.match(r"^\d{1,2}:\d{2}(\s|$)", ln)
                  and "Win Tips" not in ln and not ln.endswith("%")
                  and "comment" not in ln and ln != "Expired"
                  and ln != "Add" and not ln.isdigit()
                  and not re.match(r"^\d+ experts?$", ln)):
                market = ln
        cons = CONSENSUS_RE.search(block)
        cons_wins = int(cons.group(1)) if cons else None
        cons_total = int(cons.group(2)) if cons else None
        pct = re.search(r"\n(\d+)%\n", block)
        status = "expired" if re.search(r"\bExpired\b", block) else "open"
        cards.append({
            "event_name": name, "sport": sport, "league": league,
            "time_label": time_label, "selection": selection,
            "market": market, "consensus_wins": cons_wins,
            "consensus_total": cons_total,
            "consensus_pct": (int(pct.group(1)) if pct else None),
            "status": status, "url": url, "source_event_id": event_id,
        })
    return cards


def parse_event_snapshot(path: str) -> Dict:
    """Parse a manual OLBG event-page snapshot: title, consensus table,
    best-tipster tip (selection + text + displayed stats)."""
    get_policy("olbg").assert_permitted(MODE_MANUAL_SNAPSHOT)
    with open(path, "r", encoding="utf-8") as fh:
        text = fh.read()
    title_m = re.search(r"^# (.+?) Tips\s*$", text, re.MULTILINE)
    event_name = title_m.group(1).strip() if title_m else ""
    consensus = []
    for row in CONSENSUS_TABLE_RE.finditer(text):
        consensus.append({"selection": row.group(1).strip(),
                          "wins": int(row.group(2)),
                          "total": int(row.group(3)),
                          "pct": int(row.group(4))})
    # Best tipster's tip: the first "WIN @" block after the header.
    best = None
    m = re.search(r"### Best Tipster's Tip\n+#### (.+?)\n+##### (.+?)\n",
                  text)
    if m:
        seg_start = m.end()
        tip_m = re.search(r"WIN @\s*\n+(.*?)(?:\n+Annual Profit|\Z)",
                          text[seg_start:], re.DOTALL)
        profit_m = re.search(r"Annual Profit(-?\d+)", text[seg_start:])
        strike_m = re.search(r"Annual Strike Rate(\d+) ?%", text[seg_start:])
        best = {
            "selection": m.group(1).strip(),
            "market": m.group(2).strip(),
            "text": (tip_m.group(1).strip() if tip_m else ""),
            "annual_profit": int(profit_m.group(1)) if profit_m else None,
            "annual_strike_rate_pct": (int(strike_m.group(1))
                                       if strike_m else None),
        }
    return {"event_name": event_name, "consensus": consensus,
            "best_tip": best, "snapshot_sha256": _snapshot_hash(path)}


def _split_name(event_name: str):
    parts = re.split(r"\s+(?:v|vs)\.?\s+", event_name, maxsplit=1)
    if len(parts) == 2:
        return parts[0].strip(), parts[1].strip()
    return event_name.strip(), "(unresolved)"


def _register_olbg_event(store: Store, event_id: str, sport: str,
                         competition: str, event_name: str,
                         start_utc: datetime, url: str,
                         version: str) -> None:
    home, away = _split_name(event_name)
    store.upsert_event(models.Event(
        event_id=event_id,
        sport=SPORT_MAP.get(sport, sport.lower().replace("_", " ")),
        competition=competition or f"OLBG {sport}",
        home_team_id="olbg-home", home_team=home,
        away_team_id="olbg-away", away_team=away,
        scheduled_start_utc=start_utc,
        status="scheduled",
        source_event_id=event_id,
        source_provider=PROVIDER_ID,
        source_url=url,
        source_version=version,
        identity_confidence="unmatched",
    ))


def ingest_snapshots(store: Store, raw_dir: str,
                     captured_at: Optional[datetime] = None) -> Dict:
    """Import manual OLBG snapshots into the store as *pending* imported
    tips and imported-tipster entrants. Never verified, never PnL."""
    index_path = os.path.join(
        raw_dir, "olbg_betting_tips_index_2026-09-19.md")
    if captured_at is None:
        captured_at = (_captured_at_from_header(index_path)
                       or utcnow())
    stats = {"index_cards": 0, "event_tips": 0, "tipsters": 0,
             "anomalies": []}

    cards_by_event_id: Dict[str, Dict] = {}
    if os.path.exists(index_path):
        for card in parse_index_snapshot(index_path):
            if not card["event_name"] or not card["selection"]:
                continue
            if card["source_event_id"]:
                cards_by_event_id[card["source_event_id"]] = card
            event_id = stable_id("ev-olbg", card["source_event_id"])
            start = _parse_olbg_time_label(card["time_label"], captured_at)
            if start is not None:
                # Only create the event row when the snapshot gives a
                # parsable kickoff; otherwise the tip stays linked to a
                # dangling event id and the UI shows it as unmatched.
                _register_olbg_event(
                    store, event_id, card["sport"], card["league"],
                    card["event_name"], start, card["url"],
                    _snapshot_hash(index_path))
            tip_id = stable_id("tip-olbg", card["url"], card["selection"],
                               card["market"])
            store.add_tip(Tip(
                tip_id=tip_id,
                tipster_id=f"olbg-crowd-{card['sport'].lower()}",
                strategy_id="imported",
                event_id=stable_id("ev-olbg", card["source_event_id"]),
                market=f"olbg:{card['market'] or 'unknown'}",
                selection=card["selection"],
                selection_key="crowd",
                published_at_utc=captured_at,
                collected_at_utc=captured_at,
                cutoff_at_utc=captured_at,
                odds_decimal=None,
                odds_source=None,
                source_url=card["url"],
                raw_payload_hash=_snapshot_hash(index_path),
                status=TIP_STATUS_PENDING,
                notes=(f"manual OLBG snapshot {card['time_label']} "
                       f"consensus {card['consensus_wins']}/"
                       f"{card['consensus_total']}; no permissioned odds, "
                       f"no official result path -> can never settle")))
            stats["index_cards"] += 1

    event_path = os.path.join(
        raw_dir, "olbg_event_mancity_sunderland_2026-09-19.md")
    if os.path.exists(event_path):
        parsed = parse_event_snapshot(event_path)
        # Register the event row too (kickoff from the matching index card,
        # if the snapshot shares its event_id).
        with open(event_path, "r", encoding="utf-8") as fh:
            m_ev = re.search(r"event_id=(\d+)", fh.read())
        canonical_id = m_ev.group(1) if m_ev else \
            parsed["event_name"].replace(" v", "-")
        ev_id = stable_id("ev-olbg", canonical_id)
        idx_card = cards_by_event_id.get(canonical_id)
        if idx_card is not None:
            start = _parse_olbg_time_label(idx_card["time_label"],
                                           captured_at)
            if start is not None:
                _register_olbg_event(store, ev_id, idx_card["sport"],
                                     idx_card["league"],
                                     parsed["event_name"], start,
                                     idx_card["url"],
                                     parsed["snapshot_sha256"])
        for row in parsed["consensus"]:
            tip_id = stable_id("tip-olbg-ev", parsed["snapshot_sha256"],
                               row["selection"])
            store.add_tip(Tip(
                tip_id=tip_id,
                tipster_id=f"olbg-crowd-{parsed['event_name'].lower()}",
                strategy_id="imported",
                event_id=ev_id,
                market="olbg:Full Time Result" if "Full Time" in str(row)
                else "olbg:unknown",
                selection=row["selection"],
                selection_key="crowd",
                published_at_utc=captured_at,
                collected_at_utc=captured_at,
                cutoff_at_utc=captured_at,
                source_url=("https://www.olbg.com/betting-tips/Football/UK/"
                            "England_Premier_League/"
                            "Man_City_v_Sunderland/1?event_id=2039511"),
                raw_payload_hash=parsed["snapshot_sha256"],
                status=TIP_STATUS_PENDING,
                notes=(f"snapshot consensus {row['wins']}/{row['total']} "
                       f"({row['pct']}%)")))
            stats["event_tips"] += 1
        best = parsed.get("best_tip")
        if best:
            store.upsert_entrant(
                "olbg-best-tipster-mancity-sunderland",
                f"OLBG best tipster ({parsed['event_name']})",
                "imported_tipster",
                (f"Anonymous 'Best Tipster' from manual snapshot 2026-09-19: "
                 f"annual profit {best['annual_profit']}, strike rate "
                 f"{best['annual_strike_rate_pct']}%. Displayed stats are "
                 f"OLBG self-reported (10-point stake basis) and unverified."))
            stats["tipsters"] += 1
    store.commit()
    return stats


def detect_consensus_drift(store: Store, raw_dir: str,
                           old_index_path: str, new_index_path: str,
                           captured_at_old: datetime,
                           captured_at_new: datetime) -> List[str]:
    """Compare two manual index snapshots of the same site and flag events
    whose consensus counts changed between captures (source drift)."""
    anomalies = []
    old_cards = {c["url"]: c for c in parse_index_snapshot(old_index_path)}
    new_cards = {c["url"]: c for c in parse_index_snapshot(new_index_path)}
    for url, new in new_cards.items():
        old = old_cards.get(url)
        if old and (old.get("consensus_wins") != new.get("consensus_wins")
                    or old.get("consensus_total") != new.get("consensus_total")):
            aid = stable_id("an", ANOMALY_CONSENSUS_DRIFT, url,
                            new.get("consensus_wins"))
            store.add_anomaly(models.Anomaly(
                anomaly_id=aid, kind=ANOMALY_CONSENSUS_DRIFT,
                entity_type="event", entity_id=stable_id("ev-olbg",
                                                         new["event_name"]),
                detected_at_utc=captured_at_new,
                detail=(f"consensus changed {old.get('consensus_wins')}/"
                        f"{old.get('consensus_total')} -> "
                        f"{new.get('consensus_wins')}/"
                        f"{new.get('consensus_total')} between manual "
                        f"captures {captured_at_old:%Y-%m-%d} and "
                        f"{captured_at_new:%Y-%m-%d}"),
                source_urls=[url]))
            anomalies.append(aid)
    store.commit()
    return anomalies
