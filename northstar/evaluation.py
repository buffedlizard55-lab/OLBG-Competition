"""Prediction grading for sports without a permissioned odds path.

A prediction-only sport (currently ice hockey/DEL) cannot produce PnL:
there is no recorded entry price, so no stake, no win amount, no loss. What
*can* be measured honestly is predictive quality against stored results:
hit rate and Brier score, per matchday. This module computes exactly that
and nothing more. It refuses to grade events whose stored results are
conflicting or missing a final score - those stay in the review queue.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from . import models
from .db import Store
from .models import ANOMALY_RESULT_KIND_INCONSISTENT, parse_utc

OUTCOMES = ("home", "draw", "away")


def outcome_key(home_goals: int, away_goals: int) -> str:
    if home_goals > away_goals:
        return "home"
    if home_goals < away_goals:
        return "away"
    return "draw"


def regulation_outcome(result_row: Dict[str, Any],
                       home_goals: int, away_goals: int
                       ) -> Optional[str]:
    """Regulation-time (3-period) 3-way outcome for hockey, or None.

    The stored result row is the FINAL (OT/SO-aware) row chosen by the
    adapter's priority rule (AfterPenalties > AfterExtraTime >
    After90Minutes):
    - kind ``After90Minutes``: the final was decided in regulation, so the
      stored scoreline IS the regulation scoreline;
    - kind ``AfterExtraTime`` / ``AfterPenalties``: the game went to
      overtime/penalties, which is only possible after a DRAWN regulation.
    Unknown/missing kind -> None (refuse to guess; the row stays
    ungraded).
    """
    kind = result_row.get("result_type_kind")
    if kind == models.RESULT_KIND_AFTER_90:
        return outcome_key(home_goals, away_goals)
    if kind in (models.RESULT_KIND_AFTER_EXTRA,
                models.RESULT_KIND_AFTER_PENALTIES):
        return "draw"
    return None


def naive_baseline_comparison(desk_eval: Optional[Dict[str, Any]],
                              baseline_eval: Optional[Dict[str, Any]],
                              baseline_id: str) -> Optional[Dict[str, Any]]:
    """Compare an accuracy desk against its naive baseline (site flag).

    Pure point-estimate comparison of hit rates, each on its OWN graded
    pool (a selective desk grades fewer matches than a no-selectivity
    baseline - the pools differ and the payload says so).  Returns None
    when either side has nothing graded: no number beats nothing, and the
    site renders no flag instead of inventing a comparison.  ``beats``
    is strictly-greater hit rate on this sample - never a significance
    claim; the caller's wording must keep the error-bar caveat.
    """
    if not desk_eval or not baseline_eval:
        return None
    da = desk_eval.get("accuracy")
    ba = baseline_eval.get("accuracy")
    dn = desk_eval.get("n_graded") or 0
    bn = baseline_eval.get("n_graded") or 0
    if da is None or ba is None or not dn or not bn:
        return None
    return {
        "strategy_id": baseline_id,
        "desk_accuracy": da,
        "desk_n_graded": dn,
        "accuracy": ba,
        "n_graded": bn,
        "beats_baseline": da > ba,
    }


def brier_three(probs: Dict[str, float], actual: str) -> float:
    if actual not in OUTCOMES:
        raise ValueError(f"unknown outcome {actual}")
    return sum((float(probs.get(k, 0.0)) - (1.0 if k == actual else 0.0)) ** 2
               for k in OUTCOMES)


def prediction_accuracy(store: Store, bets: List[Dict[str, Any]],
                        sport: Optional[str] = None,
                        outcome: str = "final") -> Dict[str, Any]:
    """Measure a walk-forward report's prediction quality from the store.

    ``bets`` are engine decision logs (event_id, selection, model). Only
    rows whose event has a finished, mutually-consistent stored result are
    graded; everything else is listed under ``ungraded`` with a reason.

    ``outcome``: which stored result row defines "actual".
    - ``"final"`` (default): the decisive final score (OT/SO-aware for
      hockey) -> 2-way/3-way as scored by ``outcome_key``.
    - ``"regulation_3way"``: the regulation-time (3-period) 3-way outcome
      for hockey, resolved via :func:`regulation_outcome` from the stored
      final row's kind.  Rows whose kind cannot be resolved stay ungraded.
    """
    if outcome not in ("final", "regulation_3way"):
        raise ValueError(f"unknown outcome mode: {outcome}")
    graded: List[Dict[str, Any]] = []
    ungraded: List[Dict[str, Any]] = []
    # Results under review (RESULT_KIND_INCONSISTENT) are never graded on -
    # the review queue owns the verdict (same rule as the walk-forward).
    flagged = {a["entity_id"]
               for a in store.anomalies(status="open")
               if a["kind"] == ANOMALY_RESULT_KIND_INCONSISTENT}
    for bet in bets:
        eid = bet["event_id"]
        if eid in flagged:
            ungraded.append({"event_id": eid,
                             "reason": "result flagged for review "
                                       "(RESULT_KIND_INCONSISTENT)"})
            continue
        event = store.get_event(eid)
        results = [r for r in store.results(eid)
                   if r["final_status"] == "finished"]
        scores = {(r["home_goals"], r["away_goals"]) for r in results}
        if not results:
            ungraded.append({"event_id": eid, "reason": "no finished result"})
            continue
        if len(scores) != 1 or None in next(iter(scores)):
            ungraded.append({"event_id": eid,
                             "reason": "conflicting or incomplete result"})
            continue
        hg, ag = next(iter(scores))
        if outcome == "regulation_3way":
            primary = max(results,
                          key=lambda r: parse_utc(r["officially_final_at_utc"]))
            actual = regulation_outcome(primary, hg, ag)
            if actual is None:
                ungraded.append({
                    "event_id": eid,
                    "reason": ("regulation outcome not resolvable from the "
                               "stored final row's kind")})
                continue
        else:
            actual = outcome_key(hg, ag)
        probs = (bet.get("model") or {}).get("model_prob") or {}
        graded.append({
            "event_id": eid,
            "group_order": event.get("group_order") if event else None,
            "start_utc": event.get("scheduled_start_utc") if event else None,
            "selection": bet["selection"],
            "actual": actual,
            "hit": bet["selection"] == actual,
            "brier": (brier_three(probs, actual)
                      if all(k in probs for k in OUTCOMES) else None),
            "result_kind": results[0].get("result_type_kind"),
            "outcome_mode": outcome,
            "single_source_providers": [r["provider"] for r in results],
        })

    n = len(graded)
    hits = sum(1 for g in graded if g["hit"])
    briers = [g["brier"] for g in graded if g["brier"] is not None]
    by_matchday: Dict[str, Dict[str, Any]] = {}
    for g in graded:
        key = str(g["group_order"])
        d = by_matchday.setdefault(key, {"n": 0, "hits": 0})
        d["n"] += 1
        d["hits"] += 1 if g["hit"] else 0
    for d in by_matchday.values():
        d["accuracy"] = round(d["hits"] / d["n"], 6) if d["n"] else None
    return {
        "sport": sport,
        "outcome_mode": outcome,
        "n_graded": n,
        "hits": hits,
        "accuracy": round(hits / n, 6) if n else None,
        "mean_brier": (round(sum(briers) / len(briers), 6)
                       if briers else None),
        "by_matchday": by_matchday,
        "ungraded": ungraded,
        "graded": graded,
        "note": ("Hit rate and Brier score against stored single-source "
                 "results (identity 'probable' until an independent "
                 "cross-check is attached). Not PnL: no entry price exists "
                 "for this sport, so profit cannot be computed and is shown "
                 "as unavailable, never as zero."),
    }
