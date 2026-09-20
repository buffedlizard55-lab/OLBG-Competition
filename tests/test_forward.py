"""Forward-test engine: append-only ledger, cutoff discipline, grading.

The forward test is the user-requested protocol for sports/seasons where a
backtest on verified official outcomes is not (yet) available: freeze
predictions before the start, grade them when results arrive, never invent
PnL without a permissioned price.
"""
from __future__ import annotations

import json

import pytest

from northstar import models
from northstar.adapters import openligadb
from northstar.forward import (
    grade_forward, issue_forward, load_ledger, save_ledger,
)
from northstar.leaderboard import upcoming_bets
from northstar.models import Event, parse_utc
from northstar.predictor import render_forward_prediction

from conftest import mk_result

AS_OF = "2026-01-08T06:00:00Z"


def _payload():
    """Synthetic current-season capture: 2 finished + 1 upcoming fixture.

    Same schema as the live OpenLigaDB payloads (fields the adapter reads).
    """
    def match(mid, day, start, t1, t2, finished, r1=None, r2=None,
              updated=None):
        m = {
            "matchID": mid,
            "matchDateTime": start,
            "timeZoneID": None,
            "leagueId": 9999,
            "leagueName": "Test Liga 2026/2027",
            "leagueSeason": 2026,
            "leagueShortcut": "bl1",
            "matchDateTimeUTC": start,
            "group": {"groupName": f"{day}. Spieltag", "groupOrderID": day,
                      "groupID": 5000 + day},
            "team1": {"teamId": t1[0], "teamName": t1[1], "shortName": None,
                      "teamIconUrl": None, "teamGroupName": None},
            "team2": {"teamId": t2[0], "teamName": t2[1], "shortName": None,
                      "teamIconUrl": None, "teamGroupName": None},
            "lastUpdateDateTime": updated,
            "matchIsFinished": finished,
            "matchResults": ([] if r1 is None else [{
                "resultID": mid * 10, "resultName": "Endergebnis",
                "pointsTeam1": r1, "pointsTeam2": r2, "resultOrderID": 2,
                "resultTypeID": 2, "resultTypeKind": "After90Minutes",
                "resultDescription": "final"}]),
            "goals": [], "location": None, "numberOfViewers": None,
        }
        return m

    return json.dumps([
        match(9001, 1, "2026-01-03T15:00:00Z", (11, "FC Strong"),
              (22, "FC Weak"), True, 3, 0, "2026-01-03T17:30:00"),
        match(9002, 2, "2026-01-06T15:00:00Z", (22, "FC Weak"),
              (11, "FC Strong"), True, 0, 2, "2026-01-06T17:30:00"),
        match(9003, 3, "2026-01-10T15:00:00Z", (11, "FC Strong"),
              (22, "FC Weak"), False),
    ])


@pytest.fixture()
def current(store, tmp_path):
    as_of = parse_utc(AS_OF)
    out = openligadb.ingest_matchday(store, _payload(), verify_identity=True,
                                     sport="football", as_of=as_of)
    events = [store.get_event(eid) for eid in out["event_ids"]]
    ledger_path = str(tmp_path / "ledger.json")
    ledger = load_ledger(ledger_path)
    return {"store": store, "events": events, "as_of": as_of,
            "ledger": ledger, "ledger_path": ledger_path,
            "ingest": out}


class TestIngestAsOf:
    def test_future_unfinished_is_scheduled_not_postponed(self, current):
        by_status = {e["status"] for e in current["events"]}
        scheduled = [e for e in current["events"]
                     if e["status"] == models.EVENT_STATUS_SCHEDULED]
        assert models.EVENT_STATUS_SCHEDULED in by_status
        assert len(scheduled) == 1
        assert scheduled[0]["source_event_id"] == "9003"

    def test_no_as_of_keeps_postponed_behaviour(self, store):
        out = openligadb.ingest_matchday(store, _payload(),
                                         sport="football")  # no as_of
        statuses = {store.get_event(eid)["status"]
                    for eid in out["event_ids"]}
        assert models.EVENT_STATUS_POSTPONED in statuses
        assert models.EVENT_STATUS_SCHEDULED not in statuses

    def test_naive_as_of_refused(self, store):
        from datetime import datetime
        with pytest.raises(ValueError):
            openligadb.ingest_matchday(store, _payload(), sport="football",
                                       as_of=datetime(2026, 1, 8))


class TestIssueForward:
    def test_issues_one_frozen_prediction_per_fixture(self, current):
        store, ledger = current["store"], current["ledger"]
        stats = issue_forward(store, current["events"], current["as_of"],
                              ["elo-favourite-3way-v1"], ledger,
                              label="bl1-2026")
        assert stats["issued"] == 1
        assert stats["leak_violations"] == []
        entry = ledger["issued"][0]
        assert entry["strategy_id"] == "elo-favourite-3way-v1"
        assert entry["start_utc"] == "2026-01-10T15:00:00Z"
        assert entry["cutoff_utc"] == AS_OF
        assert entry["issued_at_utc"] == AS_OF
        # Ratings evolved from BOTH finished matches (engine release fix),
        # so the clear favourite is selected with a real model trail.
        assert entry["selection_key"] == "home"
        assert entry["model"]["model_prob"]["home"] >= 0.45
        assert entry["model"]["ratings"]["home"] > 1500.0
        assert entry["odds"] is None

    def test_tip_mirror_is_unsettleable_and_never_settles(self, current):
        store, ledger = current["store"], current["ledger"]
        issue_forward(store, current["events"], current["as_of"],
                      ["elo-favourite-3way-v1"], ledger)
        tips = store.tips(tipster_id="fwd-elo-favourite-3way-v1")
        assert len(tips) == 1
        tip = tips[0]
        assert tip["status"] == models.TIP_STATUS_UNSETTLEABLE
        assert tip["odds_decimal"] is None
        assert parse_utc(tip["cutoff_at_utc"]) < \
            parse_utc("2026-01-10T15:00:00Z")
        assert store.all_settlements() == []
        assert "forward test" in tip["notes"]

    def test_rerun_is_idempotent_and_never_reissues(self, current):
        store, ledger = current["store"], current["ledger"]
        issue_forward(store, current["events"], current["as_of"],
                      ["elo-favourite-3way-v1"], ledger, label="bl1-2026")
        first = json.dumps(ledger["issued"], sort_keys=True)
        stats = issue_forward(store, current["events"], current["as_of"],
                              ["elo-favourite-3way-v1"], ledger,
                              label="bl1-2026")
        assert stats["issued"] == 0
        assert stats["already_ledgered"] == 1
        assert json.dumps(ledger["issued"], sort_keys=True) == first

    def test_started_events_are_never_issued(self, store, tmp_path):
        as_of_late = parse_utc("2026-01-10T16:00:00Z")  # after kickoff
        out = openligadb.ingest_matchday(store, _payload(),
                                         sport="football", as_of=as_of_late)
        events = [store.get_event(eid) for eid in out["event_ids"]]
        ledger = load_ledger(str(tmp_path / "l.json"))
        stats = issue_forward(store, events, as_of_late,
                              ["elo-favourite-3way-v1"], ledger)
        assert stats["issued"] == 0
        assert ledger["issued"] == []

    def test_ledger_file_roundtrip_and_no_rewrite_when_unchanged(
            self, current):
        ledger = current["ledger"]
        path = current["ledger_path"]
        issue_forward(current["store"], current["events"], current["as_of"],
                      ["elo-favourite-3way-v1"], ledger)
        assert save_ledger(path, ledger) is True
        reloaded = load_ledger(path)
        assert reloaded["issued"] == ledger["issued"]
        assert save_ledger(path, reloaded) is False  # byte-identical

    def test_events_beyond_the_horizon_are_not_issued(self, store, tmp_path):
        # A fixture 40 days after the capture stays out of the ledger until
        # a later capture brings it inside the horizon (no months-frozen
        # calls from stale ratings).
        import json as _json
        payload = _json.loads(_payload())
        payload[2]["matchDateTimeUTC"] = "2026-02-20T15:00:00Z"
        payload[2]["matchDateTime"] = "2026-02-20T15:00:00Z"
        as_of = parse_utc(AS_OF)
        out = openligadb.ingest_matchday(store, _json.dumps(payload),
                                         sport="football", as_of=as_of)
        events = [store.get_event(eid) for eid in out["event_ids"]]
        ledger = load_ledger(str(tmp_path / "l.json"))
        stats = issue_forward(store, events, as_of,
                              ["elo-favourite-3way-v1"], ledger)
        assert stats["issued"] == 0
        assert stats["out_of_horizon"] == 1
        assert ledger["issued"] == []

    def test_ledger_version_guard(self, tmp_path):
        p = tmp_path / "bad.json"
        p.write_text(json.dumps({"version": "other", "issued": []}))
        with pytest.raises(ValueError):
            load_ledger(str(p))


class TestGradeForward:
    def _issue(self, current):
        issue_forward(current["store"], current["events"], current["as_of"],
                      ["elo-favourite-3way-v1"], current["ledger"],
                      label="bl1-2026")
        return current["ledger"]["issued"][0]

    def test_awaiting_then_graded_when_result_arrives(self, current):
        store = current["store"]
        entry = self._issue(current)
        rep = grade_forward(store, current["ledger"],
                            latest_as_of=current["as_of"])
        assert rep["n_awaiting"] == 1 and rep["n_graded"] == 0
        assert rep["desks"]["elo-favourite-3way-v1"]["accuracy"] is None

        # Simulate the next committed capture: the fixture finished 2-0
        # (a normal lifecycle transition - must NOT raise an anomaly).
        ev = store.get_event(entry["event_id"])
        n_anoms_before = len(store.anomalies())
        store.upsert_event(Event(
            **{**ev,
               "scheduled_start_utc": parse_utc(ev["scheduled_start_utc"]),
               "status": models.EVENT_STATUS_FINISHED}))
        assert len(store.anomalies()) == n_anoms_before
        mk_result(store, event_id=entry["event_id"], home_goals=2,
                  away_goals=0, final_at="2026-01-10T17:30:00Z")
        rep = grade_forward(store, current["ledger"],
                            latest_as_of=parse_utc("2026-01-12T06:00:00Z"))
        assert rep["n_graded"] == 1
        row = rep["graded"][0]
        assert row["hit"] is True
        assert row["result"] == "2-0"
        assert row["brier"] is not None and 0 <= row["brier"] <= 2
        d = rep["desks"]["elo-favourite-3way-v1"]
        assert d["accuracy"] == 1.0
        # The ledger entry itself is untouched (append-only guarantee)
        assert current["ledger"]["issued"][0] == entry

    def test_overdue_when_grace_passes_without_result(self, current):
        self._issue(current)
        rep = grade_forward(current["store"], current["ledger"],
                            latest_as_of=parse_utc("2026-02-01T00:00:00Z"))
        assert rep["n_overdue"] == 1
        assert rep["overdue"][0]["status"] == "overdue"

    def test_grading_never_creates_settlements_or_pnl(self, current):
        self._issue(current)
        grade_forward(current["store"], current["ledger"],
                      latest_as_of=current["as_of"])
        assert current["store"].all_settlements() == []

    def test_render_forward_prediction_is_evidence_only(self, current):
        self._issue(current)
        rep = grade_forward(current["store"], current["ledger"],
                            latest_as_of=current["as_of"])
        row = rep["awaiting"][0]
        out = render_forward_prediction(row, source_links=[row["source_url"]])
        assert out["evidence_ok"] is True
        assert "no market price" in out["body"].lower() or \
               "No market price" in out["body"]
        assert "accuracy" in out["body"]
        assert out["headline"].startswith("FC Strong v FC Weak")

    def test_render_refuses_incomplete_trail(self, current):
        self._issue(current)
        row = dict(current["ledger"]["issued"][0])
        row["model"] = {}
        out = render_forward_prediction(row)
        assert out["evidence_ok"] is False
        assert "refusing" in out["body"]


class TestUpcomingInclusion:
    def test_forward_tips_show_as_upcoming(self, current):
        store = current["store"]
        issue_forward(store, current["events"], current["as_of"],
                      ["elo-favourite-3way-v1"], current["ledger"])
        up = upcoming_bets(store, now=parse_utc(AS_OF))
        fwd = [b for b in up if b["entrant"] == "fwd-elo-favourite-3way-v1"]
        assert len(fwd) == 1
        assert fwd[0]["status"] == models.TIP_STATUS_UNSETTLEABLE
        assert fwd[0]["sport"] == "football"
        # After the event started, it is no longer "upcoming"
        up_later = upcoming_bets(store, now=parse_utc(
            "2026-01-11T00:00:00Z"))
        assert all(b["entrant"] != "fwd-elo-favourite-3way-v1"
                   for b in up_later)
