"""Tipster-style prediction writer.

Hard rule (from the request + docs/data-contract.md): predictions may be
worded like a top-rated tipster, but every factual claim must come from a
verified stored statistic. The renderer refuses to emit a sentence whose
evidence is missing - it would rather say "no call" than invent.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional


def _pct(x: Optional[float]) -> Optional[str]:
    return f"{x * 100:.0f}%" if x is not None else None


def render_prediction(event: Dict[str, Any],
                      model: Optional[Dict[str, Any]] = None,
                      fair: Optional[Dict[str, Any]] = None,
                      edge: Optional[Dict[str, Any]] = None,
                      selection: Optional[str] = None,
                      odds: Optional[float] = None,
                      source_links: Optional[List[str]] = None,
                      ) -> Dict[str, str]:
    """Return {"headline", "body", "evidence_ok"}.

    ``evidence_ok`` is False (and the body is a refusal) when the fields
    needed for any factual sentence are absent.
    """
    home = event.get("home_team")
    away = event.get("away_team")
    if not home or not away:
        return {"headline": "No call", "body":
                "Missing verified event identity - refusing to write a "
                "prediction without it.", "evidence_ok": False}

    bits: List[str] = []
    ok = True

    if model and "ratings" in model:
        rh, ra = model["ratings"].get("home"), model["ratings"].get("away")
        if rh is not None and ra is not None:
            diff = rh - ra
            if abs(diff) < 1.0:
                bits.append(
                    f"Ratings are level ({rh:.0f} vs {ra:.0f}) - "
                    f"nothing separates the two yet.")
            else:
                leader = home if diff > 0 else away
                bits.append(
                    f"On ratings ({rh:.0f} vs {ra:.0f}) {leader} is the "
                    f"stronger side going in.")
        else:
            ok = False
    if model and "model_prob" in model:
        mp = model["model_prob"]
        if all(k in mp for k in ("home", "draw", "away")):
            bits.append(
                f"Our three-way model has "
                f"{home} {_pct(mp['home'])}, draw {_pct(mp['draw'])}, "
                f"{away} {_pct(mp['away'])}.")
        else:
            ok = False
    if fair and all(k in fair for k in ("home", "draw", "away")):
        bits.append(
            f"The market (margin-removed) implies "
            f"{home} {_pct(fair['home'])}, draw {_pct(fair['draw'])}, "
            f"{away} {_pct(fair['away'])}.")
    if selection and edge:
        e = edge.get(selection)
        if e is not None:
            if e >= 0:
                bits.append(
                    f"We are backing {selection} - our model rates it "
                    f"{e * 100:+.0f} points against the market price, a "
                    f"clear value edge worth acting on.")
            else:
                ok = False
    if odds is not None and selection:
        bits.append(f"Getting it at {odds:.2f} makes the risk worth taking "
                    f"on a level stake.")

    if not bits:
        ok = False

    if not ok:
        body = ("No call. The verified evidence is incomplete for a "
                "defensible tip (missing model/market/edge), and this desk "
                "does not write predictions without evidence.")
    else:
        verdict = (f"Tip: {selection.upper()}" if selection
                   else "No bet this round.")
        body = " ".join(bits)
        if selection:
            body += f" {verdict}"
        body += " Paper trading only - not betting advice."

    headline = (f"{home} v {away}: {selection.upper()}"
                if selection else f"{home} v {away}: No call")
    return {"headline": headline, "body": body, "evidence_ok": ok,
            "source_links": source_links or []}


def render_forward_prediction(entry: Dict[str, Any],
                              source_links: Optional[List[str]] = None,
                              ) -> Dict[str, Any]:
    """Tipster-style rendering of a frozen forward-test ledger entry.

    Forward desks have *no* market price (no permissioned odds path for the
    current season), so the renderer must never imply one: it states the
    model trail, the cutoff, and that grading is accuracy-only.  Evidence
    discipline is identical to ``render_prediction``: without ratings and a
    full model probability trail it refuses (``evidence_ok`` False).
    """
    model = entry.get("model") or {}
    probs = model.get("model_prob") or {}
    ratings = model.get("ratings") or {}
    home, away = entry.get("home_team"), entry.get("away_team")
    selection = entry.get("selection")
    if not home or not away or not selection:
        return {"headline": "No call",
                "body": "Forward entry is missing verified identity or a "
                        "recorded selection - refusing to render it.",
                "evidence_ok": False, "source_links": source_links or []}
    if not all(k in probs for k in ("home", "draw", "away")) or \
            ratings.get("home") is None or ratings.get("away") is None:
        return {"headline": f"{home} v {away}: No call",
                "body": "Forward entry lacks a complete model trail "
                        "(ratings + probabilities) - refusing to write a "
                        "tip without it.",
                "evidence_ok": False, "source_links": source_links or []}

    picked = entry.get("selection_key")
    picked_name = home if picked == "home" else (
        away if picked == "away" else "the draw")
    bits = [
        f"We make {home} {_pct(probs['home'])}, the draw "
        f"{_pct(probs['draw'])} and {away} {_pct(probs['away'])} on our "
        f"published model (ratings {ratings['home']:.0f} v "
        f"{ratings['away']:.0f}).",
        f"That points to {picked_name}, and we are on record with it from "
        f"{entry.get('cutoff_utc', 'the recorded cutoff')} - before "
        f"kick-off, frozen in the forward-test ledger.",
        "No market price is recorded for this fixture (no permissioned odds "
        "path), so this call is graded on accuracy only - there is no "
        "profit claim attached to it, in either direction.",
    ]
    body = " ".join(bits) + " Paper trading only - not betting advice."
    headline = f"{home} v {away}: {str(selection).upper()}"
    return {"headline": headline, "body": body, "evidence_ok": True,
            "source_links": source_links or []}
