"""Site-data report builder (site-data/site.json for the GitHub Pages UI).

The JSON is the single source the static site renders. Every number in it
comes from the store (paper settlements, anomalies) or from the policy
registry - never from prose. Raw licensed-provider responses are never copied
into this payload.
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

from .db import Store
from .leaderboard import build_leaderboard, placed_bets, upcoming_bets
from .policy import all_policies
from .sources import sport_source_payload
from . import models

# The inventory is taken from the public OLBG betting-tips page manually
# reviewed on 2026-09-20.  A row is not a claim of data coverage.  A sport is
# ``pilot_verified`` only when a permissioned result path and a permissioned
# odds path have both passed an end-to-end audit.  The two result-path rows
# below have no odds path, so they cannot produce PnL.
SPORT_COVERAGE = [
    {
        "sport": "Football", "scope": "olbg", "status": "pilot_verified",
        "results_path": ("OpenLigaDB (ODbL-1.0), Bundesliga 2024/25 pilot; "
                         "2026/27 captures: bl1, pl, bl2, la1"),
        "odds_path": (
            "football-data.co.uk manual pilot; The Odds API licensed connector "
            "implemented but inactive"
        ),
        "note": (
            "27-match hand-audited pilot (matchdays 1/10/20), 27/27 "
            "dual-source result agreement; three markets backtested (1X2, "
            "over/under 2.5 and Asian handicap - all from the same pilot "
            "file). Forward-test "
            "desk live on the current season for Bundesliga, Premier "
            "League, 2. Bundesliga and LaLiga 2026/27 (prediction-only: "
            "no permissioned odds path for 2026/27; single-source, "
            "identity 'probable'). This is not an official DFL/PL/LaLiga "
            "feed."
        ),
    },
    # Ice Hockey is built dynamically in _hockey_coverage_row(store) so
    # the row always reflects what is actually in the store (the full
    # season once capture-pilot has committed it).
]

# Darts coverage is built dynamically (see build_coverage): the row is
# promoted from results_path_available to results_pilot only when a
# schema-audited darts pilot has actually been ingested into the store.
DARTS_COVERAGE_PENDING = {
    "sport": "Darts", "scope": "olbg", "status": "results_path_available",
    "results_path": ("OpenLigaDB PDC endpoints (ODbL-1.0); discovery probe "
                     "2026-09-20 found the previously documented "
                     "PDCWSDF/2024 pair returns an empty list - capture is "
                     "discovery-driven (CI capture-log)"),
    "odds_path": "none verified",
    "note": ("Results-only path is not enough for PnL; keep blocked until "
             "an odds path and settlement rules pass."),
}

# These are deliberately explicit rather than silently omitted.  The public
# OLBG catalogue lists them, but this repo has not verified a result+odds+rule
# path for them.  A future sport may be promoted only after the source and test
# gates pass.
BLOCKED_SPORT_COVERAGE = []
for _sport in (
    "Horse Racing", "Tennis", "Golf", "American Football", "Baseball",
    "Basketball", "Boxing", "Cricket", "Cycling", "Gaelic Football",
    "Greyhounds", "Handball", "Hurling", "Motor Racing", "Rugby Union",
    "Rugby League", "Snooker", "Volleyball",
):
    BLOCKED_SPORT_COVERAGE.append({
        "sport": _sport,
        "scope": "olbg",
        "status": "verification_blocked",
        "results_path": "none verified in this repository",
        "odds_path": "none verified in this repository",
        "note": (
            "Listed by OLBG, but no permissioned result source, historical "
            "odds source, identity join and sport-specific settlement test "
            "has passed. No PnL or prediction is generated."
        ),
    })


def _hockey_coverage_row(store: Store) -> Dict[str, Any]:
    """Ice hockey coverage row, built from the store (evidence-based).

    The row reports the actual ingested pilot: the three hand-audited
    matchdays plus the full season when ``capture-pilot`` has committed
    the whole-season payload (kv hockey_pilot_full_season).
    """
    events = store.kv_get("hockey_pilot_events")
    full_season = store.kv_get("hockey_pilot_full_season") == "1"
    if full_season:
        scope = (f"OpenLigaDB DEL 2024/25 full season, {events} events "
                 f"(plus hand-audited matchdays 1/20/40), ODbL-1.0; "
                 "single source, identity stays 'probable'")
        note = ("Full-season result ingest with OT/shootout-aware finals; "
                "prediction desks graded on the whole season (accuracy/"
                "Brier incl. the regulation-time 3-way pair) - PnL is "
                "unavailable, not zero. The 4 impossible-layering DEL "
                "matches stay flagged for review.")
    else:
        scope = ("OpenLigaDB DEL 2024/25 pilot, 21 events (matchdays "
                 "1/20/40), ODbL-1.0; single source, identity stays "
                 "'probable'")
        note = ("End-to-end result ingest with OT/shootout-aware finals: "
                "3 OT games, 1 shootout, 4 source-data irregularities "
                "flagged for review. Predictions are graded on "
                "accuracy/Brier only - PnL is unavailable, not zero.")
    return {
        "sport": "Ice Hockey", "scope": "olbg", "status": "results_pilot",
        "results_path": scope,
        "odds_path": "none verified - no permissioned DEL odds in this repo",
        "note": note,
    }


def build_coverage(store: Store) -> List[Dict[str, Any]]:
    """Sport coverage rows, with Darts promoted only on real pilot data.

    The promotion rule is evidence-based: darts events (schema-audited
    pilot fixtures) must exist in the store; otherwise the row stays
    ``results_path_available`` with the discovery findings.
    """
    darts_events = [e for e in store.events() if e["sport"] == "darts"]
    darts_finished = [e for e in darts_events
                      if e["status"] == "finished"]
    if darts_events:
        darts_row = {
            "sport": "Darts", "scope": "olbg",
            "status": ("results_pilot" if darts_finished
                       else "results_path_available"),
            "results_path": (
                f"OpenLigaDB PDC capture (ODbL-1.0), {len(darts_events)} "
                f"events ({len(darts_finished)} finished), schema-audited "
                "per docs/DARTS-AUDIT.md; single source, identity "
                "'probable'"),
            "odds_path": "none verified - no permissioned darts odds path",
            "note": (
                "Prediction-only pilot: graded on accuracy/Brier; PnL is "
                "unavailable (not zero) until an odds path passes the "
                "licensing gates."),
        }
    else:
        darts_row = dict(DARTS_COVERAGE_PENDING)
    return [SPORT_COVERAGE[0], darts_row, _hockey_coverage_row(store)] + \
        BLOCKED_SPORT_COVERAGE


def _json_kv(store: Store, key: str):
    raw = store.kv_get(key)
    if not raw:
        return None
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return None


def build_site_data(store: Store, raw_dir: str,
                    predictions: Optional[List[Dict[str, Any]]] = None,
                    backtest_meta: Optional[Dict[str, Any]] = None,
                    out_path: Optional[str] = None,
                    forward_report: Optional[Dict[str, Any]] = None,
                    registry: Optional[Dict[str, Any]] = None
                    ) -> Dict[str, Any]:
    captures = store.captures()
    leaderboard = build_leaderboard(store)
    placed = placed_bets(store)
    upcoming = upcoming_bets(store)
    anomalies = store.anomalies()

    data = {
        "meta": {
            "title": "Northstar Competition Lab",
            "built_utc": models.fmt_utc(models.utcnow()),
            "paper_trading": True,
            "stake_basis": "level 1.0 units per bet (profit units)",
            "snapshot_count": len(store.odds_snapshots()),
            "event_count": len(store.events()),
            "pilot": {
                "competition": "1. Fußball-Bundesliga 2024/2025",
                "matchdays": [1, 10, 20],
                "events": store.kv_get("pilot_events"),
                "dual_source_agreement": store.kv_get(
                    "pilot_dual_source_agreement"),
                "note": (
                    "27 hand-audited events; results OpenLigaDB (ODbL), "
                    "odds football-data.co.uk manual import "
                    "(research-use flag, no redistribution). The licensed "
                    "The Odds API connector is not active in this build."
                ),
            },
            "hockey": {
                "competition": "DEL Eishockey 2024/2025",
                "matchdays": [1, 20, 40],
                "full_season": store.kv_get("hockey_pilot_full_season")
                               == "1",
                "events": store.kv_get("hockey_pilot_events"),
                "source_anomalies": store.kv_get(
                    "hockey_pilot_source_anomalies"),
                "note": (
                    "Single-source pilot (OpenLigaDB, ODbL-1.0): identity "
                    "stays 'probable' - no independent DEL cross-check "
                    "exists in this repo. Results availability is inferred "
                    "as start+3h because the source batch-edited results at "
                    "end of season; documented in docs/STATUS.md. No "
                    "permissioned odds path - predictions only, graded on "
                    "accuracy/Brier; PnL unavailable (not zero)."
                    + (" The full 2024/25 season is ingested, so the "
                       "prediction desks grade on the whole season."
                       if store.kv_get("hockey_pilot_full_season") == "1"
                       else "")
                ),
            },
            "bl1_warmup": {
                "competition": "Bundesliga 1 2024/2025 (full season)",
                "events": store.kv_get("bl1_warmup_events"),
                "note": (
                    "Forward-desk rating history only (same Bundesliga "
                    "clubs as bl1/2026). NOT part of the frozen 27-match "
                    "PnL pilot, which stays pinned to matchdays 1/10/20."
                ),
            },
        },
        "leaderboard": leaderboard,
        "bets": {
            "placed": placed,
            "upcoming": upcoming,
            "total_placed": len(placed),
            "total_upcoming": len(upcoming),
        },
        "anomalies": {
            "queue": anomalies,
            "open": len([a for a in anomalies if a["status"] == "open"]),
        },
        "predictions": predictions or [],
        "backtest": backtest_meta or {},
        "forward": forward_report or {
            "state": "awaiting_first_capture",
            "note": ("No current-season capture is committed yet. The CI "
                     "capture workflow (capture.yml) fetches the permitted "
                     "OpenLigaDB current-season payloads and issues the "
                     "first forward-test predictions into the append-only "
                     "ledger."),
        },
        "registry": registry or {},
        "olbg_reconciliation": _json_kv(store, "olbg_reconciliation"),
        "sources": [{
            "source_id": p.source_id,
            "display_name": p.display_name,
            "license_id": p.license_id,
            "license_summary": p.license_summary,
            "collection_modes": p.collection_modes,
            "rate_limit": p.rate_limit,
            "verified_at": p.verified_at,
            "evidence_urls": p.evidence_urls,
            "caveats": p.caveats,
            "requires_active_entitlement": p.requires_active_entitlement,
            "terms_version": p.terms_version,
        } for p in all_policies()],
        "coverage": build_coverage(store),
        # Evidence-gated source registry for all 21 OLBG sport families
        # (data/sources/olbg_sports.json, validated by northstar.sources).
        "sport_sources": sport_source_payload(),
        "captures": captures,
        "entrants": store.entrants(),
    }
    if out_path:
        os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, ensure_ascii=False, sort_keys=True)
    return data
