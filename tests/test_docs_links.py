"""Documentation integrity: every local link resolves, no number drifts.

The repository's promise is that a reader can follow any claim to its
evidence.  Two mechanical checks keep that honest:

1. **Link check** - every relative link in README.md, docs/*.md and the
   site's HTML resolves to a file that exists in the repository.  A "source
   for manual review" is never a dead link.
2. **Number check** - headline counts quoted in README.md (test functions,
   open anomalies, live forward calls) must equal the values in the
   generated fact sheet / site payload.  Adding a desk, a fixture or a test
   without updating the prose fails here.

External (http/https) links are not fetched by the test suite: they are
checked by hand and recorded with fetch dates in
`data/sources/olbg_sports.json` / `docs/LICENSING.md`.
"""
import json
import os
import re

import pytest

from northstar import facts as facts_mod

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCS = [os.path.join(ROOT, "README.md")] + [
    os.path.join(ROOT, "docs", name)
    for name in sorted(os.listdir(os.path.join(ROOT, "docs")))
    if name.endswith(".md")
]
LINK_RE = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")
HTML_ATTR_RE = re.compile(r'(?:href|src)="([^"]+)"')


def _local_targets(path):
    with open(path, "r", encoding="utf-8") as fh:
        text = fh.read()
    base = os.path.dirname(path)
    for raw in LINK_RE.findall(text):
        target = raw.split("#")[0]
        if not target or target.startswith(("http://", "https://", "mailto:")):
            continue
        yield raw, target, os.path.normpath(os.path.join(base, target))


class TestLocalLinks:
    @pytest.mark.parametrize("path", DOCS,
                             ids=lambda p: os.path.relpath(p, ROOT))
    def test_markdown_links_resolve(self, path):
        missing = [raw for raw, _t, resolved in _local_targets(path)
                   if not os.path.exists(resolved)]
        assert not missing, f"{os.path.relpath(path, ROOT)}: {missing}"

    def test_site_links_resolve(self):
        missing = []
        for name in ("index.html", "app.js"):
            path = os.path.join(ROOT, name)
            with open(path, "r", encoding="utf-8") as fh:
                text = fh.read()
            for raw in HTML_ATTR_RE.findall(text):
                target = raw.split("#")[0].split("?")[0]
                if not target or target.startswith(
                        ("http://", "https://", "mailto:", "data:", "//")):
                    continue
                # app.js builds some source links from data; a template
                # expression is not a static path we can resolve here.
                if "${" in target:
                    continue
                if not os.path.exists(os.path.join(ROOT, target)):
                    missing.append(f"{name}: {raw}")
        assert not missing, missing

    def test_register_and_facts_are_linked_from_the_readme(self):
        readme = open(os.path.join(ROOT, "README.md"),
                      encoding="utf-8").read()
        assert "docs/FACTS.md" in readme
        assert "docs/SOURCE-REGISTRY.md" in readme


class TestQuotedNumbers:
    @staticmethod
    def _facts():
        with open(os.path.join(ROOT, "site-data", "site.json"),
                  encoding="utf-8") as fh:
            return facts_mod.build_facts(json.load(fh))

    @staticmethod
    def _readme():
        return open(os.path.join(ROOT, "README.md"), encoding="utf-8").read()

    def test_test_function_count_matches_the_fact_sheet(self):
        facts = self._facts()
        quoted = {int(n) for n in re.findall(r"(\d+) test functions",
                                             self._readme())}
        assert quoted, "README must quote the test-function count"
        assert quoted == {facts["tests"]["count"]}, (
            f"README quotes {sorted(quoted)}, generated fact sheet says "
            f"{facts['tests']['count']} - regenerate with "
            f"`python -m northstar.cli facts`")

    def test_open_anomaly_count_matches_the_payload(self):
        facts = self._facts()
        quoted = {int(n) for n in re.findall(r"\*\*(\d+) open anomalies\*\*",
                                             self._readme())}
        assert quoted, "README must quote the open-anomaly count"
        assert quoted == {facts["anomalies"]["open"]}, (
            f"README quotes {sorted(quoted)}, payload says "
            f"{facts['anomalies']['open']}")

    def test_forward_call_count_matches_the_payload(self):
        facts = self._facts()
        quoted = {int(n) for n in re.findall(
            r"(\d+)\s+(?:live|frozen)\s+calls", self._readme())}
        assert quoted, "README must quote the forward-call count"
        assert quoted == {facts["forward"]["issued"]}, (
            f"README quotes {sorted(quoted)}, ledger holds "
            f"{facts['forward']['issued']} issued calls")

    def test_desk_count_claims_match_the_payload(self):
        """Every desk catalogued on the site belongs to a covered sport, and
        the README quotes the same total it renders."""
        facts = self._facts()
        desks = {d["strategy_id"] for d in facts["desks"]}
        assert len(desks) == len(facts["desks"]), "duplicate desk ids"
        by_sport = {}
        for d in facts["desks"]:
            by_sport.setdefault(d["sport"], []).append(d["strategy_id"])
        covered = {"football", "ice_hockey", "darts"}
        assert set(by_sport) == covered, sorted(by_sport)
        quoted = {int(n) for n in re.findall(r"(\d+) graded desks",
                                             self._readme())}
        if quoted:
            assert quoted == {len(desks)}, (
                f"README quotes {sorted(quoted)} graded desks, payload has "
                f"{len(desks)}")
