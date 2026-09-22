"""Sport-source registry tests (evidence gates, not prose).

These tests are the anti-hallucination guard for `data/sources/olbg_sports.json`:
the registry must cover exactly the 21 OLBG sport families, every claim it
makes must carry fetched evidence (robots.txt quote + fetch date), a licence
may only be called open when the *tested* policy registry says so, and a
design may only be called graded when the strategy id really exists and
belongs to that sport.
"""
import json
import os

import pytest

from northstar.sources import (GATE_LICENCE_REVIEW, GATE_PERMITTED,
                               GATE_ROBOTS_BLOCKED, OLBG_SPORTS,
                               SourceRegistryError, gate_for, load_registry,
                               registry_covers_hypotheses,
                               registry_hypothesis_ids, sport_source_payload,
                               validate)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class TestRegistryShape:
    def test_covers_exactly_the_olbg_families(self):
        reg = load_registry()
        assert sorted(s["sport"] for s in reg["sports"]) == sorted(OLBG_SPORTS)
        assert len(OLBG_SPORTS) == 21

    def test_registry_is_valid(self):
        validate(load_registry())          # raises on any dishonest entry

    def test_extra_or_missing_sport_is_rejected(self):
        reg = load_registry()
        trimmed = {"sports": reg["sports"][:-1]}
        with pytest.raises(SourceRegistryError):
            validate(trimmed)

    def test_open_licence_requires_the_policy_registry(self):
        reg = load_registry()
        sport = json.loads(json.dumps(reg["sports"][2]))   # a blocked sport
        sport["results_candidates"][0]["licence"] = "open_licence_verified"
        sport["results_candidates"][0]["policy_source_id"] = "not_a_policy"
        with pytest.raises(SourceRegistryError):
            validate({"sports": [sport] * 21})

    def test_robots_quote_and_date_on_every_candidate(self):
        reg = load_registry()
        for sport in reg["sports"]:
            for cand in sport["results_candidates"]:
                assert cand["robots_checked_at"], sport["sport"]
                assert len(cand["robots_quote"]) > 20, sport["sport"]
                assert cand["robots_verdict"] in (
                    "allows_results", "blocks_results", "no_robots_file",
                    "partial", "unknown")
                # A verdict of "blocks" must name what it blocks.
                if cand["robots_verdict"] == "blocks_results":
                    assert cand["robots_blocks"]

    def test_every_sport_names_a_next_action(self):
        for sport in load_registry()["sports"]:
            assert sport.get("next_action"), sport["sport"]
            assert sport.get("coverage_today"), sport["sport"]


class TestGates:
    def test_gate_is_computed_not_stored(self):
        assert gate_for({"licence": "open_licence_verified"}) == GATE_PERMITTED
        assert gate_for({"licence": "not_reviewed",
                         "robots_verdict": "blocks_results"}) == \
            GATE_ROBOTS_BLOCKED
        assert gate_for({"licence": "not_reviewed",
                         "robots_verdict": "allows_results"}) == \
            GATE_LICENCE_REVIEW

    def test_payload_gates_match_the_module_rule(self):
        payload = sport_source_payload()
        for row in payload["sports"]:
            primary = (row.get("results_candidates") or [None])[0]
            assert row["automation_gate"] == gate_for(primary)
            assert row["automation_gate"] in (
                GATE_PERMITTED, GATE_LICENCE_REVIEW, GATE_ROBOTS_BLOCKED,
                "blocked_no_permissioned_source")

    def test_only_policy_backed_sources_are_permitted(self):
        payload = sport_source_payload()
        permitted = [s["sport"] for s in payload["sports"]
                     if s["automation_gate"] == GATE_PERMITTED]
        # OpenLigaDB (ODbL-1.0) is the only source this repository is
        # legally cleared to collect from; it covers three of the 21
        # families today.
        assert sorted(permitted) == ["Darts", "Football", "Ice Hockey"]

    def test_a_more_permissive_alternative_may_not_hide_behind_a_restricted_primary(self):
        """The sport gate is the primary candidate's gate; tests force the
        strongest candidate to be listed first so a sport can never look
        more blocked than it is."""
        import copy
        registry = copy.deepcopy(load_registry())
        boxing = [s for s in registry["sports"] if s["sport"] == "Boxing"][0]
        assert gate_for(boxing["results_candidates"][0]) == GATE_ROBOTS_BLOCKED
        boxing["results_candidates"].append({
            "name": "Hypothetical permitted mirror",
            "url": "https://example.invalid/results",
            "robots_url": "https://example.invalid/robots.txt",
            "robots_verdict": "allows_results",
            "robots_checked_at": "2026-09-22",
            "robots_quote": "User-agent: *\nAllow: /",
            "licence": "open_licence_verified",
            "licence_evidence_url": "https://example.invalid/licence",
            "policy_source_id": "openligadb",
        })
        with pytest.raises(SourceRegistryError, match="most permissive"):
            validate(registry)

    def test_robots_block_maps_to_the_boxrec_finding(self):
        payload = sport_source_payload()
        boxing = next(s for s in payload["sports"] if s["sport"] == "Boxing")
        assert boxing["automation_gate"] == GATE_ROBOTS_BLOCKED
        assert any("/schedule.php" in p for p in
                   boxing["results_candidates"][0]["robots_blocks"])


class TestDesigns:
    def test_graded_designs_use_real_strategy_ids(self):
        from northstar.strategies import REGISTRY
        for sid in registry_hypothesis_ids():
            assert sid in REGISTRY, sid

    def test_every_candidate_has_a_licence_evidence_url(self):
        """A gate is only reviewable if a human can open the terms page."""
        for sport in load_registry()["sports"]:
            for cand in sport["results_candidates"]:
                assert cand.get("licence_evidence_url"), (
                    f"{sport['sport']}/{cand['name']} has no licence "
                    f"evidence URL")

    def test_every_graded_hypothesis_is_named_in_the_source_registry(self):
        assert registry_covers_hypotheses() == []

    def test_sport_of_each_graded_design_matches_the_strategy(self):
        validate(load_registry())          # includes the sport cross-check

    def test_designs_carry_a_gate_statement(self):
        for sport in load_registry()["sports"]:
            for design in sport["strategy_designs"]:
                assert design.get("hypothesis"), design["design_id"]
                assert design.get("rule"), design["design_id"]
                assert design.get("gate"), design["design_id"]
                for ref in design.get("refs", []):
                    assert ref.startswith("https://"), ref

    def test_design_counts_reported_on_the_payload(self):
        payload = sport_source_payload()
        counts = payload["counts"]
        assert counts["sports"] == 21
        assert counts["designs"] == sum(
            len(s["strategy_designs"]) for s in load_registry()["sports"])
        assert counts["graded_designs"] == len(registry_hypothesis_ids())
        assert counts["designs"] >= 40        # breadth across the family


class TestCommittedSitePayload:
    def test_site_json_carries_the_registry(self):
        path = os.path.join(ROOT, "site-data", "site.json")
        site = json.load(open(path, encoding="utf-8"))
        payload = site.get("sport_sources")
        assert payload, "site.json must carry the sport source payload"
        assert payload["counts"]["sports"] == 21
        for row in payload["sports"]:
            assert row["evidence_links"], row["sport"]
            for link in row["evidence_links"]:
                assert link.startswith("https://"), link

    def test_committed_registry_file_is_inside_the_repo(self):
        assert os.path.exists(
            os.path.join(ROOT, "data", "sources", "olbg_sports.json"))


class TestGeneratedRegister:
    """docs/SOURCE-REGISTRY.md is regenerated, never hand-typed."""

    def test_register_is_current(self):
        from northstar.sources import register_is_current
        assert register_is_current() is None

    def test_multiline_robots_quotes_render_as_verbatim_blocks(self):
        """A code span cannot span lines: multi-line quotes must be fenced."""
        from northstar.sources import render_register_md
        text = render_register_md(sport_source_payload())
        multi = [(sport["sport"], cand)
                 for sport in load_registry()["sports"]
                 for cand in sport["results_candidates"]
                 if "\n" in cand.get("robots_quote", "")]
        assert multi, "expected at least one multi-line robots.txt quote"
        for _sport, cand in multi:
            assert "  ```text" in text
            for line in cand["robots_quote"].replace("\r\n", "\n").split("\n"):
                assert f"  {line}" in text, line
        # the single-line form must not be used where the quote has newlines
        for _sport, cand in multi:
            assert f"robots.txt says: `{cand['robots_quote']}`" not in text

    def test_register_links_every_candidate(self):
        import re
        from northstar.sources import REGISTER_PATH, load_registry
        text = open(REGISTER_PATH, encoding="utf-8").read()
        for sport in load_registry()["sports"]:
            assert f"## {sport['sport']}" in text
            for cand in sport["results_candidates"]:
                assert cand["robots_url"] in text, cand["robots_url"]
                assert cand["licence_evidence_url"] in text
