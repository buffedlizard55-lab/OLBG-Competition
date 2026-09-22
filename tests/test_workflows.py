"""Workflow integrity: the CI chain must stay self-consistent.

These are deliberately text-level checks (no PyYAML dependency, because CI
installs pytest only).  They exist because the first capture run on this
branch failed its own test step - the tests were right and the *workflow*
was wrong.  The rules enforced here:

* the offline `Tests` workflow runs the pipeline *before* the tests, so the
  generated-doc staleness checks judge a fresh build;
* it proves `docs/FACTS.md`, `docs/SOURCE-REGISTRY.md` and the counted
  README quotes were committed (a git diff must be empty);
* the capture workflow regenerates those files *before* it commits, and
  commits them alongside the data - otherwise a weekly refresh leaves the
  repository stale (the actual failure that motivated this file);
* the Pages workflow deploys the exact payload the tests passed, ships the
  raw source registry the site links to, and is re-triggered by the capture
  workflow (a `GITHUB_TOKEN` push does not trigger other workflows, so
  without that trigger the site would silently serve last week's data).
"""
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORKFLOWS = os.path.join(ROOT, ".github", "workflows")


def _text(name):
    with open(os.path.join(WORKFLOWS, name), "r", encoding="utf-8") as fh:
        return fh.read()


def _index(text, needle):
    assert needle in text, f"missing {needle!r}"
    return text.index(needle)


class TestOfflineTestsWorkflow:
    def test_pipeline_runs_before_the_tests(self):
        text = _text("ci.yml")
        assert _index(text, "run-pipeline --fresh") < _index(
            text, "python -m pytest")
        assert _index(text, "northstar.cli verify") < _index(
            text, "python -m pytest")

    def test_generated_docs_are_checked_and_must_be_committed(self):
        text = _text("ci.yml")
        assert "facts --check" in text
        assert "git diff --exit-code" in text
        for path in ("docs/FACTS.md", "docs/SOURCE-REGISTRY.md", "README.md"):
            assert path in text, path

    def test_site_is_smoke_tested_before_it_is_deployed(self):
        assert "node scripts/site-smoke.mjs" in _text("ci.yml")
        pages = _text("pages.yml")
        assert _index(pages, "site-smoke") < _index(pages, "deploy-pages")


class TestCaptureWorkflow:
    def test_docs_are_regenerated_before_the_commit_step(self):
        text = _text("capture.yml")
        assert _index(text, "facts --sync-readme") < _index(text, "git commit")
        assert _index(text, "python -m pytest") < _index(text, "git commit")

    def test_committed_refresh_includes_the_generated_docs(self):
        text = _text("capture.yml")
        add = text[_index(text, "git add"):text.index("git commit")]
        for path in ("data/fixtures", "data/forward/ledger.json",
                     "site-data/site.json", "docs/FACTS.md",
                     "docs/SOURCE-REGISTRY.md", "README.md"):
            assert path in add, f"{path} is not committed by the capture run"


class TestPagesWorkflow:
    def test_ships_the_payload_and_the_source_registry(self):
        text = _text("pages.yml")
        assert "site-data/site.json" in text
        assert "data/sources/*.json" in text

    def test_is_retriggered_by_the_capture_workflow(self):
        """The name in workflow_run must match capture.yml's `name:` exactly,
        or the trigger silently never fires."""
        pages = _text("pages.yml")
        capture = _text("capture.yml")
        declared = capture.splitlines()[0].split("name:", 1)[1].strip()
        assert f'"{declared}"' in pages, (
            f"pages.yml must trigger on workflow_run of {declared!r}")
        assert "conclusion == 'success'" in pages, \
            "a failed capture must never be deployed"
