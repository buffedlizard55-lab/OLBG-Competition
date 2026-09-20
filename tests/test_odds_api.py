"""Offline contract tests for the licensed historical-odds adapter.

The payload below is a schema fixture, not a claimed provider capture.  No
provider response or API key is committed.  Real imports must be made under an
active paid entitlement and are retained locally only.
"""
from __future__ import annotations

import json
from datetime import timedelta

import pytest

from northstar.adapters.the_odds_api import (
    OddsAdapterError,
    decimal_from_american,
    ingest_historical_response,
    parse_historical_snapshot,
)
from northstar.models import parse_utc
from northstar.policy import PolicyError, get_policy

from conftest import mk_event


EVENT = {
    "event_id": "ev-api",
    "source_event_id": "provider-event-1",
    "home_team": "Home FC",
    "away_team": "Away FC",
    "scheduled_start_utc": "2026-01-10T15:00:00Z",
}


def payload(*, timestamp="2026-01-09T12:00:00Z", home="Home FC",
            away="Away FC") -> str:
    return json.dumps({
        "timestamp": timestamp,
        "previous_timestamp": "2026-01-09T11:50:00Z",
        "next_timestamp": "2026-01-09T12:10:00Z",
        "data": [{
            "id": "provider-event-1",
            "sport_key": "soccer_bundesliga",
            "commence_time": "2026-01-10T15:00:00Z",
            "home_team": home,
            "away_team": away,
            "bookmakers": [{
                "key": "licensed_book",
                "title": "Licensed Book",
                "last_update": "2026-01-09T11:59:00Z",
                "markets": [{
                    "key": "h2h",
                    "outcomes": [
                        {"name": home, "price": 2.10},
                        {"name": "Draw", "price": 3.40},
                        {"name": away, "price": 3.20},
                    ],
                }],
            }],
        }],
    })


def test_policy_records_paid_plan_and_ui_boundary():
    policy = get_policy("the_odds_api")
    assert policy.requires_active_entitlement is True
    assert "paid" in policy.license_summary.lower()
    assert "https://the-odds-api.com/terms-and-conditions.html" in policy.evidence_urls
    with pytest.raises(PolicyError):
        policy.assert_entitled(api_key=None, terms_acknowledged=False)
    with pytest.raises(PolicyError):
        policy.assert_entitled(api_key="not-a-real-key", terms_acknowledged=False)
    policy.assert_entitled(api_key="not-a-real-key", terms_acknowledged=True)


def test_american_conversion_is_explicit():
    assert decimal_from_american(150) == pytest.approx(2.5)
    assert decimal_from_american(-200) == pytest.approx(1.5)
    with pytest.raises(OddsAdapterError):
        decimal_from_american(0)


def test_parse_preserves_source_identity_hash_and_strict_time():
    rows = parse_historical_snapshot(
        payload(),
        event_lookup={"provider-event-1": EVENT},
        requested_at_utc=parse_utc("2026-01-09T12:00:00Z"),
    )
    assert {row.selection_key for row in rows} == {"home", "draw", "away"}
    assert all(row.event_id == "ev-api" for row in rows)
    assert all(row.source_event_id == "provider-event-1" for row in rows)
    assert all(row.provider == "the_odds_api:licensed_book" for row in rows)
    assert all(row.raw_row_hash for row in rows)
    assert all(row.timestamp_precision == "provider_snapshot" for row in rows)
    assert all(row.observed_at_utc < parse_utc(EVENT["scheduled_start_utc"])
               for row in rows)


def test_parse_rejects_participant_mismatch_and_post_start_snapshot():
    with pytest.raises(OddsAdapterError, match="participant mismatch"):
        parse_historical_snapshot(
            payload(home="Different FC"), event_lookup={"provider-event-1": EVENT}
        )
    with pytest.raises(OddsAdapterError, match="not strictly before"):
        parse_historical_snapshot(
            payload(timestamp="2026-01-10T15:00:00Z"),
            event_lookup={"provider-event-1": EVENT},
        )


def test_parse_rejects_unmapped_provider_event():
    with pytest.raises(OddsAdapterError, match="not explicitly mapped"):
        parse_historical_snapshot(payload(), event_ids={"other": "ev-api"})


def test_parse_rejects_id_only_join_without_start_metadata():
    with pytest.raises(OddsAdapterError, match="incomplete internal join"):
        parse_historical_snapshot(
            payload(), event_ids={"provider-event-1": "ev-api"}
        )


def test_parse_rejects_missing_provider_commence_time():
    body = json.loads(payload())
    del body["data"][0]["commence_time"]
    with pytest.raises(OddsAdapterError, match="commence_time"):
        parse_historical_snapshot(
            json.dumps(body), event_lookup={"provider-event-1": EVENT}
        )


def test_licensed_import_requires_entitlement_reference_even_with_terms_ack():
    with pytest.raises(PolicyError, match="entitlement reference"):
        ingest_historical_response(
            # No event is needed: the licensing gate must fail first.
            object(), payload(), terms_acknowledged=True
        )


def test_licensed_import_is_explicit_and_stored(store):
    ev = mk_event(store, event_id="ev-api", home="Home FC", away="Away FC")
    # The event source id in this test is deliberately the provider id used by
    # the adapter.  In production a mapping is safer than assuming ids match.
    store.conn.execute(
        "UPDATE events SET source_event_id='provider-event-1' WHERE event_id='ev-api'"
    )
    store.commit()
    out = ingest_historical_response(
        store,
        payload(),
        event_ids={"provider-event-1": "ev-api"},
        requested_at_utc=parse_utc("2026-01-09T12:00:00Z"),
        entitlement_reference="paid-plan-contract-2026-09",
        terms_acknowledged=True,
    )
    assert out["snapshots"] == 3
    snapshots = store.odds_snapshots("ev-api")
    assert len(snapshots) == 3
    assert {s["source_event_id"] for s in snapshots} == {"provider-event-1"}


def test_import_without_entitlement_does_not_write(store):
    mk_event(store, event_id="ev-api", home="Home FC", away="Away FC")
    with pytest.raises(PolicyError):
        ingest_historical_response(
            store, payload(), event_ids={"provider-event-1": "ev-api"}
        )
    assert store.odds_snapshots("ev-api") == []
