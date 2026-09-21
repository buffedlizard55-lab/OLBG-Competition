"""Command-line pipeline.

    python -m northstar.cli run-pipeline [--fresh]
    python -m northstar.cli verify
    python -m northstar.cli capture-current [--out data/fixtures/current]

run-pipeline (fully offline - committed fixtures only):
  1. ingest OpenLigaDB pilot matchdays (results, ODbL)
  2. cross-check + import football-data pilot odds (manual import)
  3. ingest current-season captures (data/fixtures/current, CI-fetched)
  4. import manual OLBG snapshots (policy-gated, pending only)
  5. run the strategy family walk-forward (strict cutoffs) on the pilots,
     plus prediction-only walk-forward for darts on captured events
  6. issue/grade the forward-test ledger (append-only, pre-start cutoffs)
  7. render evidence-only predictions (settled pilot bets + forward calls)
  8. apply Holm-Bonferroni correction across the backtested family
  9. emit site-data/site.json for the GitHub Pages UI

capture-current (NETWORK; CI only): fetch whole current seasons from the
permitted OpenLigaDB automated API, validate strictly, write canonical
fixtures + sidecar metadata, discover darts leagues (no hardcoded darts
assumptions survive the 2026-09-20 empty-probe finding).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from typing import Any, Dict, List, Optional

from . import models
from .adapters import football_data, olbg, openligadb
from .backtest import run_walk_forward
from .db import Store
from .evaluation import prediction_accuracy
from .forward import grade_forward, issue_forward, load_ledger, save_ledger
from .leaderboard import build_leaderboard
from .predictor import render_forward_prediction, render_prediction
from .policy import MODE_AUTO_API
from .registry import registry_payload
from .report import build_site_data
from .stats import bootstrap_p_two_sided, holm_bonferroni
from .strategies import (
    DARTS_STRATEGIES, FOOTBALL_STRATEGIES, FORWARD_STRATEGIES,
    HOCKEY_STRATEGIES, PREDICTION_ONLY_STRATEGIES, build,
)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIXTURES = os.path.join(ROOT, "data", "fixtures")
CURRENT_FIXTURES = os.path.join(FIXTURES, "current")
RAW = os.path.join(ROOT, "data", "raw")
DB_PATH = os.path.join(ROOT, "data", "northstar.db")
SITE_OUT = os.path.join(ROOT, "site-data", "site.json")
LEDGER_PATH = os.path.join(ROOT, "data", "forward", "ledger.json")

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


def ingest_current(store: Store) -> Dict[str, Any]:
    """Ingest CI-captured current-season fixtures (offline replay).

    Every fixture must carry valid sidecar metadata (capture instant,
    sha256, sport); fixtures that fail validation are refused with an
    anomaly - never partially ingested.  Returns per-fixture groups so the
    forward engine can use each capture's own ``as_of``.
    """
    from . import capture
    groups: List[Dict[str, Any]] = []
    anomalies = 0
    for item in capture.load_current_fixtures(CURRENT_FIXTURES):
        rel = os.path.relpath(item["path"], ROOT)
        if item.get("error") or not item.get("meta") or not item.get("text"):
            aid = models.stable_id("an", models.ANOMALY_MISSING_METADATA, rel)
            if not store.anomaly_exists(aid):
                anomalies += 1
            store.add_anomaly(models.Anomaly(
                anomaly_id=aid,
                kind=models.ANOMALY_MISSING_METADATA,
                entity_type="capture", entity_id=rel,
                detected_at_utc=models.utcnow(),
                detail=(f"current-season fixture refused: "
                         f"{item.get('error')}"),
                source_urls=[(item.get("meta") or {}).get("url") or ""]))
            continue
        meta = item["meta"]
        captured_at = models.parse_utc(meta["captured_at_utc"])
        capture_id = "cap-" + os.path.basename(item["path"])
        store.register_capture(
            capture_id, "openligadb", rel,
            hashlib.sha256(item["text"].encode("utf-8")).hexdigest(),
            captured_at, meta.get("collection_mode", MODE_AUTO_API),
            f"{meta.get('league_name')} whole-season payload captured "
            f"{meta['captured_at_utc']} via permitted automated API "
            f"(ODbL-1.0); sha256 {meta['sha256'][:16]}...")
        out = openligadb.ingest_matchday(store, item["text"],
                                         verify_identity=True,
                                         sport=meta["sport"],
                                         as_of=captured_at)
        groups.append({
            "fixture": rel, "sport": meta["sport"],
            "shortcut": meta["league_shortcut"],
            "season": meta["league_season"],
            "league_name": meta.get("league_name"),
            "as_of": captured_at,
            "events": list(out.get("event_ids") or []),
            "n_events": out["events"], "n_results": out["results"],
            "anomalies": out["anomalies"],
        })
        anomalies += out["anomalies"]
    store.commit()
    return {"groups": groups, "anomalies": anomalies}


def _pilot_scope(events: List[Dict[str, Any]], sport: str,
                 url_part: str) -> List[Dict[str, Any]]:
    """Pilot backtests run ONLY on the frozen pilot fixtures.

    Current-season captures feed the forward desk and prediction-only
    walk-forwards, never the settled-PnL pilot tables (their events have
    no permissioned odds and only 'probable' identity).
    """
    return [e for e in events
            if e["sport"] == sport and url_part in (e.get("source_url") or "")]


def run_backtests(store: Store) -> Dict[str, Any]:
    finished = [e for e in store.events() if e["status"] == "finished"]
    football_events = _pilot_scope(finished, "football", "/bl1/2024/")
    hockey_events = _pilot_scope(finished, "ice_hockey", "/del/2024/")
    darts_events = [e for e in finished if e["sport"] == "darts"]
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
    for sid in DARTS_STRATEGIES:
        if not darts_events:
            continue  # no darts capture committed yet: desk stays closed
        strategy = build(sid)
        reports[sid] = run_walk_forward(store, darts_events, strategy, sid,
                                        label="darts-pilot",
                                        allow_no_odds=True)
        reports[sid]["evaluation"] = prediction_accuracy(
            store, reports[sid]["bets"], sport="darts")
    store.commit()
    return reports


def run_forward_desks(store: Store, current: Dict[str, Any],
                      ledger: Dict[str, Any]) -> Dict[str, Any]:
    """Issue (append-only) and grade forward-test predictions.

    One desk call per captured fixture group with that capture's own
    ``as_of`` - the desk can only see what the capture saw, when it saw it.
    """
    issue_stats: List[Dict[str, Any]] = []
    latest_as_of = None
    for group in current["groups"]:
        as_of = group["as_of"]
        if latest_as_of is None or as_of > latest_as_of:
            latest_as_of = as_of
        events = [store.get_event(eid) for eid in group["events"]]
        events = [e for e in events if e]
        sids = FORWARD_STRATEGIES.get(group["sport"], [])
        if not sids:
            continue
        stats = issue_forward(store, events, as_of, sids, ledger,
                              label=f"{group['shortcut']}-{group['season']}")
        issue_stats.append({"fixture": group["fixture"],
                            "sport": group["sport"], **stats})
    report = grade_forward(store, ledger, latest_as_of=latest_as_of)
    # Render tipster-style copy for the awaiting (upcoming) calls only -
    # graded ones already show their outcome; the renderer refuses any
    # entry whose model trail is incomplete.
    rendered = []
    for row in report["awaiting"]:
        out = render_forward_prediction(
            row, source_links=[u for u in (row.get("source_url"),
                                           "https://api.openligadb.de/",
                                           "https://openligadb.de/lizenz")
                               if u])
        rendered.append({"prediction_id": row["prediction_id"],
                         "event": row["event"],
                         "competition": row.get("competition"),
                         "start_utc": row["start_utc"],
                         "sport": row.get("sport"),
                         "strategy": row["strategy_id"],
                         "selection": row["selection"],
                         "cutoff_utc": row["cutoff_utc"],
                         "issued_at_utc": row["issued_at_utc"],
                         "headline": out["headline"],
                         "body": out["body"],
                         "evidence_ok": out["evidence_ok"],
                         "source_links": out["source_links"]})
    report["rendered"] = rendered
    report["issue_stats"] = issue_stats
    report["latest_capture_utc"] = (models.fmt_utc(latest_as_of)
                                    if latest_as_of else None)
    report["leak_violations"] = [v for s in issue_stats
                                 for v in s.get("leak_violations", [])]
    if current["groups"]:
        report["state"] = "live"
        report["cadence"] = ("CI capture workflow refreshes the permitted "
                             "OpenLigaDB current-season fixtures weekly "
                             "(Mondays 06:30 UTC) and on demand; every new "
                             "prediction is frozen in the append-only "
                             "ledger at capture time.")
    else:
        report["state"] = "awaiting_first_capture"
    return report


def _pick_predictions(store: Store,
                      reports: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Render evidence-only predictions for up to 4 settled backtest bets
    that carry a full model/fair/edge trail (any strategy in the family -
    the trail, not the strategy id, is the admission gate)."""
    out: List[Dict[str, Any]] = []
    seen = set()
    for sid, rep in reports.items():
        for bet in rep["bets"]:
            model = bet.get("model") or {}
            if model.get("model_prob") and model.get("fair_prob") and \
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
# ANOMALY (2026-09-20, development probe): the previously listed darts
# pair ("PDCWSDF", 2024) returns an EMPTY list from the live API, so the
# earlier "shortcut verified" claim for it is not reproducible; it was
# removed here and darts is now DISCOVERY-driven via
# `capture-current`/capture.discover_darts_seasons (findings are written to
# data/fixtures/current/capture-log.json, never assumed).  The remaining
# shortcuts are re-verified by every run of this pass: a dead shortcut
# shows up as matches: 0 in the report instead of failing silently.
FULLSEASON_LEAGUES = [
    ("bl1", 2024, "football"),         # Bundesliga 1 2024/25
    ("bl2", 2024, "football"),         # Bundesliga 2 2024/25
    ("del", 2024, "ice_hockey"),       # DEL (German top hockey) 2024/25
    ("DEL2", 2024, "ice_hockey"),      # DEL2 2024/25
    ("CHL", 2024, "ice_hockey"),       # Champions Hockey League 2024/25
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
    p_cap = sub.add_parser(
        "capture-current",
        help="CI: fetch current-season fixtures from the permitted "
             "OpenLigaDB automated API + discover darts leagues (network)")
    p_cap.add_argument("--out", default=os.path.join(
        "data", "fixtures", "current"))
    p_cap.add_argument("--season", type=int, default=2026)
    args = parser.parse_args(argv)

    if args.cmd == "ingest-fullseason":
        return ingest_fullseason(args.out, args.league)

    if args.cmd == "capture-current":
        from . import capture
        out_dir = args.out if os.path.isabs(args.out) \
            else os.path.join(ROOT, args.out)
        log = capture.capture_current(out_dir, season=args.season)
        print(json.dumps({k: v for k, v in log.items()
                          if k != "targets"}, indent=2))
        for row in log["targets"]:
            state = "WROTE" if row.get("written") else "REFUSED"
            print(f"  [{state}] {row.get('shortcut')}/{row.get('season')}: "
                  f"{row.get('matches', 0)} matches "
                  f"({row.get('error', '')})")
        return 1 if log["errors"] and not any(
            r.get("written") for r in log["targets"]) else 0

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
    current = ingest_current(store)
    olbg_stats = ingest_olbg(store)
    reports = run_backtests(store)

    # Forward test: issue new frozen predictions from the committed
    # current-season captures, then grade everything already ledgered.
    ledger = load_ledger(LEDGER_PATH)
    forward_report = run_forward_desks(store, current, ledger)
    ledger_changed = save_ledger(LEDGER_PATH, ledger)

    predictions = _pick_predictions(store, reports)
    backtest_meta = {}
    from .backtest import bootstrap_ci
    from .leaderboard import entrant_metrics
    sport_names = {"ice_hockey": "DEL", "darts": "PDC darts"}
    for sid, rep in reports.items():
        entries = [b for b in rep["bets"]]
        settled = [b for b in entries if b["outcome_action"] in
                   ("settled", "already_settled", "review")]
        m = entrant_metrics(store, sid)
        if sid in PREDICTION_ONLY_STRATEGIES:
            evaln = rep.get("evaluation")
            sport = getattr(build(sid), "sport", None) or "ice_hockey"
            backtest_meta[sid] = {
                "label": rep["label"],
                "sport": sport,
                "market": models.MARKET_MATCH_WINNER_2WAY,
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
                    f"Prediction-only pilot: {sport_names.get(sport, sport)} "
                    "has no permissioned odds path, so profit is unavailable "
                    f"(never shown as zero). "
                    f"{evaln['n_graded'] if evaln else 0} graded predictions "
                    "is far too few to claim skill."),
            }
            continue
        ci = bootstrap_ci(m["pnl_sequence"]) if m["pnl_sequence"] else None
        backtest_meta[sid] = {
            "label": rep["label"],
            "sport": "football",
            "market": (getattr(build(sid), "market", None)
                       or models.MARKET_MATCH_WINNER_3WAY),
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
            "p_value_raw": (bootstrap_p_two_sided(m["pnl_sequence"])
                            if m["pnl_sequence"] else None),
            "sample_warning": (
                f"Only {m['settled_bets']} settled bets - far too few to "
                f"distinguish skill from luck; see docs/STATUS.md"
                if m["settled_bets"] and m["settled_bets"] < 50
                else None),
        }
    # Multiple-comparisons correction across the tested PnL family (Holm
    # step-down). Prediction-only desks have no PnL hypothesis to test and
    # are excluded from the family (p stays None).
    corrections = holm_bonferroni({
        sid: meta.get("p_value_raw")
        for sid, meta in backtest_meta.items()
        if meta.get("pnl_available")})
    for sid, corr in corrections.items():
        backtest_meta[sid].update({
            "p_value_raw": corr["p_raw"],
            "p_value_holm": corr["p_adjusted"],
            "family_size": corr["family_size"],
            "significant_after_correction": corr["significant_05"],
        })

    build_site_data(store, RAW, predictions=predictions,
                    backtest_meta=backtest_meta, out_path=SITE_OUT,
                    forward_report=forward_report,
                    registry=registry_payload())
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
    print(f"  current-season fixtures: groups={len(current['groups'])} "
          f"anomalies={current['anomalies']}")
    for g in current["groups"]:
        print(f"    - {g['fixture']}: {g['league_name']} sport={g['sport']} "
              f"as_of={models.fmt_utc(g['as_of'])}")
    hockey_acc = backtest_meta.get("hockey-elo-v1", {}).get("accuracy") or {}
    print(f"  hockey predictions: graded={hockey_acc.get('n_graded')} "
          f"accuracy={hockey_acc.get('accuracy')} "
          f"mean_brier={hockey_acc.get('mean_brier')} (no PnL: no "
          f"permissioned odds path)")
    darts_meta = backtest_meta.get("darts-elo-v1") or {}
    if darts_meta:
        dacc = darts_meta.get("accuracy") or {}
        print(f"  darts predictions: graded={dacc.get('n_graded')} "
              f"accuracy={dacc.get('accuracy')} "
              f"mean_brier={dacc.get('mean_brier')} (no PnL: no "
              f"permissioned odds path)")
    print(f"  forward test: state={forward_report['state']} "
          f"issued={forward_report['n_issued']} "
          f"graded={forward_report['n_graded']} "
          f"awaiting={forward_report['n_awaiting']} "
          f"overdue={forward_report['n_overdue']} "
          f"leaks={len(forward_report['leak_violations'])} "
          f"ledger_changed={ledger_changed}")
    fam = {sid: (meta.get("p_value_raw"), meta.get("p_value_holm"))
           for sid, meta in backtest_meta.items()
           if meta.get("pnl_available")}
    if fam:
        print(f"  holm-bonferroni family (m={len(fam)}): " + ", ".join(
            f"{sid} p={p[0]}->adj={p[1]}" for sid, p in sorted(fam.items())))
        sig = [sid for sid, meta in backtest_meta.items()
               if meta.get("significant_after_correction")]
        print(f"  significant after correction: {sig or 'none'}")
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
