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
| **The Odds API** | Paid-plan provider terms (not open data); storage/UI/research/derived values allowed, raw-feed redistribution prohibited | **licensed API/import only**, active entitlement required | historical endpoint: 10 credits per region per market | 2026-09-20 |
| **Organizer result export** | Written permission/authority attestation required per competition; no blanket licence | **licensed import only**, authorization reference required | set by organizer agreement | 2026-09-20 |
| **football-data.co.uk** | No public license. Private-individuals-only; **no automated bots/scrapers/AI** | manual import · manual snapshot (**no** automated) | n/a (no auto retrieval) | 2026-09-19 |
| **OLBG (Invendium Ltd)** | Copyright reserved (ToU 9.1). Personal, non-commercial use only | **manual snapshot only** (no automated, no redistribution) | no bulk collection | 2026-09-19 |

## OpenLigaDB — ODbL-1.0 (the open-licensed result adapter)

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

## The Odds API — licensed historical odds path

**Evidence links (verify manually):**

- [Historical odds documentation](https://the-odds-api.com/liveapi/guides/v4/#get-historical-odds): the historical endpoint is paid-plan-only, returns the closest snapshot equal to or earlier than the requested timestamp, and charges 10 credits per region per market.
- [Historical data page](https://the-odds-api.com/historical-odds-data/): featured historical snapshots are documented from 6 June 2020, with 10-minute intervals initially and 5-minute intervals from September 2022; actual availability varies by sport, bookmaker and market.
- [Terms and Conditions](https://the-odds-api.com/terms-and-conditions.html), last updated 31 August 2026: the provider permits storing data indefinitely, displaying it in a UI/app, research/analytical dashboards, derived values and model training; it prohibits reselling/repackaging/redistributing the raw data as a standalone feed and requires API-key confidentiality.

**What is confirmed / what is not:**

- The published terms provide a permissioned product path for a subscribed user to use the data inside a value-adding research dashboard. They do **not** give this repository an account, a key, or a blanket right to publish raw odds.
- `northstar/adapters/the_odds_api.py` implements the historical endpoint, decimal/American conversion, explicit provider-event joins, raw-payload hashes, and strict pre-start rejection. The network path requires `NORTHSTAR_ODDS_API_KEY` plus `NORTHSTAR_ODDS_API_TERMS_ACK=2026-08-31` (or explicit function arguments); an offline import additionally requires a non-secret entitlement reference and the same terms acknowledgement.
- No key, provider response, or paid-plan data is committed here. Until the operator has an active account and confirms the intended deployment with the provider's terms, this source is **implemented but inactive**, not represented as verified pilot PnL.
- The GitHub Pages build publishes computed aggregates and source links only; it must not publish raw API responses, bulk CSV exports, API keys, or an endpoint that acts as a raw data feed.

## Official-result boundary and adapter contract

`northstar/adapters/official_results.py` is an authorization-gated adapter for a
competition-organizer export. It does not pretend that a community database or
a generic sports API is an official governing-body source. A live official
path requires a written permission record and an attested organizer feed; no
such permission or feed is bundled in this repository. Until that exists, the
pilot labels OpenLigaDB accurately as **ODbL community/reference results** and
uses the independent football-data compilation only as a cross-check. The
adapter's synthetic tests verify the contract without inventing real results.

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
- **No redistribution**: raw CSV rows and bulk source payloads stay in this
  private research repo and are excluded from the published site payload. The
  Pages payload contains only the project's computed pilot metrics, selected
  audit fields and source links; this is not a licence to republish source
  data.
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
