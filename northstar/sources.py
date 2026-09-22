"""OLBG sport-family source registry (evidence-gated, machine-checked).

Why this module exists: the project must be able to say, for **every**
sport family OLBG publishes (21 of them, catalogue manually reviewed
2026-09-20 in docs/OLBG-RESEARCH.md), exactly:

* which official / permissioned **results** source is the candidate,
* what its robots.txt and licence actually say (with the fetched evidence
  and the date it was fetched),
* whether automated collection is permitted, undecided or blocked, and
* which pre-registered strategy designs wait behind that gate.

Nothing here is a claim of coverage.  The registry is deliberately
conservative:

1. ``licence`` is ``open_licence_verified`` **only** when the licence is
   recorded in ``northstar.policy`` (the existing, tested licensing
   registry) - i.e. a source that is already legally cleared for the
   collection mode used.  Every other source is ``not_reviewed`` and its
   gate says so.
2. ``robots`` findings are stored with the exact fetched text and the
   fetch date; a missing robots.txt (e.g. an HTTP 404) is recorded as
   *no robots file served*, which is **not** permission.
3. ``automation_gate`` is computed from those two facts by
   :func:`gate_for` - never hand-written - so a source cannot be
   promoted to "permitted" by editing prose.
4. Strategy designs are ``design-stage`` unless they name a strategy id
   that actually exists in ``northstar.strategies.REGISTRY``; the test
   suite enforces that (``tests/test_sources.py``).

The JSON lives at ``data/sources/olbg_sports.json`` and is rendered on the
site's Sport-coverage view with every evidence link clickable for manual
review.
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

from . import policy
from .registry import HYPOTHESES

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REGISTRY_PATH = os.path.join(ROOT, "data", "sources", "olbg_sports.json")

REGISTRY_VERSION = "nr-sport-sources-2026-09-22.1"

# The 21 sport families listed on the public OLBG tips page (manual review
# 2026-09-20; docs/OLBG-RESEARCH.md).  The registry must cover exactly
# these - a test fails on a missing or extra sport.
OLBG_SPORTS: List[str] = [
    "Horse Racing", "Football", "Tennis", "Golf", "American Football",
    "Baseball", "Basketball", "Boxing", "Cricket", "Cycling", "Darts",
    "Gaelic Football", "Greyhounds", "Handball", "Hurling", "Ice Hockey",
    "Motor Racing", "Rugby Union", "Rugby League", "Snooker", "Volleyball",
]

# Gate vocabulary.  "permitted_open_licence" is the only state in which a
# collector may run without a further human decision.
GATE_PERMITTED = "permitted_open_licence"
GATE_LICENCE_REVIEW = "blocked_pending_licence_review"
GATE_ROBOTS_BLOCKED = "blocked_by_robots"
GATE_NO_SOURCE = "blocked_no_permissioned_source"
GATE_STATES = (GATE_PERMITTED, GATE_LICENCE_REVIEW, GATE_ROBOTS_BLOCKED,
               GATE_NO_SOURCE)


class SourceRegistryError(ValueError):
    """Raised when the registry file is structurally dishonest."""


def _permitted_source_ids() -> Dict[str, policy.SourcePolicy]:
    return {p.source_id: p for p in policy.all_policies()}


def gate_for(candidate: Dict[str, Any]) -> str:
    """Compute the automation gate from stored facts (never hand-written).

    - ``licence`` == ``open_licence_verified`` -> permitted (the licence is
      recorded in the tested policy registry);
    - ``robots_verdict`` == ``blocks_results`` -> blocked by robots;
    - a candidate with no licence review -> pending licence review;
    - no candidate at all -> no permissioned source.
    """
    if candidate.get("licence") == "open_licence_verified":
        return GATE_PERMITTED
    if candidate.get("robots_verdict") == "blocks_results":
        return GATE_ROBOTS_BLOCKED
    return GATE_LICENCE_REVIEW


def load_registry(path: Optional[str] = None) -> Dict[str, Any]:
    with open(path or REGISTRY_PATH, "r", encoding="utf-8") as fh:
        return json.load(fh)


def validate(registry: Dict[str, Any]) -> None:
    """Structural honesty checks (also asserted by tests/test_sources.py)."""
    sports = registry.get("sports")
    if not isinstance(sports, list):
        raise SourceRegistryError("registry.sports must be a list")
    names = [s.get("sport") for s in sports]
    if sorted(names) != sorted(OLBG_SPORTS):
        missing = sorted(set(OLBG_SPORTS) - set(names))
        extra = sorted(set(names) - set(OLBG_SPORTS))
        raise SourceRegistryError(
            f"registry must cover exactly the {len(OLBG_SPORTS)} OLBG sport "
            f"families (missing={missing}, extra={extra})")
    permitted = _permitted_source_ids()
    for sport in sports:
        for cand in sport.get("results_candidates", []):
            for key in ("name", "url", "robots_url", "robots_verdict",
                        "robots_checked_at", "robots_quote", "licence",
                        "licence_evidence_url"):
                if key not in cand:
                    raise SourceRegistryError(
                        f"{sport['sport']}/{cand.get('name')}: missing {key}")
            if cand["licence"] == "open_licence_verified":
                sid = cand.get("policy_source_id")
                if sid not in permitted:
                    raise SourceRegistryError(
                        f"{sport['sport']}: licence claimed open but "
                        f"policy_source_id {sid!r} is not in the policy "
                        f"registry")
                if not cand.get("licence_evidence_url"):
                    raise SourceRegistryError(
                        f"{sport['sport']}: open licence without evidence URL")
            if cand.get("link_verified") and not cand.get("link_checked_at"):
                raise SourceRegistryError(
                    f"{sport['sport']}/{cand['name']}: link marked verified "
                    f"without a checked_at date")
            if cand.get("robots_verdict") == "blocks_results" and \
                    not cand.get("robots_blocks"):
                raise SourceRegistryError(
                    f"{sport['sport']}/{cand['name']}: robots_verdict says "
                    f"blocks_results but no robots_blocks paths are listed")
            if cand.get("robots_verdict") not in (
                    "allows_results", "blocks_results", "no_robots_file",
                    "partial", "unknown"):
                raise SourceRegistryError(
                    f"{sport['sport']}/{cand['name']}: unknown robots_verdict "
                    f"{cand.get('robots_verdict')!r}")
        # The sport-level gate is the gate of the *primary* (first)
        # candidate.  That is only honest while the primary is the most
        # permissive candidate: if a later candidate were easier to use,
        # the sport would look more blocked than it is.
        cands = sport.get("results_candidates", [])
        if cands:
            order = [GATE_PERMITTED, GATE_LICENCE_REVIEW, GATE_ROBOTS_BLOCKED]
            primary_gate = gate_for(cands[0])
            best = min((gate_for(c) for c in cands), key=order.index)
            if order.index(primary_gate) > order.index(best):
                raise SourceRegistryError(
                    f"{sport['sport']}: the primary candidate is more "
                    f"restricted ({primary_gate}) than another candidate "
                    f"({best}) - list the most permissive source first")
        for design in sport.get("strategy_designs", []):
            if design.get("status") not in ("design-stage", "graded",
                                            "forward-live"):
                raise SourceRegistryError(
                    f"{sport['sport']}/{design.get('design_id')}: unknown "
                    f"status {design.get('status')!r}")
            if design.get("status") in ("graded", "forward-live") and \
                    not design.get("strategy_id"):
                raise SourceRegistryError(
                    f"{sport['sport']}/{design.get('design_id')}: a graded "
                    f"design must name the strategy id it ran as")
    # Every covered sport's graded designs must exist in the strategy
    # registry; the sport-source file may not invent results.
    from .strategies import REGISTRY as STRATEGY_REGISTRY
    from . import models
    sport_keys = {"Football": models.SPORT_FOOTBALL,
                  "Ice Hockey": models.SPORT_ICE_HOCKEY,
                  "Darts": models.SPORT_DARTS}
    for sport in sports:
        for design in sport.get("strategy_designs", []):
            sid = design.get("strategy_id")
            if not sid:
                continue
            if sid not in STRATEGY_REGISTRY:
                raise SourceRegistryError(
                    f"{sport['sport']}: strategy id {sid!r} is not in the "
                    f"strategy registry")
            expected_sport = sport_keys.get(sport["sport"])
            if expected_sport is not None:
                # Market strategies declare ``sport = None`` (the run sets
                # it); only a *declared* mismatch is an error.
                inst = STRATEGY_REGISTRY[sid]()
                if inst.sport is not None and inst.sport != expected_sport:
                    raise SourceRegistryError(
                        f"{sport['sport']}: strategy {sid} belongs to "
                        f"{inst.sport}, not {expected_sport}")


def sport_source_payload(path: Optional[str] = None) -> Dict[str, Any]:
    """Validated registry + computed gates for the site payload."""
    registry = load_registry(path)
    validate(registry)
    sports: List[Dict[str, Any]] = []
    for sport in registry["sports"]:
        # Normalise fetched line endings to LF for display and for the
        # generated register (the CR characters are the source's own line
        # endings, not content: the quoted text is otherwise verbatim).
        candidates = [{
            **cand,
            "robots_quote": (cand.get("robots_quote") or "")
            .replace("\r\n", "\n").replace("\r", "\n"),
        } for cand in sport.get("results_candidates", [])]
        primary = candidates[0] if candidates else None
        gate = gate_for(primary) if primary else GATE_NO_SOURCE
        graded = [d for d in sport.get("strategy_designs", [])
                  if d.get("status") in ("graded", "forward-live")]
        sports.append({
            **sport,
            "results_candidates": candidates,
            "automation_gate": gate,
            "graded_design_count": len(graded),
            "design_count": len(sport.get("strategy_designs", [])),
            "evidence_links": sorted({
                cand["url"] for cand in candidates if cand.get("url")
            } | {cand.get("robots_url") for cand in candidates
                 if cand.get("robots_url")} | {
                d_ref for d in sport.get("strategy_designs", [])
                for d_ref in d.get("refs", [])}),
        })
    return {
        "version": registry.get("version", REGISTRY_VERSION),
        "verified_at": registry.get("verified_at"),
        "note": registry.get("note"),
        "method": registry.get("method"),
        "sports": sports,
        "counts": {
            "sports": len(sports),
            "permitted_open_licence": len(
                [s for s in sports
                 if s["automation_gate"] == GATE_PERMITTED]),
            "blocked_pending_licence_review": len(
                [s for s in sports
                 if s["automation_gate"] == GATE_LICENCE_REVIEW]),
            "blocked_by_robots": len(
                [s for s in sports
                 if s["automation_gate"] == GATE_ROBOTS_BLOCKED]),
            "designs": sum(s["design_count"] for s in sports),
            "graded_designs": sum(s["graded_design_count"] for s in sports),
        },
    }


def registry_hypothesis_ids() -> List[str]:
    """Strategy ids named by sport-source designs (for cross-checks)."""
    registry = load_registry()
    out: List[str] = []
    for sport in registry["sports"]:
        for design in sport.get("strategy_designs", []):
            if design.get("strategy_id"):
                out.append(design["strategy_id"])
    return out


def registry_covers_hypotheses() -> List[str]:
    """Graded hypothesis ids in northstar.registry missing from this file."""
    named = set(registry_hypothesis_ids())
    return sorted({h["tested"] for h in HYPOTHESES
                   if h.get("tested") and h["tested"] not in named})


REGISTER_PATH = os.path.join(ROOT, "docs", "SOURCE-REGISTRY.md")


def render_register_md(payload: Optional[Dict[str, Any]] = None) -> str:
    """Human-readable OLBG source register (generated, never hand-typed).

    Rendered from the same validated payload the site shows, so the doc
    cannot disagree with the data. Every URL is clickable for manual review.
    """
    payload = payload or sport_source_payload()
    counts = payload["counts"]
    lines: List[str] = []
    add = lines.append
    add("# OLBG sport source register (generated)")
    add("")
    add(f"Version `{payload['version']}` · evidence fetched "
        f"{payload['verified_at']} · rendered from "
        "`data/sources/olbg_sports.json` by `python -m northstar.cli facts`. "
        "Do not edit by hand: `tests/test_sources.py` revalidates the file "
        "and this document is regenerated with it.")
    add("")
    add(f"**{counts['sports']} sport families · {counts['designs']} registered "
        f"strategy designs ({counts['graded_designs']} graded) · "
        f"{counts['permitted_open_licence']} permitted automatically, "
        f"{counts['blocked_pending_licence_review']} awaiting a licence "
        f"review, {counts['blocked_by_robots']} blocked by robots.txt.**")
    add("")
    add("Reading rules: a robots.txt verdict is the site's crawling policy, "
        "**not** a licence. `licence: not_reviewed` means no permission has "
        "been established, so no collection happens. The only sources with "
        "`permitted_open_licence` are those already recorded and tested in "
        "`northstar/policy.py`.")
    add("")
    for sport in payload["sports"]:
        add(f"## {sport['sport']}")
        add("")
        add(f"- **Coverage today:** {sport.get('coverage_today')}")
        add(f"- **Automation gate:** `{sport['automation_gate']}`")
        add(f"- **Registered designs:** {sport['design_count']} "
            f"({sport['graded_design_count']} graded)")
        add("")
        add("| candidate result source | link | robots.txt | licence |")
        add("|---|---|---|---|")
        for cand in sport.get("results_candidates", []):
            name = str(cand.get("name") or "").replace("|", "\\|")
            link = (f"[{name}]({cand['url']})" +
                    ("" if cand.get("link_verified")
                     else " *(deep link unverified)*"))
            robots = (f"[robots.txt]({cand['robots_url']}) · "
                      f"`{cand['robots_verdict']}` · fetched "
                      f"{cand['robots_checked_at']}")
            evidence = cand.get("licence_evidence_url")
            evidence_md = (f"[evidence]({evidence})" if evidence
                           else "*(none recorded)*")
            add(f"| {link} | {evidence_md} | "
                f"{robots} | `{cand['licence']}` |")
        add("")
        for cand in sport.get("results_candidates", []):
            quote = (cand.get("robots_quote") or "").replace("\r\n", "\n")
            if "\n" in quote:
                # Verbatim, multi-line: a fenced block, never a mangled span.
                add(f"- **{cand['name']}** robots.txt says (verbatim):")
                add("")
                add("  ```text")
                for line in quote.split("\n"):
                    add(f"  {line}")
                add("  ```")
            else:
                add(f"- **{cand['name']}** robots.txt says: `{quote}`")
        add("")
        if sport.get("strategy_designs"):
            add("Strategy designs (pre-registered, gate-checked):")
            add("")
            for design in sport["strategy_designs"]:
                tag = ("**graded** `" + str(design.get("strategy_id")) + "`"
                       if design.get("status") in ("graded", "forward-live")
                       else "design-stage")
                add(f"- {tag} — *{design['name']}*: {design['hypothesis']} "
                    f"Rule: {design['rule']} Gate: {design['gate']}")
                for ref in design.get("refs", []):
                    add(f"  - prior: {ref}")
            add("")
        add(f"**Next action:** {sport.get('next_action')}")
        add("")
    return "\n".join(lines)


def write_register(path: str = REGISTER_PATH) -> Dict[str, Any]:
    """Write docs/SOURCE-REGISTRY.md from the validated payload."""
    payload = sport_source_payload()
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(render_register_md(payload))
    return payload


def register_is_current(path: str = REGISTER_PATH) -> Optional[str]:
    """Return None when the committed register matches a fresh render."""
    expected = render_register_md(sport_source_payload())
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
