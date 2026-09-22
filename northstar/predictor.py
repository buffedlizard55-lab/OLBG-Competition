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

    if model and model.get("ratings") is not None:
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
    totals = False
    ah = False
    if model and "model_prob" in model:
        mp = model["model_prob"]
        if all(k in mp for k in ("home", "draw", "away")):
            bits.append(
                f"Our three-way model has "
                f"{home} {_pct(mp['home'])}, draw {_pct(mp['draw'])}, "
                f"{away} {_pct(mp['away'])}.")
        elif all(k in mp for k in ("over", "under")):
            totals = True
            lam = model.get("lambda")
            lam_txt = (f" (expected goals {lam['home']:.2f} + "
                       f"{lam['away']:.2f})"
                       if lam and lam.get("home") is not None
                       and lam.get("away") is not None else "")
            bits.append(
                f"Our Poisson goal model{lam_txt} has over 2.5 "
                f"{_pct(mp['over'])}, under 2.5 {_pct(mp['under'])}.")
        elif all(k in mp for k in ("home", "away")) and all(
                isinstance(mp.get(k), dict)
                and all(x in mp[k] for x in ("win", "push", "lose"))
                for k in ("home", "away")):
            # Asian-handicap trail: model_prob is a per-side
            # win/push/lose distribution on the priced line.
            ah = True
            line = model.get("line")
            line_txt = f" (line {line:+g} on the home side)" if line is not None else ""
            sel_key = selection if selection in ("home", "away") else "home"
            p = mp[sel_key]
            side_name = home if sel_key == "home" else away
            bits.append(
                f"Our Poisson goal model on the Asian handicap{line_txt} "
                f"makes {side_name} {_pct(p['win'])} to cover, "
                f"{_pct(p['push'])} to push (stake refunded) and "
                f"{_pct(p['lose'])} to lose the line.")
        else:
            ok = False
    if fair and all(k in fair for k in ("home", "draw", "away")):
        bits.append(
            f"The market (margin-removed) implies "
            f"{home} {_pct(fair['home'])}, draw {_pct(fair['draw'])}, "
            f"{away} {_pct(fair['away'])}.")
    elif fair and totals and all(k in fair for k in ("over", "under")):
        bits.append(
            f"The market (margin-removed) implies over "
            f"{_pct(fair['over'])}, under {_pct(fair['under'])}.")
    elif fair and ah and all(k in fair for k in ("home", "away")):
        bits.append(
            f"The de-margined prices imply {home} {_pct(fair['home'])} / "
            f"{away} {_pct(fair['away'])} to cover the line.")
    if selection and edge:
        e = edge.get(selection)
        if e is not None:
            if e >= 0:
                if ah:
                    bits.append(
                        f"We are backing {selection} - our model makes it "
                        f"{e * 100:+.1f} expected-value points per unit "
                        f"staked against the de-margined price, a value "
                        f"edge worth acting on.")
                else:
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

    if totals and selection in ("over", "under"):
        sel_label = f"{selection.upper()} 2.5 GOALS"
    elif ah and selection in ("home", "away"):
        line = model.get("line")
        side = home if selection == "home" else away
        # the stored line is quoted on the home team; the away side's
        # handicap is the mirror (same convention as the bets table)
        own_line = -line if (line is not None
                             and selection == "away") else line
        sel_label = (f"{side.upper()} {own_line:+g} AH"
                     if own_line is not None else f"{side.upper()} AH")
    else:
        sel_label = selection.upper() if selection else ""
    if not ok:
        body = ("No call. The verified evidence is incomplete for a "
                "defensible tip (missing model/market/edge), and this desk "
                "does not write predictions without evidence.")
    else:
        verdict = (f"Tip: {sel_label}" if selection
                   else "No bet this round.")
        body = " ".join(bits)
        if selection:
            body += f" {verdict}"
        body += " Paper trading only - not betting advice."

    headline = (f"{home} v {away}: {sel_label}"
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
    # Naive baseline desks (home-ice / listed-first) carry the flat 0.5/0.5
    # prior and a rule, deliberately no ratings: render them with their own
    # honest copy instead of refusing - a reference call is worth reading.
    if not ratings and model.get("prior") and model.get("rule"):
        if not all(k in probs for k in ("home", "draw", "away")):
            return {"headline": f"{home} v {away}: No call",
                    "body": "Forward baseline entry lacks its full flat "
                            "prior trail - refusing to write it.",
                    "evidence_ok": False, "source_links": source_links or []}
        picked = entry.get("selection_key")
        picked_name = home if picked == "home" else away
        bits = [
            f"This is the desk's no-information reference call: "
            f"{model.get('rule')} - flat 50/50 prior, no model, no market "
            f"input.",
            f"It is on record as {picked_name} from "
            f"{entry.get('cutoff_utc', 'the recorded cutoff')} - before "
            f"kick-off, frozen in the forward-test ledger.",
            "Its graded hit rate is the bar the model desks must beat; "
            "there is no profit claim attached to it in either direction.",
        ]
        body = " ".join(bits) + " Paper trading only - not betting advice."
        headline = f"{home} v {away}: {str(selection).upper()} (baseline)"
        return {"headline": headline, "body": body, "evidence_ok": True,
                "source_links": source_links or []}
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
