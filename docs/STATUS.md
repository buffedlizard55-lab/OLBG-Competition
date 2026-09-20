# Status, limitations & remaining work

**Updated 2026-09-20** (ice-hockey expansion + licensing re-verification
pass). Read together with `README.md` (what this is), `docs/LICENSING.md`
(what sources allow), `docs/OLBG-RESEARCH.md` (what OLBG is), and
`docs/data-contract.md` (the rules every number must pass). This pass's
licensing claims were **re-fetched and re-confirmed verbatim today** (see
the "Re-verified 2026-09-20" note in `docs/LICENSING.md`).

## What is done and verified (this pass)

- **Source licensing confirmed first-hand** with evidence links
  (`docs/LICENSING.md`): OpenLigaDB = ODbL-1.0 (automated API allowed);
  The Odds API = paid-plan historical endpoint with storage/UI/research
  permitted but raw-feed redistribution prohibited; football-data.co.uk =
  private use, no bots (manual import only); OLBG = copyright reserved,
  manual personal review only. The policy gates live in code
  (`northstar/policy.py`) and are tested. No provider account or key is
  claimed for The Odds API.
- **Pilot dataset, locked and committed** (hash-checked by
  `python -m northstar.cli verify`): Bundesliga 1 2024/25 matchdays 1, 10, 20
  = 27 matches. Results from OpenLigaDB (ODbL); odds from a human-captured
  football-data D1 excerpt (5 bookmaker columns incl. market average; Pinnacle
  excluded per the source's own 2025-07-23 notice).
- **Dual-source verification: 27/27** full-time results agree between the two
  independent compilations; UK-local → UTC join is exact-minute for all 27.
  Events are upgraded to `verified` identity only after this agreement.
- **Result adapters**: OpenLigaDB's ODbL community/reference adapter plus a
  separate authorization-gated official-organizer export adapter. The latter
  has contract tests but is inactive without written organizer permission;
  OpenLigaDB is not called an official governing-body feed. The football-data
  import adapter and manual-snapshot OLBG adapter remain policy-gated. All
  ingestion is idempotent and result/odds source edits are flagged.
- **Licensed historical odds adapter** for The Odds API: paid-plan key and
  terms acknowledgement required, source-event joins are explicit, raw
  payload hashes are retained, and post-start snapshots are rejected. No
  licensed response is bundled or claimed as pilot data.
- **Settlement engine** with the 7 verification gates, versioned rule
  (`SETTLEMENT_RULE_VERSION`), and the required edge-case behaviour:
  postponed → pending (never a loss), cancelled/abandoned → void (stake
  refunded, out of turnover), disputed / conflicting providers → withheld with
  anomalies, duplicate tips → flagged, source edits → flagged.
- **Walk-forward backtesting with strict time cutoffs**
  (`TimeBoundedStore` raises `TimeLeakageError` on post-cutoff reads; cutoff
  must be pre-start; entry price = earliest stored snapshot ≤ cutoff; ordering
  invariance tested).
- **Four football strategies backtested on real cross-checked outcomes**
  (level 1.0 units): market favourite, market longshot probe, Elo value edge
  (K=40, home advantage 60, 3% edge threshold), Draw-No-Bet decisive.
  **Honest result: all four are negative on this 27-match sample** (best: Elo
  edge −4.04 units / ROI −36.7%; full table on the site). Bootstrap 95% CIs
  all include zero. No edge claimed.
- **Sport #2 live: ice hockey (DEL 2024/25, matchdays 1/20/40 — 21
  events)** through the same ODbL OpenLigaDB path: OT/shootout-aware final
  selection (AfterPenalties > AfterExtraTime > After90Minutes), results
  released to models at start+3h (inferred — DEL community rows were
  batch-edited at end of season; limitation #11), and one prediction-only
  strategy (`hockey-elo-v1`: 2-way Elo, K=32, home advantage 35 Elo points —
  research priors, not fitted). **Graded: 13 predictions, 9 hits (69.2%),
  mean Brier 0.473, per-matchday accuracy on the site.** Hockey **PnL is
  unavailable by construction** (no permissioned odds source): tips are
  `unsettleable`, the leaderboard excludes the desk, and no settlement row
  exists for it. Identity stays `probable` (single source).
- **Real source irregularities surfaced, not smoothed**: 4 DEL matches
  carry an impossible result layering (decisive "after regulation" *and*
  an overtime/shootout entry) → `RESULT_KIND_INCONSISTENT`; 1 match
  (matchID 76412) arrived with `leagueSeason: null` → normalized to 2024
  from the payload's unambiguous rows and flagged `MISSING_METADATA`. All
  five sit in the review queue with evidence URLs.
- **The flags were right (manual corroboration, 2026-09-20).** The two
  keystone finals were re-checked by hand against independent outlets:
  Augsburg 3-2 Ingolstadt on 19.09.2024 was **2-2 after regulation, 1-0 in
  overtime** — kicker, sportal and the
  [official DEL match sheet](https://www.penny-del.org/statistik/spieldetails/19092024_augsburger-panther_gg_erc-ingolstadt_3504)
  agree with the `AfterExtraTime` final our priority rule selected (the
  source's 3.Drittel entry was mislayered, as flagged); Iserlohn 5-6
  Eisbären Berlin on 26.01.2025 was **5-5 after regulation, decided in the
  shootout** ([official DEL sheet](https://www.penny-del.org/statistik/spieldetails/26012025_iserlohn-roosters_gg_eisbaeren-berlin_3778),
  [eisbaeren.de](https://www.eisbaeren.de/news/detail/penaltysieg-im-sauerland))
  — again matching the `AfterPenalties` final we stored. The DEL official
  site is review evidence only; no bulk collection permission exists for
  it, so OpenLigaDB remains the sole systematic DEL source and identity
  stays `probable`.
- **One engine-ordering bug found and fixed**: walk-forward ordering now
  tie-breaks same-start events by `event_id`; a full hockey matchday can
  share a puck-drop time, and input order changed the evaluation order
  before the fix (football results on the pilot are unchanged — the pilot
  times were unambiguous).
- **Automated tests: 142 passing** covering the user-specified matrix —
  postponements, voids, duplicate tips, time leakage, disputed results,
  settlement arithmetic — plus adapter parsing of the real fixtures, the
  27/27 cross-check, policy gates, leaderboard math, and walk-forward
  invariants. Run: `python -m pytest`.
- **Competition leaderboard + tip desk + full bet review** rendered on the
  GitHub Pages site from `site-data/site.json` (regenerated by the pipeline):
  verified-profit ranking with review-state demotion, per-tipster tips,
  **all placed bets and all upcoming bets** reviewable, tipster-style
  generated predictions built **only** from stored verified statistics
  (evidence links attached; the renderer refuses to write a prediction when
  the model/fair/edge trail is missing).
- **Sport coverage table for all OLBG sport families**: Football
  `pilot_verified`; Ice Hockey `results_pilot` (21 events end-to-end,
  prediction-only); Darts `results_path_available` (PDC endpoints, ODbL —
  schema audit still pending); the other 18 `verification_blocked` with
  explicit not-covered states.
- **CI**: `ci.yml` runs the test suite + fixture re-verification on every
  PR/push; `pages.yml` rebuilds the site data and deploys only the site
  payload; `ingest.yml` (Monday 06:00 UTC) runs the full-season OpenLigaDB
  verification pass (football bl1/bl2, hockey del/DEL2/CHL, darts PDCWSDF)
  into a temporary store and uploads a report artifact.

## Hard limitations (do not mistake for bugs)

1. **Sample size.** 27 matches / 11–27 bets per strategy cannot separate
   skill from luck. Every negative (or positive) number on the site carries a
   sample-size warning. This is the single biggest limitation.
2. **Odds are window-close-inferred, not exact.** football-data.co.uk gives
   batch-collected prices (Fri 17:00 UK / Tue 13:00 UK closes) with no
   per-event timestamp. We store the *close of the collection window* as
   `observed_at` with `timestamp_precision = window_close_inferred`, which is
   a conservative (earlier) bound — no leakage — but not the true trade time.
3. **The pilot has no active governing-body result feed.** OpenLigaDB is ODbL
   and useful, but community-entered, not the DFL's feed. The new official
   result adapter refuses unauthorised/unauthenticated exports; its tests use
   only a synthetic schema fixture. Pilot identity therefore needs the
   independent cross-check, and full-season CI runs keep events at `probable`
   until a second source is attached.
4. **One market only.** Only `match_winner_3way` has a settled rule set.
   OLBG's other markets (totals, handicaps, each-way, darts sets…) are not
   settleable here yet — imported OLBG tips therefore stay `pending` forever.
5. **No forward test has run yet.** The pilot is historical; a live paper
   forward-test (the protocol the user asked for where backtesting is
   unavailable) starts only when a recurring capture cadence exists.
6. **OLBG is manual-only.** No automated OLBG access exists or is permitted.
   Its tipster statistics are self-reported and never enter PnL.
7. **Odds licensing boundary.** The Odds API connector is permissioned only
   for an active paid-plan customer who accepts the current terms; this repo
   has no such key or response. The provider permits value-adding UI/research
   use but prohibits a raw odds feed, so raw captures must stay local. The
   football-data pilot remains a private/manual research fixture and should
   not be redistributed or used for automated collection, commercial use, or
   training without separate permission.
8. **Multiple comparisons.** 25 hypotheses were designed; 4 were run on one
   27-match sample. No correction for multiple testing has been applied —
   treat all four results as exploratory, not confirmatory.
9. **DST clock-change days.** UK wall times on the two clock-change days are
   refused by `uk_local_to_utc` (ambiguous) rather than guessed; such rows
   would surface as `TIME_CONFLICT` anomalies. None occur in the pilot.
10. **Hockey is single-source.** The DEL pilot's results come only from
    OpenLigaDB (ODbL community data). No independent DEL compilation is
    attached, so identity stays `probable`, the desk is review-state, and
    accuracy metrics are explicitly not verified official outcomes.
11. **Hockey result availability is inferred (start+3h).** DEL community
    rows carry end-of-season batch-edit timestamps (e.g. 2025-04-07 for a
    September game); using them as availability would erase walk-forward
    history. The adapter instead releases results exactly 3 hours after
    start — a *conservative construction* (a desk cannot know a game is
    final before it ends), documented here, never a claim about the source's
    true availability time.
12. **13 graded hockey predictions is not evidence of skill.** 69.2%
    accuracy on 13 picks (plus a 0/1 collapse on matchday 40) has a huge
    binomial error bar; it proves the path, not an edge. No hockey number
    may be quoted as profitability.

## Remaining work, in priority order (next session)

1. **Start the forward test (the real competition clock).**
   - Capture fresh OLBG snapshots on a fixed cadence (manual, ToS-compliant)
     into `data/raw/` and re-run the pipeline; the drift detector and the
     pending-tip queue already exist.
   - Let `ingest.yml` keep pulling finished OpenLigaDB matchdays for the
     pilot competition; new results upgrade from `probable` only after the
     dual-source check.
   - Mark every forward-test number on the site as `forward_test` (separate
     from backtest PnL) once it exists.
2. **Scale odds legitimately.** Human manual import of full-season D1 2024/25
   (and more seasons) into `data/imports/` (git-ignored) →
   `football_data.ingest_csv_text` already consumes that path; or obtain
   explicit permission / a licensed provider before any automated scale-up.
   Then: full-season walk-forward for the four strategies with season-split
   validation (no cross-season leakage).
3. **Expand sport by sport, only after verification passes:**
   - Ice hockey (done this pass, results pilot): next milestone is an
     independent DEL cross-check source (to lift identity from `probable`)
     and a permissioned historical DEL odds path (only then may hockey PnL
     exist). Scale DEL fixtures to the full season via the Monday CI ingest
     before trusting any accuracy trend.
   - Darts: audit the PDC result schema on OpenLigaDB (legs/sets, possible
     walkovers, group/round naming) against real payloads, then repeat the
     pilot pattern used for hockey. Only after that audit passes does a
     darts strategy exist.
   - The 18 `verification_blocked` sports each need a permissioned results
     path first; keep them visibly blocked until then.
4. **More markets** (totals, Asian handicap, each-way) once odds coverage
   allows; each market gets its own versioned rule set and test matrix row.
5. **Model work**: Poisson goal totals (features: pre-cutoff goals-for/against
   per team from the released history), rating decay, draw-rate calibration;
   multiple-comparisons correction across the strategy family.
6. **Identity hardening**: add a third independent result source or the DFL
   official feed for the pilot league so `verified` identity does not rest on
   two community compilations.
7. **Site**: per-tipster performance sparklines, anomaly-queue page,
   forward-test badge; keep the payload free of raw football-data rows.

## Reproduce everything

```bash
python -m venv .venv && .venv/bin/pip install pytest
python -m pytest                     # 142 tests, offline
python -m northstar.cli run-pipeline --fresh   # rebuild store + site-data/site.json
python -m northstar.cli verify               # re-check fixture hashes + 27/27
```
