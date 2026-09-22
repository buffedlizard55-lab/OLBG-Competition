"""Walk-forward backtesting with strict time cutoffs.

Guarantees (enforced, and tested):
1. ``TimeBoundedStore`` raises ``TimeLeakageError`` if any feature is read
   at a timestamp later than the read-at time - models can only see what a
   desk would have known at the moment the bet is made.
2. For every bet the cutoff (latest input time) is strictly before the
   event start; the engine refuses to run otherwise.
3. Ordering invariance: inputs are internally sorted by (group_order,
   start); shuffling the input list must not change any result.
4. Every backtest bet gets a Tip + Settlement row in the store, so the
   backtest is inspectable through the same audit trail as live paper
   bets (strategy_id marks the entrant).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional, Sequence

from . import models
from .db import Store
from .models import (
    EVENT_STATUS_FINISHED, MARKET_ASIAN_HANDICAP, MARKET_MATCH_WINNER_3WAY,
    MARKET_TOTALS_2_5, TIP_STATUS_OPEN, TIP_STATUS_UNSETTLEABLE, Tip,
    parse_utc, stable_id, utcnow,
)
from .settlement import settle_tip


class TimeLeakageError(RuntimeError):
    pass


@dataclass
class TimeBoundedStore:
    """Feature store that only serves data whose availability time <= now."""
    events: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    # team -> list of (available_at, dict(home, away, hg, ag, event_id,
    #                                      group_order, start_utc))
    team_history: Dict[str, List[Dict[str, Any]]] = field(default_factory=dict)
    ratings: Dict[str, float] = field(default_factory=dict)
    rating_updates: Dict[str, List[Dict[str, Any]]] = field(default_factory=dict)
    # Read-audit state is reset for every decision.  It lets the engine catch
    # a strategy that reads a feature at t=12:00 but falsely declares a
    # cutoff of t=11:00 after returning.
    _decision_reads: List[datetime] = field(default_factory=list,
                                             init=False, repr=False)
    _decision_start: Optional[datetime] = field(default=None,
                                                init=False, repr=False)

    # ---------------------------------------------------------- read auditing

    def begin_decision(self, event_start: datetime) -> None:
        self._decision_reads = []
        self._decision_start = event_start

    def record_external_read(self, available_at: Optional[datetime]) -> None:
        if available_at is not None:
            self._record_read(available_at)

    def end_decision(self) -> None:
        self._decision_start = None

    @property
    def latest_read_at(self) -> Optional[datetime]:
        return max(self._decision_reads) if self._decision_reads else None

    def _record_read(self, at: datetime) -> None:
        if at.tzinfo is None:
            raise TimeLeakageError("feature read timestamp must be timezone-aware")
        at = at.astimezone(at.tzinfo)
        if self._decision_start is not None and at >= self._decision_start:
            raise TimeLeakageError(
                f"feature read at {at} is not strictly before decision event "
                f"start {self._decision_start}"
            )
        self._decision_reads.append(at)

    # ------------------------------------------------------------ ingestion

    def register_event(self, event: Dict[str, Any]) -> None:
        self.events[event["event_id"]] = event

    def add_result(self, event: Dict[str, Any], home_goals: int,
                   away_goals: int, available_at: datetime) -> None:
        for team, goal in ((event["home_team"], home_goals),
                           (event["away_team"], away_goals)):
            self.team_history.setdefault(team, []).append({
                "available_at": available_at,
                "event_id": event["event_id"],
                "group_order": event.get("group_order"),
                "start_utc": parse_utc(event["scheduled_start_utc"]),
                "opponent": (event["away_team"]
                             if team == event["home_team"]
                             else event["home_team"]),
                "home": team == event["home_team"],
                "goals": goal,
                "opponent_goals": (away_goals if team == event["home_team"]
                                   else home_goals),
            })

    def update_ratings(self, ratings: Dict[str, float],
                       available_at: datetime) -> None:
        for team, r in ratings.items():
            self.rating_updates.setdefault(team, []).append(
                {"available_at": available_at, "rating": r})

    # ---------------------------------------------------------------- reads

    def team_rating(self, team: str, at: datetime) -> Optional[float]:
        self._record_read(at)
        updates = [u for u in self.rating_updates.get(team, [])
                   if u["available_at"] <= at]
        if not updates:
            return None
        latest = max(updates, key=lambda u: u["available_at"])
        return latest["rating"]

    def last_result(self, team: str, at: datetime) -> Optional[Dict[str, Any]]:
        self._record_read(at)
        rows = [r for r in self.team_history.get(team, [])
                if r["available_at"] <= at]
        if not rows:
            return None
        return max(rows, key=lambda r: r["available_at"])

    def recent_form(self, team: str, at: datetime,
                    n: int = 3) -> List[Dict[str, Any]]:
        """The last ``n`` released matches for a team at time ``at``.

        Read-audited like every other feature read.  Rows carry the
        conventional football points (win 3 / draw 1 / loss 0) computed from
        the released scoreline only.  Newest first.
        """
        self._record_read(at)
        rows = [r for r in self.team_history.get(team, [])
                if r["available_at"] <= at]
        rows.sort(key=lambda r: (r["available_at"], r["event_id"]))
        out = []
        for r in reversed(rows[-n:]):
            g, og = r["goals"], r["opponent_goals"]
            pts = 3 if g > og else (1 if g == og else 0)
            out.append({**r, "points": pts})
        return out

    def goal_record(self, team: str, at: datetime) -> List[Dict[str, Any]]:
        """Every released match row for ``team`` at time ``at`` (oldest
        first): goals for / against, venue flag.  Read-audited."""
        self._record_read(at)
        rows = [r for r in self.team_history.get(team, [])
                if r["available_at"] <= at]
        rows.sort(key=lambda r: (r["available_at"], r["event_id"]))
        return rows

    def released_matches(self, at: datetime) -> List[Dict[str, Any]]:
        """Distinct released matches (one row per event) at time ``at``:
        {event_id, home_goals, away_goals, start_utc}.  Used for the
        walk-forward league scoring baseline; read-audited."""
        self._record_read(at)
        seen: Dict[str, Dict[str, Any]] = {}
        for team, rows in self.team_history.items():
            for r in rows:
                if r["available_at"] > at or r["event_id"] in seen:
                    continue
                hg = r["goals"] if r["home"] else r["opponent_goals"]
                ag = r["opponent_goals"] if r["home"] else r["goals"]
                seen[r["event_id"]] = {"event_id": r["event_id"],
                                       "home_goals": hg, "away_goals": ag,
                                       "start_utc": r["start_utc"]}
        return sorted(seen.values(),
                      key=lambda m: (m["start_utc"], m["event_id"]))

    def head_to_head(self, team_a: str, team_b: str, at: datetime
                     ) -> List[Dict[str, Any]]:
        self._record_read(at)
        return [r for r in self.team_history.get(team_a, [])
                if r["available_at"] <= at and r["opponent"] == team_b]

    def event(self, event_id: str, at: datetime) -> Dict[str, Any]:
        self._record_read(at)
        ev = self.events.get(event_id)
        if ev is None:
            raise TimeLeakageError(f"unknown event {event_id}")
        if parse_utc(ev["scheduled_start_utc"]) <= at:
            raise TimeLeakageError(
                f"event {event_id} start is not in the future of read time "
                f"{at}; refusing (post-start read)")
        return ev


class BacktestResult:
    def __init__(self):
        self.bets: List[Dict[str, Any]] = []
        self.skipped: List[Dict[str, Any]] = []
        self.leak_violations: List[str] = []


def run_walk_forward(store: Store, events: Sequence[Dict[str, Any]],
                     strategy: "Strategy", strategy_id: str,
                     stake: float = 1.0,
                     label: str = "",
                     allow_no_odds: bool = False) -> Dict[str, Any]:
    """Run a strategy walk-forward over finished events.

    ``events``: stored event dicts (scheduled_start_utc string) that are all
    finished. The strategy sees a TimeBoundedStore and must only read
    features at its declared cutoff.

    ``allow_no_odds``: when True (review-state sports without a permissioned
    odds path), decisions with a selection are stored as ``unsettleable``
    prediction-only tips instead of being skipped for a missing entry price.
    They are NEVER settled and NEVER contribute to PnL; grading happens via
    ``northstar.evaluation.prediction_accuracy``. When False, a decision
    without a stored pre-cutoff price is skipped exactly as before.
    """
    strategy_sport = getattr(strategy, "sport", None)
    # Market the strategy trades (default 1X2).  Only snapshots of that
    # market are offered as the market view / entry price, and the tip is
    # stored under it so settlement applies the matching rule set.
    market_key = getattr(strategy, "market", None) or MARKET_MATCH_WINNER_3WAY
    if market_key == MARKET_TOTALS_2_5:
        market_selections = ("over", "under")
    elif market_key == MARKET_ASIAN_HANDICAP:
        market_selections = ("home", "away")
    else:
        market_selections = ("home", "draw", "away")
    # Deterministic total order: same-start games (a whole hockey matchday
    # can share a puck-drop time) must not depend on input order - the
    # event_id tiebreak makes any shuffle of the input list equivalent.
    # Start-first (not group-first) because walk-forwards can now span
    # several competitions in one rating pool (darts 2025-26 events): a
    # group_order-first sort would process a November tournament's early
    # rounds before a July tournament's final, leaving chronologically
    # available ratings unregistered at read time (under-use, not leakage -
    # TimeBoundedStore still filters by availability - but it distorts the
    # pool). For single-competition pilots the two orders coincide because
    # matchday group_order is chronological with start time.
    ordered = sorted(events, key=lambda e: (e["scheduled_start_utc"],
                                            e.get("group_order") or 0,
                                            e["event_id"]))
    if strategy_sport:
        ordered = [e for e in ordered if e.get("sport") == strategy_sport]
    tbs = TimeBoundedStore()
    # Data contract: an event whose result is under review
    # (RESULT_KIND_INCONSISTENT - impossible layering or conflicting
    # duplicate entries) must neither update ratings nor be graded on;
    # the review queue owns its verdict, and a silent first-entry read
    # would launder a disputed source row into the model.
    flagged = {a["entity_id"] for a in store.anomalies(status="open")
               if a["kind"] == models.ANOMALY_RESULT_KIND_INCONSISTENT}
    for e in ordered:
        tbs.register_event(e)

    result = BacktestResult()
    store.upsert_entrant(strategy_id, strategy.name or strategy_id,
                         "strategy", strategy.description or label)

    for e in ordered:
        start = parse_utc(e["scheduled_start_utc"])
        if e["status"] != EVENT_STATUS_FINISHED:
            continue
        if e["event_id"] in flagged:
            result.skipped.append({
                "event_id": e["event_id"],
                "reason": "result flagged for review "
                          "(RESULT_KIND_INCONSISTENT)"})
            continue
        results = [r for r in store.results(e["event_id"])
                   if r["final_status"] == "finished"]
        if not results:
            result.skipped.append({"event_id": e["event_id"],
                                   "reason": "no finished result"})
            continue
        score_pairs = {(r["home_goals"], r["away_goals"]) for r in results}
        if len(score_pairs) != 1 or any(
                r["home_goals"] is None or r["away_goals"] is None
                for r in results):
            # A walk-forward must not use a disputed/correction-sensitive
            # result to update ratings.  Leave it in the review queue instead
            # of allowing the latest row to win by insertion order.
            result.skipped.append({"event_id": e["event_id"],
                                   "reason": "conflicting or incomplete result"})
            continue
        primary = max(results,
                      key=lambda r: parse_utc(r["officially_final_at_utc"]))

        # Market view the desk could see: earliest stored market_avg
        # snapshot strictly before start (same window for every strategy).
        # A line market (Asian handicap) additionally carries the priced
        # line; if the stored snapshots disagree on the line the view is
        # withheld (a desk must never guess which line it traded).
        market_odds = None
        odds_observed_at = None
        snaps = [s for s in store.odds_snapshots(e["event_id"])
                 if s["provider"] == "market_avg"
                 and s["market_key"] == market_key
                 and parse_utc(s["observed_at_utc"]) < start]
        market_line = None
        if snaps:
            first = min(snaps, key=lambda s: s["observed_at_utc"])
            first_at = parse_utc(first["observed_at_utc"])
            odds_observed_at = first_at
            market_odds = {
                sel: next((s["decimal_odds"] for s in snaps
                           if s["selection_key"] == sel
                           and parse_utc(s["observed_at_utc"]) <= first_at),
                          None)
                for sel in market_selections}
            if market_key == MARKET_ASIAN_HANDICAP:
                lines = {s.get("line") for s in snaps
                         if parse_utc(s["observed_at_utc"]) <= first_at}
                if len(lines) == 1 and None not in lines:
                    market_line = next(iter(lines))
                    market_odds["line"] = market_line
                else:
                    market_odds = None
        else:
            market_odds = None

        # Strategy declares its cutoff (the latest time any input it used
        # became available) and reads features only at/before that.  The
        # market snapshot is itself an input, even if the strategy does not
        # call a TimeBoundedStore method.
        #
        # ENGINE FIX (2026-09-20): every finished event with a consistent
        # stored result now RELEASES that result to the feature timeline,
        # whether the strategy bet, passed, or violated the cutoff rules.
        # Previously a "strategy passed" decision skipped the release,
        # which froze rating-based strategies at their last *bet* match and
        # starved history-based features.  That is wrong walk-forward
        # semantics (the match happened; a real desk observes it) and it
        # silently distorted the pilot's Elo desks - all pilot numbers in
        # docs/site are regenerated from the fixed engine.
        tbs.begin_decision(start)
        tbs.record_external_read(odds_observed_at)
        decision = None
        cutoff = None
        try:
            decision = strategy.predict(e, tbs, start,
                                        market_odds=market_odds,
                                        odds_observed_at=odds_observed_at)
        except TimeLeakageError as exc:
            result.leak_violations.append(
                f"{strategy_id}: {exc} for {e['event_id']}")
        if decision is not None:
            cutoff = decision.get("cutoff_utc")
            if cutoff is not None:
                if not isinstance(cutoff, datetime) or cutoff.tzinfo is None:
                    result.leak_violations.append(
                        f"{strategy_id}: cutoff must be timezone-aware "
                        f"datetime for {e['event_id']}"
                    )
                    decision = None
                else:
                    cutoff = cutoff.astimezone(timezone.utc)
        if decision is not None:
            latest_read = tbs.latest_read_at
            if latest_read is not None and (cutoff is None
                                            or latest_read > cutoff):
                result.leak_violations.append(
                    f"{strategy_id}: read at {latest_read} exceeds declared "
                    f"cutoff {cutoff} for {e['event_id']}"
                )
                decision = None
        if decision is not None and cutoff is not None and cutoff >= start:
            result.leak_violations.append(
                f"{strategy_id}: cutoff {cutoff} not before start {start} "
                f"for {e['event_id']}"
            )
            decision = None
        if decision is not None and (
                not decision.get("selection_key")
                or decision["selection_key"] == "none"):
            result.skipped.append({"event_id": e["event_id"],
                                   "reason": "strategy passed",
                                   "model": decision.get("model", {})})
            decision = None
        if decision is not None and cutoff is None:
            result.leak_violations.append(
                f"{strategy_id}: bet has no cutoff for {e['event_id']}")
            decision = None

        if decision is not None:
            # Entry price: earliest stored snapshot at/before cutoff (the
            # price the desk actually saw) - never a later 'better' price.
            # A line market additionally pins the snapshot's line to the
            # line the desk declared (a re-quoted line is a different bet).
            odds = None
            provider = None
            prediction_only = False
            provider_key = decision.get(
                "odds_provider",
                getattr(strategy, "odds_provider", "market_avg"))
            if provider_key:
                snaps = [s for s in store.odds_snapshots(e["event_id"])
                         if s["provider"] == provider_key
                         and s["market_key"] == market_key
                         and s["selection_key"] == decision["selection_key"]
                         and parse_utc(s["observed_at_utc"]) <= cutoff]
                if market_key == MARKET_ASIAN_HANDICAP:
                    snaps = [s for s in snaps
                             if s.get("line") == decision.get("line")]
                if snaps:
                    snap = min(snaps, key=lambda s: s["observed_at_utc"])
                    odds = snap["decimal_odds"]
                    provider = snap["provider"]
                elif allow_no_odds:
                    prediction_only = True
                else:
                    # No price stored for this selection/cutoff: we cannot
                    # settle a bet that never had an observable entry price.
                    result.skipped.append({
                        "event_id": e["event_id"],
                        "reason": "no pre-cutoff odds",
                        "selection": decision["selection_key"]})
                    decision = None
            elif allow_no_odds:
                prediction_only = True
            else:
                result.skipped.append({
                    "event_id": e["event_id"],
                    "reason": "strategy declares no odds provider and none "
                              "is permitted",
                    "selection": decision["selection_key"]})
                decision = None

        if decision is not None:
            tip_id = stable_id("bt-tip", strategy_id, e["event_id"])
            tip = Tip(
                tip_id=tip_id,
                tipster_id=strategy_id,
                strategy_id=strategy_id,
                event_id=e["event_id"],
                market=market_key,
                selection=decision.get("selection_text",
                                       decision["selection_key"]),
                selection_key=decision["selection_key"],
                published_at_utc=cutoff,
                collected_at_utc=utcnow(),
                cutoff_at_utc=cutoff,
                odds_decimal=odds,
                odds_source=provider,
                stake_units=stake,
                line=decision.get("line"),
                source_url=e.get("source_url"),
                raw_payload_hash=None,
                status=(TIP_STATUS_UNSETTLEABLE if prediction_only
                        else TIP_STATUS_OPEN),
                notes=((f"prediction-only walk-forward {label}: no "
                        "permissioned odds path for this sport; PnL not "
                        "computable and not zero").strip()
                       if prediction_only
                       else f"walk-forward backtest {label}".strip()),
            )
            store.add_tip(tip)
            decision_log = {
                "event_id": e["event_id"],
                "selection": decision["selection_key"],
                "odds": odds,
                "cutoff": models.fmt_utc(cutoff),
                "model": decision.get("model", {}),
                "strategy": strategy_id,
            }
            if prediction_only:
                outcome = {"action": "prediction_only",
                           "settlement_id": None}
            else:
                outcome = settle_tip(store, tip_id)
            result.bets.append({**decision_log,
                                "outcome_action": outcome["action"],
                                "settlement_id": outcome.get("settlement_id")})

        # Release this event's result to the feature store AFTER the
        # decision window closes - for EVERY decided event (bet, pass or
        # violation; see ENGINE FIX above).  The post-result rating update
        # may read the final timestamp; it is outside the audit window.
        tbs.end_decision()
        final_at = parse_utc(primary["officially_final_at_utc"])
        tbs.add_result(e, primary["home_goals"], primary["away_goals"],
                       available_at=final_at)
        ratings = strategy.ratings_after(e, primary["home_goals"],
                                         primary["away_goals"], tbs,
                                         final_at)
        if ratings:
            tbs.update_ratings(ratings, available_at=final_at)

    store.commit()
    return {
        "strategy_id": strategy_id,
        "label": label,
        "bets": result.bets,
        "skipped": result.skipped,
        "leak_violations": result.leak_violations,
        "n_settled": len(result.bets),
    }


def bootstrap_ci(pnl_sequence: Sequence[float], n_resamples: int = 2000,
                 seed: int = 12345, ci: float = 0.95) -> Dict[str, float]:
    """Plain bootstrap CI on per-bet PnL (deterministic seed)."""
    import random
    if not pnl_sequence:
        return {"mean": 0.0, "lo": 0.0, "hi": 0.0, "n": 0}
    rng = random.Random(seed)
    n = len(pnl_sequence)
    totals = []
    for _ in range(n_resamples):
        sample = [pnl_sequence[rng.randrange(n)] for _ in range(n)]
        totals.append(sum(sample))
    totals.sort()
    lo_i = int((1 - ci) / 2 * n_resamples)
    hi_i = int((1 + ci) / 2 * n_resamples) - 1
    return {"mean": sum(pnl_sequence) / n,
            "lo": totals[lo_i] / n,
            "hi": totals[hi_i] / n,
            "n": n}


from .strategies.base import Strategy  # noqa: E402
