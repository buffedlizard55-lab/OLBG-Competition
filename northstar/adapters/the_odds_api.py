"""Licensed historical-odds adapter for The Odds API.

This module is deliberately split into two paths:

* ``fetch_historical_snapshot`` is the network path.  It requires an API key
  from an active paid plan and an explicit acknowledgement of the provider's
  current terms.  The key is read from the caller/environment and is never
  written to a source URL or database row.
* ``parse_historical_snapshot`` and ``ingest_historical_response`` operate on
  a response already obtained under that licence.  Offline imports require an
  explicit non-secret entitlement reference.  They preserve the provider event
  id, response hash, snapshot timestamp and bookmaker identity, and reject an
  event or price that cannot pass the strict pre-start cutoff.

The provider's documentation says the historical endpoint returns the closest
snapshot equal to or earlier than the requested time.  It also says the
endpoint is paid-plan-only.  The provider's terms permit storage, UI display,
research and derived values but prohibit raw-feed redistribution; raw response
bodies therefore remain local and are not included in the Pages payload.
See ``docs/LICENSING.md`` for the evidence links and the exact boundary.
"""
from __future__ import annotations

import json
import math
import os
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any, Dict, List, Mapping, Optional

from ..db import Store
from ..models import (
    MARKET_MATCH_WINNER_3WAY,
    OddsSnapshot,
    fmt_utc,
    parse_utc,
    sha256_text,
    stable_id,
    utcnow,
)
from ..policy import (
    MODE_LICENSED_API,
    MODE_LICENSED_IMPORT,
    PolicyError,
    get_policy,
)

PROVIDER_ID = "the_odds_api"
API_BASE = "https://api.the-odds-api.com/v4"
HISTORICAL_ODDS_DOC = (
    "https://the-odds-api.com/liveapi/guides/v4/#get-historical-odds"
)
TERMS_ACK_ENV = "NORTHSTAR_ODDS_API_TERMS_ACK"
API_KEY_ENV = "NORTHSTAR_ODDS_API_KEY"
TERMS_VERSION = "2026-08-31"


class OddsAdapterError(ValueError):
    """The licensed response cannot be used without making an assumption."""


def historical_url(sport: str, regions: str, markets: str,
                   requested_at_utc: datetime) -> str:
    """Return a reviewable URL with no secret query parameters."""
    stamp = fmt_utc(requested_at_utc)
    query = urllib.parse.urlencode({
        "regions": regions,
        "markets": markets,
        "oddsFormat": "decimal",
        "date": stamp,
    })
    return f"{API_BASE}/historical/sports/{sport}/odds?{query}"


def _assert_license(*, api_key: Optional[str],
                    entitlement_reference: Optional[str] = None,
                    terms_acknowledged: bool,
                    mode: str) -> str:
    policy = get_policy(PROVIDER_ID)
    policy.assert_permitted(mode)
    key = api_key or os.environ.get(API_KEY_ENV)
    acknowledged = terms_acknowledged or (
        os.environ.get(TERMS_ACK_ENV, "") == TERMS_VERSION
    )
    # An offline import may use a non-secret entitlement reference; it is not
    # persisted. Network access always requires the actual API key.
    policy.assert_entitled(
        api_key=key if mode == MODE_LICENSED_API else None,
        entitlement_reference=(entitlement_reference
                              if mode == MODE_LICENSED_IMPORT else None),
        terms_acknowledged=acknowledged,
    )
    return key or ""


def fetch_historical_snapshot(
    sport: str,
    requested_at_utc: datetime,
    *,
    regions: str = "uk",
    markets: str = "h2h",
    api_key: Optional[str] = None,
    terms_acknowledged: bool = False,
    timeout: int = 60,
) -> str:
    """Fetch one licensed historical snapshot as text.

    The returned text is intentionally not written anywhere by this function.
    Callers should hash it and pass it to ``ingest_historical_response`` in a
    local, access-controlled store.
    """
    key = _assert_license(api_key=api_key,
                          terms_acknowledged=terms_acknowledged,
                          mode=MODE_LICENSED_API)
    requested_at_utc = _aware_utc(requested_at_utc)
    params = {
        "apiKey": key,
        "regions": regions,
        "markets": markets,
        "oddsFormat": "decimal",
        "date": fmt_utc(requested_at_utc),
    }
    url = f"{API_BASE}/historical/sports/{urllib.parse.quote(sport, safe='')}/odds"
    url += "?" + urllib.parse.urlencode(params)
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "NorthstarCompetitionLab/0.3"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read().decode("utf-8")


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise OddsAdapterError("timestamp must be timezone-aware UTC")
    return value.astimezone(timezone.utc)


def _normal_name(value: str) -> str:
    return " ".join(str(value).casefold().split())


def _parse_provider_timestamp(value: Any, label: str) -> datetime:
    try:
        return parse_utc(str(value))
    except (TypeError, ValueError) as exc:
        raise OddsAdapterError(f"invalid {label} timestamp: {value!r}") from exc


def decimal_from_american(value: float | int) -> float:
    """Convert an American price to decimal odds without rounding early."""
    try:
        value = float(value)
    except (TypeError, ValueError) as exc:
        raise OddsAdapterError(f"non-numeric American price: {value!r}") from exc
    if not math.isfinite(value) or value == 0:
        raise OddsAdapterError(f"invalid American price: {value!r}")
    return 1.0 + (value / 100.0 if value > 0 else 100.0 / abs(value))


def _decimal_price(value: Any, odds_format: str) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError) as exc:
        raise OddsAdapterError(f"non-numeric price: {value!r}") from exc
    if odds_format == "american":
        numeric = decimal_from_american(numeric)
    elif odds_format != "decimal":
        raise OddsAdapterError(f"unsupported odds format: {odds_format}")
    if not math.isfinite(numeric) or numeric <= 1.0:
        raise OddsAdapterError(f"decimal odds must be finite and > 1: {numeric!r}")
    return numeric


def _event_map(event_ids: Optional[Mapping[str, str]],
               event_lookup: Optional[Mapping[str, Mapping[str, Any]]]
               ) -> Dict[str, Mapping[str, Any]]:
    """Join provider ids to stored events without name-based guessing."""
    out: Dict[str, Mapping[str, Any]] = {}
    if event_lookup:
        out.update(event_lookup)
    by_internal = {
        str(event.get("event_id")): event
        for event in (event_lookup or {}).values()
        if event.get("event_id")
    }
    if event_ids:
        for provider_id, internal_id in event_ids.items():
            # Prefer the full stored event when the mapping points at one.
            # An id-only placeholder is retained only so validation can give
            # a precise incomplete-join error; it can never pass ingestion.
            out[provider_id] = by_internal.get(
                str(internal_id), {"event_id": internal_id})
    return out


def _validate_event(item: Mapping[str, Any], expected: Mapping[str, Any],
                    snapshot_at: datetime) -> str:
    provider_id = str(item.get("id") or "")
    if not provider_id:
        raise OddsAdapterError("historical event has no provider id")
    required_expected = ("event_id", "home_team", "away_team",
                         "scheduled_start_utc")
    missing_expected = [key for key in required_expected
                        if not expected.get(key)]
    if missing_expected:
        raise OddsAdapterError(
            f"provider event {provider_id} has incomplete internal join: "
            f"{', '.join(missing_expected)}"
        )
    internal_id = expected["event_id"]

    expected_home = expected["home_team"]
    expected_away = expected["away_team"]
    if _normal_name(item.get("home_team", "")) != _normal_name(expected_home):
        raise OddsAdapterError(
            f"home participant mismatch for {provider_id}: "
            f"{item.get('home_team')!r} != {expected_home!r}"
        )
    if _normal_name(item.get("away_team", "")) != _normal_name(expected_away):
        raise OddsAdapterError(
            f"away participant mismatch for {provider_id}: "
            f"{item.get('away_team')!r} != {expected_away!r}"
        )

    start_text = item.get("commence_time")
    if not start_text:
        raise OddsAdapterError(
            f"provider event {provider_id} has no commence_time for cutoff validation"
        )
    provider_start = _parse_provider_timestamp(start_text, "commence_time")
    expected_start = _parse_provider_timestamp(expected["scheduled_start_utc"], "stored event start")
    # The odds feed is not an identity authority.  A one-minute tolerance
    # covers serialization precision but not a rescheduled fixture.
    if abs((provider_start - expected_start).total_seconds()) > 60:
        raise OddsAdapterError(
            f"start-time mismatch for {provider_id}: "
            f"{fmt_utc(provider_start)} != {fmt_utc(expected_start)}"
        )
    if snapshot_at >= expected_start:
        raise OddsAdapterError(
            f"historical odds snapshot {snapshot_at.isoformat()} is not "
            f"strictly before event start {expected_start.isoformat()}"
        )
    return str(internal_id)


def parse_historical_snapshot(
    text: str,
    *,
    event_ids: Optional[Mapping[str, str]] = None,
    event_lookup: Optional[Mapping[str, Mapping[str, Any]]] = None,
    requested_at_utc: Optional[datetime] = None,
    regions: str = "uk",
    market: str = "h2h",
    odds_format: str = "decimal",
    source_url: Optional[str] = None,
) -> List[OddsSnapshot]:
    """Parse a historical response into normalized immutable snapshots.

    ``event_lookup`` must contain the stored participant and start fields for
    each provider event id.  ``event_ids`` can map provider ids to internal
    ids, but an id-only mapping is rejected because it cannot prove identity
    or the strict pre-start cutoff. Ambiguous or post-start records raise
    rather than being silently dropped.
    """
    if not text or not text.strip():
        raise OddsAdapterError("empty historical response")
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise OddsAdapterError(f"invalid JSON response: {exc}") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
        raise OddsAdapterError("historical response must contain a data list")

    snapshot_value = payload.get("timestamp")
    if not snapshot_value:
        raise OddsAdapterError("historical response has no timestamp")
    snapshot_at = _parse_provider_timestamp(snapshot_value, "snapshot")
    if requested_at_utc is not None:
        requested = _aware_utc(requested_at_utc)
        if snapshot_at > requested:
            raise OddsAdapterError(
                f"provider returned snapshot after requested cutoff: "
                f"{snapshot_at.isoformat()} > {requested.isoformat()}"
            )
    event_map = _event_map(event_ids, event_lookup)
    payload_hash = sha256_text(text)
    review_url = source_url or HISTORICAL_ODDS_DOC
    snapshots: List[OddsSnapshot] = []

    for item in payload["data"]:
        if not isinstance(item, dict):
            raise OddsAdapterError("historical data item is not an object")
        provider_event_id = str(item.get("id") or "")
        expected = event_map.get(provider_event_id)
        if expected is None:
            raise OddsAdapterError(
                f"provider event {provider_event_id!r} is not explicitly "
                "mapped to an internal event"
            )
        internal_event_id = _validate_event(item, expected, snapshot_at)
        home = _normal_name(item.get("home_team", ""))
        away = _normal_name(item.get("away_team", ""))
        if not home or not away:
            raise OddsAdapterError(f"event {provider_event_id} has no participants")

        for bookmaker in item.get("bookmakers") or []:
            if not isinstance(bookmaker, dict) or not bookmaker.get("key"):
                raise OddsAdapterError(f"invalid bookmaker in event {provider_event_id}")
            book_key = str(bookmaker["key"])
            for market_obj in bookmaker.get("markets") or []:
                if not isinstance(market_obj, dict) or market_obj.get("key") != market:
                    continue
                seen: set[str] = set()
                for outcome in market_obj.get("outcomes") or []:
                    if not isinstance(outcome, dict):
                        raise OddsAdapterError("invalid outcome object")
                    outcome_name = _normal_name(outcome.get("name", ""))
                    if outcome_name == home:
                        selection_key = "home"
                    elif outcome_name == away:
                        selection_key = "away"
                    elif outcome_name == "draw" and market == "h2h":
                        selection_key = "draw"
                    else:
                        # Player/prop names cannot be coerced into a 1X2
                        # selection.  The caller should use a future market
                        # adapter with a sport-specific ruleset.
                        continue
                    if selection_key in seen:
                        raise OddsAdapterError(
                            f"duplicate {selection_key} outcome for "
                            f"{provider_event_id}/{book_key}"
                        )
                    seen.add(selection_key)
                    price = _decimal_price(outcome.get("price"), odds_format)
                    last_update = bookmaker.get("last_update") or market_obj.get("last_update")
                    last_update_text = str(last_update) if last_update else ""
                    if last_update_text:
                        # A malformed provider timestamp is a data-integrity
                        # failure, not a reason to invent a timestamp.
                        _parse_provider_timestamp(last_update_text, "bookmaker last_update")
                    snapshots.append(OddsSnapshot(
                        snapshot_id=stable_id(
                            "os", internal_event_id, PROVIDER_ID, book_key,
                            market, selection_key, fmt_utc(snapshot_at),
                            payload_hash,
                        ),
                        event_id=internal_event_id,
                        observed_at_utc=snapshot_at,
                        provider=f"{PROVIDER_ID}:{book_key}",
                        market_key=(MARKET_MATCH_WINNER_3WAY
                                    if market == "h2h" else market),
                        selection_key=selection_key,
                        decimal_odds=price,
                        source_event_id=provider_event_id,
                        timestamp_precision="provider_snapshot",
                        raw_row_hash=payload_hash,
                        source_url=review_url,
                        notes=(f"provider snapshot timestamp; bookmaker last_update="
                               f"{last_update_text or 'not supplied'}; "
                               f"requested_at={fmt_utc(requested_at_utc) if requested_at_utc else 'not supplied'}"),
                    ))
    if not snapshots:
        raise OddsAdapterError("historical response contained no supported h2h outcomes")
    return snapshots


def ingest_historical_response(
    store: Store,
    text: str,
    *,
    event_ids: Optional[Mapping[str, str]] = None,
    requested_at_utc: Optional[datetime] = None,
    regions: str = "uk",
    market: str = "h2h",
    odds_format: str = "decimal",
    api_key: Optional[str] = None,
    entitlement_reference: Optional[str] = None,
    terms_acknowledged: bool = False,
) -> Dict[str, Any]:
    """Licensed import path; add only validated snapshots to ``store``."""
    _assert_license(api_key=api_key,
                    entitlement_reference=entitlement_reference,
                    terms_acknowledged=terms_acknowledged,
                    mode=MODE_LICENSED_IMPORT)
    lookup = {
        e.get("source_event_id"): e
        for e in store.events()
        if e.get("source_event_id")
    }
    # A provider event id can also be stored in a prior odds row.  Explicit
    # event_ids takes precedence and is the only supported way to join a
    # response when the result source uses a different external id.
    snapshots = parse_historical_snapshot(
        text,
        event_ids=event_ids,
        event_lookup=lookup,
        requested_at_utc=requested_at_utc,
        regions=regions,
        market=market,
        odds_format=odds_format,
    )
    for snapshot in snapshots:
        store.add_odds_snapshot(snapshot)
    store.commit()
    return {
        "snapshots": len(snapshots),
        "events": len({s.event_id for s in snapshots}),
        "provider": PROVIDER_ID,
        "payload_sha256": sha256_text(text),
        "imported_at_utc": fmt_utc(utcnow()),
    }


__all__ = [
    "API_BASE",
    "HISTORICAL_ODDS_DOC",
    "OddsAdapterError",
    "PROVIDER_ID",
    "TERMS_VERSION",
    "decimal_from_american",
    "fetch_historical_snapshot",
    "historical_url",
    "ingest_historical_response",
    "parse_historical_snapshot",
]
