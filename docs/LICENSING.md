# Source licensing & collection permissions

Every source that can feed the pipeline is registered in
[`northstar/policy.py`](../northstar/policy.py). The pipeline **refuses** to run
a collection mode a source has not permitted (`PolicyError`), so an unpermitted
path cannot run silently. All entries below were verified by **direct
retrieval** on the dates shown; keep the evidence links for manual review.

## The matrix

| Source | License / policy | Permitted collection modes | Rate limit | Verified |
|---|---|---|---|---|
| **OpenLigaDB** | Open Database License 1.0 (ODbL-1.0), share-alike | automated API · manual import · manual snapshot | 60 requests/min/IP | 2026-09-19 |
| **football-data.co.uk** | No public license. Private-individuals-only; **no automated bots/scrapers/AI** | manual import · manual snapshot (**no** automated) | n/a (no auto retrieval) | 2026-09-19 |
| **OLBG (Invendium Ltd)** | Copyright reserved (ToU 9.1). Personal, non-commercial use only | **manual snapshot only** (no automated, no redistribution) | no bulk collection | 2026-09-19 |

## OpenLigaDB — ODbL-1.0 (the one official-result path)

**Evidence links (verify manually):**
- https://openligadb.de/ — front page: *"Die über diese API bereitgestellten
  Daten stehen unter der Open Database License (ODbL)"*
- https://openligadb.de/lizenz — license statement
- https://api.openligadb.de/ — API front page: *"Es gilt ein Limit von 60
  Anfragen pro Minute und IP"*
- https://opendatacommons.org/licenses/odbl/1-0/ — ODbL 1.0 text

**Consequences we enforce:**
- Automated API collection **is** permitted (used by `northstar.cli
  ingest-fullseason` in CI and by the pilot fixtures' provenance).
- ODbL is share-alike: derived **database files** must carry ODbL attribution.
  Our committed pilot fixtures under `data/fixtures/openligadb_*.json` are
  OpenLigaDB payloads; attribution + license are recorded here and in the
  repo README.
- Data are **community-entered**, not a DFL/governing-body feed. That is why
  the identity gate keeps events at `probable` until an *independent* source
  agrees (see `docs/data-contract.md`).

## football-data.co.uk — private use, no bots (research-use flag)

**Evidence links (verify manually):**
- https://www.football-data.co.uk/data.php — *"All FREE!!! ... however its use
  is intended for private individuals only, NOT commerical or data training
  products using automated bots/scrapers/AI."*
- https://www.football-data.co.uk/matches.php — odds collection windows
  (weekend fixtures: Fridays not later than 17:00 British time; midweek:
  Tuesdays not later than 13:00 British time)
- https://www.football-data.co.uk/notes.txt — result/odds provenance notes

**Consequences we enforce:**
- `MODE_AUTO_API` **raises PolicyError** for this source. CI never downloads a
  CSV from this site.
- The pilot uses a **human-captured** 27-row excerpt committed to
  `data/fixtures/football_data_d1_2425_pilot.csv` (manual import). Full-season
  scale-up requires a human to place files under `data/imports/` (git-ignored)
  or to obtain explicit permission / a licensed provider.
- **Pinnacle columns are excluded**: the site states Pinnacle odds have been
  systematically out of date since 23/07/2025 and excludes them from market
  averages; we do the same.
- **No redistribution**: derived data stays in this private research repo and
  is excluded from the published site payload (only computed aggregates ship).
- **Residual legal risk**: this is a personal-research use, not a commercial
  product. Before any scale-up, commercial use, or training use, obtain
  explicit written permission or switch to a licensed provider (the site
  partners with TheStatsAPI).

## OLBG — copyright reserved, manual review only

**Evidence links (verify manually):**
- https://www.olbg.com/use — Terms of Use (current, last updated 09 July 2025,
  operator Invendium Ltd, England & Wales 04490764)
- https://www.olbg.com/robots.txt — disallows `/api/`, `/sports/`,
  `/tipster/`, `/premium/`, `/newbg/`
- https://www.olbg.com/betting-tips — the public tips listing studied for the
  adapter (see `docs/OLBG-RESEARCH.md`)

**Relevant clauses (verified 2026-09-19, quoted):**
- §7.1 — use is for *"personal, non-commercial use and lawful purposes"*
- §7.3 — *"not to access without our consent, interfere with, hack into,
  damage or disrupt"* the service
- §9.1 — OLBG owns *"all intellectual property rights in our service ... All
  rights are reserved"*
- §9.2 — *"No copying or distribution of our service for any commercial or
  business purpose is permitted without our prior written consent"*
- §13.3 — *"You agree not to use our service for any commercial or business
  purposes"*

**Consequences we enforce:**
- `northstar/adapters/olbg.py::auto_fetch()` **raises PolicyError**
  unconditionally. There is no live OLBG collection path in this codebase.
- The only supported mode is ingesting **human-captured snapshots** stored
  under `data/raw/olbg_*.md` (captured 2026-09-19 for review).
- Imported OLBG tips are `pending`: they carry no permissioned odds and no
  official result path, so they **can never enter verified PnL**. OLBG
  tipster statistics (e.g. "Profits calculated to a 10 point stake") are
  OLBG's own public presentation — self-reported, unverified by us.

## What this does **not** permit

- Scraping OLBG pages at scale, mirroring them, or republishing their content.
- Automated downloads from football-data.co.uk by any process (including CI).
- Using the football-data CSVs as training data for any model.
- Treating OpenLigaDB community data as an official governing-body record
  (it is an open reference source; independent cross-checking is mandatory for
  `verified` identity).
