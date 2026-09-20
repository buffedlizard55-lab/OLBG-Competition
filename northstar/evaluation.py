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

from .db import Store
from .models import parse_utc

OUTCOMES = ("home", "draw", "away")


def outcome_key(home_goals: int, away_goals: int) -> str:
    if home_goals > away_goals:
        return "home"
    if home_goals < away_goals:
        return "away"
    return "draw"


def brier_three(probs: Dict[str, float], actual: str) -> float:
    if actual not in OUTCOMES:
        raise ValueError(f"unknown outcome {actual}")
    return sum((float(probs.get(k, 0.0)) - (1.0 if k == actual else 0.0)) ** 2
               for k in OUTCOMES)


def prediction_accuracy(store: Store, bets: List[Dict[str, Any]],
                        sport: Optional[str] = None) -> Dict[str, Any]:
    """Measure a walk-forward report's prediction quality from the store.

    ``bets`` are engine decision logs (event_id, selection, model). Only
    rows whose event has a finished, mutually-consistent stored result are
    graded; everything else is listed under ``ungraded`` with a reason.
    """
    graded: List[Dict[str, Any]] = []
    ungraded: List[Dict[str, Any]] = []
    for bet in bets:
        eid = bet["event_id"]
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
