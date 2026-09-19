"""Source-policy gates: the pipeline must refuse unpermitted collection
modes instead of failing silently.

Requirement coverage: "confirm source licensing + collection permissions" -
these tests pin the verified licensing matrix in code.
"""
from __future__ import annotations

import pytest

from northstar.policy import (
    MODE_AUTO_API, MODE_MANUAL_IMPORT, MODE_MANUAL_SNAPSHOT, PolicyError,
    all_policies, get_policy,
)


class TestMatrix:
    def test_openligadb_allows_automated_api(self):
        p = get_policy("openligadb")
        assert p.permits(MODE_AUTO_API)
        assert p.permits(MODE_MANUAL_IMPORT)
        assert p.permits(MODE_MANUAL_SNAPSHOT)
        assert p.license_id == "odbl-1.0"
        assert p.rate_limit.startswith("60")

    def test_footballdata_forbids_automated(self):
        p = get_policy("football_data")
        assert not p.permits(MODE_AUTO_API)
        assert p.permits(MODE_MANUAL_IMPORT)
        assert p.permits(MODE_MANUAL_SNAPSHOT)
        with pytest.raises(PolicyError):
            p.assert_permitted(MODE_AUTO_API)

    def test_olbg_manual_snapshot_only(self):
        p = get_policy("olbg")
        assert not p.permits(MODE_AUTO_API)
        assert not p.permits(MODE_MANUAL_IMPORT)
        assert p.permits(MODE_MANUAL_SNAPSHOT)
        with pytest.raises(PolicyError):
            p.assert_permitted(MODE_AUTO_API)
        with pytest.raises(PolicyError):
            p.assert_permitted(MODE_MANUAL_IMPORT)

    def test_every_registered_source_has_evidence(self):
        for p in all_policies():
            assert p.evidence_urls, f"{p.source_id} missing evidence URLs"
            assert p.verified_at, f"{p.source_id} missing verified_at date"
            assert p.license_id, f"{p.source_id} missing license id"

    def test_unknown_source_raises(self):
        with pytest.raises(PolicyError):
            get_policy("does-not-exist")

    def test_policy_error_message_is_actionable(self):
        with pytest.raises(PolicyError) as exc:
            get_policy("olbg").assert_permitted(MODE_AUTO_API)
        msg = str(exc.value)
        assert "manual_snapshot" in msg
        assert "LICENSING.md" in msg
