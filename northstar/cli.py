"""Command-line pipeline.

    python -m northstar.cli run-pipeline [--fresh]
    python -m northstar.cli verify

run-pipeline (fully offline - committed fixtures only):
  1. ingest OpenLigaDB pilot matchdays (results, ODbL)
  2. cross-check + import football-data pilot odds (manual import)
  3. import manual OLBG snapshots (policy-gated, pending only)
  4. run the four strategies walk-forward (strict cutoffs)
  5. render evidence-only predictions for a few settled bets
  6. emit site-data/site.json for the GitHub Pages UI
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from typing import Any, Dict, List

from . import models
from .adapters import football_data, olbg, openligadb
from .backtest import run_walk_forward
from .db import Store
from .evaluation import prediction_accuracy
from .leaderboard import build_leaderboard
from .predictor import render_prediction
from .policy import MODE_AUTO_API
from .report import build_site_data
from .strategies import (
    FOOTBALL_STRATEGIES, HOCKEY_STRATEGIES, PREDICTION_ONLY_STRATEGIES,
    build,
)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIXTURES = os.path.join(ROOT, "data", "fixtures")
RAW = os.path.join(ROOT, "data", "raw")
DB_PATH = os.path.join(ROOT, "data", "northstar.db")
SITE_OUT = os.path.join(ROOT, "site-data", "site.json")

CAPTURE_DATE = "2026-09-19"
HOCKEY_CAPTURE_DATE = "2026-09-20"


def _sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _read(path: str) -> str:
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read()


def ingest_pilot(store: Store) -> Dict[str, Any]:
    stats: Dict[str, Any] = {"events": 0, "results": 0}
    for name in ("openligadb_bl1_2024_sd1.json",
                 "openligadb_bl1_2024_sd10.json",
                 "openligadb_bl1_2024_sd20.json"):
        path = os.path.join(FIXTURES, name)
        text = _read(path)
        capture_id = "cap-" + name
        store.register_capture(
            capture_id, "openligadb",
            os.path.relpath(path, ROOT), _sha256_file(path),
            models.parse_utc(CAPTURE_DATE + "T00:00:00Z"),
            "manual_snapshot",
            "pilot fixture transcribed 2026-09-19 from "
            "api.openligadb.de/getmatchdata/bl1/2024/<matchday>")
        out = openligadb.ingest_matchday(store, text, verify_identity=True,
                                         sport="football")
        stats["events"] += out["events"]
        stats["results"] += out["results"]
    csv_path = os.path.join(FIXTURES, "football_data_d1_2425_pilot.csv")
    store.register_capture(
        "cap-footballdata-d1-2425-pilot", "football_data",
        os.path.relpath(csv_path, ROOT), _sha256_file(csv_path),
        models.parse_utc(CAPTURE_DATE + "T00:00:00Z"),
        "manual_import",
        "27 rows of mmz4281/2425/D1.csv captured 2026-09-19 for private "
        "non-commercial research; no redistribution")
    csv_stats = football_data.ingest_csv_text(store, _read(csv_path))
    stats["odds_snapshots"] = csv_stats["odds_snapshots"]
    stats["cross_checked"] = csv_stats["cross_checked"]
    stats["cross_checked_agree"] = csv_stats["cross_checked_agree"]
    stats["csv_anomalies"] = csv_stats["anomalies"]
    stats["events_pilot"] = store.kv_get("pilot_events")
    return stats


def ingest_hockey_pilot(store: Store) -> Dict[str, Any]:
    """DEL 2024/25 matchdays 1/20/40 (OpenLigaDB, ODbL-1.0).

    Single-source results: identity stays 'probable' (no independent
    cross-check exists for DEL in this repo), so hockey never produces
    verified PnL - only predictions graded on accuracy.
    """
    stats: Dict[str, Any] = {"events": 0, "results": 0, "anomalies": 0}
    for name in ("openligadb_del_2024_sd1.json",
                 "openligadb_del_2024_sd20.json",
                 "openligadb_del_2024_sd40.json"):
        path = os.path.join(FIXTURES, name)
        text = _read(path)
        store.register_capture(
            "cap-" + name, "openligadb",
            os.path.relpath(path, ROOT), _sha256_file(path),
            models.parse_utc(HOCKEY_CAPTURE_DATE + "T00:00:00Z"),
            MODE_AUTO_API,
            "DEL 2024/25 matchday payload fetched via permitted automated "
            "API (ODbL-1.0) on 2026-09-20, chunk-assembled with strict JSON "
            "validation (scripts/assemble_fixture.py)")
        out = openligadb.ingest_matchday(store, text, verify_identity=True,
                                         sport="ice_hockey")
        stats["events"] += out["events"]
        stats["results"] += out["results"]
        stats["anomalies"] += out["anomalies"]
    return stats


def ingest_olbg(store: Store) -> Dict[str, Any]:
    return olbg.ingest_snapshots(store, RAW)


def run_backtests(store: Store) -> Dict[str, Any]:
    finished = [e for e in store.events() if e["status"] == "finished"]
    football_events = [e for e in finished if e["sport"] == "football"]
    hockey_events = [e for e in finished if e["sport"] == "ice_hockey"]
    reports: Dict[str, Any] = {}
    for sid in FOOTBALL_STRATEGIES:
        strategy = build(sid)
        strategy.sport = "football"
        reports[sid] = run_walk_forward(store, football_events, strategy,
                                        sid, label="pilot")
    for sid in HOCKEY_STRATEGIES:
        strategy = build(sid)
        reports[sid] = run_walk_forward(store, hockey_events, strategy, sid,
                                        label="hockey-pilot",
                                        allow_no_odds=True)
        reports[sid]["evaluation"] = prediction_accuracy(
            store, reports[sid]["bets"], sport="ice_hockey")
    store.commit()
    return reports


def _pick_predictions(store: Store,
                      reports: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Render evidence-only predictions for up to 4 settled backtest bets
    that carry a full model/fair/edge trail."""
    out: List[Dict[str, Any]] = []
    seen = set()
    for sid, rep in reports.items():
        for bet in rep["bets"]:
            model = bet.get("model") or {}
            if sid in ("elo-edge-v1", "draw-no-bet-v1") and \
                    model.get("model_prob") and model.get("fair_prob") and \
                    model.get("edge") is not None:
                event = store.get_event(bet["event_id"])
                if not event or bet["event_id"] in seen:
                    continue
                sel = bet["selection"]
                rendered = render_prediction(
                    event,
                    model={"ratings": model.get("ratings"),
                           "model_prob": model["model_prob"]},
                    fair=model.get("fair_prob"),
                    edge=model.get("edge"),
                    selection=sel,
                    odds=bet.get("odds"),
                    source_links=[event.get("source_url") or "",
                                  football_data.FILE_URL])
                if not rendered["evidence_ok"]:
                    continue
                seen.add(bet["event_id"])
                out.append({
                    "strategy": sid,
                    "headline": rendered["headline"],
                    "body": rendered["body"],
                    "event_start_utc": event["scheduled_start_utc"],
                    "odds": bet.get("odds"),
                    "source_links": rendered["source_links"],
                    "paper_only": True,
                })
                if len(out) >= 4:
                    return out
    return out


# Leagues the CI full-season verification pass covers (OpenLigaDB only -
# the only source whose license permits automated API collection).
# One request per league-season returns the complete season.
# Shortcuts verified against the live openligadb.de index (2026-09-19):
# bl1, bl2, del are lowercase; DEL2, CHL, PDC* are uppercase.
FULLSEASON_LEAGUES = [
    ("bl1", 2024, "football"),         # Bundesliga 1 2024/25
    ("bl2", 2024, "football"),         # Bundesliga 2 2024/25
    ("del", 2024, "ice_hockey"),       # DEL (German top hockey) 2024/25
    ("DEL2", 2024, "ice_hockey"),      # DEL2 2024/25
    ("CHL", 2024, "ice_hockey"),       # Champions Hockey League 2024/25
    ("PDCWSDF", 2024, "darts"),        # PDC World Series of Darts Finals
]


def ingest_fullseason(out_path: str, league_filter: str = None) -> int:
    """CI-only: verify the OpenLigaDB result paths at full-season scale.

    Fetches one request per league-season (60 req/min limit respected),
    ingests into a TEMPORARY store (nothing is written into the repo),
    and emits a verification report. No football-data CSVs are downloaded
    here (their policy forbids automated retrieval) - so events stay at
    'probable' identity and any backtest PnL from this pass is review-state
    only. The report proves the result paths work at scale.
    """
    import json as _json
    from .adapters import openligadb
    import time as _time

    s = Store(":memory:")  # temporary in-memory store; nothing written to repo
    report = {"generated_utc": models.fmt_utc(models.utcnow()),
              "leagues": [], "errors": []}
    for i, (shortcut, season, sport) in enumerate(FULLSEASON_LEAGUES):
        if league_filter and shortcut != league_filter:
            continue
        if i:
            _time.sleep(1.1)  # stay far below 60 req/min
        entry = {"league": shortcut, "season": season, "sport": sport}
        try:
            text = openligadb.fetch_matchdata(shortcut, season)
            matches = openligadb.parse_matchdata(text, sport=sport)
            finished = sum(1 for m in matches if m["finished"])
            entry.update({
                "matches": len(matches),
                "finished": finished,
                "postponed_or_unfinished": len(matches) - finished,
            })
            stats = openligadb.ingest_matchday(s, text, sport=sport)
            entry["events_ingested"] = stats["events"]
            entry["results_ingested"] = stats["results"]
        except Exception as exc:  # noqa: BLE001 - report, don't crash
            entry["error"] = f"{type(exc).__name__}: {exc}"
            report["errors"].append(entry)
        report["leagues"].append(entry)
    events = s.events()
    report["total_events"] = len(events)
    report["by_sport"] = {}
    for e in events:
        report["by_sport"][e["sport"]] = report["by_sport"].get(e["sport"], 0) + 1
    report["note"] = ("CI verification pass. No football-data CSVs fetched "
                      "(policy: no automated retrieval); identities are "
                      "'probable' here and PnL from this pass is review-state "
                      "only. Pilot PnL on the site uses the committed, "
                      "dual-source-verified fixtures.")
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        _json.dump(report, fh, indent=2)
    s.close()
    print(f"fullseason report -> {out_path}")
    print(_json.dumps(report, indent=2))
    return 0


def verify(store: Store) -> int:
    """Re-verify fixture integrity + dual-source agreement. Exit code 0/1."""
    ok = True
    events = store.events()
    print(f"events in store: {len(events)}")
    agree = store.kv_get("pilot_dual_source_agreement") or "n/a"
    print(f"dual-source FT agreement recorded: {agree}")
    for c in store.captures():
        path = os.path.join(ROOT, c["path"])
        if not os.path.exists(path):
            print(f"MISSING capture {c['path']}")
            ok = False
            continue
        actual = _sha256_file(path)
        status = "OK " if actual == c["sha256"] else "MISMATCH"
        if actual != c["sha256"]:
            ok = False
        print(f"[{status}] {c['path']} sha256={actual[:16]}...")
    open_anoms = [a for a in store.anomalies() if a["status"] == "open"]
    print(f"open anomalies: {len(open_anoms)}")
    for a in open_anoms:
        print(f"  - {a['kind']} on {a['entity_id']}: {a['detail'][:100]}")
    return 0 if ok else 1


def main(argv: List[str] = None) -> int:
    parser = argparse.ArgumentParser(prog="northstar")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_run = sub.add_parser("run-pipeline", help="offline pilot pipeline")
    p_run.add_argument("--fresh", action="store_true",
                       help="rebuild the store from scratch")
    sub.add_parser("verify", help="re-verify fixtures + agreements")
    p_ing = sub.add_parser(
        "ingest-fullseason",
        help="CI: verify OpenLigaDB result paths at full-season scale "
             "(network; temporary store only)")
    p_ing.add_argument("--out", default="data/fullseason-report.json")
    p_ing.add_argument("--league", default=None,
                       help="only one league shortcut, e.g. bl1")
    args = parser.parse_args(argv)

    if args.cmd == "ingest-fullseason":
        return ingest_fullseason(args.out, args.league)

    if os.path.exists(DB_PATH) and getattr(args, "fresh", False):
        os.remove(DB_PATH)
    store = Store(DB_PATH)

    if args.cmd == "verify":
        return verify(store)

    stats = ingest_pilot(store)
    store.kv_set("pilot_events", str(stats["events"]))
    store.kv_set("pilot_dual_source_agreement",
                 f"{stats['cross_checked_agree']}/"
                 f"{stats['cross_checked']}")
    hockey_stats = ingest_hockey_pilot(store)
    store.kv_set("hockey_pilot_events", str(hockey_stats["events"]))
    store.kv_set("hockey_pilot_source_anomalies",
                 str(hockey_stats["anomalies"]))
    olbg_stats = ingest_olbg(store)
    reports = run_backtests(store)
    predictions = _pick_predictions(store, reports)
    backtest_meta = {}
    from .backtest import bootstrap_ci
    from .leaderboard import entrant_metrics
    for sid, rep in reports.items():
        entries = [b for b in rep["bets"]]
        settled = [b for b in entries if b["outcome_action"] in
                   ("settled", "already_settled", "review")]
        m = entrant_metrics(store, sid)
        if sid in PREDICTION_ONLY_STRATEGIES:
            evaln = rep.get("evaluation")
            backtest_meta[sid] = {
                "label": rep["label"],
                "sport": "ice_hockey",
                "pnl_available": False,
                "bets": len(entries),
                "settled": len(settled),
                "predictions": len([
                    b for b in entries
                    if b["outcome_action"] == "prediction_only"]),
                "skipped": len(rep["skipped"]),
                "leak_violations": rep["leak_violations"],
                "profit_units": None,
                "turnover_units": None,
                "roi": None,
                "strike_rate": None,
                "max_drawdown_units": None,
                "verification_state": "review",
                "profit_ci95": None,
                "accuracy": evaln,
                "sample_warning": (
                    "Prediction-only pilot: DEL has no permissioned odds "
                    "path, so profit is unavailable (never shown as zero). "
                    f"{evaln['n_graded'] if evaln else 0} graded predictions "
                    "is far too few to claim skill."),
            }
            continue
        ci = bootstrap_ci(m["pnl_sequence"]) if m["pnl_sequence"] else None
        backtest_meta[sid] = {
            "label": rep["label"],
            "sport": "football",
            "pnl_available": True,
            "bets": len(entries),
            "settled": len(settled),
            "skipped": len(rep["skipped"]),
            "leak_violations": rep["leak_violations"],
            "profit_units": m["profit_units"],
            "turnover_units": m["turnover_units"],
            "roi": m["roi"],
            "strike_rate": m["strike_rate"],
            "max_drawdown_units": m["max_drawdown_units"],
            "verification_state": m["verification_state"],
            "profit_ci95": ({"lo": ci["lo"], "hi": ci["hi"]} if ci else None),
            "sample_warning": (
                f"Only {m['settled_bets']} settled bets - far too few to "
                f"distinguish skill from luck; see docs/STATUS.md"
                if m["settled_bets"] and m["settled_bets"] < 50
                else None),
        }
    build_site_data(store, RAW, predictions=predictions,
                    backtest_meta=backtest_meta, out_path=SITE_OUT)
    store.commit()

    print("pipeline complete")
    print(f"  events={stats['events']} results={stats['results']} "
          f"odds_snapshots={stats['odds_snapshots']}")
    print(f"  dual-source agreement="
          f"{stats['cross_checked_agree']}/{stats['cross_checked']}")
    print(f"  hockey events={hockey_stats['events']} "
          f"results={hockey_stats['results']} "
          f"source anomalies={hockey_stats['anomalies']} (single-source, "
          f"identity probable)")
    hockey_acc = backtest_meta.get("hockey-elo-v1", {}).get("accuracy") or {}
    print(f"  hockey predictions: graded={hockey_acc.get('n_graded')} "
          f"accuracy={hockey_acc.get('accuracy')} "
          f"mean_brier={hockey_acc.get('mean_brier')} (no PnL: no "
          f"permissioned odds path)")
    print(f"  olbg snapshots: cards={olbg_stats['index_cards']} "
          f"event_tips={olbg_stats['event_tips']} "
          f"tipsters={olbg_stats['tipsters']}")
    lb = build_leaderboard(store)
    print("  leaderboard:")
    for row in lb:
        print(f"    #{row['rank']} {row['name']}: "
              f"profit={row['profit_units']} units "
              f"roi={row['roi']} state={row['verification_state']}")
    print(f"  site data -> {os.path.relpath(SITE_OUT, ROOT)}")
    return verify(store)


if __name__ == "__main__":
    sys.exit(main())
