"""Forward-desk history warm-up + outcome-mode grading.

Offline. Guarantees:
- finished past-season events warm the rating pool and are released at
  their own stored availability time (leak-safe, audited);
- a history event whose start is at/after the desk's as_of is a data bug
  and is refused loudly (never silently used or dropped);
- unfinished and flagged history events are excluded;
- issued ledger entries carry the desk's outcome mode; the grader resolves
  regulation 3-way calls through the final-row kind (an OT/SO final means
  regulation draw = a hit) and legacy entries without the key grade the
  final exactly as before;
- the cli history selector picks finished earlier-season events by the
  per-match source URL only.
"""
from __future__ import annotations

import json

import pytest

from northstar import cli, models
from northstar.adapters import openligadb
from northstar.forward import grade_forward, issue_forward, load_ledger
from northstar.models import parse_utc

AS_OF = "2026-01-08T06:00:00Z"


def _match(mid, season, day, start, t1, t2, finished, r1=None, r2=None,
           updated=None, r2_conflict=None, kind="After90Minutes"):
    """Same schema as the live OpenLigaDB payloads (adapter-read fields)."""
    results = []
    if r1 is not None:
        results.append({
            "resultID": mid * 10, "resultName": "Endergebnis",
            "pointsTeam1": r1, "pointsTeam2": r2, "resultOrderID": 2,
            "resultTypeID": 2, "resultTypeKind": kind,
            "resultDescription": "final"})
    if r2_conflict is not None:
        results.append({
            "resultID": mid * 10 + 1, "resultName": "Endergebnis",
            "pointsTeam1": r1, "pointsTeam2": r2_conflict, "resultOrderID": 3,
            "resultTypeID": 2, "resultTypeKind": kind,
            "resultDescription": "final (stale duplicate)"})
    return {
        "matchID": mid,
        "matchDateTime": start,
        "timeZoneID": None,
        "leagueId": 9999,
        "leagueName": f"Test Liga {season}/{str(season + 1)[2:]}",
        "leagueSeason": season,
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
        "matchResults": results,
        "goals": [], "location": None, "numberOfViewers": None,
    }


def _history_payload() -> str:
    """Two finished bl1/2025 matches (same clubs, earlier season).

    Dates are deliberately DISJOINT from the current-season payload:
    same-instant release timestamps would tie in the rating chain.
    """
    return json.dumps([
        _match(8001, 2025, 1, "2025-12-10T15:00:00Z", (11, "FC Strong"),
               (22, "FC Weak"), True, 3, 0, "2025-12-10T17:30:00"),
        _match(8002, 2025, 2, "2025-12-14T15:00:00Z", (22, "FC Weak"),
               (11, "FC Strong"), True, 0, 2, "2025-12-14T17:30:00"),
    ])


def _current_payload() -> str:
    return json.dumps([
        _match(9001, 2026, 1, "2026-01-03T15:00:00Z", (11, "FC Strong"),
               (22, "FC Weak"), True, 3, 0, "2026-01-03T17:30:00"),
        _match(9002, 2026, 2, "2026-01-06T15:00:00Z", (22, "FC Weak"),
               (11, "FC Strong"), True, 0, 2, "2026-01-06T17:30:00"),
        _match(9003, 2026, 3, "2026-01-10T15:00:00Z", (11, "FC Strong"),
               (22, "FC Weak"), False),
    ])


def _issue(store, events, history, tmp_path, label="t"):
    ledger = load_ledger(str(tmp_path / "ledger.json"))
    as_of = parse_utc(AS_OF)
    stats = issue_forward(store, events, as_of, ["elo-favourite-3way-v1"],
                          ledger, label=label, history_events=history)
    return stats, ledger


class TestHistoryWakeup:
    def test_history_moves_cold_ratings(self, store, tmp_path):
        as_of = parse_utc(AS_OF)
        hist = openligadb.ingest_matchday(
            store, _history_payload(), sport="football", as_of=as_of)
        cur = openligadb.ingest_matchday(store, _current_payload(),
                                         sport="football", as_of=as_of)
        events = [store.get_event(eid) for eid in cur["event_ids"]]
        history = [store.get_event(eid) for eid in hist["event_ids"]]
        stats, ledger = _issue(store, events, history, tmp_path, "warm")
        assert stats["leak_violations"] == []
        assert stats["history_released"] == 2
        assert stats["issued"] == 1

        # cold run: same data minus the history
        s2 = type(store)(str(tmp_path / "cold.db"))
        cur2 = openligadb.ingest_matchday(s2, _current_payload(),
                                          sport="football", as_of=as_of)
        events2 = [s2.get_event(eid) for eid in cur2["event_ids"]]
        _, ledger2 = _issue(s2, events2, [], tmp_path, "cold")
        assert ledger2["issued"][0]["prediction_id"] == \
            ledger["issued"][0]["prediction_id"]
        warm_p = ledger["issued"][0]["model"]["model_prob"]
        cold_p = ledger2["issued"][0]["model"]["model_prob"]
        # 4 wins in the pool vs 2: the warmed desk favours home MORE
        assert warm_p["home"] > cold_p["home"]
        # the entry carries the desk's outcome mode
        assert ledger["issued"][0]["outcome"] == "final"
        s2.close()

    def test_history_starting_after_as_of_refused(self, store, tmp_path):
        as_of = parse_utc(AS_OF)
        bad = _match(8101, 2025, 1, "2026-01-20T15:00:00Z",  # starts AFTER
                     (11, "FC Strong"), (22, "FC Weak"), True, 1, 0,
                     "2026-01-20T17:30:00")
        out = openligadb.ingest_matchday(
            store, json.dumps([bad]), sport="football", as_of=as_of)
        assert store.get_event(out["event_ids"][0])["status"] == \
            models.EVENT_STATUS_FINISHED
        cur = openligadb.ingest_matchday(store, _current_payload(),
                                         sport="football", as_of=as_of)
        events = [store.get_event(eid) for eid in cur["event_ids"]]
        history = [store.get_event(out["event_ids"][0])]
        with pytest.raises(ValueError, match="starts at/after as_of"):
            _issue(store, events, history, tmp_path, "bad")

    def test_unfinished_history_skipped_silently(self, store, tmp_path):
        as_of = parse_utc(AS_OF)
        hist = openligadb.ingest_matchday(
            store, _history_payload(), sport="football", as_of=as_of)
        hist_ids = hist["event_ids"]
        # an unfinished earlier-season match (review-queue material)
        unfin = _match(8003, 2025, 3, "2026-01-05T15:00:00Z",
                       (11, "FC Strong"), (22, "FC Weak"), False)
        out3 = openligadb.ingest_matchday(
            store, json.dumps([unfin]), sport="football", as_of=as_of)
        cur = openligadb.ingest_matchday(store, _current_payload(),
                                         sport="football", as_of=as_of)
        events = [store.get_event(eid) for eid in cur["event_ids"]]
        history = [store.get_event(eid) for eid in hist_ids] + \
            [store.get_event(out3["event_ids"][0])]
        stats, ledger = _issue(store, events, history, tmp_path, "mix")
        assert stats["leak_violations"] == []
        assert stats["history_released"] == 2  # only the finished ones


class TestHistorySelector:
    def _store(self, store):
        as_of = parse_utc(AS_OF)
        hist_ids = openligadb.ingest_matchday(
            store, _history_payload(), sport="football", as_of=as_of
        )["event_ids"]
        cur = openligadb.ingest_matchday(store, _current_payload(),
                                         sport="football", as_of=as_of)
        # a flagged earlier-season event (conflicting duplicate scores)
        flagged = _match(8201, 2025, 4, "2026-01-04T15:00:00Z",
                         (11, "FC Strong"), (22, "FC Weak"), True, 2, 0,
                         "2026-01-04T17:30:00", r2_conflict=1)
        outf = openligadb.ingest_matchday(
            store, json.dumps([flagged]), sport="football", as_of=as_of)
        return (hist_ids, cur,
                [outf["event_ids"][0]] if outf["event_ids"] else [])

    def test_selector_picks_finished_earlier_season_only(self, store):
        hist_ids, cur, _ = self._store(store)
        group = {"shortcut": "bl1", "season": 2026, "sport": "football"}
        current_ids = {eid for eid in cur["event_ids"]}
        out = cli._history_events_for_group(store, group, current_ids)
        assert {e["event_id"] for e in out} == set(hist_ids)
        assert all(e["status"] == models.EVENT_STATUS_FINISHED for e in out)

    def test_selector_excludes_flagged_events(self, store):
        hist_ids, cur, flagged_ids = self._store(store)
        group = {"shortcut": "bl1", "season": 2026, "sport": "football"}
        current_ids = {eid for eid in cur["event_ids"]}
        out = cli._history_events_for_group(store, group, current_ids)
        assert not (set(flagged_ids) & {e["event_id"] for e in out})

    def test_selector_requires_shortcut_season(self, store):
        self._store(store)
        assert cli._history_events_for_group(
            store, {"shortcut": None, "season": 2026, "sport": "football"},
            set()) == []
        assert cli._history_events_for_group(
            store, {"shortcut": "bl1", "season": None, "sport": "football"},
            set()) == []


class TestRegDeskMarketStamp:
    def test_reg_entries_carry_the_regulation_market(self, store,
                                                    tmp_path):
        as_of = parse_utc(AS_OF)
        payload = json.dumps([
            _match(7101, 2026, 1, "2026-01-05T18:00:00Z", (1, "Ice A"),
                   (2, "Ice B"), True, 2, 1, "2026-01-05T22:00:00"),
            _match(7102, 2026, 2, "2026-01-10T18:00:00Z", (1, "Ice A"),
                   (2, "Ice B"), False),
        ])
        out = openligadb.ingest_matchday(store, payload,
                                         sport="ice_hockey", as_of=as_of)
        events = [store.get_event(eid) for eid in out["event_ids"]]
        ledger = load_ledger(str(tmp_path / "l.json"))
        stats = issue_forward(store, events, as_of,
                              ["hockey-reg-poisson-v1", "hockey-reg-home-v1",
                               "hockey-elo-v1"], ledger, label="reg-mkt")
        assert stats["leak_violations"] == []
        assert stats["issued"] == 3
        by_sid = {e["strategy_id"]: e for e in ledger["issued"]}
        for sid in ("hockey-reg-poisson-v1", "hockey-reg-home-v1"):
            entry = by_sid[sid]
            assert entry["market"] == models.MARKET_REGULATION_3WAY
            assert entry["outcome"] == "regulation_3way"
        # the 2-way final desks keep the final market
        assert by_sid["hockey-elo-v1"]["market"] == \
            models.MARKET_MATCH_WINNER_2WAY
        assert by_sid["hockey-elo-v1"]["outcome"] == "final"


class TestOutcomeModeGrading:
    def _reg_store(self, store):
        as_of = parse_utc(AS_OF)
        m = _match(7001, 2026, 1, "2026-01-05T18:00:00Z", (1, "Ice A"),
                   (2, "Ice B"), True, 3, 4, "2026-01-05T22:00:00",
                   kind="AfterExtraTime")
        out = openligadb.ingest_matchday(
            store, json.dumps([m]), sport="ice_hockey", as_of=as_of)
        return out["event_ids"][0]

    def _entry(self, eid, start, selection, outcome, prob3=True):
        return {
            "prediction_id": "fwd-test-" + selection,
            "strategy_id": ("hockey-reg-poisson-v1"
                            if outcome else "hockey-elo-v1"),
            "strategy_name": "test desk", "sport": "ice_hockey",
            "event_id": eid, "source_event_id": "7001",
            "competition": "Test Liga", "event": "Ice A v Ice B",
            "home_team": "Ice A", "away_team": "Ice B",
            "start_utc": start, "group_order": 1, "group_name": "1",
            "issued_at_utc": "2026-01-01T00:00:00Z",
            "cutoff_utc": "2026-01-01T00:00:00Z",
            "selection": selection, "selection_key": selection,
            "market": "1X2", "model": {"model_version": "test",
                                       "model_prob": ({
                                           "home": 0.30, "draw": 0.40,
                                           "away": 0.30}
                                          if prob3 else
                                          {"home": 0.60, "away": 0.40}),
                                       "rating_trail": []},
            "model_version": "test", "source_url": "https://example.org",
            "label": "t", "odds": None, "odds_note": "test",
            "outcome": outcome,
        }

    def test_regulation_draw_call_hits_on_lost_ot_game(self, store):
        eid = self._reg_store(store)
        entry = self._entry(eid, "2026-01-05T18:00:00Z", "draw",
                            "regulation_3way")
        report = grade_forward(store, {"issued": [entry]},
                               parse_utc(AS_OF))
        row = report["rows"][0]
        assert row["status"] == "graded"
        assert row["outcome_mode"] == "regulation_3way"
        assert row["actual"] == "draw"  # regulation draw, not the 3-4
        assert row["hit"] is True
        assert "regulation draw" in row["result"]
        assert report["n_graded"] == 1

    def test_legacy_entry_without_outcome_key_grades_final(self, store):
        eid = self._reg_store(store)
        entry = self._entry(eid, "2026-01-05T18:00:00Z", "home",
                            outcome=None, prob3=False)
        del entry["outcome"]  # legacy entry shape
        report = grade_forward(store, {"issued": [entry]},
                               parse_utc(AS_OF))
        row = report["rows"][0]
        assert row["status"] == "graded"
        assert row["outcome_mode"] == "final"
        assert row["actual"] == "away"  # final is 3-4
        assert row["hit"] is False
        assert row["result"] == "3-4"

    def test_awaiting_result_for_upcoming_call(self, store):
        eid = self._reg_store(store)
        # a second, upcoming event of the same sport
        m = _match(7002, 2026, 2, "2026-01-15T18:00:00Z", (1, "Ice A"),
                   (2, "Ice B"), False)
        out2 = openligadb.ingest_matchday(
            store, json.dumps([m]), sport="ice_hockey",
            as_of=parse_utc(AS_OF))
        entry = self._entry(out2["event_ids"][0], "2026-01-15T18:00:00Z",
                            "draw", "regulation_3way")
        report = grade_forward(store, {"issued": [entry]},
                               parse_utc(AS_OF))
        row = report["rows"][0]
        assert row["status"] == "awaiting_result"
        assert report["n_awaiting"] == 1
        # the resolved OT/SO game still grades correctly in the same batch
        done = self._entry(eid, "2026-01-05T18:00:00Z", "draw",
                           "regulation_3way")
        report = grade_forward(store, {"issued": [entry, done]},
                               parse_utc(AS_OF))
        assert report["n_graded"] == 1
        assert report["n_awaiting"] == 1
