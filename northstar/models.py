"""Northstar data models.

Pure dataclasses. All timestamps are timezone-aware UTC (or naive = UTC with a
comment where the source format forces it). No logic beyond validation lives
here.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------- constants

SPORT_FOOTBALL = "football"
SPORT_ICE_HOCKEY = "ice_hockey"
SPORT_DARTS = "darts"

MARKET_MATCH_WINNER_3WAY = "match_winner_3way"
# 2-way match winner (no draw outcome possible: hockey incl. OT/SO, darts).
# Prediction-only desks use it; the settlement engine has no rule set for it
# yet (settlement would flag MARKET_RULE_UNKNOWN), which is intentional.
MARKET_MATCH_WINNER_2WAY = "match_winner_2way"
# Regulation-time 3-way (ice hockey): home win / draw / away win over the
# three regulation periods. Prediction-only (no permissioned odds path);
# the 3-period outcome is derived from the stored final-priority row's
# ``resultTypeKind`` (evaluation.regulation_outcome) - never settled.
MARKET_REGULATION_3WAY = "regulation_3way"
# Total goals over/under 2.5 (football). Settled on the 90-minute score:
# ``over`` wins when home+away >= 3, ``under`` when <= 2; a half-goal line
# can never push. Rule set: settlement.match_outcome_totals.
MARKET_TOTALS_2_5 = "total_goals_over_under_2_5"
TOTALS_2_5_LINE = 2.5
# Asian handicap (football). The line is stored per snapshot/tip (the
# handicap varies per event); ``home`` is the team the (negative) line is
# quoted on per the football-data.co.uk key "AHh = Market size of handicap
# (home team)". Quarter lines split the stake in half across the two
# neighbouring integer/half lines; integer lines can push (stake refunded).
# Rule set: settlement.match_outcome_asian_handicap.
MARKET_ASIAN_HANDICAP = "asian_handicap"
# Total goals over/under 5.5 (ice hockey). Prediction-only: there is no
# permissioned DEL odds path in this repository, so the desk is graded on
# the stored final score (>= 6 goals = over, <= 5 = under; a half-goal line
# can never push) by northstar.evaluation - never settled, never PnL.
# Market id added 2026-09-22 with the hockey totals desks.
MARKET_TOTALS_5_5 = "total_goals_over_under_5_5"
TOTALS_5_5_LINE = 5.5

EVENT_STATUS_SCHEDULED = "scheduled"
EVENT_STATUS_LIVE = "live"
EVENT_STATUS_FINISHED = "finished"
EVENT_STATUS_POSTPONED = "postponed"
EVENT_STATUS_CANCELLED = "cancelled"
EVENT_STATUS_ABANDONED = "abandoned"
EVENT_STATUS_DISPUTED = "disputed"

TIP_STATUS_OPEN = "open"
TIP_STATUS_WON = "won"
TIP_STATUS_LOST = "lost"
TIP_STATUS_VOID = "void"
TIP_STATUS_PUSH = "push"
TIP_STATUS_PENDING = "pending"
TIP_STATUS_UNSETTLEABLE = "unsettleable"
TIP_STATUS_DISPUTED = "disputed"

RESULT_KIND_AFTER_90 = "After90Minutes"
RESULT_KIND_AFTER_EXTRA = "AfterExtraTime"
RESULT_KIND_AFTER_PENALTIES = "AfterPenalties"
RESULT_KIND_HALF_TIME = "HalfTime"

SETTLEMENT_RULE_VERSION = "nr-settlement-2026-09-22.1"

# Anomaly taxonomy (superset of docs/data-contract.md section 4).
ANOMALY_MISSING_ODDS = "MISSING_ODDS"
ANOMALY_ODDS_AFTER_START = "ODDS_AFTER_START"
ANOMALY_SOURCE_EDITED = "SOURCE_EDITED"
ANOMALY_DUPLICATE_TIP = "DUPLICATE_TIP"
ANOMALY_EVENT_UNMATCHED = "EVENT_UNMATCHED"
ANOMALY_PARTICIPANT_AMBIGUOUS = "PARTICIPANT_AMBIGUOUS"
ANOMALY_COMPETITION_MISMATCH = "COMPETITION_MISMATCH"
ANOMALY_TIME_CONFLICT = "TIME_CONFLICT"
ANOMALY_RESULT_NOT_FINAL = "RESULT_NOT_FINAL"
ANOMALY_RESULT_SOURCE_CONFLICT = "RESULT_SOURCE_CONFLICT"
ANOMALY_VOID_RULE_UNKNOWN = "VOID_RULE_UNKNOWN"
ANOMALY_MARKET_RULE_UNKNOWN = "MARKET_RULE_UNKNOWN"
ANOMALY_TIP_EDITED_AFTER_CUTOFF = "TIP_EDITED_AFTER_CUTOFF"
ANOMALY_JURISDICTION_NOT_COVERED = "JURISDICTION_NOT_COVERED"
ANOMALY_POLICY_VIOLATION = "POLICY_VIOLATION"
ANOMALY_CONSENSUS_DRIFT = "CONSENSUS_DRIFT"
ANOMALY_EVENT_CHANGED = "EVENT_CHANGED"
ANOMALY_RESULT_KIND_INCONSISTENT = "RESULT_KIND_INCONSISTENT"
ANOMALY_MISSING_METADATA = "MISSING_METADATA"

VERIFICATION_VERIFIED = "verified"
VERIFICATION_REVIEW = "review"
VERIFICATION_BLOCKED = "blocked"

UTC = timezone.utc


def utcnow() -> datetime:
    return datetime.now(UTC)


def parse_utc(value: str) -> datetime:
    """Parse ISO-8601 variants seen in source payloads into aware UTC."""
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def fmt_utc(dt: Optional[datetime]) -> Optional[str]:
    if dt is None:
        return None
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def stable_id(prefix: str, *parts: Any) -> str:
    payload = json.dumps(list(parts), ensure_ascii=False, sort_keys=True,
                         separators=(",", ":"))
    return f"{prefix}-{sha256_text(payload)[:20]}"


# ---------------------------------------------------------------- entities

@dataclass
class Event:
    event_id: str
    sport: str
    competition: str
    home_team_id: str
    home_team: str
    away_team_id: str
    away_team: str
    scheduled_start_utc: datetime
    status: str = EVENT_STATUS_SCHEDULED
    group_order: Optional[int] = None          # matchday / round
    group_name: Optional[str] = None
    source_event_id: Optional[str] = None      # e.g. openligadb matchID
    source_provider: Optional[str] = None
    source_url: Optional[str] = None
    source_version: Optional[str] = None       # e.g. lastUpdateDateTime
    identity_confidence: str = "unmatched"     # verified | probable | unmatched
    revision: int = 0

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["scheduled_start_utc"] = fmt_utc(self.scheduled_start_utc)
        return d


@dataclass
class Tip:
    tip_id: str
    tipster_id: str
    strategy_id: str            # "human", "imported" or versioned model id
    event_id: str
    market: str
    selection: str              # display text
    selection_key: str          # "home" | "draw" | "away"
    published_at_utc: datetime
    collected_at_utc: datetime
    cutoff_at_utc: datetime     # last permissible input time for any feature
    odds_decimal: Optional[float] = None
    odds_source: Optional[str] = None
    stake_units: float = 1.0
    # Market line for line markets (e.g. the Asian-handicap line carried by
    # the priced snapshot the desk bet). ``None`` for line-less markets.
    line: Optional[float] = None
    source_url: Optional[str] = None
    raw_payload_hash: Optional[str] = None
    status: str = TIP_STATUS_OPEN
    notes: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        for k in ("published_at_utc", "collected_at_utc", "cutoff_at_utc"):
            d[k] = fmt_utc(d[k])
        return d


@dataclass
class OddsSnapshot:
    snapshot_id: str
    event_id: str
    observed_at_utc: datetime
    provider: str               # e.g. "b365", "pinacle" -> "pinnacle", "market_avg"
    market_key: str
    selection_key: str
    decimal_odds: float
    # Handicap/total line when the market is line-quoted (Asian handicap).
    # The football-data AH key is a per-event value (AHh), so it belongs on
    # the snapshot, not on the market constant. ``None`` for line-less
    # markets (1X2, O/U 2.5 has a fixed 2.5 line by definition).
    line: Optional[float] = None
    # Provider-side event id is retained so a later replay can prove which
    # external object was joined to the internal event.  It is not used as
    # the internal identity because providers can change ids across feeds.
    source_event_id: Optional[str] = None
    timestamp_precision: str = "exact"   # exact | window_close_inferred
    raw_row_hash: Optional[str] = None
    source_url: Optional[str] = None
    notes: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["observed_at_utc"] = fmt_utc(self.observed_at_utc)
        return d


@dataclass
class Result:
    result_id: str
    event_id: str
    provider: str
    retrieved_at_utc: datetime
    source_url: Optional[str]
    raw_payload_hash: Optional[str]
    final_status: str                       # "finished" | "postponed" | ...
    officially_final_at_utc: datetime
    home_goals: Optional[int] = None
    away_goals: Optional[int] = None
    result_type_kind: Optional[str] = None  # After90Minutes etc.
    version: Optional[str] = None           # source amendment/version info

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["retrieved_at_utc"] = fmt_utc(self.retrieved_at_utc)
        d["officially_final_at_utc"] = fmt_utc(self.officially_final_at_utc)
        return d


@dataclass
class Settlement:
    settlement_id: str
    tip_id: str
    settled_at_utc: datetime
    rule_version: str
    outcome: str                      # won | lost | void | push
    pnl_units: float
    stake_units: float
    odds_decimal: Optional[float]
    result_id: Optional[str]
    verification_state: str           # verified | review
    gate_log: Dict[str, Any] = field(default_factory=dict)
    anomaly_ids: List[str] = field(default_factory=list)
    supersedes_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["settled_at_utc"] = fmt_utc(self.settled_at_utc)
        return d


@dataclass
class Anomaly:
    anomaly_id: str
    kind: str
    entity_type: str                # event | tip | result | odds | entrant
    entity_id: str
    detected_at_utc: datetime
    detail: str
    source_urls: List[str] = field(default_factory=list)
    status: str = "open"            # open | resolved
    resolution: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["detected_at_utc"] = fmt_utc(self.detected_at_utc)
        return d
