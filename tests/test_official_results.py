"""The official-result adapter is authorization-gated and schema-tested.

The fixture is intentionally a synthetic contract example.  The repository
contains no organizer feed or implied permission; a real import needs a signed
or otherwise reviewable permission record from the organizer.
"""
from __future__ import annotations

import json

import pytest

from northstar.adapters.official_results import (
    OfficialFeedAuthorization,
    OfficialResultError,
    ingest_authorized_results,
    parse_authorized_results,
)
from northstar.models import parse_utc
from northstar.policy import PolicyError

from conftest import mk_event


AUTH = OfficialFeedAuthorization(
    provider_id="league-official",
    organizer="Example League",
    permission_reference="written-agreement-2026-01",
    permission_granted_at="2026-01-01T00:00:00Z",
    source_url="https://official.example/results",
    official_source_attested=True,
)


def payload(final_status="finished", scores=(2, 1)):
    row = {
        "source_event_id": "official-1",
        "sport": "football",
        "competition": "Test League",
        "home_team": "Home FC",
        "away_team": "Away FC",
        "final_status": final_status,
        "officially_final_at_utc": "2026-01-10T17:00:00Z",
        "source_url": "https://official.example/results/official-1",
        "version": "2026-01-10-v1",
        "result_type_kind": "regulation",
    }
    if scores is not None:
        row["home_goals"], row["away_goals"] = scores
    return json.dumps({
        "source": {"provider_id": "league-official", "organizer": "Example League"},
        "version": "export-v1",
        "results": [row],
    })


def test_unauthorised_official_claim_is_refused():
    with pytest.raises(PolicyError):
        parse_authorized_results(
            payload(),
            OfficialFeedAuthorization(
                provider_id="league-official",
                organizer="Example League",
                permission_reference="",
                permission_granted_at="2026-01-01T00:00:00Z",
                source_url="https://official.example/results",
                official_source_attested=False,
            ),
            event_ids={"official-1": "ev-official"},
            event_lookup={},
        )


def test_official_result_requires_explicit_identity_and_is_reproducible(store):
    mk_event(store, event_id="ev-official", competition="Test League",
             identity="unmatched")
    parsed = parse_authorized_results(
        payload(), AUTH,
        event_ids={"official-1": "ev-official"},
        event_lookup={"ev-official": store.get_event("ev-official")},
    )
    assert len(parsed) == 1
    assert parsed[0].provider == "league-official"
    assert parsed[0].raw_payload_hash
    assert parsed[0].home_goals == 2

    out = ingest_authorized_results(
        store, payload(), AUTH, event_ids={"official-1": "ev-official"}
    )
    assert out["finished"] == 1
    assert store.results("ev-official")[0]["provider"] == "league-official"
    assert store.get_event("ev-official")["identity_confidence"] == "verified"


def test_official_adapter_rejects_participant_and_pre_start_final(store):
    mk_event(store, event_id="ev-official", competition="Test League")
    with pytest.raises(OfficialResultError, match="home participant"):
        parse_authorized_results(
            payload().replace("Home FC", "Other FC"), AUTH,
            event_ids={"official-1": "ev-official"},
            event_lookup={"ev-official": store.get_event("ev-official")},
        )
    before = payload().replace(
        "2026-01-10T17:00:00Z", "2026-01-10T14:59:59Z"
    )
    with pytest.raises(OfficialResultError, match="not after"):
        parse_authorized_results(
            before, AUTH,
            event_ids={"official-1": "ev-official"},
            event_lookup={"ev-official": store.get_event("ev-official")},
        )


def test_official_result_rejects_malformed_final_timestamp(store):
    mk_event(store, event_id="ev-official", competition="Test League")
    text = payload().replace(
        "2026-01-10T17:00:00Z", "not-a-timestamp"
    )
    with pytest.raises(OfficialResultError, match="invalid officially_final_at_utc"):
        parse_authorized_results(
            text, AUTH,
            event_ids={"official-1": "ev-official"},
            event_lookup={"ev-official": store.get_event("ev-official")},
        )


def test_official_void_state_has_no_guessed_score(store):
    mk_event(store, event_id="ev-official", competition="Test League")
    text = payload(final_status="cancelled", scores=None)
    out = ingest_authorized_results(
        store, text, AUTH, event_ids={"official-1": "ev-official"}
    )
    assert out["results"] == 1
    result = store.results("ev-official")[0]
    assert result["final_status"] == "cancelled"
    assert result["home_goals"] is None
    assert store.get_event("ev-official")["status"] == "cancelled"
