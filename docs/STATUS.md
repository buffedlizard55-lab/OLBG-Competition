# Status, limitations & remaining work

**Updated 2026-09-22 (third-market + naive-baselines + capture-cadence pass).**
Changes since 2026-09-21 in one paragraph: the Asian handicap became the
third settleable football market (line stored on snapshots/tips; quarter
lines split half/half, integer lines push — settlement rule written and
tested, all 52 pilot settlements re-derived independently from the raw CSV
with 0 mismatches); two AH strategies ran walk-forward on the verified
pilot — the **first positive result in the repo** (`ah-poisson-value-v1`
+9.835 u, ROI +44.7%) which is **NOT significant after Holm correction
(p=0.0605, family m=11)** and is reported strictly as exploratory;
prediction-only sports gained naive baselines (`hockey-home-v1`: 64.7% on
17 graded — the hockey Elo desk does *not* beat always-home on this pilot;
`darts-listed-first-v1`: 66.3% on 421 graded — the darts Elo desk's 81.25%
does clear its real reference bar), and both baselines also run as live
forward desks (15 new frozen DEL calls); the weekly **manual OLBG capture
cadence** now has a written runbook (`docs/OLBG-CAPTURE-RUNBOOK.md`) plus
a scheduled reminder workflow that opens a checklist issue every Monday
without ever touching olbg.com. Test count 341.
Read together with `README.md` (what this is), `docs/LICENSING.md` (what
sources allow), `docs/OLBG-RESEARCH.md` (what OLBG is),
`docs/data-contract.md` (the rules every number must pass),
`docs/STRATEGIES.md` (research log + citations), `docs/FORWARD-TEST.md`
(the live protocol) and `docs/DARTS-AUDIT.md` (darts schema findings).
Licensing claims were re-fetched and re-confirmed verbatim (see the
"Re-verified 2026-09-20" note in `docs/LICENSING.md`).

## What is done and verified

### Data & licensing
- **Source licensing confirmed first-hand** with evidence links
  (`docs/LICENSING.md`): OpenLigaDB = ODbL-1.0 (automated API allowed);
  The Odds API = paid-plan historical endpoint with storage/UI/research
  permitted but raw-feed redistribution prohibited; football-data.co.uk =
  private use, no bots (manual import only); OLBG = copyright reserved,
  manual personal review only. The policy gates live in code
  (`northstar/policy.py`) and are tested. No provider account or key is
  claimed for The Odds API.
- **Pilot dataset, locked and committed** (hash-checked by
  `python -m northstar.cli verify`): Bundesliga 1 2024/25 matchdays 1, 10,
  20 = 27 matches; DEL 2024/25 matchdays 1, 20, 40 = 21 matches. Results
  from OpenLigaDB (ODbL); football odds from a human-captured football-data
  D1 excerpt (5 bookmaker columns incl. market average; Pinnacle excluded
  per the source's own 2025-07-23 notice).
- **Dual-source verification: 27/27** full-time football results agree
  between two independent compilations; UK-local → UTC join is
  exact-minute for all 27. Events upgrade to `verified` identity only after
  this agreement.
- **Live current-season captures (real data, committed)**:
  `data/fixtures/current/` now carries CI-captured 2026/27 payloads —
  Bundesliga (306 matches), DEL (364 matches), and eight PDC darts events
  2025–26 (423 finished matches: World Matchplay, Baltic Sea Darts Open and
  Players Championship Finals 2025; the complete World Championship
  2025/26; World Masters, Czech Darts Open and Flanders Darts Trophy 2026;
  the World Series of Darts Finals 2026 captured **while its final was in
  play**) — each with a `.meta.json` sha256 sidecar and a
  `capture-log.json` documenting every probe/404/refusal. Captured by
  `.github/workflows/capture.yml` (Mondays 06:30 UTC + scoped push
  trigger), committed by the workflow bot. 1152 events in the store after
  ingest; current-season groups raise 2 review items (the darts duplicate
  conflict below, and the in-play WSDF final held `postponed` until the
  next capture resolves it). An abandoned duplicate darts league
  (`darts-wm-26`, 52 rows stale since Dec 2025) was detected, its fixture
  removed, and discovery now demotes such leagues — `docs/DARTS-AUDIT.md`.

### Engines & integrity
- **Result adapters**: OpenLigaDB ODbL adapter plus a separate
  authorization-gated official-organizer export adapter (contract-tested,
  inactive without written permission). The football-data import adapter
  and manual-snapshot OLBG adapter remain policy-gated. All ingestion is
  idempotent; result/odds source edits are flagged.
- **Settlement engine** with the 7 verification gates, versioned rule, and
  required edge-case behaviour (postponed → pending never a loss;
  cancelled → void; disputed → withheld with anomalies; duplicate tips →
  flagged; source edits → flagged).
- **Walk-forward backtesting with strict time cutoffs**
  (`TimeLeakageError` on post-cutoff reads; cutoff pre-start; entry price =
  earliest snapshot ≤ cutoff; ordering invariance incl. same-start
  tie-breaks tested).
- **Statistics layer** (`northstar/stats.py`): bootstrap 95% CIs, binomial
  tests, and **Holm step-down correction** (Holm 1979) across the PnL
  family (m=11 since 2026-09-22). Applied in the pipeline and rendered per-card on the site.
- **Real source irregularities surfaced, not smoothed**: 13 open anomalies
  in the review queue — 4 DEL matches with impossible result layering, 1
  DEL match with `leagueSeason: null` (normalized + flagged), 2 darts
  matches (PDCPCF 2025 matchID 79962, Price v Littler; PDCWM 2026 matchID
  80237, Littler v Ratajski) with **conflicting duplicate result entries**
  (one real score + stale 0-0 duplicates; found by the 2026-09-20 darts
  audit), and — since the 2026-09-21 capture — 1 Premier League match
  (pl/2026 matchID 86559, Aston Villa v Nottingham Forest, 2026-09-12)
  carrying the same defect: five duplicate `HalfTime 0-0` rows plus three
  `After90Minutes` rows (1-2, 0-0, 0-0); the ingest kept 1-2 as the
  candidate but refuses to grade or rate on it until reviewed
  (<https://api.openligadb.de/getmatchdata/pl/2026/86559>). Flagged events are excluded from rating
  updates and from grading until a human resolves them — a silent
  first-entry read would launder disputed rows into the model.
- **OLBG snapshot kickoffs were wrong by 5 h (found 2026-09-21, now 13 open
  anomalies).** A new reconciliation step (`northstar/reconcile.py`, curated
  table `data/aliases/football_olbg.json`, 10 evidence-linked team aliases)
  cross-checks every manually snapshotted OLBG football event against the
  permitted OpenLigaDB fixture list. All 5 matchable cards (Sevilla v
  Barcelona la1 85402; Man City v Sunderland pl 86573; Leeds v Crystal
  Palace 86572; Bournemouth v Liverpool 86576; Fulham v Man Utd 86577)
  sit exactly 5.0 h *before* the official UTC kickoff: the manual page
  render's "Today 15:00" labels were evidently produced in a UTC−5 locale,
  not UK time, so parsing them as UK local time was wrong. The OLBG rows are
  **not** edited (they are captured evidence); each carries a
  `TIME_CONFLICT` anomaly with both source URLs in the review queue, and
  the reconciliation table is published in `site.json.olbg_reconciliation`.
  Venezia v Lazio and Sporting v Arouca have no permitted fixture source
  and stay `unmatched`. These pending OLBG tips were never gradable anyway
  (no permissioned odds, no official result path) so no PnL is affected.
- **The DEL flags were right (manual corroboration, 2026-09-20).** The two
  keystone finals were re-checked by hand against independent outlets:
  Augsburg 3-2 Ingolstadt on 19.09.2024 was **2-2 after regulation, 1-0 in
  overtime** — kicker, sportal and the
  [official DEL match sheet](https://www.penny-del.org/statistik/spieldetails/19092024_augsburger-panther_gg_erc-ingolstadt_3504)
  agree with the `AfterExtraTime` final our priority rule selected;
  Iserlohn 5-6 Eisbären Berlin on 26.01.2025 was **5-5 after regulation,
  decided in the shootout**
  ([official DEL sheet](https://www.penny-del.org/statistik/spieldetails/26012025_iserlohn-roosters_gg_eisbaeren-berlin_3778),
  [eisbaeren.de](https://www.eisbaeren.de/news/detail/penaltysieg-im-sauerland))
  — matching the `AfterPenalties` final we stored. The DEL official site is
  review evidence only; no bulk collection permission exists for it, so
  OpenLigaDB remains the sole systematic DEL source and identity stays
  `probable`.
- **Automated tests: 262 passing** covering the user-specified matrix —
  postponements, voids, duplicate tips, time leakage, disputed results,
  settlement arithmetic — plus adapter parsing of the real fixtures, the
  27/27 cross-check, policy gates, leaderboard math, walk-forward
  invariants, capture discovery (incl. the darts 404 fallback and the
  upcoming-first priority sort), forward-ledger idempotency/horizon/leak
  tests, and Holm/stats tests. Run: `python -m pytest`.

### Strategies & results (all details + citations: docs/STRATEGIES.md)
- **Eleven football strategies on three markets** on the 27-match pilot.
  1X2 (seven): all negative; best ROI form-value −16.3% (3 bets); worst
  longshot probe −29.2% (27 bets). O/U 2.5 (added 2026-09-21): Poisson
  value desk −0.48 u, ROI −1.9% (25 bets); totals-favourite baseline
  −4.19 u, ROI −15.5% (27 bets). **Asian handicap (added 2026-09-22,
  third settleable market): `ah-poisson-value-v1` +9.835 u, ROI +44.7%,
  strike 68.2% (25 bets, 3 pushes), raw p 0.0055 — the first positive
  result in the repository — and `ah-market-favourite-v1` −1.595 u, ROI
  −6.6%. The Holm family is now m=11 and the AH value desk's
  adjusted p is 0.0605: NOT significant at 5%.** It is the best of 11
  strategies on one 27-match sample (the exact selection effect the
  correction guards against); reported as exploratory, never as an edge.
  No edge is claimed anywhere in this repository.
- **Hockey pilot (prediction-only)**: `hockey-elo-v1` graded on **11
  predictions, 7 hits = 63.6%, mean Brier 0.4737** (two disputed DEL rows
  are excluded from grading — review queue owns them; before exclusion the
  number was 13/9 = 69.2%). **Since 2026-09-22 the naive reference exists:
  `hockey-home-v1` scores 11/17 = 64.7% on the same pool — the Elo desk
  does not beat always-home on this pilot, and its hit rate must never be
  quoted without that context** (both numbers sit well inside each other's
  error bars at this sample size). Hockey **PnL is unavailable by
  construction** (no permissioned odds source): tips are `unsettleable`,
  the leaderboard excludes the desks, never shown as zero. Identity
  `probable` (single source).
- **Darts audit + pilot (prediction-only)**: schema audited on five real
  PDC events (`docs/DARTS-AUDIT.md`) — decisive leg/set counts, round
  groups, entry-lag stats (same-day max 11.73 h → start+12h availability),
  two duplicate-conflict matches, an abandoned duplicate league, and real
  player-name identity splits. `darts-elo-v1` (pre-registered priors K=24,
  MIN_PROB=0.60) produced **0 selections on the cold 2025 pool (141
  matches, max probability 0.551)** — the desk stayed silent rather than
  force bets — and on the **full 423-match 2025–26 pool (eight events, as
  captured 2026-09-20): 48 selections, 39 hits = 81.25%, mean Brier
  0.3489, 0 leak violations**. Same priors throughout; nothing refitted
  after seeing data; 48 graded predictions with no market baseline prove
  the path, not an edge. **Since 2026-09-22 the naive reference exists:
  `darts-listed-first-v1` scores 279/421 = 66.3% — listing order itself
  correlates with winning in this pool (a real data finding; the reason is
  not verified), so the Elo desk's 81.25% is measured against 66.3%, not
  against a coin flip — it clears that bar on this sample, error bars
  and all.** Numbers re-grade at every capture — the site is the live
  view.
- **Forward test is LIVE** (`docs/FORWARD-TEST.md`): 24 frozen calls — 9
  `hockey-elo-v1` (selectivity ≥ 0.55) + 15 `hockey-home-v1` (naive
  baseline, every upcoming game) on real DEL games 2026-09-22 → 09-27
  issued from the committed capture into the append-only ledger; football
  desks dormant by design (MD5 starts 2026-10-09, outside the 10-day issue
  horizon); the darts desks met their first genuinely live event (the
  WSDF 2026 final, in play at capture → held `postponed` for the next
  capture, never guessed) and activate for the next World Championship
  (December 2026). 0 leaks; issuance idempotent across reruns.

### Site & CI
- **Competition leaderboard + tip desk + full bet review + Forward +
  Integrity** rendered on GitHub Pages from `site-data/site.json`:
  verified-profit ranking with review-state demotion, per-tipster tips,
  **all placed and all upcoming bets** reviewable (upcoming now includes
  the forward calls), tipster-style predictions built **only** from stored
  verified statistics with evidence links (the renderer refuses to write a
  prediction when the model/fair/edge trail is missing), the frozen
  forward ledger with per-desk accuracy, and the anomaly/verification-state
  review queue.
- **CI**: `ci.yml` runs tests + fixture re-verification on every PR/push;
  `pages.yml` rebuilds site data and deploys the site payload;
  `capture.yml` (Mondays 06:30 UTC + scoped push trigger) captures
  permitted current-season fixtures, commits them, and re-runs the pipeline
  including forward issuance/grading; `ingest.yml` keeps the older
  full-season verification pass (note: its darts target `PDCWSDF` was found
  empty on 2026-09-20 — discovery in `capture.yml` supersedes it); and
  `olbg-capture-reminder.yml` (Mondays 07:10 UTC, added 2026-09-22) opens
  the **manual** OLBG snapshot checklist issue — it never accesses
  olbg.com; the human follows `docs/OLBG-CAPTURE-RUNBOOK.md`. Since the
  same pass, the site renders the third market (Asian handicap with its
  priced line) and the naive baseline desks alongside every accuracy
  number.

## Hard limitations (do not mistake for bugs)

1. **Sample size.** 27 football matches / 3–27 bets per strategy, 21
   hockey events (11 graded predictions), 423 darts matches (48 graded
   predictions). No number here can
   separate skill from luck; every site card carries the warning. This is
   the single biggest limitation.
2. **Odds are window-close-inferred, not exact.** football-data.co.uk
   gives batch-collected prices (Fri 17:00 UK / Tue 13:00 UK closes) with
   no per-event timestamp; we store the window close as a conservative
   (earlier) bound — no leakage, but not the true trade time.
3. **No active governing-body result feed.** OpenLigaDB is ODbL and
   useful, but community-entered. The official-organizer adapter refuses
   unauthorised exports. Full-season CI captures keep events at `probable`
   until a second source is attached; only the football pilot (dual-source
   27/27) is `verified`.
4. **Three markets only.** `match_winner_3way`,
   `total_goals_over_under_2_5` and (since 2026-09-22)
   `asian_handicap` for football, plus the 2-way match-winner for
   hockey/darts (prediction-only). The AH settlement rule is written and
   tested (quarter-line split, integer push, weighted W/L), but every AH
   number inherits the pilot's sample-size and window-close-inferred-odds
   caveats, and the AH value desk's positive result is not significant
   after correction (see #8). Other OLBG markets (BTTS, correct score,
   each-way, outright) are not settleable here; imported OLBG tips on
   them stay `pending`.
5. **Forward test has no PnL and one weekly heartbeat.** The live forward
   desks grade accuracy/Brier only (no permissioned odds for DEL/darts);
   the capture cadence is weekly (Mondays) plus scoped pushes, so grading
   lags reality by up to a week, and the 10-day issue horizon means desks
   go legitimately dormant during breaks (football MD5, Oct 9).
6. **OLBG is manual-only.** No automated OLBG access exists or is
   permitted (ToS). Its tipster statistics are self-reported and never
   enter PnL. The manual-snapshot path (`data/raw/` + drift detector) is
   built, and since 2026-09-22 has a written weekly protocol
   (`docs/OLBG-CAPTURE-RUNBOOK.md`) plus a Monday reminder workflow that
   opens a checklist issue — but the snapshot itself still depends on a
   human; the reminder does not and must never touch olbg.com.
7. **Odds licensing boundary.** The Odds API connector is permissioned only
   for an active paid-plan customer accepting current terms; this repo has
   no key or response. football-data remains a private/manual fixture.
8. **Multiple comparisons.** 11 PnL strategies (7 on 1X2, 2 on O/U 2.5,
   2 on AH) were run on one 27-match sample, and several share the same
   Poisson model and the same matches. Holm correction is applied: ten
   adjusted p = 1.0; `ah-poisson-value-v1` adjusts to 0.0605 — still
   above 0.05, so **nothing is significant after correction** and every
   pilot result is exploratory, not confirmatory. The raw p = 0.0055 of
   the AH desk is the strongest signal the repo has produced and is
   exactly the kind that most needs the correction before anyone quotes
   it. The design-stage catalog has **not** been run and must never be
   quoted as results.
9. **DST clock-change days.** UK wall times on the two clock-change days
   are refused by `uk_local_to_utc` (ambiguous) rather than guessed. None
   occur in the pilot.
10. **Hockey & darts are single-source.** No independent DEL/PDC
    compilation is attached; identity stays `probable`; accuracy metrics
    are explicitly not verified official outcomes.
11. **Result availability is inferred for hockey and darts — and
    `lastUpdateDateTime` is German local time, not UTC.** DEL rows carry
    end-of-season batch-edit timestamps; darts entry mixes live and
    multi-day batch entry. The audit proved OpenLigaDB's
    `lastUpdateDateTime` carries no timezone and is CET/CEST (a capture at
    20:08:53Z contained a row stamped 22:07:50 — `docs/DARTS-AUDIT.md`
    §3.2); where the pipeline uses it (football availability,
    `retrieved_at_utc` on OpenLigaDB rows) the value is treated as UTC,
    which shifts timestamps 1–2 h *later* — conservative for every
    leakage-relevant read, never earlier — but the mislabel is a known
    caveat and a proper CET/CEST conversion utility is backlog work. The
    adapters release hockey/darts results at start+3h / start+12h —
    *conservative constructions* (a desk cannot know a result before the
    match ends, and +12h covers every observed same-day darts entry),
    documented, never a claim about the source's true availability. For
    batch-entered rows the inference is optimistic relative to the API's
    own edit time — a known, bounded caveat of walk-forward ordering.
12. **11 graded hockey predictions, 48 graded darts predictions and 24
    forward calls are not evidence of skill.** 63.6% on 11 picks and
    81.25% on 48 picks have large binomial error bars (darts 95% ≈
    68–90%). Since 2026-09-22 the naive baselines exist and must be
    quoted alongside: hockey always-home scores 64.7% (the Elo desk does
    not beat it on this pilot), darts listed-first scores 66.3% (the Elo
    desk does beat it, on far fewer selections). There is still no market
    baseline (no permissioned odds), and the forward ledger has graded
    nothing yet. No hockey/darts number may be quoted as profitability.
13. **Darts player identity is only as good as the alias table.** Three
    verified splits are merged via `data/aliases/darts.json` (evidence
    links inside; `northstar/aliases.py` refuses unverified entries).
    Anything not listed still fragments rating history → the desk biases
    toward silence. New splits must be added by a human with a link,
    never by a heuristic.
15. **New football leagues are warm-up only.** pl/bl2/la1 2026/27 feed the
    forward desk's rating history; they are single-source (`probable`)
    and have no odds path. The pl payload already showed the duplicate
    conflicting-result defect (matchID 86559) and 10 matchday-5 fixtures
    without result rows at capture time (held unresolved). No settled
    PnL exists or can exist for them.
16. **O/U 2.5 shares the pilot's sample-size problem** (25–27 bets) and its
    window-close-inferred odds; the Poisson model's league priors
    (1.60/1.30) are generic pre-registered values, not fitted — a
    different prior would move early-season probabilities. Asian handicap
    stays design-only (no push/split rule written).
14. **18 sports stay `verification_blocked`.** Each needs a permissioned
    results path before any strategy may run; the registry and site keep
    them visibly blocked.

## Remaining work, in priority order (next session)

1. **Let the forward test speak.** Watch the Monday captures grade the 24
   frozen hockey calls (9 Elo + 15 home-baseline; and resolve the in-play
   WSDF darts final); football MD5 issues automatically from the
   2026-10-09 window; the next darts World Championship (December 2026)
   becomes the first live darts forward capture via the upcoming-first
   discovery. After ~30 graded calls per desk, add per-desk calibration
   (reliability) plots — still accuracy-only until an odds path exists.
2. **Run the manual OLBG snapshot cadence** (human, ToS-compliant): the
   weekly protocol is written (`docs/OLBG-CAPTURE-RUNBOOK.md`) and the
   Monday reminder workflow opens the checklist issue automatically —
   what remains is a human actually taking the snapshot each week.
   Last completed capture: 2026-09-19; the drift detector and
   pending-tip queue already exist. Only a human can do this step — it
   cannot be automated here.
3. **Scale odds legitimately.** Human manual import of full-season D1
   2024/25 (and more seasons) into `data/imports/` (git-ignored) — the
   ingest path already consumes it; or obtain a licensed provider. Then:
   full-season walk-forward with season-split validation, and PnL-capable
   forward desks.
4. **Hockey identity + odds**: an independent DEL cross-check source (to
   lift identity from `probable`) and a permissioned historical DEL odds
   path (only then may hockey PnL exist).
5. **Darts identity mapping — keep it human.** The alias table exists
   (3 entries); extend it only with an evidence link per entry as new
   PDC payloads arrive (WM 2026 field in December). ✔ done 2026-09-21
   for the splits known today.
6. **More markets.** O/U 2.5 ✔ done 2026-09-21. Asian handicap ✔ done
   2026-09-22 (quarter-line split + integer push written and tested; two
   strategies backtested; line stored on snapshots/tips). Next: BTTS
   (blocked — needs a priced BTTS source; the football-data file carries
   no BTTS columns), then each-way for outright sports once any outright
   data path exists.
7. **Model work**: Poisson totals ✔ done; Dixon-Coles tau correction is
   the natural next member of that family (registry entry exists — the
   AH desk's positive raw p makes an out-of-sample check of the whole
   Poisson family the top model priority once an odds path exists).
   Next: rating decay (registry entry exists), draw-rate calibration —
   each as a new registry hypothesis, never a silent parameter change.
8. **Timezone utility** ✔ `cet_offset_at_utc` landed 2026-09-21 and every
   OpenLigaDB row is cross-checked. Still open: restate
   `retrieved_at_utc`/football availability on exact `lastUpdateDateTime`
   timestamps (today's treatment is conservatively shifted, see
   limitation #11).
9. **DEL2 / CHL hockey extension**: write the period-row schema audit
   (the del2/2026 probe showed HalfTime/After90 labels with scores that
   disagree with the goal list), add a FINAL_KIND rule + anomaly tests,
   then list the shortcuts in `CURRENT_TARGETS`.
10. **Site**: per-tipster sparklines; per-league forward accuracy once the
    four football desks issue; keep the payload free of raw football-data
    rows. Candidate next: a per-card "beats its naive baseline?" flag on
    the accuracy desks (the numbers are already in the payload side by
    side).

## Reproduce everything

```bash
python -m venv .venv && .venv/bin/pip install pytest
python -m pytest                     # 341 tests, offline
python -m northstar.cli run-pipeline --fresh   # rebuild store + site-data/site.json
python -m northstar.cli verify               # re-check fixture hashes + 27/27
node scripts/site-smoke.mjs          # renders the site payload headlessly
```
