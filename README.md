# Northstar Competition Lab

A source-first **paper-trading** research desk for the OLBG-Competition
project: it collects tipster selections (manually, where sources forbid
automation), verifies official results, settles paper PnL through audit
gates, and backtests sport-specific strategies **walk-forward with strict
time cutoffs** — all on data whose licensing is documented and whose hashes
are checked.

> **Honesty status (2026-09-19):** the pipeline is implemented and
> verified on a **27-match football pilot** (Bundesliga 1 2024/25, matchdays
> 1/10/20) with **27/27 dual-source result agreement**. Four strategies were
> backtested on those real verified outcomes; **all four are negative on this
> tiny sample** (best: −4.04 units, ROI −36.7%, 95% CI includes 0). Nothing
> here claims an edge, and no number on the site exists that the pipeline did
> not compute from hash-checked fixtures. Read
> [`docs/STATUS.md`](docs/STATUS.md) for limitations and remaining work.

## What is built (this pass)

- **Licensing gates in code** (`northstar/policy.py`, tested): OpenLigaDB
  ODbL-1.0 (automated API permitted), football-data.co.uk (manual import
  only — their no-bots policy), OLBG (manual personal review only — ToS
  §7.1/7.3/9.1/9.2). Unpermitted collection modes raise `PolicyError`.
  Full matrix + evidence links: [`docs/LICENSING.md`](docs/LICENSING.md).
- **Entities**: `events`, `tips`, `odds_snapshots`, `results`,
  `settlements` (append-only, revisioned), `anomalies` — SQLite store in
  `northstar/db.py`, schema per [`docs/data-contract.md`](docs/data-contract.md).
- **One official-result adapter** (OpenLigaDB, ODbL) + a football-data
  import adapter (manual, research-use flag, Pinnacle excluded per the
  source's notice) + a manual-snapshot OLBG adapter (auto path policy-blocked).
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
- **105 automated tests** (offline, `python -m pytest`) covering the
  required matrix: postponements, voids, duplicate tips, time leakage,
  disputed results, settlement arithmetic — plus adapter parsing of the
  real fixtures, the 27/27 cross-check, policy gates, leaderboard math,
  and walk-forward invariants.
- **GitHub Pages site** (`index.html`, `app.js`, `styles.css`) rendering
  `site-data/site.json`: competition leaderboard (verified-profit ranking,
  review-state demotion), **per-tipster tip desk**, **full review of all
  placed and all upcoming bets**, strategy lab with backtest + CI,
  tipster-style generated predictions (evidence-only, refuses without a
  full model/fair/edge trail), source registry with official verified
  links, and hash-checked fixture provenance.
- **CI**: `ci.yml` (tests + fixture re-verification on PR/push),
  `pages.yml` (rebuilds site data, deploys only the site payload),
  `ingest.yml` (Monday: full-season OpenLigaDB verification for
  football/hockey/darts into a temp store, report artifact).

## Verify the build locally

```bash
python3 -m venv .venv && .venv/bin/pip install pytest

python -m pytest                      # 105 tests, offline
python -m northstar.cli run-pipeline --fresh   # rebuild store + site data
python -m northstar.cli verify              # fixture hashes + 27/27 agreement
node scripts/site-smoke.mjs            # (optional) site render smoke test

python3 -m http.server 4173 --bind 0.0.0.0   # then open http://localhost:4173
```

The site is a static build using relative assets and is designed for GitHub
Pages; external source links open in a new tab for manual review.

## The pilot, in one table

| Item | Value | Evidence |
|---|---|---|
| Competition | 1. Fußball-Bundesliga 2024/25 | [`data/fixtures/openligadb_bl1_2024_sd{1,10,20}.json`](data/fixtures/) |
| Matches | 27 (matchdays 1, 10, 20) | sha256-verified by `verify` |
| Results source | OpenLigaDB (ODbL-1.0, community-entered) | [api.openligadb.de](https://api.openligadb.de/) |
| Odds source | football-data.co.uk D1 manual import (research-use flag) | [football-data.co.uk/data.php](https://www.football-data.co.uk/data.php) |
| Cross-check | **27/27 FT results agree**, UK-time join exact-minute | `run-pipeline` output |
| Odds snapshots | 405 (5 providers × 3 selections × 27), pre-start, window-close inferred | `site-data/site.json` |
| Backtest | 4 strategies, 11–27 bets each, all negative, CIs include 0 | site → Strategy lab |
| Policy | OpenLigaDB automated OK · football-data manual only · OLBG manual only | `docs/LICENSING.md` |

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
                      leaderboard, predictor, report, timeutil, cli,
                      adapters/{openligadb,football_data,olbg}, strategies/
tests/                105 offline tests (pytest)
data/fixtures/        committed pilot fixtures (sha256-verified)
data/raw/             manual OLBG snapshots (provenance headers)
site-data/site.json   generated site payload (rebuilt by the pipeline)
index.html app.js styles.css   GitHub Pages site
docs/                 LICENSING, OLBG-RESEARCH, STATUS, data-contract
.github/workflows/    ci.yml, pages.yml, ingest.yml
scripts/site-smoke.mjs          Node render smoke test
```

## Data provenance and licenses

- `data/fixtures/openligadb_*.json` — OpenLigaDB payloads, **ODbL-1.0**,
  attribution retained; fetched 2026-09-19 from
  [api.openligadb.de](https://api.openligadb.de/) (60 req/min, no key).
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
provider); expand sport-by-sport (hockey & darts next — results paths are
open-licensed, odds unverified); add more markets; correct for multiple
comparisons; harden identity with a third source.
