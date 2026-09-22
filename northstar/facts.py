"""Generated fact sheet - the anti-hallucination surface for prose.

Every headline number that appears in README.md, docs/STATUS.md or on the
site is produced by the pipeline.  This module turns the generated
``site-data/site.json`` (which is itself built from hash-verified fixtures)
into ``docs/FACTS.md``: a single, regenerated, machine-checked list of the
numbers this repository is allowed to quote.

Rules enforced here:

* every number in the fact sheet is read from ``site.json`` - nothing is
  typed by hand;
* test counts are *counted from the test sources*, not remembered;
* ``tests/test_facts.py`` fails when ``docs/FACTS.md`` is stale, so prose
  cannot drift away from the data;
* numbers that cannot be computed are printed as "unavailable" with the
  reason, never as zero.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from typing import Any, Dict, List, Optional

from . import models
from .sources import sport_source_payload

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
README_PATH = os.path.join(ROOT, "README.md")
FIXTURES_DIR = os.path.join(ROOT, "data", "fixtures")
FACTS_PATH = os.path.join(ROOT, "docs", "FACTS.md")
SITE_PATH = os.path.join(ROOT, "site-data", "site.json")
TESTS_DIR = os.path.join(ROOT, "tests")
MODULES = ("northstar", "tests", "scripts")

FACTS_VERSION = "nr-facts-2026-09-22.1"


def count_tests(tests_dir: str = TESTS_DIR) -> int:
    """Count pytest test functions from the sources (deterministic)."""
    total = 0
    for name in sorted(os.listdir(tests_dir)):
        if not (name.startswith("test_") and name.endswith(".py")):
            continue
        with open(os.path.join(tests_dir, name), "r", encoding="utf-8") as fh:
            total += len(re.findall(r"^\s*def test_", fh.read(), re.M))
    return total


def count_source_lines(root: str = ROOT) -> Dict[str, int]:
    """Total Python lines in the package + tests (line-by-line surface)."""
    out: Dict[str, int] = {}
    for module in MODULES:
        path = os.path.join(root, module)
        if not os.path.isdir(path):
            continue
        lines = 0
        for dirpath, _dirnames, filenames in os.walk(path):
            for name in filenames:
                if name.endswith(".py"):
                    with open(os.path.join(dirpath, name), "r",
                              encoding="utf-8") as fh:
                        lines += sum(1 for _ in fh)
        out[module] = lines
    return out


def fixtures_digest(fixtures_dir: str = FIXTURES_DIR) -> Dict[str, Any]:
    """Aggregate digest of the committed fixture sidecars.

    The sheet must be reproducible: a wall-clock timestamp or the payload's
    own build time would make every regeneration look like drift.  What
    actually identifies the evidence base is the set of hash-verified
    fixture payloads, so that is what gets printed - it changes exactly when
    the captured data changes, which is exactly when the sheet must be
    regenerated (the capture workflow does so and commits it).
    """
    rows = []
    for dirpath, _dirs, files in os.walk(fixtures_dir):
        for name in sorted(files):
            if not name.endswith(".meta.json"):
                continue
            with open(os.path.join(dirpath, name), "r",
                      encoding="utf-8") as fh:
                meta = json.load(fh)
            fixture = meta.get("fixture", name[:-len(".meta.json")])
            rows.append([os.path.relpath(os.path.join(dirpath, fixture),
                                         ROOT),
                         meta.get("sha256")])
    rows.sort()
    digest = hashlib.sha256(
        json.dumps(rows, separators=(",", ":")).encode("utf-8")).hexdigest()
    return {"count": len(rows), "sha256": digest}


def site_json_sha256(path: str = SITE_PATH) -> Optional[str]:
    """sha256 of the *canonical* JSON (sorted keys, no whitespace), so the
    hash is stable across formatting-only rewrites of the payload."""
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as fh:
        payload = json.load(fh)
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _fmt(value: Any) -> str:
    if value is None:
        return "unavailable"
    if isinstance(value, float):
        return f"{value:.4f}"
    return str(value)


def build_facts(site: Dict[str, Any],
                tests_dir: str = TESTS_DIR) -> Dict[str, Any]:
    """Assemble the fact sheet from the generated site payload."""
    meta = site.get("meta", {})
    anomalies = site.get("anomalies", {})
    queue = anomalies.get("queue", [])
    by_kind: Dict[str, int] = {}
    for row in queue:
        if row.get("status") == "open":
            by_kind[row["kind"]] = by_kind.get(row["kind"], 0) + 1

    backtest = site.get("backtest", {})
    desks: List[Dict[str, Any]] = []
    for sid in sorted(backtest):
        card = backtest[sid]
        acc = card.get("accuracy") or {}
        baseline = card.get("naive_baseline") or {}
        desks.append({
            "strategy_id": sid,
            "label": card.get("label"),
            "sport": card.get("sport"),
            "market": card.get("market"),
            "bets": card.get("bets"),
            "settled": card.get("settled"),
            "pnl_available": card.get("pnl_available"),
            "profit_units": card.get("profit_units"),
            "roi": card.get("roi"),
            "p_value_raw": card.get("p_value_raw"),
            "p_value_holm": card.get("p_value_holm"),
            "significant_after_correction":
                card.get("significant_after_correction"),
            "accuracy": acc.get("accuracy"),
            "mean_brier": acc.get("mean_brier"),
            "n_graded": acc.get("n_graded"),
            "baseline_id": baseline.get("strategy_id"),
            "baseline_accuracy": baseline.get("accuracy"),
            "beats_baseline": baseline.get("beats_baseline"),
            "leak_violations": len(card.get("leak_violations") or []),
        })

    forward = site.get("forward", {})
    coverage = site.get("coverage", [])
    sources = site.get("sport_sources", {})
    return {
        "version": FACTS_VERSION,
        "built_utc": meta.get("built_utc"),
        "site_json_sha256": site_json_sha256(),
        "fixtures": fixtures_digest(),
        "meta": meta,
        "anomalies": {"open": len([r for r in queue
                                   if r.get("status") == "open"]),
                      "by_kind": dict(sorted(by_kind.items()))},
        "desks": desks,
        "forward": {
            "issued": forward.get("n_issued", forward.get("issued")),
            "graded": forward.get("n_graded", forward.get("graded")),
            "overdue": forward.get("n_overdue", forward.get("overdue")),
            "awaiting": forward.get("n_awaiting"),
            "leak_violations": len(forward.get("leak_violations") or []),
            "desks": forward.get("desks") or {},
            "state": forward.get("state"),
            "next_event_utc": next((r.get("start_utc")
                                    for r in (forward.get("awaiting") or [])
                                    if r.get("start_utc")), None),
        },
        "coverage": coverage,
        "sport_sources": {
            "version": sources.get("version"),
            "verified_at": sources.get("verified_at"),
            "counts": sources.get("counts", {}),
            "sports_with_verified_results_path": len([
                s for s in sources.get("sports", [])
                if s.get("automation_gate") == "permitted_open_licence"]),
        },
        "tests": {"count": count_tests(tests_dir)},
        "source_lines": count_source_lines(),
        "verify_checks": [
            "fixture sha256 + dual-source agreement: "
            "`python -m northstar.cli verify`",
            "leak audit (no read after a decision cutoff): walk-forward "
            "leak_violations per desk, `python -m northstar.cli run-pipeline`",
            "forward ledger append-only + pre-kickoff issuance: "
            "tests/test_forward.py",
            "sport-source evidence gates: tests/test_sources.py",
            "documentation links resolve: tests/test_docs_links.py",
        ],
    }


# ---------------------------------------------------------------------------
# README number sync
#
# README.md is prose, but a handful of its numbers are *counts* that move
# whenever the pipeline does (test functions, open anomalies, issued forward
# calls, graded desks).  Typing them by hand is how documentation drifts, so
# the same generated fact sheet that backs docs/FACTS.md also rewrites those
# quotes in place.  `facts --check` (CI) fails when a quote is stale, so a
# hand-edit can never survive.
# ---------------------------------------------------------------------------

def _readme_rules(facts: Dict[str, Any]):
    """(pattern, replacement) pairs - every number comes from the payload."""
    issued = facts["forward"]["issued"]
    return [
        (re.compile(r"\b\d+ test functions\b"),
         f"{facts['tests']['count']} test functions"),
        # Deliberately narrow: only the repo-wide claim is a generated
        # number.  Sentences about a *specific* pilot's anomaly count stay
        # as written - a broad regex would rewrite history (learned the
        # hard way: "0 open anomalies on the pilot itself" must not become
        # the repo-wide total).
        (re.compile(r"\*\*\d+ open anomalies\*\*"),
         f"**{facts['anomalies']['open']} open anomalies**"),
        (re.compile(r"\b\d+ open anomalies repo-wide\b"),
         f"{facts['anomalies']['open']} open anomalies repo-wide"),
        (re.compile(r"\b\d+ graded desks\b"),
         f"{len(facts['desks'])} graded desks"),
        (re.compile(r"\b\d+ (frozen|live) calls\b"),
         lambda m: f"{issued} {m.group(1)} calls"),
    ]


def sync_readme_numbers(facts: Dict[str, Any],
                        path: str = README_PATH) -> List[str]:
    """Rewrite the counted quotes in README.md; return what changed."""
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8", newline="") as fh:
        text = fh.read()
    updated = text
    for pattern, replacement in _readme_rules(facts):
        updated = pattern.sub(replacement, updated)
    if updated == text:
        return []
    changes = []
    for old, new in zip(text.splitlines(), updated.splitlines()):
        if old != new:
            changes.append(f"{old.strip()!r} -> {new.strip()!r}")
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(updated)
    return changes


def readme_drift(facts: Dict[str, Any],
                 path: str = README_PATH) -> Optional[str]:
    """Return None when README quotes the payload's numbers, else a note."""
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8", newline="") as fh:
        text = fh.read()
    updated = text
    for pattern, replacement in _readme_rules(facts):
        updated = pattern.sub(replacement, updated)
    if updated == text:
        return None
    for old, new in zip(text.splitlines(), updated.splitlines()):
        if old != new:
            return (f"README.md quotes a stale number:\n"
                    f"  file:     {old.strip()}\n  expected: {new.strip()}")
    return ("README.md quotes stale counted numbers - run "
            "`python -m northstar.cli facts`")


def render_facts_md(facts: Dict[str, Any]) -> str:
    """Deterministic markdown rendering (byte-comparable)."""
    lines: List[str] = []
    add = lines.append
    add("# Generated fact sheet (do not edit by hand)")
    add("")
    add(f"Written by `python -m northstar.cli run-pipeline` / `facts` "
        f"({facts['version']}) from the pipeline payload. "
        "`tests/test_facts.py` fails when this file is stale, which is what "
        "stops prose numbers from drifting away from the data.")
    add("")
    fx = facts["fixtures"]
    add(f"- **Fixtures:** {fx['count']} hash-verified payloads, aggregate "
        f"sha256 `{fx['sha256']}` (computed from the committed sidecars; "
        "reproducible, so a diff here always means the evidence changed)")
    add("")
    add("Nothing above is a clock reading: the sheet is a pure function of "
        "the committed fixture hashes and the payload built from them, so a "
        "diff always means the evidence changed (never that time passed).")
    add(f"- **{facts['tests']['count']}** test functions are counted from "
        "the test sources (never remembered); pytest additionally expands "
        "parametrised cases.")
    add("- **Python lines:** " + ", ".join(
        f"{k} {v}" for k, v in facts["source_lines"].items()))
    add("")
    add("## Evidence base (what the numbers below are computed from)")
    add("")
    add("| sport | status | results path | odds path |")
    add("|---|---|---|---|")
    for row in facts["coverage"]:
        add(f"| {row.get('sport')} | `{row.get('status')}` | "
            f"{row.get('results_path')} | {row.get('odds_path')} |")
    add("")
    add("## Anomalies (flagged, never smoothed)")
    add("")
    add(f"**{facts['anomalies']['open']} open anomalies** in the review "
        "queue:")
    add("")
    for kind, n in facts["anomalies"]["by_kind"].items():
        add(f"- `{kind}`: {n}")
    add("")
    add("## Desks (all backtests in the payload)")
    add("")
    add("| desk | sport | market | bets | settled | PnL | ROI | "
        "accuracy | n | Brier | vs naive baseline | p (Holm) |")
    add("|---|---|---|---|---|---|---|---|---|---|---|---|")
    for d in facts["desks"]:
        pnl = (_fmt(round(d["profit_units"], 4))
               if d["pnl_available"] else "unavailable (no odds path)")
        roi = (_fmt(round(d["roi"], 4)) if d["roi"] is not None else "-")
        acc = (_fmt(round(d["accuracy"], 4))
               if d["accuracy"] is not None else "-")
        brier = (_fmt(round(d["mean_brier"], 4))
                 if d["mean_brier"] is not None else "-")
        if d["baseline_id"]:
            beats = ("YES" if d["beats_baseline"] else "NO")
            vs = (f"{d['baseline_id']} ({_fmt(d['baseline_accuracy'])}): "
                  f"{beats}")
        else:
            vs = "-"
        holm = (_fmt(round(d["p_value_holm"], 4))
                if d["p_value_holm"] is not None else "-")
        graded = d["n_graded"] if d["accuracy"] is not None else "-"
        add(f"| `{d['strategy_id']}` | {d['sport']} | {d['market']} | "
            f"{d['bets']} | {d['settled']} | {pnl} | {roi} | {acc} | "
            f"{graded} | {brier} | {vs} | {holm} |")
    add("")
    fwd = facts["forward"]
    add("## Forward test (append-only ledger, state: "
        f"{_fmt(fwd.get('state'))})")
    add("")
    add(f"- issued {_fmt(fwd['issued'])} frozen pre-kickoff calls "
        f"({_fmt(fwd['awaiting'])} awaiting a result)")
    add(f"- graded {_fmt(fwd['graded'])}; overdue (started, ungraded) "
        f"{_fmt(fwd['overdue'])}")
    add(f"- leak violations: {fwd['leak_violations']}")
    add(f"- next kick-off: {_fmt(fwd['next_event_utc'])}")
    add("")
    if fwd["desks"]:
        add("| forward desk | issued |")
        add("|---|---|")
        for sid, n in sorted(fwd["desks"].items()):
            if isinstance(n, dict):
                n = n.get("issued", n.get("predictions", n.get("n_issued")))
            add(f"| `{sid}` | {_fmt(n)} |")
        add("")
    add("## Sport source registry (all 21 OLBG families)")
    add("")
    src = facts["sport_sources"]
    counts = src["counts"]
    add(f"- **Version:** `{_fmt(src['version'])}` (evidence fetched "
        f"{_fmt(src['verified_at'])})")
    add(f"- **Gates:** {counts.get('permitted_open_licence', '?')} permitted "
        f"under an open licence, "
        f"{counts.get('blocked_pending_licence_review', '?')} awaiting a "
        f"licence review, {counts.get('blocked_by_robots', '?')} blocked by "
        "the source's own robots.txt.")
    add(f"- **Designs:** {counts.get('designs', '?')} registered "
        f"({counts.get('graded_designs', '?')} graded). Full detail in "
        "`docs/SOURCE-REGISTRY.md` (generated from "
        "`data/sources/olbg_sports.json`).")
    add("")
    add("## Automated checks behind these numbers")
    add("")
    for check in facts["verify_checks"]:
        add(f"- {check}")
    add("")
    return "\n".join(lines)


def write_facts(path: str = FACTS_PATH,
                site_path: str = SITE_PATH,
                sync_readme: bool = False) -> Dict[str, Any]:
    """Regenerate docs/FACTS.md.

    ``sync_readme`` is deliberately opt-in: a plain pipeline run must leave
    README.md untouched so CI can prove (with a git diff) that the committed
    prose already quotes the generated numbers.  The capture workflow, which
    commits its own refresh, passes ``sync_readme=True``.
    """
    with open(site_path, "r", encoding="utf-8") as fh:
        site = json.load(fh)
    facts = build_facts(site)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(render_facts_md(facts))
    facts["readme_synced"] = (sync_readme_numbers(facts)
                              if sync_readme else [])
    return facts


def facts_are_current(path: str = FACTS_PATH,
                      site_path: str = SITE_PATH) -> Optional[str]:
    """Return None when current, else a one-line description of the drift."""
    with open(site_path, "r", encoding="utf-8") as fh:
        site = json.load(fh)
    facts = build_facts(site)
    drift = readme_drift(facts)
    if drift:
        return drift
    expected = render_facts_md(facts)
    if not os.path.exists(path):
        return (f"{os.path.relpath(path, ROOT)} is missing - run "
                f"`python -m northstar.cli facts`")
    with open(path, "r", encoding="utf-8", newline="") as fh:
        actual = fh.read()
    if actual != expected:
        a_lines, e_lines = actual.splitlines(), expected.splitlines()
        for i, (a, b) in enumerate(zip(a_lines, e_lines)):
            if a != b:
                return (f"{os.path.relpath(path, ROOT)} line {i + 1} is "
                        f"stale:\n  file:     {a}\n  expected: {b}")
        return (f"{os.path.relpath(path, ROOT)} differs in length - "
                f"regenerate with `python -m northstar.cli facts`")
    return None
