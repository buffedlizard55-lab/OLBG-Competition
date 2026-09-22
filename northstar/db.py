"""SQLite storage with append-only semantics and revision tracking.

Design rules (from docs/data-contract.md):
- tips are immutable; a changed source snapshot gets a new tip_id and the
  collision is recorded as an anomaly, never a silent overwrite;
- results are upserted per (event_id, provider); cross-provider disagreement
  is recorded as RESULT_SOURCE_CONFLICT;
- settlements are append-only; corrections add a revision that supersedes;
- every raw payload keeps its sha256 so source edits are detectable.
"""
from __future__ import annotations

import json
import math
import os
import sqlite3
from typing import Any, Dict, Iterable, List, Optional

from . import models
from .models import (
    Anomaly, Event, OddsSnapshot, Result, Settlement, Tip,
    ANOMALY_EVENT_CHANGED, ANOMALY_DUPLICATE_TIP, ANOMALY_RESULT_SOURCE_CONFLICT,
    ANOMALY_SOURCE_EDITED, parse_utc, utcnow,
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
  event_id TEXT PRIMARY KEY,
  sport TEXT NOT NULL,
  competition TEXT NOT NULL,
  home_team_id TEXT NOT NULL,
  home_team TEXT NOT NULL,
  away_team_id TEXT NOT NULL,
  away_team TEXT NOT NULL,
  scheduled_start_utc TEXT NOT NULL,
  status TEXT NOT NULL,
  group_order INTEGER,
  group_name TEXT,
  source_event_id TEXT,
  source_provider TEXT,
  source_url TEXT,
  source_version TEXT,
  identity_confidence TEXT NOT NULL,
  revision INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS tips (
  tip_id TEXT PRIMARY KEY,
  tipster_id TEXT NOT NULL,
  strategy_id TEXT NOT NULL,
  event_id TEXT NOT NULL REFERENCES events(event_id),
  market TEXT NOT NULL,
  selection TEXT NOT NULL,
  selection_key TEXT NOT NULL,
  published_at_utc TEXT NOT NULL,
  collected_at_utc TEXT NOT NULL,
  cutoff_at_utc TEXT NOT NULL,
  odds_decimal REAL,
  odds_source TEXT,
  stake_units REAL NOT NULL DEFAULT 1.0,
  line REAL,
  source_url TEXT,
  raw_payload_hash TEXT,
  status TEXT NOT NULL,
  notes TEXT
);
CREATE INDEX IF NOT EXISTS idx_tips_event ON tips(event_id);
CREATE INDEX IF NOT EXISTS idx_tips_tipster ON tips(tipster_id);
CREATE TABLE IF NOT EXISTS odds_snapshots (
  snapshot_id TEXT PRIMARY KEY,
  event_id TEXT NOT NULL REFERENCES events(event_id),
  observed_at_utc TEXT NOT NULL,
  provider TEXT NOT NULL,
  market_key TEXT NOT NULL,
  selection_key TEXT NOT NULL,
  decimal_odds REAL NOT NULL,
  line REAL,
  source_event_id TEXT,
  timestamp_precision TEXT NOT NULL,
  raw_row_hash TEXT,
  source_url TEXT,
  notes TEXT
);
CREATE INDEX IF NOT EXISTS idx_odds_event ON odds_snapshots(event_id);
CREATE TABLE IF NOT EXISTS results (
  result_id TEXT PRIMARY KEY,
  event_id TEXT NOT NULL REFERENCES events(event_id),
  provider TEXT NOT NULL,
  retrieved_at_utc TEXT NOT NULL,
  source_url TEXT,
  raw_payload_hash TEXT,
  final_status TEXT NOT NULL,
  officially_final_at_utc TEXT NOT NULL,
  home_goals INTEGER,
  away_goals INTEGER,
  result_type_kind TEXT,
  version TEXT,
  UNIQUE(event_id, provider)
);
CREATE TABLE IF NOT EXISTS settlements (
  settlement_id TEXT PRIMARY KEY,
  tip_id TEXT NOT NULL REFERENCES tips(tip_id),
  settled_at_utc TEXT NOT NULL,
  rule_version TEXT NOT NULL,
  outcome TEXT NOT NULL,
  pnl_units REAL NOT NULL,
  stake_units REAL NOT NULL,
  odds_decimal REAL,
  result_id TEXT,
  verification_state TEXT NOT NULL,
  gate_log TEXT NOT NULL,
  anomaly_ids TEXT NOT NULL,
  supersedes_id TEXT
);
CREATE INDEX IF NOT EXISTS idx_settle_tip ON settlements(tip_id);
CREATE TABLE IF NOT EXISTS anomalies (
  anomaly_id TEXT PRIMARY KEY,
  kind TEXT NOT NULL,
  entity_type TEXT NOT NULL,
  entity_id TEXT NOT NULL,
  detected_at_utc TEXT NOT NULL,
  detail TEXT NOT NULL,
  source_urls TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'open',
  resolution TEXT
);
CREATE INDEX IF NOT EXISTS idx_anomalies_entity ON anomalies(entity_id);
CREATE TABLE IF NOT EXISTS entrants (
  entrant_id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  kind TEXT NOT NULL,
  description TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS raw_captures (
  capture_id TEXT PRIMARY KEY,
  source_id TEXT NOT NULL,
  path TEXT NOT NULL,
  sha256 TEXT NOT NULL,
  captured_at_utc TEXT NOT NULL,
  capture_mode TEXT NOT NULL,
  note TEXT
);
CREATE TABLE IF NOT EXISTS kv (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
"""


class Store:
    def __init__(self, path: str):
        self.path = path
        if path != ":memory:":
            os.makedirs(os.path.dirname(os.path.abspath(path)) or ".",
                        exist_ok=True)
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(_SCHEMA)
        self._migrate_schema()
        self.conn.commit()

    def _migrate_schema(self) -> None:
        """Apply additive migrations to stores created by older releases.

        The project keeps raw captures out of the public site, but local
        research databases can survive a code upgrade.  Migrations are
        intentionally additive and never rewrite an audit row.
        """
        columns = {row["name"] for row in self._rows(
            "PRAGMA table_info(odds_snapshots)")}
        if "source_event_id" not in columns:
            self.conn.execute(
                "ALTER TABLE odds_snapshots ADD COLUMN source_event_id TEXT")

    # ------------------------------------------------------------- helpers

    def _row(self, sql: str, *params: Any) -> Optional[sqlite3.Row]:
        cur = self.conn.execute(sql, params)
        return cur.fetchone()

    def _rows(self, sql: str, *params: Any) -> List[sqlite3.Row]:
        cur = self.conn.execute(sql, params)
        return cur.fetchall()

    def commit(self) -> None:
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    # ------------------------------------------------------------- events

    def upsert_event(self, event: Event) -> List[str]:
        """Insert or reconcile an event. Returns anomaly ids created."""
        anomalies: List[str] = []
        existing = self._row("SELECT * FROM events WHERE event_id=?",
                             event.event_id)
        if existing is None:
            self.conn.execute(
                """INSERT INTO events (event_id, sport, competition,
                   home_team_id, home_team, away_team_id, away_team,
                   scheduled_start_utc, status, group_order, group_name,
                   source_event_id, source_provider, source_url,
                   source_version, identity_confidence, revision)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,0)""",
                (event.event_id, event.sport, event.competition,
                 event.home_team_id, event.home_team, event.away_team_id,
                 event.away_team, models.fmt_utc(event.scheduled_start_utc),
                 event.status, event.group_order, event.group_name,
                 event.source_event_id, event.source_provider,
                 event.source_url, event.source_version,
                 event.identity_confidence))
            return anomalies

        # A substantive change is an identity change (teams/start) or an
        # *irregular* status change.  Normal fixture lifecycle transitions
        # (scheduled/postponed -> finished/cancelled/abandoned, and the
        # reinstatement of a cancelled fixture) are how a live season
        # capture evolves week to week - they are provenance, not
        # anomalies.  A source_version change alone is a re-capture of the
        # same event.  Regressions (finished -> scheduled), terminal-state
        # flips (finished -> postponed) and any team/start edit remain
        # flagged EVENT_CHANGED with a revision bump.
        lifecycle_ok = {
            ("scheduled", "finished"), ("scheduled", "postponed"),
            ("scheduled", "cancelled"), ("scheduled", "abandoned"),
            ("postponed", "scheduled"), ("postponed", "finished"),
            ("postponed", "cancelled"), ("postponed", "abandoned"),
            ("cancelled", "scheduled"), ("abandoned", "scheduled"),
        }
        identity_changed = (
            existing["home_team"] != event.home_team
            or existing["away_team"] != event.away_team
            or existing["scheduled_start_utc"]
            != models.fmt_utc(event.scheduled_start_utc)
        )
        status_changed = existing["status"] != event.status
        irregular_status = (status_changed
                            and (existing["status"], event.status)
                            not in lifecycle_ok)
        changed = identity_changed or irregular_status
        if changed:
            anomalies.append(self.add_anomaly(Anomaly(
                anomaly_id=models.stable_id("an", ANOMALY_EVENT_CHANGED,
                                             event.event_id,
                                             existing["revision"]),
                kind=ANOMALY_EVENT_CHANGED,
                entity_type="event", entity_id=event.event_id,
                detected_at_utc=utcnow(),
                detail=(
                    f"event changed between source versions: "
                    f"status {existing['status']}->{event.status}, "
                    f"start {existing['scheduled_start_utc']}->"
                    f"{models.fmt_utc(event.scheduled_start_utc)}, "
                    f"source_version {existing['source_version']}->"
                    f"{event.source_version}"),
                source_urls=[event.source_url or ""])))
        confidence_rank = {"unmatched": 0, "probable": 1, "verified": 2}
        old_conf = existing["identity_confidence"]
        new_conf = (event.identity_confidence
                    if confidence_rank.get(event.identity_confidence, -1)
                    >= confidence_rank.get(old_conf, -1)
                    else old_conf)
        new_rev = existing["revision"] + (1 if changed else 0)
        self.conn.execute(
            """UPDATE events SET sport=?, competition=?, home_team_id=?,
               home_team=?, away_team_id=?, away_team=?,
               scheduled_start_utc=?, status=?, group_order=?, group_name=?,
               source_event_id=?, source_provider=?, source_url=?,
               source_version=?, identity_confidence=?, revision=?
               WHERE event_id=?""",
            (event.sport, event.competition, event.home_team_id,
             event.home_team, event.away_team_id, event.away_team,
             models.fmt_utc(event.scheduled_start_utc), event.status,
             event.group_order, event.group_name, event.source_event_id,
             event.source_provider, event.source_url, event.source_version,
             new_conf, new_rev, event.event_id))
        return anomalies

    def get_event(self, event_id: str) -> Optional[Dict[str, Any]]:
        row = self._row("SELECT * FROM events WHERE event_id=?", event_id)
        return dict(row) if row else None

    def events(self) -> List[Dict[str, Any]]:
        return [dict(r) for r in self._rows("SELECT * FROM events ORDER BY scheduled_start_utc")]

    # -------------------------------------------------------------- tips

    def add_tip(self, tip: Tip) -> Dict[str, Any]:
        """Idempotent by (tipster,event,market,selection,published).

        Same content again  -> no-op, returns {'created': False}.
        Same key, new hash  -> SOURCE_EDITED + DUPLICATE_TIP anomalies.
        Different published time for same tipster/event/market/selection
                             -> DUPLICATE_TIP anomaly (kept as its own tip).
        """
        try:
            stake = float(tip.stake_units)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"stake must be numeric, got {tip.stake_units!r}") from exc
        if not math.isfinite(stake) or stake <= 0:
            raise ValueError(f"stake must be finite and > 0, got {tip.stake_units!r}")
        if tip.odds_decimal is not None:
            try:
                odds = float(tip.odds_decimal)
            except (TypeError, ValueError) as exc:
                raise ValueError(
                    f"odds must be numeric, got {tip.odds_decimal!r}"
                ) from exc
            if not math.isfinite(odds) or odds <= 1.0:
                raise ValueError(
                    f"odds must be finite and > 1.0, got {tip.odds_decimal!r}"
                )
        dup = self._row(
            """SELECT * FROM tips WHERE tipster_id=? AND event_id=?
               AND market=? AND selection_key=?""",
            tip.tipster_id, tip.event_id, tip.market, tip.selection_key)
        outcome: Dict[str, Any] = {"created": False, "anomalies": []}
        if dup:
            same_published = (dup["published_at_utc"] ==
                              models.fmt_utc(tip.published_at_utc))
            if same_published:
                if (dup["raw_payload_hash"] or "") != (tip.raw_payload_hash or ""):
                    outcome["anomalies"].append(self.add_anomaly(Anomaly(
                        anomaly_id=models.stable_id(
                            "an", ANOMALY_SOURCE_EDITED, tip.tip_id),
                        kind=ANOMALY_SOURCE_EDITED,
                        entity_type="tip", entity_id=tip.tip_id,
                        detected_at_utc=utcnow(),
                        detail=("re-captured tip payload hash differs for the "
                                "same publish time; source was edited"),
                        source_urls=[tip.source_url or ""])))
                outcome["tip_id"] = dup["tip_id"]
                return outcome
            outcome["anomalies"].append(self.add_anomaly(Anomaly(
                anomaly_id=models.stable_id(
                    "an", ANOMALY_DUPLICATE_TIP, tip.tip_id),
                kind=ANOMALY_DUPLICATE_TIP,
                entity_type="tip", entity_id=tip.tip_id,
                detected_at_utc=utcnow(),
                detail=(f"tipster {tip.tipster_id} has two tips with "
                        f"different publish times for {tip.market} "
                        f"{tip.selection_key} on event {tip.event_id}"),
                source_urls=[tip.source_url or ""])))
        self.conn.execute(
            """INSERT INTO tips (tip_id, tipster_id, strategy_id, event_id,
               market, selection, selection_key, published_at_utc,
               collected_at_utc, cutoff_at_utc, odds_decimal, odds_source,
               stake_units, line, source_url, raw_payload_hash, status, notes)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (tip.tip_id, tip.tipster_id, tip.strategy_id, tip.event_id,
             tip.market, tip.selection, tip.selection_key,
             models.fmt_utc(tip.published_at_utc),
             models.fmt_utc(tip.collected_at_utc),
             models.fmt_utc(tip.cutoff_at_utc), tip.odds_decimal,
             tip.odds_source, tip.stake_units, tip.line, tip.source_url,
             tip.raw_payload_hash, tip.status, tip.notes))
        outcome["created"] = True
        outcome["tip_id"] = tip.tip_id
        return outcome

    def get_tip(self, tip_id: str) -> Optional[Dict[str, Any]]:
        row = self._row("SELECT * FROM tips WHERE tip_id=?", tip_id)
        return dict(row) if row else None

    def tips(self, tipster_id: Optional[str] = None,
             status: Optional[str] = None) -> List[Dict[str, Any]]:
        sql = "SELECT * FROM tips"
        params: List[Any] = []
        clauses = []
        if tipster_id:
            clauses.append("tipster_id=?")
            params.append(tipster_id)
        if status:
            clauses.append("status=?")
            params.append(status)
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY published_at_utc"
        return [dict(r) for r in self._rows(sql, *params)]

    def set_tip_status(self, tip_id: str, status: str,
                       notes: Optional[str] = None) -> None:
        if notes is None:
            self.conn.execute("UPDATE tips SET status=? WHERE tip_id=?",
                              (status, tip_id))
        else:
            self.conn.execute(
                "UPDATE tips SET status=?, notes=? WHERE tip_id=?",
                (status, notes, tip_id))

    # ------------------------------------------------------ odds snapshots

    def add_odds_snapshot(self, snap: OddsSnapshot) -> None:
        try:
            odds = float(snap.decimal_odds)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"decimal odds must be numeric, got {snap.decimal_odds!r}"
            ) from exc
        if not math.isfinite(odds) or odds <= 1.0:
            raise ValueError(
                f"decimal odds must be finite and > 1.0, got {snap.decimal_odds}"
            )
        existing = self._row(
            "SELECT * FROM odds_snapshots WHERE snapshot_id=?", snap.snapshot_id
        )
        if existing is not None:
            comparable = (
                existing["event_id"], existing["observed_at_utc"],
                existing["provider"], existing["market_key"],
                existing["selection_key"], existing["decimal_odds"],
                existing["line"], existing["source_event_id"],
                existing["timestamp_precision"],
                existing["raw_row_hash"],
            )
            incoming = (
                snap.event_id, models.fmt_utc(snap.observed_at_utc),
                snap.provider, snap.market_key, snap.selection_key,
                snap.decimal_odds, snap.line, snap.source_event_id,
                snap.timestamp_precision, snap.raw_row_hash,
            )
            if comparable != incoming:
                self.add_anomaly(Anomaly(
                    anomaly_id=models.stable_id(
                        "an", ANOMALY_SOURCE_EDITED, "odds", snap.snapshot_id
                    ),
                    kind=ANOMALY_SOURCE_EDITED,
                    entity_type="odds", entity_id=snap.snapshot_id,
                    detected_at_utc=utcnow(),
                    detail=("same odds snapshot id was re-imported with "
                            "different immutable content; original retained"),
                    source_urls=[snap.source_url or ""],
                ))
            return
        self.conn.execute(
            """INSERT OR IGNORE INTO odds_snapshots (snapshot_id, event_id,
               observed_at_utc, provider, market_key, selection_key,
               decimal_odds, line, source_event_id, timestamp_precision,
               raw_row_hash, source_url, notes)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (snap.snapshot_id, snap.event_id,
             models.fmt_utc(snap.observed_at_utc), snap.provider,
             snap.market_key, snap.selection_key, snap.decimal_odds,
             snap.line, snap.source_event_id, snap.timestamp_precision,
             snap.raw_row_hash, snap.source_url, snap.notes))

    def odds_snapshots(self, event_id: Optional[str] = None
                       ) -> List[Dict[str, Any]]:
        if event_id:
            rows = self._rows(
                "SELECT * FROM odds_snapshots WHERE event_id=? "
                "ORDER BY observed_at_utc", event_id)
        else:
            rows = self._rows("SELECT * FROM odds_snapshots")
        return [dict(r) for r in rows]

    def entry_odds(self, event_id: str, provider: str, selection_key: str,
                   market_key: str = models.MARKET_MATCH_WINNER_3WAY
                   ) -> Optional[Dict[str, Any]]:
        """The earliest stored snapshot for (event, provider, selection) that
        is not after event start. Used as the entry price; a later price can
        never silently become the entry price."""
        event = self.get_event(event_id)
        if event is None:
            return None
        start = parse_utc(event["scheduled_start_utc"])
        row = self._row(
            """SELECT * FROM odds_snapshots
               WHERE event_id=? AND provider=? AND selection_key=?
                 AND market_key=? AND observed_at_utc < ?
               ORDER BY observed_at_utc LIMIT 1""",
            event_id, provider, selection_key, market_key,
            models.fmt_utc(start))
        return dict(row) if row else None

    # -------------------------------------------------------------- results

    def add_result(self, result: Result) -> List[str]:
        """Upsert per (event, provider); cross-provider conflict -> anomaly."""
        anomalies: List[str] = []
        existing = self._row(
            "SELECT * FROM results WHERE event_id=? AND provider=?",
            result.event_id, result.provider,
        )
        if existing is not None:
            previous_content = (
                existing["raw_payload_hash"], existing["final_status"],
                existing["officially_final_at_utc"], existing["home_goals"],
                existing["away_goals"], existing["version"],
            )
            incoming_content = (
                result.raw_payload_hash, result.final_status,
                models.fmt_utc(result.officially_final_at_utc),
                result.home_goals, result.away_goals, result.version,
            )
            if previous_content != incoming_content:
                anomalies.append(self.add_anomaly(Anomaly(
                    anomaly_id=models.stable_id(
                        "an", ANOMALY_SOURCE_EDITED, "result",
                        result.event_id, result.provider,
                        result.raw_payload_hash or "missing",
                    ),
                    kind=ANOMALY_SOURCE_EDITED,
                    entity_type="result", entity_id=result.event_id,
                    detected_at_utc=utcnow(),
                    detail=("result provider replaced an existing payload or "
                            f"score: {existing['raw_payload_hash']} -> "
                            f"{result.raw_payload_hash}; review before "
                            "re-settlement"),
                    source_urls=[result.source_url or ""],
                )))
        self.conn.execute(
            """INSERT INTO results (result_id, event_id, provider,
               retrieved_at_utc, source_url, raw_payload_hash, final_status,
               officially_final_at_utc, home_goals, away_goals,
               result_type_kind, version)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(event_id, provider) DO UPDATE SET
                 result_id=excluded.result_id,
                 retrieved_at_utc=excluded.retrieved_at_utc,
                 source_url=excluded.source_url,
                 raw_payload_hash=excluded.raw_payload_hash,
                 final_status=excluded.final_status,
                 officially_final_at_utc=excluded.officially_final_at_utc,
                 home_goals=excluded.home_goals,
                 away_goals=excluded.away_goals,
                 result_type_kind=excluded.result_type_kind,
                 version=excluded.version""",
            (result.result_id, result.event_id, result.provider,
             models.fmt_utc(result.retrieved_at_utc), result.source_url,
             result.raw_payload_hash, result.final_status,
             models.fmt_utc(result.officially_final_at_utc),
             result.home_goals, result.away_goals,
             result.result_type_kind, result.version))

        others = self._rows(
            """SELECT * FROM results WHERE event_id=? AND provider<>?
               AND final_status='finished'""",
            result.event_id, result.provider)
        if result.final_status == "finished":
            for other in others:
                if (other["home_goals"], other["away_goals"]) != (
                        result.home_goals, result.away_goals):
                    anomalies.append(self.add_anomaly(Anomaly(
                        anomaly_id=models.stable_id(
                            "an", ANOMALY_RESULT_SOURCE_CONFLICT,
                            result.event_id,
                            sorted([result.provider, other["provider"]])),
                        kind=ANOMALY_RESULT_SOURCE_CONFLICT,
                        entity_type="result", entity_id=result.event_id,
                        detected_at_utc=utcnow(),
                        detail=(
                            f"providers disagree: {result.provider}="
                            f"{result.home_goals}-{result.away_goals} vs "
                            f"{other['provider']}="
                            f"{other['home_goals']}-{other['away_goals']}"),
                        source_urls=[result.source_url or "",
                                     (other["source_url"] or "")])))
        return anomalies

    def results(self, event_id: Optional[str] = None
                ) -> List[Dict[str, Any]]:
        if event_id:
            rows = self._rows("SELECT * FROM results WHERE event_id=?",
                              event_id)
        else:
            rows = self._rows("SELECT * FROM results")
        return [dict(r) for r in rows]

    # ---------------------------------------------------------- settlements

    def add_settlement(self, settlement: Settlement) -> None:
        self.conn.execute(
            """INSERT INTO settlements (settlement_id, tip_id,
               settled_at_utc, rule_version, outcome, pnl_units, stake_units,
               odds_decimal, result_id, verification_state, gate_log,
               anomaly_ids, supersedes_id)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (settlement.settlement_id, settlement.tip_id,
             models.fmt_utc(settlement.settled_at_utc),
             settlement.rule_version, settlement.outcome,
             settlement.pnl_units, settlement.stake_units,
             settlement.odds_decimal, settlement.result_id,
             settlement.verification_state,
             json.dumps(settlement.gate_log, sort_keys=True),
             json.dumps(settlement.anomaly_ids, sort_keys=True),
             settlement.supersedes_id))

    def settlements_for_tip(self, tip_id: str) -> List[Dict[str, Any]]:
        rows = self._rows(
            "SELECT * FROM settlements WHERE tip_id=? ORDER BY settled_at_utc",
            tip_id)
        out = []
        for r in rows:
            d = dict(r)
            d["gate_log"] = json.loads(d["gate_log"])
            d["anomaly_ids"] = json.loads(d["anomaly_ids"])
            out.append(d)
        return out

    def latest_settlement(self, tip_id: str) -> Optional[Dict[str, Any]]:
        rows = self.settlements_for_tip(tip_id)
        if not rows:
            return None
        return rows[-1]

    def all_settlements(self) -> List[Dict[str, Any]]:
        rows = self._rows("SELECT * FROM settlements ORDER BY settled_at_utc")
        out = []
        for r in rows:
            d = dict(r)
            d["gate_log"] = json.loads(d["gate_log"])
            d["anomaly_ids"] = json.loads(d["anomaly_ids"])
            out.append(d)
        return out

    # ------------------------------------------------------------- anomalies

    def add_anomaly(self, anomaly: Anomaly) -> str:
        self.conn.execute(
            """INSERT OR IGNORE INTO anomalies (anomaly_id, kind,
               entity_type, entity_id, detected_at_utc, detail, source_urls,
               status, resolution) VALUES (?,?,?,?,?,?,?,?,?)""",
            (anomaly.anomaly_id, anomaly.kind, anomaly.entity_type,
             anomaly.entity_id, models.fmt_utc(anomaly.detected_at_utc),
             anomaly.detail, json.dumps(anomaly.source_urls),
             anomaly.status, anomaly.resolution))
        return anomaly.anomaly_id

    def anomaly_exists(self, anomaly_id: str) -> bool:
        return self._row("SELECT 1 FROM anomalies WHERE anomaly_id=?",
                         anomaly_id) is not None

    def anomalies(self, status: Optional[str] = None
                  ) -> List[Dict[str, Any]]:
        if status:
            rows = self._rows("SELECT * FROM anomalies WHERE status=?",
                              status)
        else:
            rows = self._rows("SELECT * FROM anomalies")
        out = []
        for r in rows:
            d = dict(r)
            d["source_urls"] = json.loads(d["source_urls"])
            out.append(d)
        return out

    # ------------------------------------------------------------- entrants

    def upsert_entrant(self, entrant_id: str, name: str, kind: str,
                       description: str) -> None:
        self.conn.execute(
            """INSERT INTO entrants (entrant_id, name, kind, description)
               VALUES (?,?,?,?)
               ON CONFLICT(entrant_id) DO UPDATE SET name=excluded.name,
               kind=excluded.kind, description=excluded.description""",
            (entrant_id, name, kind, description))

    def entrants(self) -> List[Dict[str, Any]]:
        return [dict(r) for r in self._rows("SELECT * FROM entrants")]

    # --------------------------------------------------------- raw captures

    def register_capture(self, capture_id: str, source_id: str, path: str,
                         sha256: str, captured_at_utc: models.datetime,
                         capture_mode: str, note: str = "") -> None:
        self.conn.execute(
            """INSERT OR REPLACE INTO raw_captures (capture_id, source_id,
               path, sha256, captured_at_utc, capture_mode, note)
               VALUES (?,?,?,?,?,?,?)""",
            (capture_id, source_id, path, sha256,
             models.fmt_utc(captured_at_utc), capture_mode, note))

    def captures(self) -> List[Dict[str, Any]]:
        return [dict(r) for r in self._rows("SELECT * FROM raw_captures")]

    # ------------------------------------------------------------------ kv

    def kv_set(self, key: str, value: str) -> None:
        self.conn.execute(
            "INSERT INTO kv (key, value) VALUES (?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value))

    def kv_get(self, key: str) -> Optional[str]:
        row = self._row("SELECT value FROM kv WHERE key=?", key)
        return row["value"] if row else None
