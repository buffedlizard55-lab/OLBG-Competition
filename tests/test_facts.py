"""Fact-sheet tests: prose numbers must be generated, and stay current.

`docs/FACTS.md` is produced by `python -m northstar.cli facts` from the
same payload the site renders.  If the repository's data changes without
regenerating the sheet, these tests fail - which is the point: no number
in the README or the docs is allowed to drift away from the pipeline.
"""
import json
import os
import re

from northstar.facts import (FACTS_PATH, build_facts, count_tests,
                             facts_are_current, render_facts_md)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE_PATH = os.path.join(ROOT, "site-data", "site.json")


def _site():
    with open(SITE_PATH, "r", encoding="utf-8") as fh:
        return json.load(fh)


class TestFactSheet:
    def test_fact_sheet_exists_and_is_current(self):
        assert os.path.exists(FACTS_PATH), \
            "docs/FACTS.md missing - run `python -m northstar.cli facts`"
        assert facts_are_current() is None

    def test_render_is_deterministic(self):
        site = _site()
        assert render_facts_md(build_facts(site)) == \
            render_facts_md(build_facts(site))

    def test_no_placeholder_leaks(self):
        text = open(FACTS_PATH, "r", encoding="utf-8").read()
        assert "None" not in text
        assert "nan" not in text.lower().replace("financ", "")
        assert "{" not in text.replace("{}", "")

    def test_headline_numbers_match_the_site_payload(self):
        site = _site()
        text = open(FACTS_PATH, "r", encoding="utf-8").read()
        facts = build_facts(site)
        # anomaly count
        assert f"**{site['anomalies']['open']} open anomalies**" in text
        # every committed desk appears as a row
        for sid in site["backtest"]:
            assert f"`{sid}`" in text, sid
        # prediction-only desks must never render as zero PnL
        for sid, card in site["backtest"].items():
            if card.get("pnl_available") is False:
                row = [ln for ln in text.splitlines() if f"`{sid}`" in ln][0]
                assert "unavailable" in row, row
        # forward ledger numbers
        assert f"issued {facts['forward']['issued']}" in text

    def test_test_count_is_counted_not_remembered(self):
        counted = count_tests()
        assert counted > 300
        text = open(FACTS_PATH, "r", encoding="utf-8").read()
        assert f"**{counted}**" in text

    def test_fact_sheet_declares_its_version_and_source_hash(self):
        text = open(FACTS_PATH, "r", encoding="utf-8").read()
        assert "Generated fact sheet" in text
        assert re.search(r"site\.json` sha256 \(canonical JSON\): `[0-9a-f]{64}`",
                         text)

    def test_stale_detection_reports_the_line(self, tmp_path):
        stale = tmp_path / "FACTS.md"
        stale.write_text("stale content\n", encoding="utf-8")
        reason = facts_are_current(path=str(stale))
        assert reason and "stale" in reason.lower()
