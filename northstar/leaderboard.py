"""Leaderboard engine (The LEAP style, but honest about verification).

Ranking rule: entrants are ordered by *verified* profit units only.
Pending/unsettled/void/imported tips never contribute to profit. An entrant
whose settled bets all came from ``review``-state settlements is shown, but
flagged ``verification_state: review`` so the UI can separate verified from
review PnL (the audit-first stance of docs/data-contract.md).
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from .db import Store
from .models import (
    TIP_STATUS_DISPUTED, TIP_STATUS_LOST, TIP_STATUS_PENDING,
    TIP_STATUS_UNSETTLEABLE, TIP_STATUS_VOID, TIP_STATUS_WON,
)


def _max_drawdown(pnl_sequence: List[float]) -> float:
    """Peak-to-trough drawdown of the *cumulative* PnL curve, in units.

    Note: this is not the worst single bet - a run of losses that never
    recovers has a larger drawdown than its worst single leg (tested).
    """
    cumulative = 0.0
    peak = 0.0
    max_dd = 0.0
    for pnl in pnl_sequence:
        cumulative += pnl
        peak = max(peak, cumulative)
        max_dd = max(max_dd, peak - cumulative)
    return round(max_dd, 10)


def entrant_metrics(store: Store, entrant_id: str) -> Dict[str, Any]:
    """Metrics for one entrant from its *settled* (non-void) paper bets."""
    tips = store.tips(tipster_id=entrant_id)
    settled = 0
    wins = 0
    losses = 0
    voids = 0
    pending = 0
    disputed = 0
    profit_units = 0.0
    turnover_units = 0.0
    pnl_seq: List[float] = []
    any_review = False
    any_verified = False
    for tip in tips:
        # The settlement row is the PnL source of truth (audit trail). A tip
        # may still carry status 'open' while holding a review-state
        # settlement; that PnL is counted but demoted, never ranked as
        # verified.
        s = store.latest_settlement(tip["tip_id"])
        if s is not None and s["outcome"] in ("won", "half_won", "lost",
                                              "half_lost", "void", "push"):
            settled += 1
            if s["verification_state"] == "review":
                any_review = True
            else:
                any_verified = True
            if s["outcome"] in ("void", "push"):
                voids += 1
                continue
            # counted bets (won/lost, incl. quarter-line half outcomes):
            # pnl is the exact blended figure from the settlement row; the
            # W/L display counts half stakes as half a win / half a loss
            # (weighted), so strike rate stays an honest probability.
            profit_units += s["pnl_units"]
            turnover_units += s["stake_units"]
            pnl_seq.append(s["pnl_units"])
            if s["outcome"] in ("won", "half_won"):
                wins += 1.0 if s["outcome"] == "won" else 0.5
            else:
                losses += 1.0 if s["outcome"] == "lost" else 0.5
            continue
        status = tip["status"]
        if status == TIP_STATUS_PENDING:
            pending += 1
        elif status == TIP_STATUS_DISPUTED:
            disputed += 1
        # open tips: nothing yet
    counted = len(pnl_seq)
    roi = (profit_units / turnover_units) if turnover_units else None
    strike = (wins / counted) if counted else None
    return {
        "entrant_id": entrant_id,
        "settled_bets": counted,
        "wins": wins,
        "losses": losses,
        "voids": voids,
        "pending": pending,
        "disputed": disputed,
        "profit_units": round(profit_units, 6),
        "turnover_units": round(turnover_units, 6),
        "roi": round(roi, 6) if roi is not None else None,
        "strike_rate": round(strike, 6) if strike is not None else None,
        "max_drawdown_units": _max_drawdown(pnl_seq) if pnl_seq else None,
        "verification_state": ("review" if any_review and not any_verified
                               else ("mixed" if any_review and any_verified
                                     else ("verified" if any_verified
                                           else "none"))),
        "pnl_sequence": pnl_seq,
    }


def build_leaderboard(store: Store) -> List[Dict[str, Any]]:
    entrants = store.entrants()
    rows = []
    for e in entrants:
        m = entrant_metrics(store, e["entrant_id"])
        entrant_tips = store.tips(tipster_id=e["entrant_id"])
        if not entrant_tips:
            # A strategy that passed on every event has no record at all;
            # a 0.00-profit row would imply a settled zero.  It is shown in
            # the strategy lab (bets=0), not on the PnL board.
            continue
        if (m["settled_bets"] == 0 and all(
                t["status"] == TIP_STATUS_UNSETTLEABLE
                for t in entrant_tips)):
            # Prediction-only desk (e.g. a sport without a permissioned odds
            # path). Showing a 0.00 profit row would imply a settled zero;
            # the desk belongs to the accuracy section, not the PnL
            # competition table.
            continue
        rows.append({
            "entrant_id": e["entrant_id"],
            "name": e["name"],
            "kind": e["kind"],
            "description": e["description"],
            **{k: v for k, v in m.items() if k != "pnl_sequence"},
            "profit_units_ranked": m["profit_units"],
        })
    # Rank by verified profit; review-state PnL is shown but demoted after
    # fully-verified entrants with equal-or-better profit.
    def sort_key(r):
        verified = 0 if r["verification_state"] == "review" else 1
        return (verified, r["profit_units_ranked"],
                r["roi"] if r["roi"] is not None else -999.0,
                r["entrant_id"])
    rows.sort(key=sort_key, reverse=True)
    for i, r in enumerate(rows, 1):
        r["rank"] = i
    return rows


def placed_bets(store: Store,
                entrant_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """All settled + open bets (for the "review all placed bets" view)."""
    out = []
    tips = store.tips(tipster_id=entrant_id)
    for tip in tips:
        event = store.get_event(tip["event_id"]) or {}
        s = store.latest_settlement(tip["tip_id"])
        if event.get("home_team") and event.get("away_team"):
            event_label = f"{event['home_team']} v {event['away_team']}"
        else:
            event_label = "OLBG snapshot event (not matched to an " \
                          "official fixture)"
        out.append({
            "tip_id": tip["tip_id"],
            "entrant": tip["tipster_id"],
            "event_id": tip["event_id"],
            "event": event_label,
            "sport": event.get("sport"),
            "event_start_utc": event.get("scheduled_start_utc"),
            "market": tip["market"],
            "selection": tip["selection"],
            "selection_key": tip["selection_key"],
            "odds": tip["odds_decimal"],
            "odds_source": tip["odds_source"],
            "stake_units": tip["stake_units"],
            "line": tip.get("line"),
            "published_at_utc": tip["published_at_utc"],
            "cutoff_at_utc": tip["cutoff_at_utc"],
            "source_url": tip.get("source_url"),
            "status": tip["status"],
            "pnl_units": (s["pnl_units"] if s and s["outcome"] != "void"
                          else None),
            "settlement": ({"outcome": s["outcome"],
                            "verification_state": s["verification_state"]}
                           if s else None),
            "notes": tip["notes"],
        })
    out.sort(key=lambda r: (r["event_start_utc"] or "", r["entrant"]))
    return out


def upcoming_bets(store: Store,
                  now: Optional[Any] = None) -> List[Dict[str, Any]]:
    """Bets the desk currently holds that are not yet decided.

    Includes open/pending/disputed rows (as before) and *forward-test*
    prediction rows (status ``unsettleable``) whose event start lies in
    the future of ``now`` - those are genuine upcoming calls.  Historical
    prediction-only rows (hockey/darts pilots on 2024/25 fixtures) stay out
    of "upcoming": their events already started, and they are graded in the
    strategy/accuracy views instead.
    """
    from .models import parse_utc, utcnow
    now = now or utcnow()
    out = []
    for b in placed_bets(store):
        if b["status"] in ("open", "pending", "disputed"):
            out.append(b)
        elif b["status"] == TIP_STATUS_UNSETTLEABLE and b["event_start_utc"]:
            try:
                if parse_utc(b["event_start_utc"]) > now:
                    out.append(b)
            except ValueError:
                continue
    return out
