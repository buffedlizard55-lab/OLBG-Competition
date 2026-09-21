"""OLBG-snapshot vs OpenLigaDB fixture reconciliation."""
from __future__ import annotations

from northstar.reconcile import reconcile_olbg_events

from conftest import mk_event


def _olbg(store, eid, home, away, start):
    from northstar.models import Event, parse_utc
    store.upsert_event(Event(
        event_id=eid, sport="football", competition="England Premier League",
        home_team_id="olbg-home", home_team=home, away_team_id="olbg-away",
        away_team=away, scheduled_start_utc=parse_utc(start),
        status="scheduled", identity_confidence="unmatched",
        source_provider="olbg", source_url="https://www.olbg.com/x",
        source_version="v1"))
    store.commit()


def _official(store, eid, home, away, start):
    from northstar.models import Event, parse_utc
    store.upsert_event(Event(
        event_id=eid, sport="football", competition="Premier League 2026/2027",
        home_team_id="1", home_team=home, away_team_id="2", away_team=away,
        scheduled_start_utc=parse_utc(start), status="scheduled",
        identity_confidence="probable", source_provider="openligadb",
        source_url="https://api.openligadb.de/getmatchdata/pl/2026/1",
        source_version="v1"))
    store.commit()


class TestReconcile:
    def test_alias_match_with_time_conflict_is_flagged_not_edited(self, store):
        _olbg(store, "ev-olbg-1", "Man City", "Sunderland",
              "2026-09-20T08:00:00Z")
        _official(store, "ev-off-1", "Manchester City", "Sunderland",
                  "2026-09-20T13:00:00Z")
        out = reconcile_olbg_events(store)
        assert out["matched"] == 1 and out["time_conflicts"] == 1
        row = out["rows"][0]
        assert row["status"] == "time_conflict"
        assert row["delta_hours"] == 5.0
        assert row["official_event_id"] == "ev-off-1"
        kinds = [a["kind"] for a in store.anomalies()]
        assert kinds.count("TIME_CONFLICT") == 1
        # the OLBG row is untouched
        assert store.get_event("ev-olbg-1")["scheduled_start_utc"] == \
            "2026-09-20T08:00:00Z"
        # idempotent: re-running adds no second anomaly
        reconcile_olbg_events(store)
        assert [a["kind"] for a in store.anomalies()].count(
            "TIME_CONFLICT") == 1

    def test_agreeing_kickoff_has_no_anomaly(self, store):
        _olbg(store, "ev-olbg-1", "Fulham", "Man Utd", "2026-09-20T15:30:00Z")
        _official(store, "ev-off-1", "Fulham FC", "Manchester United FC",
                  "2026-09-20T15:30:00Z")
        out = reconcile_olbg_events(store)
        assert out["rows"][0]["status"] == "agree"
        assert store.anomalies() == []

    def test_unknown_names_stay_unmatched_no_heuristics(self, store):
        # "Spurs" is not in the curated table -> must NOT be matched to
        # Tottenham by any fuzzy rule.
        _olbg(store, "ev-olbg-1", "Spurs", "Aston Villa",
              "2026-09-19T11:30:00Z")
        _official(store, "ev-off-1", "Tottenham Hotspur FC", "Aston Villa",
                  "2026-09-19T11:30:00Z")
        out = reconcile_olbg_events(store)
        assert out["unmatched"] == 1 and out["matched"] == 0

    def test_pipeline_store_finding(self):
        """The committed snapshot + captures reproduce the 5-hour offset on
        every matchable card (documented finding, 2026-09-21)."""
        import json, os
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        site = json.load(open(os.path.join(root, "site-data", "site.json"),
                              encoding="utf-8"))
        rec = site.get("olbg_reconciliation")
        assert rec and rec["matched"] >= 5
        assert all(r["delta_hours"] == 5.0 for r in rec["rows"]
                   if r["status"] == "time_conflict")
