# Northstar Competition Lab

A source-first **paper-trading** research desk for the OLBG-Competition
project: it collects tipster selections (manually, where sources forbid
automation), verifies final results through permissioned/reference adapters,
settles paper PnL through audit
gates, and backtests sport-specific strategies **walk-forward with strict
time cutoffs** — all on data whose licensing is documented and whose hashes
are checked.

> **Honesty status (2026-09-22 — third-market + naive-baselines +
> capture-cadence pass):** the pipeline is verified on a **27-match
> football pilot** (Bundesliga 1 2024/25) with **27/27 dual-source result
> agreement**; **eleven strategies on three markets (1X2, O/U 2.5, Asian
> handicap)** run on that tiny sample — ten negative, and the one
> positive desk (`ah-poisson-value-v1`, +9.8 u, ROI +44.7%) is **not
> significant after Holm correction (p = 0.0605, family m = 11)**, so no
> edge is claimed. Sport #2 is
> **ice hockey** (DEL 2024/25 pilot, 21 events) and sport #3 is **darts**
> (eight real PDC events 2025–26, 423 finished matches — schema audit in
> [`docs/DARTS-AUDIT.md`](docs/DARTS-AUDIT.md)); both are
> **prediction-only**: hockey grades **7/11 = 63.6% (Brier 0.474)**; the
> darts desk stayed silent on the cold 2025 pool (**0 selections in 141
> matches**, max probability 0.551 vs its pre-registered 0.60 threshold)
> and graded **39/48 = 81.25% (Brier 0.349)** once the 2025–26 pool warmed
> — same priors throughout, nothing refitted, large error bars and no
> market baseline, so no skill or PnL claim.
> **Naive baselines now anchor those accuracy numbers** (added
> 2026-09-22): hockey always-home scores **64.7%** — the hockey Elo desk
> (63.6%) does *not* beat it on this pilot; darts listed-first scores
> **66.3%** — the darts Elo desk (81.25%) does clear its real reference
> bar. **The forward test is LIVE**: CI-captured real 2026/27 fixtures are
> committed under `data/fixtures/current/`, and **24 frozen hockey calls
> (DEL, Sep 22–27: 9 Elo + 15 home-baseline)** sit in the append-only
> ledger (`docs/FORWARD-TEST.md`). The weekly **manual OLBG capture
> cadence** has a written runbook (`docs/OLBG-CAPTURE-RUNBOOK.md`) and a
> Monday reminder workflow that never touches olbg.com. Hockey/darts PnL
> is unavailable (no permissioned odds path) and shown as unavailable,
> never as zero. **13 real source irregularities** are flagged, not
> smoothed — including conflicting duplicate result rows on two PDC
> matches (matchIDs 79962, 80237), excluded from grading until reviewed,
> and an abandoned duplicate darts league that discovery now demotes. Read
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
  flagged, source edits → flagged. Three market rule sets (1X2, O/U 2.5,
  Asian handicap incl. quarter-line stake splits and integer-line pushes).
  Rule version: `nr-settlement-2026-09-22.1`.
- **Walk-forward backtest engine** (`northstar/backtest.py`): a
  `TimeBoundedStore` that raises `TimeLeakageError` on post-cutoff reads,
  pre-start cutoff enforcement, entry price = earliest stored snapshot ≤
  cutoff, ordering invariance, deterministic bootstrap CIs.
- **Eleven football strategies on three markets** (level 1.0 units). 1X2:
  market favourite, market longshot probe, Elo value edge (K=40, home adv
  60, 3% edge threshold), Draw-No-Bet decisive, form value, home-edge
  value, draw value. Over/under 2.5 goals (added 2026-09-21, same verified
  pilot file — its O/U columns, same collection window): Poisson goal-model
  value desk and a market-totals-favourite baseline. **Asian handicap
  (added 2026-09-22, third settleable market)**: the line is stored on
  every priced snapshot and tip; settlement implements quarter-line
  stake splits (`half_won`/`half_lost`) and integer-line pushes (rule
  `nr-settlement-2026-09-22.1`; all 52 pilot settlements re-derived from
  the raw CSV with 0 mismatches); the Poisson AH value desk and the
  market-AH-favourite baseline ran walk-forward. **Ten of eleven
  negative; the positive AH value desk (+9.8 u, ROI +44.7%) has raw
  p = 0.0055 but Holm-adjusted p = 0.0605 (family m=11) — not
  significant, reported as exploratory only**. Research priors +
  citations: `docs/STRATEGIES.md`.
- **341 automated tests** (offline, `python -m pytest`) covering the
  required matrix: postponements, voids, duplicate tips, time leakage,
  disputed results, settlement arithmetic — plus adapter parsing of the
  real fixtures, the 27/27 cross-check, policy gates, leaderboard math,
  walk-forward invariants (including same-start ordering), capture
  discovery (darts 404 fallback, upcoming-first priority), forward-ledger
  idempotency/horizon/leak rules, Holm/bootstrap stats, and the hockey and
  darts pilot guarantees below.
- **Sport #2: ice hockey (DEL 2024/25)** through the verified ODbL
  OpenLigaDB result path: 21 events, OT/shootout-aware final selection,
  results become available at start+3h (inferred; the source batch-edited
  results at end of season — documented), one strategy
  (`hockey-elo-v1`: 2-way Elo, K=32, home advantage 35, research priors)
  producing **predictions only** — recorded as `unsettleable`, graded on
  accuracy/Brier by `northstar/evaluation.py` (**11 graded, 7 hits =
  63.6%, Brier 0.4737**; 2 disputed rows excluded from grading — the
  review queue owns them), never settled, and kept off the PnL leaderboard
  by design. Seven real irregularities in the community sources were
  flagged instead of smoothed over (4 impossible regulation+OT/SO result
  layerings, 1 null-season schema deviation, 2 darts matches with
  conflicting duplicate result entries — `docs/DARTS-AUDIT.md` §3.1).
- **Sport #3: darts (PDC)** — schema-audited on eight real committed
  events 2025–26 (World Matchplay, Baltic Sea Darts Open, Players
  Championship Finals 2025; the complete World Championship 2025/26; World
  Masters, Czech Darts Open, Flanders Darts Trophy and World Series Finals
  2026 — the last captured while its final was in play). `darts-elo-v1`
  (pre-registered priors K=24, HOME_ADV=0, MIN_PROB=0.60) made **0
  selections on the cold 2025 pool** (141 matches, max probability 0.551 —
  silence over forced bets), then **48 selections / 39 hits = 81.25%
  (Brier 0.349, 0 leaks)** on the full 423-match pool — same priors, no
  refit, large error bars, no market baseline, no skill claim. A
  **listed-first naive baseline** (added 2026-09-22) scores 66.3% on 421
  graded matches — listing order itself correlates with winning in this
  pool — so the Elo number is quoted against 66.3%, not a coin flip.
  Findings (leg/set encodings, entry-lag stats → start+12h
  availability, player-name identity splits, an abandoned duplicate league)
  are documented in [`docs/DARTS-AUDIT.md`](docs/DARTS-AUDIT.md).
- **Live current-season capture + forward test**: `.github/workflows/
  capture.yml` (Mondays 06:30 UTC + scoped push trigger) fetches the
  permitted OpenLigaDB current seasons (bl1 2026/27, del 2026/27, darts via
  discovery with upcoming-first priority), commits hash-sidecarred fixtures
  + a capture log, and re-runs the pipeline. The forward desk freezes
  predictions **at capture time** into the append-only
  `data/forward/ledger.json` (10-day issue horizon, start−30min cutoffs,
  leakage guards, idempotent issuance) — currently **24 live hockey calls
  (9 Elo + 15 home-baseline)**; protocol:
  [`docs/FORWARD-TEST.md`](docs/FORWARD-TEST.md). A second workflow
  (`olbg-capture-reminder.yml`) opens the weekly **manual** OLBG snapshot
  checklist issue ( Mondays 07:10 UTC) — it never touches olbg.com; the
  protocol is [`docs/OLBG-CAPTURE-RUNBOOK.md`](docs/OLBG-CAPTURE-RUNBOOK.md).
- **GitHub Pages site** (`index.html`, `app.js`, `styles.css`) rendering
  `site-data/site.json`: competition leaderboard (verified-profit ranking,
  review-state demotion), **per-tipster tip desk**, **full review of all
  placed and all upcoming bets**, strategy lab with backtest + CI,
  tipster-style generated predictions (evidence-only, refuses without a
  full model/fair/edge trail), source registry with evidence links for
  manual review, hash-checked fixture provenance, a **Forward** view (the
  frozen ledger: per-desk issued/graded/awaiting with accuracy + Brier) and
  an **Integrity** view (hypothesis registry, verification states, anomaly
  review queue, Holm-adjusted p-values per card).
- **CI**: `ci.yml` (tests + fixture re-verification on PR/push),
  `pages.yml` (rebuilds site data, deploys only the site payload),
  `capture.yml` (Monday 06:30 UTC + scoped pushes: captures permitted
  current-season fixtures, commits them, re-runs the pipeline incl.
  forward issuance/grading), `ingest.yml` (older Monday full-season
  verification pass into a temp store; its darts target `PDCWSDF` was found
  empty 2026-09-20 — `capture.yml` discovery supersedes it), and
  `olbg-capture-reminder.yml` (Monday 07:10 UTC: opens the manual OLBG
  snapshot checklist issue; no OLBG access — ToS).

## Verify the build locally

```bash
python3 -m venv .venv && .venv/bin/pip install pytest

python -m pytest                      # 341 tests, offline
python -m northstar.cli run-pipeline --fresh   # rebuild store + site data
python -m northstar.cli verify              # fixture hashes + 27/27 agreement
node scripts/site-smoke.mjs            # (optional) site render smoke test

python3 -m http.server 4173 --bind 0.0.0.0   # then open http://localhost:4173
```

The site is a static build using relative assets and is designed for GitHub
Pages; external source links open in a new tab for manual review.

## The pilots, in one table

| Item | Football (Bundesliga 1 2024/25) | Ice hockey (DEL 2024/25) | Darts (PDC 2025) |
|---|---|---|---|
| Fixtures | 27 matches (matchdays 1/10/20) | 21 matches (matchdays 1/20/40) | 423 finished matches (8 events 2025–26: PDCMP, BSDO, PDCPCF, PDCWM, PDCWOMA, PDCCDO, PDCFDT, PDCWSDF) |
| Fixture files | [`openligadb_bl1_2024_sd{1,10,20}.json`](data/fixtures/) | [`openligadb_del_2024_sd{1,20,40}.json`](data/fixtures/) | [`openligadb_*_{2025,2026}.json`](data/fixtures/current/) — 8 CI-captured PDC events |
| Results source | OpenLigaDB (ODbL-1.0) | OpenLigaDB (ODbL-1.0) | OpenLigaDB (ODbL-1.0), discovery-driven |
| Identity | **verified** (27/27 dual-source agreement vs football-data) | `probable` (single source; no independent DEL cross-check) | `probable` (single source; audit in `docs/DARTS-AUDIT.md`) |
| Odds path | football-data.co.uk manual pilot; The Odds API connector inactive | **none verified** → prediction-only | **none** → prediction-only |
| Engine output | 829 odds snapshots (405 1X2 + 208 O/U 2.5 + 216 AH) · 11 strategies · real settled PnL | 11 graded predictions · accuracy **7/11 (63.6%)** · Brier 0.4737 · **vs home baseline 11/17 = 64.7%** · **PnL unavailable (not zero)** | cold 2025 pool: **0 selections in 141** (max prob 0.551 < 0.60 — silence, no refit); full 2025–26 pool: **39/48 = 81.25%**, Brier 0.349 · **vs listed-first baseline 279/421 = 66.3%** · **PnL unavailable (not zero)** |
| Regularity | 0 open anomalies on the pilot; 1 flagged on the pl/2026 capture (duplicate conflicting result rows, matchID 86559) | **5 flagged source irregularities** (review queue) | **2 flagged** (conflicting duplicate results, matchIDs 79962 + 80237) + 1 abandoned duplicate league excluded |
| Backtest | ten of eleven strategies negative; `ah-poisson-value-v1` **+9.8 u (ROI +44.7%) but Holm-adjusted p = 0.0605 — not significant** (family m=11); no edge claimed | no odds → no PnL by construction; Elo does **not** beat the home baseline on this sample | no odds → no PnL by construction; Elo **does** beat the listed-first baseline (81.25% vs 66.3%) |
| Forward desk | dormant by design across bl1/pl/bl2/la1 (international break; next kick-offs 2026-10-09/10, outside the 10-day horizon) | **LIVE: 24 frozen calls (9 Elo + 15 home-baseline), DEL Sep 22–27** | first live event met in play (WSDF final → review queue, next capture resolves); both darts desks activate for the next World Championship (Dec 2026) |

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
                      stats, registry, capture, forward, value, cli,
                      adapters/{openligadb,official_results,the_odds_api,
                      football_data,olbg},
                      strategies/{base,market,elo,draw,value,totals,asian,
                      hockey,darts,baselines}
tests/                341 offline tests (pytest)
data/fixtures/        committed pilot fixtures: football-bl1 + hockey-del
                      (sha256-verified)
data/fixtures/current/ CI-captured live-season fixtures + capture log
                      (bl1/pl/bl2/la1/del 2026/27, PDC darts 2025-26; sha256 sidecars)
data/forward/         append-only forward-test ledger (frozen predictions)
data/raw/             manual OLBG snapshots (provenance headers)
site-data/site.json   generated site payload (rebuilt by the pipeline)
index.html app.js styles.css   GitHub Pages site
docs/                 LICENSING, OLBG-RESEARCH, STATUS, data-contract,
                      STRATEGIES, FORWARD-TEST, DARTS-AUDIT,
                      OLBG-CAPTURE-RUNBOOK (the weekly manual OLBG cadence)
.github/workflows/    ci.yml, pages.yml, capture.yml, ingest.yml,
                      olbg-capture-reminder.yml (manual-cadence reminder)
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
- `data/fixtures/current/openligadb_*.json` — live-season OpenLigaDB
  payloads (**ODbL-1.0**), captured and committed automatically by
  `.github/workflows/capture.yml` since 2026-09-20 (bl1/del 2026/27; from
  2026-09-21 also Premier League `pl`, 2. Bundesliga `bl2` and LaLiga `la1`
  2026/27 — each probed live before listing; team crest URLs are stripped
  on capture and the raw sha256 kept in the sidecar; PDC
  darts events 2025–26 found via league-index discovery after
  `getavailableseasons` returned 404 for every darts shortcut — see
  `capture-log.json` and `docs/DARTS-AUDIT.md`).
- `data/fixtures/football_data_d1_2425_pilot.csv` — 27-row human-captured
  excerpt of [mmz4281/2425/D1.csv](https://www.football-data.co.uk/germanym.php)
  (Bundesliga 1 = `D1` for 2020/21+). **Private research use only** per the
  site's stated policy; not for redistribution, training, or commercial use;
  Pinnacle columns unused (site notice 23/07/2025).
- `data/raw/olbg_*.md` — manual OLBG page captures for review; OLBG content
  rights reserved (ToU 9.1), personal non-commercial use only.

## Suggested next session (summary)

Full list in [`docs/STATUS.md`](docs/STATUS.md): let the live forward test
grade the 24 frozen hockey calls (football MD5 issues automatically from
2026-10-09; darts `darts-wm-26` in December); **run** the manual OLBG
snapshot cadence each week (the runbook and Monday reminder issue exist;
ToS means only a human can take the snapshot); scale odds via human
manual import or a licensed provider (then PnL-capable forward desks —
and the first out-of-sample check of the AH desk's exploratory positive
result); give hockey
an independent cross-check and a permissioned odds path before it ever
shows PnL; the 18 `verification_blocked` sports need a permissioned
results path first; add more markets (BTTS is blocked on a priced source);
harden identity with a third source.
