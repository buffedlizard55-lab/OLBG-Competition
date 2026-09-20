# Northstar Competition Lab

A source-first **paper-trading** research desk for the OLBG-Competition
project: it collects tipster selections (manually, where sources forbid
automation), verifies final results through permissioned/reference adapters,
settles paper PnL through audit
gates, and backtests sport-specific strategies **walk-forward with strict
time cutoffs** — all on data whose licensing is documented and whose hashes
are checked.

> **Honesty status (2026-09-20):** the pipeline is verified on a **27-match
> football pilot** (Bundesliga 1 2024/25) with **27/27 dual-source result
> agreement**; four strategies are **all negative** on that tiny sample
> (best: −4.04 units, ROI −36.7%, CI includes 0). Sport #2 is now live:
> a **21-event ice hockey pilot** (DEL 2024/25 matchdays 1/20/40) on the same
> ODbL source, with OT/shootout-aware finals, **5 real source irregularities
> flagged**, and predictions graded **only on accuracy (9/13 = 69.2%, Brier
> 0.473) — hockey PnL is unavailable (no permissioned odds path), and shown
> as unavailable, never as zero.** Every licensing claim was re-confirmed
> verbatim against the live sources today. Read
> [`docs/STATUS.md`](docs/STATUS.md) for limitations and remaining work.

## What is built (this pass)

- **Licensing gates in code** (`northstar/policy.py`, tested): OpenLigaDB
  ODbL-1.0 (automated API permitted), The Odds API (paid-plan historical
  access with explicit entitlement/terms acknowledgement), football-data.co.uk
  (manual import only — their no-bots policy), and OLBG (manual personal review
  only — ToS §7.1/7.3/9.1/9.2). Unpermitted collection modes raise
  `PolicyError`.
  Full matrix + evidence links: [`docs/LICENSING.md`](docs/LICENSING.md).
- **Entities**: `events`, `tips`, `odds_snapshots`, `results`,
  `settlements` (append-only, revisioned), `anomalies` — SQLite store in
  `northstar/db.py`, schema per [`docs/data-contract.md`](docs/data-contract.md).
- **Result adapters**: an ODbL OpenLigaDB reference-result adapter (the
  verified pilot path) and a separate authorization-gated official-organizer
  export adapter. The latter is tested as a contract but is inactive until a
  governing body grants written permission; OpenLigaDB is not mislabeled as an
  official governing-body feed. A football-data import adapter (manual,
  research-use flag, Pinnacle excluded per the source's notice) and a
  manual-snapshot OLBG adapter (auto path policy-blocked) complete the pilot.
- **Permissioned historical odds connector** for The Odds API: paid-plan
  historical snapshots, explicit entitlement/terms acknowledgement (plus a
  non-secret entitlement reference for offline imports), provider event-id
  reconciliation, hash preservation, and strict pre-start rejection.
  No key or provider response is committed; it is ready but inactive here.
- **Settlement engine** with 7 verification gates and the required
  edge-case behaviour: postponed → pending, cancelled/abandoned → void,
  disputed/conflicting results → withheld + anomaly, duplicate tips →
  flagged, source edits → flagged. Rule version:
  `nr-settlement-2026-09-19.1`.
- **Walk-forward backtest engine** (`northstar/backtest.py`): a
  `TimeBoundedStore` that raises `TimeLeakageError` on post-cutoff reads,
  pre-start cutoff enforcement, entry price = earliest stored snapshot ≤
  cutoff, ordering invariance, deterministic bootstrap CIs.
- **Four football strategies** (level 1.0 units): market favourite, market
  longshot probe, Elo value edge (K=40, home adv 60, 3% edge threshold),
  Draw-No-Bet decisive — all negative on the pilot; results shown as-is.
- **144 automated tests** (offline, `python -m pytest`) covering the
  required matrix: postponements, voids, duplicate tips, time leakage,
  disputed results, settlement arithmetic — plus adapter parsing of the
  real fixtures, the 27/27 cross-check, policy gates, leaderboard math,
  walk-forward invariants (including same-start ordering), and the hockey
  pilot guarantees below.
- **Sport #2: ice hockey (DEL 2024/25)** through the verified ODbL
  OpenLigaDB result path: 21 events, OT/shootout-aware final selection,
  results become available at start+3h (inferred; the source batch-edited
  results at end of season — documented), one strategy
  (`hockey-elo-v1`: 2-way Elo, K=32, home advantage 35, research priors)
  producing **predictions only** — recorded as `unsettleable`, graded on
  accuracy/Brier by `northstar/evaluation.py`, never settled, and kept off
  the PnL leaderboard by design. Five real irregularities in the community
  source were flagged instead of smoothed over (4 impossible
  regulation+OT/SO result layerings, 1 null-season schema deviation).
- **GitHub Pages site** (`index.html`, `app.js`, `styles.css`) rendering
  `site-data/site.json`: competition leaderboard (verified-profit ranking,
  review-state demotion), **per-tipster tip desk**, **full review of all
  placed and all upcoming bets**, strategy lab with backtest + CI,
  tipster-style generated predictions (evidence-only, refuses without a
  full model/fair/edge trail), source registry with evidence links for
  manual review, and hash-checked fixture provenance.
- **CI**: `ci.yml` (tests + fixture re-verification on PR/push),
  `pages.yml` (rebuilds site data, deploys only the site payload),
  `ingest.yml` (Monday: full-season OpenLigaDB verification for
  football/hockey/darts into a temp store, report artifact).

## Verify the build locally

```bash
python3 -m venv .venv && .venv/bin/pip install pytest

python -m pytest                      # 144 tests, offline
python -m northstar.cli run-pipeline --fresh   # rebuild store + site data
python -m northstar.cli verify              # fixture hashes + 27/27 agreement
node scripts/site-smoke.mjs            # (optional) site render smoke test

python3 -m http.server 4173 --bind 0.0.0.0   # then open http://localhost:4173
```

The site is a static build using relative assets and is designed for GitHub
Pages; external source links open in a new tab for manual review.

## The pilots, in one table

| Item | Football (Bundesliga 1 2024/25) | Ice hockey (DEL 2024/25) |
|---|---|---|
| Fixtures | 27 matches (matchdays 1/10/20) | 21 matches (matchdays 1/20/40) |
| Fixture files | [`openligadb_bl1_2024_sd{1,10,20}.json`](data/fixtures/) | [`openligadb_del_2024_sd{1,20,40}.json`](data/fixtures/) |
| Results source | OpenLigaDB (ODbL-1.0) | OpenLigaDB (ODbL-1.0) |
| Identity | **verified** (27/27 dual-source agreement vs football-data) | `probable` (single source; no independent DEL cross-check) |
| Odds path | football-data.co.uk manual pilot; The Odds API connector inactive | **none verified** → prediction-only |
| Engine output | 405 odds snapshots · 4 strategies · real settled PnL | 13 predictions · accuracy **9/13 (69.2%)** · Brier 0.473 · **PnL unavailable (not zero)** |
| Regularity | 0 open anomalies | **5 flagged source irregularities** (review queue) |
| Backtest | all four football strategies negative, CIs include 0 | no odds → no PnL by construction |

Anchors: 72214 M'gladbach 2-3 Leverkusen (23/08/24, B365 5.25/4.5/1.55);
72300 Mainz 3-1 Dortmund (09/11/24, 3.5/3.6/2.0); 72387 Bayern 4-3 Kiel
(01/02/25, 1.05/17/26).

## OLBG in this project

OLBG is the **competition context and tip source**, studied and snapshotted
manually (see [`docs/OLBG-RESEARCH.md`](docs/OLBG-RESEARCH.md) and
`data/raw/olbg_*.md`). Its ToS (verified 2026-09-19) forbids automated
access, so:

- no live OLBG collector exists — `auto_fetch()` raises `PolicyError`;
- imported OLBG tips are `pending` forever (no permissioned odds, no
  official result path) and never enter verified PnL;
- OLBG tipster statistics are shown only as external benchmark context;
- real drift between list and event-page consensus counts was captured and
  the `CONSENSUS_DRIFT` detector exists for future manual captures.

## Data integrity rules (invariant)

1. A tip is a prediction record, never a result.
2. Store the original source URL, source event ID, publication time,
   collection time, selection, market, and odds exactly as observed.
3. Store odds with their timestamp and source; never backfill a later price
   into an earlier tip (entry price = earliest stored snapshot ≤ cutoff).
4. Do not settle until a permissioned result source reports a final result
   and identity is verified.
5. Pending, postponed, abandoned, void, and disputed outcomes are **not**
   losses.
6. Reconcile event identity, competition, start time, participants, market
   rules, and result before settlement (7 gates).
7. Preserve the raw payload and a content hash so an amended source is
   detectable.
8. Flag conflicting sources, impossible timestamps, duplicate tips, edits
   after start, missing odds, ambiguous participants, and result changes —
   no silent "force settle" path exists.
9. PnL is paper-only, level-stakes, computed only from verified settled
   records; review-state PnL is demoted and labelled.
10. Predictions show evidence links, input cutoff, and model version, and
    are refused when the evidence trail is incomplete. Never call an
    untested hypothesis a "top tipster" prediction.

Full protocol: [`docs/data-contract.md`](docs/data-contract.md).

## Repository layout

```
northstar/            package: models, db, policy, settlement, backtest,
                      evaluation, leaderboard, predictor, report, timeutil,
                      cli, adapters/{openligadb,official_results,
                      the_odds_api,football_data,olbg},
                      strategies/{market,elo,draw,hockey}
tests/                144 offline tests (pytest)
data/fixtures/        committed pilot fixtures: football-bl1 + hockey-del
                      (sha256-verified)
data/raw/             manual OLBG snapshots (provenance headers)
site-data/site.json   generated site payload (rebuilt by the pipeline)
index.html app.js styles.css   GitHub Pages site
docs/                 LICENSING, OLBG-RESEARCH, STATUS, data-contract
.github/workflows/    ci.yml, pages.yml, ingest.yml
scripts/site-smoke.mjs          Node render smoke test
scripts/assemble_fixture.py     strict chunk-assembly + validation used to
                                commit the DEL fixtures (see capture notes)
```

## Data provenance and licenses

- `data/fixtures/openligadb_bl1_*.json` — OpenLigaDB payloads, **ODbL-1.0**,
  attribution retained; fetched 2026-09-19 from
  [api.openligadb.de](https://api.openligadb.de/) (60 req/min, no key).
- `data/fixtures/openligadb_del_*.json` — OpenLigaDB DEL payloads,
  **ODbL-1.0**, attribution retained; fetched 2026-09-20 from
  [api.openligadb.de](https://api.openligadb.de/) (permitted automated API),
  chunk-assembled and JSON-validated by `scripts/assemble_fixture.py`.
- `data/fixtures/football_data_d1_2425_pilot.csv` — 27-row human-captured
  excerpt of [mmz4281/2425/D1.csv](https://www.football-data.co.uk/germanym.php)
  (Bundesliga 1 = `D1` for 2020/21+). **Private research use only** per the
  site's stated policy; not for redistribution, training, or commercial use;
  Pinnacle columns unused (site notice 23/07/2025).
- `data/raw/olbg_*.md` — manual OLBG page captures for review; OLBG content
  rights reserved (ToU 9.1), personal non-commercial use only.

## Suggested next session (summary)

Full list in [`docs/STATUS.md`](docs/STATUS.md): start the forward test on a
fixed capture cadence; scale odds via human manual import (or a licensed
provider); continue sport-by-sport (darts next — its PDC result schema
still needs a walkover/format audit; the 18 `verification_blocked` sports
need a permissioned results path first); give hockey an independent
cross-check and a permissioned odds path before it ever shows PnL; add
more markets; correct for multiple comparisons; harden identity with a
third source.
