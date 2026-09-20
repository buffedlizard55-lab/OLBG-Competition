"""Settlement engine: market rules, verification gates, decimal arithmetic.

Rules implemented (versioned in SETTLEMENT_RULE_VERSION):

- Market ``match_winner_3way`` (full time result):
    won  -> pnl = stake * (odds - 1)
    lost -> pnl = -stake
    void -> pnl = 0, stake refunded, NOT counted in turnover
    (push is not possible in a 3-way match market; it exists for handicap
    markets and is handled by the generic outcome table below)
- Event ``postponed``  -> tip stays ``pending`` (never a loss; UK bookmaker
  convention: void if not played within 48h, but we never guess - we wait
  for the source status to resolve).
- Event ``cancelled`` / ``abandoned`` -> tip ``void``, stake refunded, no
  turnover, no strike-rate effect.
- Event ``disputed`` or conflicting result providers -> no settlement; the
  tip goes to ``disputed`` with a review anomaly.
- A tip is only settled from a result whose ``officially_final_at_utc`` is
  after the event start and whose provider is in the allowed registry.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Any, Dict, List, Optional

from . import models
from .db import Store
from .models import (
    Anomaly, SETTLEMENT_RULE_VERSION,
    EVENT_STATUS_CANCELLED, EVENT_STATUS_DISPUTED, EVENT_STATUS_FINISHED,
    EVENT_STATUS_POSTPONED,
    MARKET_MATCH_WINNER_3WAY,
    TIP_STATUS_DISPUTED, TIP_STATUS_LOST, TIP_STATUS_PENDING, TIP_STATUS_VOID,
    TIP_STATUS_WON,
    VERIFICATION_REVIEW, VERIFICATION_VERIFIED,
    parse_utc, stable_id, utcnow,
)
from .policy import PolicyError, get_policy


@dataclass
class GateLog:
    identity: str = "skipped"
    time: str = "skipped"
    market: str = "skipped"
    result: str = "skipped"
    reconciliation: str = "skipped"
    integrity: str = "skipped"
    arithmetic: str = "skipped"

    def ok(self) -> bool:
        return all(v == "skipped" or v.startswith("pass")
                   for v in self.__dict__.values())

    def to_dict(self) -> Dict[str, str]:
        return dict(self.__dict__)


def decimal_pnl(stake: float, odds: Optional[float], outcome: str) -> float:
    """Pure settlement arithmetic for level-stakes decimal bets."""
    if not math.isfinite(float(stake)) or stake <= 0:
        raise ValueError(f"stake must be finite and > 0, got {stake}")
    if outcome in ("void", "push"):
        return 0.0
    if odds is None:
        raise ValueError(f"outcome '{outcome}' requires stored odds")
    if not math.isfinite(float(odds)) or odds <= 1.0:
        raise ValueError(f"odds must be finite and > 1.0, got {odds}")
    if outcome == "won":
        return round(stake * (odds - 1), 10)
    if outcome == "lost":
        return round(-stake, 10)
    raise ValueError(f"unknown outcome '{outcome}'")


def implied_probabilities(odds: List[float]) -> List[float]:
    """Margin-removed (proportional normalisation) implied probabilities."""
    if any((o is None) or not math.isfinite(float(o)) or o <= 1.0
           for o in odds):
        raise ValueError(f"odds must be finite and > 1.0, got {odds}")
    inv = [1.0 / o for o in odds]
    total = sum(inv)
    return [x / total for x in inv]


def match_outcome_3way(selection_key: str, home_goals: int,
                       away_goals: str | int) -> str:
    if selection_key not in ("home", "draw", "away"):
        raise ValueError(f"unknown 3-way selection: {selection_key}")
    if (isinstance(home_goals, bool) or isinstance(away_goals, bool)
            or not isinstance(home_goals, int)
            or not isinstance(away_goals, int)
            or home_goals < 0 or away_goals < 0):
        raise ValueError(f"invalid final score: {home_goals}-{away_goals}")
    if home_goals > away_goals:
        win = "home"
    elif home_goals < away_goals:
        win = "away"
    else:
        win = "draw"
    return "won" if win == selection_key else "lost"


def settle_tip(store: Store, tip_id: str,
               allowed_result_providers: Optional[List[str]] = None
               ) -> Dict[str, Any]:
    """Run the verification gates and, when they pass, append a settlement.

    Returns a dict describing the decision:
      {"action": "settled"|"pending"|"void"|"disputed"|"blocked",
       "settlement_id": ...|None, "gates": {...}, "anomalies": [...]}
    """
    tip = store.get_tip(tip_id)
    if tip is None:
        raise KeyError(f"unknown tip {tip_id}")
    event = store.get_event(tip["event_id"])
    if event is None:
        raise KeyError(f"tip {tip_id} references unknown event")

    # Idempotency: re-settling the same (tip, result) is a no-op, so
    # backtest re-runs cannot double-count PnL.  A changed result_id is not a
    # no-op: it must create an auditable settlement revision.
    prior = store.latest_settlement(tip_id)
    current_result_ids = {
        r["result_id"] for r in store.results(tip["event_id"])
    }
    same_result = bool(prior and prior.get("result_id") in current_result_ids)
    same_void = bool(
        prior and not prior.get("result_id")
        and prior.get("outcome") == "void"
        and event["status"] in (EVENT_STATUS_CANCELLED, "abandoned")
    )
    if (prior and prior["rule_version"] == SETTLEMENT_RULE_VERSION
            and prior["outcome"] in ("won", "lost", "void", "push")
            and (same_result or same_void)):
        return {"action": "already_settled",
                "settlement_id": prior["settlement_id"],
                "gates": prior["gate_log"],
                "anomalies": []}

    gates = GateLog()
    anomalies: List[str] = []
    action = "blocked"

    # Gate 1: identity
    if event["identity_confidence"] == "verified":
        gates.identity = "pass"
    else:
        gates.identity = f"fail:{event['identity_confidence']}"

    # Gate 2: time - publication/odds strictly before event start
    start = parse_utc(event["scheduled_start_utc"])
    if parse_utc(tip["published_at_utc"]) < start and \
            parse_utc(tip["cutoff_at_utc"]) < start:
        gates.time = "pass"
    else:
        gates.time = "fail:post-start input"
        anomalies.append(store.add_anomaly(Anomaly(
            anomaly_id=stable_id("an", "ODDS_AFTER_START", tip_id),
            kind=models.ANOMALY_ODDS_AFTER_START, entity_type="tip",
            entity_id=tip_id, detected_at_utc=utcnow(),
            detail=("tip publish/cutoff timestamp is not before event start"),
            source_urls=[tip["source_url"] or ""])))

    # Gate 3: market
    if tip["market"] == MARKET_MATCH_WINNER_3WAY and \
            tip["selection_key"] in ("home", "draw", "away"):
        gates.market = "pass"
    else:
        gates.market = "fail:unknown market rule"
        anomalies.append(store.add_anomaly(Anomaly(
            anomaly_id=stable_id("an", models.ANOMALY_MARKET_RULE_UNKNOWN,
                                 tip_id),
            kind=models.ANOMALY_MARKET_RULE_UNKNOWN, entity_type="tip",
            entity_id=tip_id, detected_at_utc=utcnow(),
            detail=f"market {tip['market']} / {tip['selection_key']} has no "
                   f"implemented rule set",
            source_urls=[])))

    # Event state branches (postponed / cancelled / disputed) take priority
    # over result settlement: uncertainty is never converted to a loss.
    if event["status"] == EVENT_STATUS_POSTPONED:
        store.set_tip_status(tip_id, TIP_STATUS_PENDING,
                             notes="event postponed; awaiting reschedule")
        return {"action": "pending", "settlement_id": None,
                "gates": gates.to_dict(), "anomalies": anomalies}
    if event["status"] in (EVENT_STATUS_CANCELLED, "abandoned"):
        outcome = "void"
        pnl = decimal_pnl(tip["stake_units"], tip["odds_decimal"], outcome)
        state = (VERIFICATION_VERIFIED if gates.identity == "pass"
                 else VERIFICATION_REVIEW)
        sid = _append_settlement(store, tip, outcome, pnl, None, gates,
                                 anomalies, "cancelled event -> void",
                                 state=state)
        store.set_tip_status(tip_id, TIP_STATUS_VOID,
                             notes="event cancelled/abandoned; stake refunded")
        return {"action": "void", "settlement_id": sid,
                "gates": gates.to_dict(), "anomalies": anomalies}
    if event["status"] == EVENT_STATUS_DISPUTED:
        store.set_tip_status(tip_id, TIP_STATUS_DISPUTED,
                             notes="event disputed; review required")
        anomalies.append(store.add_anomaly(Anomaly(
            anomaly_id=stable_id("an", "DISPUTED_EVENT", tip_id),
            kind=models.ANOMALY_RESULT_NOT_FINAL, entity_type="tip",
            entity_id=tip_id, detected_at_utc=utcnow(),
            detail="event is in disputed state; settlement withheld",
            source_urls=[event["source_url"] or ""])))
        return {"action": "disputed", "settlement_id": None,
                "gates": gates.to_dict(), "anomalies": anomalies}
    if event["status"] != EVENT_STATUS_FINISHED:
        store.set_tip_status(tip_id, TIP_STATUS_PENDING,
                             notes=f"event status {event['status']}")
        return {"action": "pending", "settlement_id": None,
                "gates": gates.to_dict(), "anomalies": anomalies}

    # Gate 4: result exists, is final, from an allowed provider
    results = [r for r in store.results(tip["event_id"])
               if r["final_status"] == "finished"]
    if allowed_result_providers is not None:
        results = [r for r in results
                   if r["provider"] in allowed_result_providers]
    if not results:
        store.set_tip_status(tip_id, TIP_STATUS_PENDING,
                             notes="no finished result yet")
        return {"action": "pending", "settlement_id": None,
                "gates": gates.to_dict(), "anomalies": anomalies}

    allowed = [r for r in results
               if parse_utc(r["officially_final_at_utc"]) > start]
    if not allowed:
        gates.result = "fail:result timestamp before start"
        return {"action": "blocked", "settlement_id": None,
                "gates": gates.to_dict(), "anomalies": anomalies}
    gates.result = "pass"

    # Gate 5: reconciliation across providers
    if len(allowed) >= 2:
        distinct = {(r["home_goals"], r["away_goals"]) for r in allowed}
        if len(distinct) > 1:
            gates.reconciliation = "fail:providers disagree"
            store.set_tip_status(tip_id, TIP_STATUS_DISPUTED,
                                 notes="result source conflict")
            return {"action": "disputed", "settlement_id": None,
                    "gates": gates.to_dict(), "anomalies": anomalies}
        gates.reconciliation = f"pass:{len(allowed)} providers agree"
    else:
        gates.reconciliation = "pass:single provider"

    # Gate 6: integrity - every provider used for settlement must have a
    # stored raw payload hash (detects post-hoc source edits).
    missing = [r["provider"] for r in allowed
               if r.get("raw_payload_hash") is None]
    ok_integrity = not missing
    gates.integrity = ("pass" if ok_integrity
                       else "fail:no raw hash: " + ",".join(missing))

    # Gate 7: arithmetic + settle.  A number without a named, timestamped
    # odds source is not a bet price; do not turn it into a guessed loss.
    if tip["odds_decimal"] is None or not tip.get("odds_source"):
        gates.arithmetic = "fail:missing odds"
        anomalies.append(store.add_anomaly(Anomaly(
            anomaly_id=stable_id("an", models.ANOMALY_MISSING_ODDS, tip_id),
            kind=models.ANOMALY_MISSING_ODDS, entity_type="tip",
            entity_id=tip_id, detected_at_utc=utcnow(),
            detail="settlement requires a stored decimal price and odds source",
            source_urls=[tip["source_url"] or ""],
        )))
        return {"action": "blocked", "settlement_id": None,
                "gates": gates.to_dict(), "anomalies": anomalies}
    primary = max(allowed, key=lambda r: parse_utc(
        r["officially_final_at_utc"]))
    try:
        outcome = match_outcome_3way(tip["selection_key"],
                                     primary["home_goals"],
                                     primary["away_goals"])
        pnl = decimal_pnl(tip["stake_units"], tip["odds_decimal"], outcome)
        gates.arithmetic = "pass"
    except ValueError as exc:
        gates.arithmetic = f"fail:{exc}"
        return {"action": "blocked", "settlement_id": None,
                "gates": gates.to_dict(), "anomalies": anomalies}

    state = VERIFICATION_VERIFIED if gates.ok() and ok_integrity \
        and gates.identity == "pass" and gates.time == "pass" \
        and gates.market == "pass" else VERIFICATION_REVIEW
    sid = _append_settlement(store, tip, outcome, pnl,
                             primary["result_id"], gates, anomalies,
                             f"result {primary['home_goals']}-"
                             f"{primary['away_goals']} via "
                             f"{primary['provider']}",
                             state=state)
    if state == VERIFICATION_VERIFIED:
        store.set_tip_status(tip_id, TIP_STATUS_WON if outcome == "won"
                             else TIP_STATUS_LOST,
                             notes=f"settled vs {primary['provider']}")
        action = "settled"
    else:
        action = "review"
    return {"action": action, "settlement_id": sid,
            "gates": gates.to_dict(), "anomalies": anomalies}


def _append_settlement(store: Store, tip: Dict[str, Any], outcome: str,
                       pnl: float, result_id: Optional[str],
                       gates: GateLog, anomalies: List[str],
                       note: str, state: str = VERIFICATION_REVIEW) -> str:
    from .models import Settlement
    previous = store.latest_settlement(tip["tip_id"])
    supersedes = previous["settlement_id"] if previous else None
    sid = stable_id("st", tip["tip_id"], note,
                    supersedes or "initial")
    store.add_settlement(Settlement(
        settlement_id=sid,
        tip_id=tip["tip_id"],
        settled_at_utc=utcnow(),
        rule_version=SETTLEMENT_RULE_VERSION,
        outcome=outcome,
        pnl_units=pnl,
        stake_units=tip["stake_units"],
        odds_decimal=tip["odds_decimal"],
        result_id=result_id,
        verification_state=state,
        gate_log={**gates.to_dict(), "note": note},
        anomaly_ids=anomalies,
        supersedes_id=supersedes))
    return sid
