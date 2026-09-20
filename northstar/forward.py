"""Forward-test engine: the live paper competition clock.

Why this exists (docs/FORWARD-TEST.md): the historical pilots can only be
backtests; the user-requested *forward* protocol - predictions issued
before an event starts, frozen, then graded against results as they arrive -
needs a ledger that survives store rebuilds and CI re-captures.

Design rules:
1. Append-only ledger (``data/forward/ledger.json``).  A prediction is
   issued once, at a recorded capture instant (``as_of``), and is never
   edited, re-issued, or deleted.  Later pipeline runs *grade* entries; they
   do not change them.
2. Cutoff discipline: only events whose stored start is strictly after
   ``as_of`` are eligible; every feature read happens at ``as_of``; the
   declared cutoff is ``as_of``.  The TimeBoundedStore audit raises on any
   read at/after an event's start, exactly as in backtests.
3. No permissioned odds path exists for the current season, so forward
   entries are prediction-only: store tips get status ``unsettleable`` and
   NO settlement row is ever created.  PnL is unavailable, never zero.
4. Grading is accuracy-only (hit / Brier) against results that arrive in
   later committed captures; overdue entries (start passed, no result in
   the latest capture) are surfaced for review, not silently dropped.
5. Offline determinism: with the same committed fixtures + ledger, any
   pipeline re-run produces the same report (issued set is ledger-driven;
   grading is store-driven).
"""
from __future__ import annotations

import json
import os
from datetime import timedelta
from typing import Any, Dict, List, Optional, Sequence

from . import models
from .adapters.openligadb import availability_for
from .backtest import TimeBoundedStore, TimeLeakageError
from .db import Store
from .evaluation import OUTCOMES, brier_three, outcome_key
from .models import (
    EVENT_STATUS_FINISHED, EVENT_STATUS_SCHEDULED, MARKET_MATCH_WINNER_2WAY,
    MARKET_MATCH_WINNER_3WAY, TIP_STATUS_UNSETTLEABLE, Tip,
    parse_utc, stable_id, utcnow,
)
from .strategies import build

LEDGER_VERSION = "nr-forward-ledger-1"

# How long after the scheduled start a missing result is merely "awaiting"
# before it becomes "overdue" (review queue).  Community sources can lag;
# this mirrors the per-sport availability inference plus slack.
OVERDUE_GRACE = {
    "football": timedelta(hours=30),
    "ice_hockey": timedelta(hours=30),
    "darts": timedelta(hours=54),
}
DEFAULT_GRACE = timedelta(hours=54)

MODEL_VERSION = "nr-forward-2026-09-20.1"

# Forward desks only issue predictions inside this horizon from the capture
# instant (roughly one matchweek + slack).  Predicting a fixture months
# ahead from today's ratings would be a frozen call no real desk makes, and
# it would flood the ledger; the weekly capture issues each matchweek as it
# enters the horizon.  Documented in docs/FORWARD-TEST.md.
ISSUE_HORIZON = timedelta(days=10)


# ------------------------------------------------------------------ ledger

def load_ledger(path: str) -> Dict[str, Any]:
    if not os.path.exists(path):
        return {"version": LEDGER_VERSION, "issued": []}
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    if data.get("version") != LEDGER_VERSION:
        raise ValueError(f"unsupported forward ledger version: "
                         f"{data.get('version')!r}")
    return data


def save_ledger(path: str, ledger: Dict[str, Any]) -> bool:
    """Write the ledger if (and only if) its serialized form changed.

    Returns True when the file was written.  Byte-identical rewrites are
    skipped so offline pipeline re-runs stay side-effect-free.
    """
    new_text = json.dumps(ledger, indent=2, ensure_ascii=False,
                          sort_keys=True) + "\n"
    old_text = None
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as fh:
            old_text = fh.read()
    if old_text == new_text:
        return False
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(new_text)
    return True


# ----------------------------------------------------------------- issuing

def _sport_market(sport: Optional[str]) -> str:
    return MARKET_MATCH_WINNER_3WAY if sport == models.SPORT_FOOTBALL \
        else MARKET_MATCH_WINNER_2WAY


def issue_forward(store: Store, events: Sequence[Dict[str, Any]],
                  as_of, strategy_ids: Sequence[str],
                  ledger: Dict[str, Any], label: str = "forward",
                  horizon: timedelta = ISSUE_HORIZON) -> Dict[str, Any]:
    """Walk the current-season events and append new predictions.

    ``events``: stored event dicts from the *current-season* captures
    (finished + scheduled).  Ratings are released from finished events at
    their stored availability time; scheduled events starting after
    ``as_of`` are offered to each strategy at ``as_of``.

    Ledger entries already issued (by prediction_id) are never re-issued:
    the first capture that saw the fixture froze the call forever.
    """
    if as_of is None or as_of.tzinfo is None:
        raise ValueError("as_of must be a timezone-aware datetime")
    issued_ids = {e["prediction_id"] for e in ledger["issued"]}
    stats = {"issued": 0, "already_ledgered": 0, "out_of_horizon": 0,
             "skipped": [], "leak_violations": []}

    ordered = sorted(events, key=lambda e: (e["scheduled_start_utc"],
                                            e["event_id"]))
    for sid in strategy_ids:
        strategy = build(sid)
        sport = getattr(strategy, "sport", None)
        if sport:
            ordered_s = [e for e in ordered if e.get("sport") == sport]
        else:
            ordered_s = ordered
        tbs = TimeBoundedStore()
        for e in ordered_s:
            tbs.register_event(e)
        entrant_id = f"fwd-{sid}"
        for e in ordered_s:
            start = parse_utc(e["scheduled_start_utc"])
            if e["status"] == EVENT_STATUS_FINISHED:
                # Release the result to the feature timeline at its stored
                # availability time (never earlier, never later).
                results = [r for r in store.results(e["event_id"])
                           if r["final_status"] == "finished"]
                if not results:
                    continue
                scores = {(r["home_goals"], r["away_goals"])
                          for r in results}
                if len(scores) != 1 or None in next(iter(scores)):
                    continue  # disputed/incomplete: review queue owns it
                primary = max(results,
                              key=lambda r: parse_utc(
                                  r["officially_final_at_utc"]))
                final_at = parse_utc(primary["officially_final_at_utc"])
                tbs.add_result(e, primary["home_goals"],
                               primary["away_goals"], available_at=final_at)
                ratings = strategy.ratings_after(
                    e, primary["home_goals"], primary["away_goals"], tbs,
                    final_at)
                if ratings:
                    tbs.update_ratings(ratings, available_at=final_at)
                continue
            if e["status"] != EVENT_STATUS_SCHEDULED or start <= as_of:
                continue  # unresolved (postponed) or already started
            if start > as_of + horizon:
                stats["out_of_horizon"] += 1
                continue  # the weekly capture issues it when it nears
            prediction_id = stable_id("fwd", sid, e["event_id"])
            if prediction_id in issued_ids:
                stats["already_ledgered"] += 1
                # Still recreate the store tip (store is rebuilt each run;
                # the ledger is the source of truth).
                entry = next(x for x in ledger["issued"]
                             if x["prediction_id"] == prediction_id)
                _store_tip(store, entry, label)
                continue
            tbs.begin_decision(start)
            try:
                decision = strategy.predict(e, tbs, start, as_of=as_of)
            except TimeLeakageError as exc:
                stats["leak_violations"].append(f"{sid}: {exc} "
                                                f"for {e['event_id']}")
                tbs.end_decision()
                continue
            cutoff = decision.get("cutoff_utc")
            latest_read = tbs.latest_read_at
            tbs.end_decision()
            if cutoff is None or cutoff >= start or cutoff > as_of:
                stats["leak_violations"].append(
                    f"{sid}: forward cutoff {cutoff} invalid (must be <= "
                    f"as_of {as_of} and < start {start}) for {e['event_id']}")
                continue
            if latest_read is not None and latest_read > cutoff:
                stats["leak_violations"].append(
                    f"{sid}: read at {latest_read} exceeds cutoff {cutoff} "
                    f"for {e['event_id']}")
                continue
            if not decision.get("selection_key") or \
                    decision["selection_key"] == "none":
                stats["skipped"].append({"event_id": e["event_id"],
                                         "strategy": sid,
                                         "reason": "strategy passed"})
                continue
            entry = {
                "prediction_id": prediction_id,
                "strategy_id": sid,
                "strategy_name": strategy.name,
                "sport": e.get("sport") or sport,
                "event_id": e["event_id"],
                "source_event_id": e.get("source_event_id"),
                "competition": e.get("competition"),
                "event": f"{e['home_team']} v {e['away_team']}",
                "home_team": e["home_team"],
                "away_team": e["away_team"],
                "start_utc": e["scheduled_start_utc"],
                "group_order": e.get("group_order"),
                "group_name": e.get("group_name"),
                "issued_at_utc": models.fmt_utc(as_of),
                "cutoff_utc": models.fmt_utc(cutoff),
                "selection": decision.get("selection_text",
                                          decision["selection_key"]),
                "selection_key": decision["selection_key"],
                "market": _sport_market(e.get("sport") or sport),
                "model": decision.get("model", {}),
                "model_version": MODEL_VERSION,
                "source_url": e.get("source_url"),
                "label": label,
                "odds": None,
                "odds_note": ("no permissioned odds path for the current "
                              "season - prediction-only, graded on accuracy"),
            }
            ledger["issued"].append(entry)
            issued_ids.add(prediction_id)
            stats["issued"] += 1
            _store_tip(store, entry, label)
    store.commit()
    return stats


def _store_tip(store: Store, entry: Dict[str, Any], label: str) -> None:
    """(Re)create the audit-trail tip row for a ledger entry.

    Tips are immutable and idempotent by stable id; the ledger is the
    source of truth, so a rebuilt store always mirrors it.  Status is
    ``unsettleable``: no odds, no settlement, no PnL - by construction.
    """
    sid = entry["strategy_id"]
    store.upsert_entrant(
        f"fwd-{sid}", f"{entry['strategy_name']} (forward test)",
        "strategy",
        f"Forward-test desk {label}: predictions issued pre-start from "
        "committed captures; prediction-only (no permissioned odds path); "
        "graded on accuracy, PnL unavailable (never zero).")
    tip = Tip(
        tip_id=stable_id("fwd-tip", sid, entry["event_id"]),
        tipster_id=f"fwd-{sid}",
        strategy_id=sid,
        event_id=entry["event_id"],
        market=entry["market"],
        selection=entry["selection"],
        selection_key=entry["selection_key"],
        published_at_utc=parse_utc(entry["issued_at_utc"]),
        collected_at_utc=parse_utc(entry["issued_at_utc"]),
        cutoff_at_utc=parse_utc(entry["cutoff_utc"]),
        odds_decimal=None,
        odds_source=None,
        stake_units=1.0,
        source_url=entry.get("source_url"),
        raw_payload_hash=None,
        status=TIP_STATUS_UNSETTLEABLE,
        notes=(f"forward test {label}: issued {entry['issued_at_utc']} "
               f"(cutoff {entry['cutoff_utc']}); prediction-only - no "
               "permissioned odds path, PnL unavailable (not zero)"),
    )
    store.add_tip(tip)


# ----------------------------------------------------------------- grading

def grade_forward(store: Store, ledger: Dict[str, Any],
                  latest_as_of=None) -> Dict[str, Any]:
    """Grade ledger entries against stored results; never mutate entries.

    Returns the report structure rendered by the site:
    per-entry status ``graded`` | ``awaiting_result`` | ``overdue``,
    per-desk accuracy/Brier, and the full lists.
    """
    graded: List[Dict[str, Any]] = []
    awaiting: List[Dict[str, Any]] = []
    overdue: List[Dict[str, Any]] = []
    rows: List[Dict[str, Any]] = []
    # Results under review (RESULT_KIND_INCONSISTENT) are held ungraded
    # until the review queue resolves them - never graded on a silent
    # first-entry read of a disputed source row.
    flagged = {a["entity_id"] for a in store.anomalies(status="open")
               if a["kind"] == models.ANOMALY_RESULT_KIND_INCONSISTENT}
    for entry in ledger["issued"]:
        eid = entry["event_id"]
        event = store.get_event(eid) or {}
        results = [r for r in store.results(eid)
                   if r["final_status"] == "finished"]
        row = {**entry, "status": "awaiting_result"}
        if eid in flagged:
            row["note"] = ("result flagged for review "
                           "(RESULT_KIND_INCONSISTENT) - held ungraded "
                           "until the review queue resolves it")
            awaiting.append(row)
            rows.append(row)
            continue
        scores = {(r["home_goals"], r["away_goals"]) for r in results}
        if results and len(scores) == 1 and None not in next(iter(scores)):
            hg, ag = next(iter(scores))
            actual = outcome_key(hg, ag)
            probs = (entry.get("model") or {}).get("model_prob") or {}
            row.update({
                "status": "graded",
                "result": f"{hg}-{ag}",
                "actual": actual,
                "hit": bool(entry["selection_key"] == actual),
                "brier": (round(brier_three(probs, actual), 6)
                          if all(k in probs for k in OUTCOMES) else None),
                "graded_from": [r["provider"] for r in results],
            })
            graded.append(row)
        elif results:
            row.update({"status": "awaiting_result",
                        "note": "conflicting/incomplete result - review "
                                "queue owns it"})
            awaiting.append(row)
        else:
            start = parse_utc(entry["start_utc"])
            grace = OVERDUE_GRACE.get(entry.get("sport") or "",
                                      DEFAULT_GRACE)
            if latest_as_of is not None and start + grace < latest_as_of:
                row.update({"status": "overdue",
                            "note": "start passed the grace window without a "
                                    "result in the latest committed capture"})
                overdue.append(row)
            else:
                awaiting.append(row)
        rows.append(row)

    desks: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        d = desks.setdefault(row["strategy_id"], {
            "strategy_id": row["strategy_id"],
            "strategy_name": row["strategy_name"],
            "sport": row.get("sport"),
            "predictions": 0, "graded": 0, "hits": 0,
            "awaiting": 0, "overdue": 0,
        })
        d["predictions"] += 1
        if row["status"] == "graded":
            d["graded"] += 1
            d["hits"] += 1 if row["hit"] else 0
        elif row["status"] == "overdue":
            d["overdue"] += 1
        else:
            d["awaiting"] += 1
    for d in desks.values():
        d["accuracy"] = (round(d["hits"] / d["graded"], 6)
                         if d["graded"] else None)
        briers = [r["brier"] for r in rows
                  if r["strategy_id"] == d["strategy_id"]
                  and r.get("brier") is not None]
        d["mean_brier"] = (round(sum(briers) / len(briers), 6)
                           if briers else None)
    return {
        "model_version": MODEL_VERSION,
        "graded": graded, "awaiting": awaiting, "overdue": overdue,
        "rows": rows, "desks": desks,
        "n_issued": len(rows), "n_graded": len(graded),
        "n_awaiting": len(awaiting), "n_overdue": len(overdue),
        "note": ("Forward-test predictions are frozen at issue time and "
                 "graded on accuracy only. PnL is unavailable until a "
                 "permissioned odds path exists - it is never shown as "
                 "zero."),
    }
