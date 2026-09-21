"""Curated participant alias tables (evidence-linked, no heuristics)."""
from __future__ import annotations

import json
import os

import pytest

from northstar import aliases
from northstar.aliases import validate_alias_table, canonical_name

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class TestDartsTable:
    def test_committed_table_valid_and_evidence_linked(self):
        doc = json.load(open(os.path.join(ROOT, "data", "aliases",
                                          "darts.json"), encoding="utf-8"))
        m = validate_alias_table(doc)
        assert m == {"D. van Duijvenbode": "Dirk van Duijvenbode",
                     "R. van Barneveld": "Raymond van Barneveld",
                     "Michael Mansell": "Mickey Mansell"}
        for e in doc["aliases"]:
            assert e["evidence"] and e["evidence_note"]

    def test_unknown_names_stay_raw(self):
        assert canonical_name("darts", "Michael Smith") == "Michael Smith"
        assert canonical_name("darts", "Ross Smith") == "Ross Smith"
        assert canonical_name("football", "FC Bayern München") == \
            "FC Bayern München"

    def test_every_alias_raw_name_exists_in_a_committed_payload(self):
        """The table must describe real payload spellings, not guesses."""
        import glob
        names = set()
        for f in glob.glob(os.path.join(ROOT, "data", "fixtures", "current",
                                        "openligadb_*.json")):
            if f.endswith(".meta.json"):
                continue
            for m in json.load(open(f, encoding="utf-8")):
                names.add(m["team1"]["teamName"])
                names.add(m["team2"]["teamName"])
        for raw, canon in aliases.alias_map("darts").items():
            assert raw in names, raw
            assert canon in names, canon


class TestValidation:
    def _doc(self, entries):
        return {"version": "t", "aliases": entries}

    def test_missing_evidence_refused(self):
        with pytest.raises(ValueError):
            validate_alias_table(self._doc([{"canonical": "A",
                                             "aliases": ["a"],
                                             "evidence": []}]))

    def test_conflicting_maps_refused(self):
        with pytest.raises(ValueError):
            validate_alias_table(self._doc([
                {"canonical": "A", "aliases": ["x"], "evidence": ["http://e"]},
                {"canonical": "B", "aliases": ["x"], "evidence": ["http://e"]},
            ]))

    def test_canonical_cannot_also_be_alias(self):
        with pytest.raises(ValueError):
            validate_alias_table(self._doc([
                {"canonical": "A", "aliases": ["B"], "evidence": ["http://e"]},
                {"canonical": "B", "aliases": ["c"], "evidence": ["http://e"]},
            ]))

    def test_self_alias_refused(self):
        with pytest.raises(ValueError):
            validate_alias_table(self._doc([
                {"canonical": "A", "aliases": ["A"], "evidence": ["http://e"]},
            ]))


class TestDartsEloUsesCanonicalNames:
    def test_rating_shared_across_spellings(self):
        from datetime import datetime, timezone, timedelta
        from northstar.backtest import TimeBoundedStore
        from northstar.strategies import build
        st = build("darts-elo-v1")
        tbs = TimeBoundedStore()
        t0 = datetime(2026, 1, 1, 12, tzinfo=timezone.utc)
        ev = {"event_id": "e1", "home_team": "D. van Duijvenbode",
              "away_team": "Someone Else",
              "scheduled_start_utc": "2026-01-01T12:00:00Z"}
        ratings = st.ratings_after(ev, 6, 0, tbs, t0)
        assert "Dirk van Duijvenbode" in ratings
        assert "D. van Duijvenbode" not in ratings
        tbs.update_ratings(ratings, available_at=t0)
        ev2 = {"event_id": "e2", "home_team": "Dirk van Duijvenbode",
               "away_team": "Someone Else",
               "scheduled_start_utc": "2026-01-02T12:00:00Z"}
        d = st.predict(ev2, tbs, t0 + timedelta(days=1),
                       as_of=t0 + timedelta(hours=12))
        assert d["model"]["ratings"]["home"] > 1500
        assert d["model"]["identity"]["applied"] == {}
        d1 = st.predict(ev, tbs, t0 + timedelta(days=1),
                        as_of=t0 + timedelta(hours=12))
        assert d1["model"]["identity"]["applied"] == {
            "D. van Duijvenbode": "Dirk van Duijvenbode"}
