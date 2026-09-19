"""Site-data report builder (site-data/site.json for the GitHub Pages UI).

The JSON is the single source the static site renders. Every number in it
comes from the store (paper settlements, anomalies) or from the policy
registry - never from prose.
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

from .db import Store
from .leaderboard import build_leaderboard, placed_bets, upcoming_bets
from .policy import all_policies
from . import models

# Sport coverage: the honest per-sport status, mirroring the sports OLBG
# lists (verified 2026-09-19 on the site's tips index and sports menu).
# A sport is "pilot_verified" only when a permissioned results path AND a
# permissioned odds path have been verified end-to-end with stored,
# hash-checked evidence. "scope": "olbg" = listed on OLBG; "extra" =
# candidate beyond the OLBG list.
SPORT_COVERAGE = [
    {"sport": "Football", "scope": "olbg",
     "status": "pilot_verified",
     "results_path": "OpenLigaDB (ODbL-1.0), Bundesliga 2024/25 pilot",
     "odds_path": "football-data.co.uk D1 manual import (research-use flag)",
     "note": "27-match hand-audited pilot (matchdays 1/10/20), 27/27 "
             "dual-source result agreement. Full-season ingest runs in CI."},
    {"sport": "Darts", "scope": "olbg",
     "status": "results_path_available",
     "results_path": "OpenLigaDB PDC endpoints (ODbL-1.0)",
     "odds_path": "unverified",
     "note": "Results path open-licensed; no permissioned odds source "
             "verified yet -> no PnL. Next expansion candidate after "
             "football scale-up."},
    {"sport": "Horse Racing", "scope": "olbg", "status": "verification_blocked",
     "results_path": "none verified", "odds_path": "none verified",
     "note": "Not covered: no permissioned results or odds source "
             "identified yet."},
    {"sport": "Rugby Union", "scope": "olbg", "status": "verification_blocked",
     "results_path": "none verified", "odds_path": "none verified",
     "note": "Not covered: no permissioned results or odds source "
             "identified yet."},
    {"sport": "American Football", "scope": "olbg",
     "status": "verification_blocked",
     "results_path": "none verified", "odds_path": "none verified",
     "note": "Not covered: no permissioned results or odds source "
             "identified yet (CFL events observed on OLBG)."},
    {"sport": "Baseball", "scope": "olbg", "status": "verification_blocked",
     "results_path": "none verified", "odds_path": "none verified",
     "note": "Not covered: no permissioned results or odds source "
             "identified yet (MLB events observed on OLBG)."},
    {"sport": "Motor Racing", "scope": "olbg", "status": "verification_blocked",
     "results_path": "none verified", "odds_path": "none verified",
     "note": "Not covered: no permissioned results or odds source "
             "identified yet."},
    {"sport": "Boxing", "scope": "olbg", "status": "verification_blocked",
     "results_path": "none verified", "odds_path": "none verified",
     "note": "Not covered: no permissioned results or odds source "
             "identified yet."},
    {"sport": "Greyhounds", "scope": "olbg", "status": "verification_blocked",
     "results_path": "none verified", "odds_path": "none verified",
     "note": "Not covered: no permissioned results or odds source "
             "identified yet."},
    {"sport": "Ice Hockey", "scope": "extra",
     "status": "results_path_available",
     "results_path": "OpenLigaDB del/del2/CHL endpoints (ODbL-1.0)",
     "odds_path": "unverified",
     "note": "NOT listed on OLBG (2026-09-19 capture); tracked as an extra "
             "candidate because its results path is open-licensed. No "
             "permissioned odds source verified yet -> no PnL."},
]


def build_site_data(store: Store, raw_dir: str,
                    predictions: Optional[List[Dict[str, Any]]] = None,
                    backtest_meta: Optional[Dict[str, Any]] = None,
                    out_path: Optional[str] = None) -> Dict[str, Any]:
    captures = store.captures()
    by_source = {}
    for c in captures:
        by_source.setdefault(c["source_id"], []).append(c)

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
                "competition": "1. Fu\u00dfball-Bundesliga 2024/2025",
                "matchdays": [1, 10, 20],
                "events": store.kv_get("pilot_events"),
                "dual_source_agreement": store.kv_get(
                    "pilot_dual_source_agreement"),
                "note": "27 hand-audited events; results OpenLigaDB (ODbL), "
                        "odds football-data.co.uk manual import "
                        "(research-use flag, no redistribution).",
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
        } for p in all_policies()],
        "coverage": SPORT_COVERAGE,
        "captures": captures,
    }
    if out_path:
        os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, ensure_ascii=False, sort_keys=True)
    return data
