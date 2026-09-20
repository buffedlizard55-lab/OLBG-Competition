"""Adapter contract for an authorised competition-organiser result export.

A result is not "official" because a web page calls itself official.  This
adapter requires an explicit authorization record supplied by the operator:
organizer, provider id, permission reference, grant date and source URL.  It
accepts a structured export obtained under that authorization and refuses to
turn an arbitrary web/JSON response into an official result.

No organizer feed is bundled in this repository.  The adapter is ready for a
league's licensed export/API once written permission and a reproducible
source path are obtained.  Until then the pilot uses OpenLigaDB plus an
independent cross-check and labels it as community/reference data, not as an
official governing-body feed.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, List, Mapping

from ..db import Store
from ..models import Result, parse_utc, sha256_text, stable_id, utcnow
from ..policy import MODE_LICENSED_IMPORT, PolicyError, get_policy

OFFICIAL_TERMINAL_STATUSES = {
    "finished", "postponed", "cancelled", "abandoned", "disputed",
}


class OfficialResultError(ValueError):
    """An authorised export is malformed or cannot be reconciled."""


@dataclass(frozen=True)
class OfficialFeedAuthorization:
    """Evidence that the adapter may treat one provider as official."""

    provider_id: str
    organizer: str
    permission_reference: str
    permission_granted_at: str
    source_url: str
    official_source_attested: bool = False

    def validate(self) -> None:
        policy = get_policy("official_organizer")
        policy.assert_permitted(MODE_LICENSED_IMPORT)
        required = {
            "provider_id": self.provider_id,
            "organizer": self.organizer,
            "permission_reference": self.permission_reference,
            "permission_granted_at": self.permission_granted_at,
            "source_url": self.source_url,
        }
        missing = [name for name, value in required.items()
                   if value is None or not str(value).strip()]
        if missing:
            raise PolicyError(
                "official result adapter requires explicit authorization "
                f"fields: {', '.join(missing)}"
            )
        if not self.official_source_attested:
            raise PolicyError(
                "official result adapter is disabled until the organizer's "
                "authority is attested in writing"
            )
        policy.assert_entitled(
            entitlement_reference=self.permission_reference,
            terms_acknowledged=self.official_source_attested,
        )
        # Permission dates are evidence metadata, not a claim that the source
        # is current forever.  Keep the value parseable for audit reports.
        try:
            parse_utc(self.permission_granted_at)
        except (TypeError, ValueError) as exc:
            raise PolicyError("permission_granted_at must be ISO-8601 UTC") from exc


def _normal(value: Any) -> str:
    return " ".join(str(value or "").casefold().split())


def _parse_result_timestamp(value: Any, label: str):
    try:
        return parse_utc(str(value))
    except (TypeError, ValueError) as exc:
        raise OfficialResultError(
            f"invalid {label} timestamp: {value!r}"
        ) from exc


def _parse_payload(text: str) -> tuple[Dict[str, Any], str]:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise OfficialResultError(f"invalid official result JSON: {exc}") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("results"), list):
        raise OfficialResultError("official export must contain a results list")
    return payload, sha256_text(text)


def parse_authorized_results(
    text: str,
    authorization: OfficialFeedAuthorization,
    *,
    event_ids: Mapping[str, str],
    event_lookup: Mapping[str, Mapping[str, Any]],
) -> List[Result]:
    """Validate and normalize an organiser export without writing it."""
    authorization.validate()
    payload, payload_hash = _parse_payload(text)
    source_meta = payload.get("source") or {}
    if not isinstance(source_meta, dict):
        raise OfficialResultError("official export source metadata is not an object")
    if source_meta.get("provider_id") != authorization.provider_id:
        raise OfficialResultError("export provider does not match authorization")
    if source_meta.get("organizer") != authorization.organizer:
        raise OfficialResultError("export organizer does not match authorization")

    out: List[Result] = []
    seen_source_events = set()
    for row in payload["results"]:
        if not isinstance(row, dict):
            raise OfficialResultError("official result row is not an object")
        source_event_id = str(row.get("source_event_id") or "")
        if not source_event_id:
            raise OfficialResultError("official result row has no source_event_id")
        if source_event_id in seen_source_events:
            raise OfficialResultError(
                f"official export repeats source event {source_event_id}"
            )
        seen_source_events.add(source_event_id)
        internal_id = event_ids.get(source_event_id)
        if not internal_id:
            raise OfficialResultError(
                f"official event {source_event_id!r} has no explicit internal join"
            )
        event = event_lookup.get(internal_id)
        if event is None:
            raise OfficialResultError(f"unknown internal event {internal_id!r}")
        for field in ("home_team", "away_team", "competition", "sport"):
            if not row.get(field):
                raise OfficialResultError(
                    f"official event {source_event_id} missing {field}"
                )
        if _normal(row["home_team"]) != _normal(event["home_team"]):
            raise OfficialResultError(f"home participant mismatch for {source_event_id}")
        if _normal(row["away_team"]) != _normal(event["away_team"]):
            raise OfficialResultError(f"away participant mismatch for {source_event_id}")
        if _normal(row["competition"]) != _normal(event["competition"]):
            raise OfficialResultError(f"competition mismatch for {source_event_id}")
        if _normal(row["sport"]) != _normal(event["sport"]):
            raise OfficialResultError(f"sport mismatch for {source_event_id}")

        final_status = str(row.get("final_status") or "")
        if final_status not in OFFICIAL_TERMINAL_STATUSES:
            raise OfficialResultError(
                f"unsupported/non-final official status {final_status!r}"
            )
        final_at = _parse_result_timestamp(
            row.get("officially_final_at_utc"), "officially_final_at_utc"
        )
        try:
            start = parse_utc(event["scheduled_start_utc"])
        except (TypeError, ValueError) as exc:
            raise OfficialResultError(
                f"stored event {internal_id} has invalid scheduled start"
            ) from exc
        if final_at <= start:
            raise OfficialResultError(
                f"official final timestamp is not after event start for "
                f"{source_event_id}"
            )

        home_score = row.get("home_goals")
        away_score = row.get("away_goals")
        if final_status == "finished":
            if (isinstance(home_score, bool) or isinstance(away_score, bool)
                    or not isinstance(home_score, int)
                    or not isinstance(away_score, int)
                    or home_score < 0 or away_score < 0):
                raise OfficialResultError(
                    f"finished result {source_event_id} has invalid scores"
                )
        else:
            # A non-played/contested event must not be assigned a guessed
            # score.  If the organizer supplied one, reject it rather than
            # allowing a later rule to treat it as final.
            if home_score is not None or away_score is not None:
                raise OfficialResultError(
                    f"non-finished result {source_event_id} must not carry scores"
                )

        out.append(Result(
            result_id=stable_id("res", authorization.provider_id,
                                source_event_id, payload_hash),
            event_id=internal_id,
            provider=authorization.provider_id,
            retrieved_at_utc=utcnow(),
            source_url=str(row.get("source_url") or authorization.source_url),
            raw_payload_hash=payload_hash,
            final_status=final_status,
            officially_final_at_utc=final_at,
            home_goals=home_score,
            away_goals=away_score,
            result_type_kind=row.get("result_type_kind"),
            version=str(row.get("version") or payload.get("version") or ""),
        ))
    if not out:
        raise OfficialResultError("official export has no result rows")
    return out


def ingest_authorized_results(
    store: Store,
    text: str,
    authorization: OfficialFeedAuthorization,
    *,
    event_ids: Mapping[str, str],
) -> Dict[str, Any]:
    """Write validated official results and update event terminal state."""
    lookup = {e["event_id"]: e for e in store.events()}
    results = parse_authorized_results(
        text, authorization, event_ids=event_ids, event_lookup=lookup
    )
    anomalies: List[str] = []
    for result in results:
        anomalies.extend(store.add_result(result))
        if result.final_status in OFFICIAL_TERMINAL_STATUSES:
            store.conn.execute(
                "UPDATE events SET status=?, identity_confidence='verified' "
                "WHERE event_id=?",
                (result.final_status, result.event_id),
            )
    store.commit()
    return {
        "results": len(results),
        "finished": len([r for r in results if r.final_status == "finished"]),
        "anomalies": anomalies,
        "provider": authorization.provider_id,
    }


__all__ = [
    "OfficialFeedAuthorization",
    "OfficialResultError",
    "ingest_authorized_results",
    "parse_authorized_results",
]
