# Status, limitations & remaining work

**Updated 2026-09-22 (hockey schema audit + exact-CET + baseline-flag pass).**
Changes in this pass: the DEL2/CHL period-row schema audit
(`docs/HOCKEY-SCHEMA-AUDIT.md`; both probe slices committed and
fixture-verified) produced the `goals_vs_results` rule — a
goal-list-vs-rows cross-check whose goal-list final is the running-score
**maximum** (goal rows arrive out of chronological order) — plus
`inconsistency_reason` and goal-list evidence on every
`RESULT_KIND_INCONSISTENT` flag (review queue 140 → **141 open**,
including the new del/2024 matchID 76236 rows-vs-goal-list finding);
`cet_local_to_utc` settles the CET/CEST timestamp question (the DARTS-AUDIT
§3.2 proof case): `retrieved_at_utc` **and football availability** now use
the exact `lastUpdateDateTime` instant (previously the stamp was parsed as
UTC and released results 1–2 h late), and the entry-lag bounds behind the
`start+3h`/`start+12h` hockey/darts constructions are restated on exact
stamps; `CURRENT_TARGETS` grows DEL2 + CHL (2026, audited shortcuts); and
every accuracy card on the site gains the "beats its naive baseline?" flag
(`NAIVE_BASELINE_FOR` + `naive_baseline_comparison` — point estimates on
their own graded pools, never evidence of skill). Test count 423.

**Prior pass (2026-09-22, fourth-strategy-family + whole-season + history
warm-up).**
Changes in this pass: two football desks — the **Dixon-Coles 1X2 value
desk** (`dixon-coles-v1`, +5.01 u / ROI +38.5% on 13 bets, p_raw 0.475,
*not* significant; the low-score draw correction is a pre-registered R8
hypothesis with a pre-registered failure mode) and the **recency-decay
Elo control** (`elo-decay-v1`, ratings relax toward 1500 with a 365-day
half-life; reproduces plain Elo's picks on this ~7-month sample) — grew the
Holm family to **m=13**, which *raised* the AH desk's adjusted p to 0.0715
(still not significant). Hockey gained the **regulation-time 3-way**: the
3-period outcome is derivable from the stored final row's kind (a
regulation draw that loses in OT/SO is a hit for a regulation-draw call),
and two desks run on it — `hockey-reg-poisson-v1` (47.1% on the 21-event
slice, *below* the new always-home 3-way baseline `hockey-reg-home-v1` at
64.7%; reported as-is, full season is the pre-registered verdict) plus the
baseline. The pilot data is widening: `capture-pilot` commits the **whole
2024/25 DEL and bl1 seasons** (hash-verified, fetched once and frozen),
the bl1 season warms the forward Elo pool as cross-season history (leak-
audited, refused loudly on any data bug), and the hockey desks re-grade on
the full season automatically. Forward ledger now carries the per-call
outcome mode and **63 frozen DEL calls**. (Test count then: 383.)

**Prior pass (2026-09-22):** the Asian handicap became the third
settleable football market (settlement rule written and tested, all 52
pilot settlements re-derived independently from the raw CSV with 0
mismatches); `ah-poisson-value-v1` (+9.835 u, ROI +44.7%) — the first
positive result in the repo, reported strictly as exploratory; naive
baselines for the prediction-only sports; the weekly **manual OLBG capture
cadence** runbook + reminder workflow (never touches olbg.com).
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
  per the source's own 2025-07-23 notice). Since this pass the **whole
  2024/25 seasons** of both leagues are also committed
  (`openligadb_bl1_2024.json`, `openligadb_del_2024.json`, captured by
  `capture-pilot`, hash-verified, `.meta.json` sidecars): the bl1 season
  is forward-desk rating history only — the frozen 27-match PnL pilot is
  **pinned to matchdays 1/10/20** in code + test so it can never silently
  widen — while the DEL season widens the hockey prediction pilot, which
  is single-source and has no PnL to protect.
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
  trigger), committed by the workflow bot. 2218 events in the store after
  the full ingest as of the 2026-09-22 capture (football pilot + whole-
  season pilots + current season; grows as the current season plays);
  current-season groups raise review items (the darts duplicate conflict
  below, and the in-play WSDF final held `postponed` until the next
  capture resolves it). An abandoned duplicate darts league
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
  family (m=13 since 2026-09-22: 9 × 1X2 + 2 × O/U 2.5 + 2 × AH). Applied in
  the pipeline and rendered per-card on the site.
- **Real source irregularities surfaced, not smoothed**: 141 open anomalies
  in the review queue — 83 DEL matches with impossible result layering
  (del/2024 rows whose regulation score is marked decisive while an
  overtime/shootout row exists), 1 DEL match whose period rows disagree
  with its goal list (del/2024 matchID 76236; quarantined by the new
  `goals_vs_results` rule — docs/HOCKEY-SCHEMA-AUDIT.md), 3
  duplicate-conflict events: 2 darts
  matches (PDCPCF 2025 matchID 79962, Price v Littler; PDCWM 2026 matchID
  80237, Littler v Ratajski) with **conflicting duplicate result entries**
  (one real score + stale 0-0 duplicates; found by the 2026-09-20 darts
  audit), and — since the 2026-09-21 capture — 1 Premier League match
  (pl/2026 matchID 86559, Aston Villa v Nottingham Forest, 2026-09-12)
  carrying the same defect: five duplicate `HalfTime 0-0` rows plus three
  `After90Minutes` rows (1-2, 0-0, 0-0); the ingest kept 1-2 as the
  candidate but refuses to grade or rate on it until reviewed
  (<https://api.openligadb.de/getmatchdata/pl/2026/86559>) — its goal list
  (1-1) now documents which duplicate the goals support, appended to the
  flag detail, 1 DEL match with `leagueSeason: null` (normalized +
  flagged), 48 `SOURCE_EDITED` rows whose source copy changed on re-fetch
  (the queue owns every diff; history is append-only), and 5 OLBG
  `TIME_CONFLICT` kickoff offsets (below).
  Flagged events are excluded from rating
  updates and from grading until a human resolves them — a silent
  first-entry read would launder disputed rows into the model.
- **OLBG snapshot kickoffs were wrong by 5 h (found 2026-09-21; the 5
  `TIME_CONFLICT` rows of the review queue).** A new reconciliation step (`northstar/reconcile.py`, curated
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
- **Automated tests: 423 passing** covering the user-specified matrix —
  postponements, voids, duplicate tips, time leakage, disputed results,
  settlement arithmetic — plus adapter parsing of the real fixtures, the
  27/27 cross-check, policy gates, leaderboard math, walk-forward
  invariants, capture discovery (incl. the darts 404 fallback and the
  upcoming-first priority sort), forward-ledger idempotency/horizon/leak
  tests, and Holm/stats tests — since 2026-09-22 also the hockey
  period-row schema rules (`goals_vs_results`, out-of-order goal rows,
  the DEL2/CHL probe slices), the CET/CEST conversion incl. DST edge
  cases and full-fixture round-trips, and the naive-baseline comparison.
  Run: `python -m pytest`.

### Strategies & results (all details + citations: docs/STRATEGIES.md)
- **Thirteen football strategies on three markets** on the 27-match pilot.
  1X2 (nine): all negative except the new `dixon-coles-v1` at +5.01 u /
  ROI +38.5% (13 bets) which is p_raw 0.475 — not significant and the
  second-best of 13 on 27 matches (selection caveat as below); the
  recency-decay Elo control (`elo-decay-v1`) reproduces plain Elo's picks
  exactly on this ~7-month sample (−2.73 u, 12 bets) as pre-registered.
  Best ROI form-value −16.3% (3 bets); worst longshot probe −29.2%
  (27 bets). O/U 2.5 (added 2026-09-21): Poisson value desk −0.48 u,
  ROI −1.9% (25 bets); totals-favourite baseline −4.19 u, ROI −15.5%
  (27 bets). **Asian handicap (added 2026-09-22, third settleable market):
  `ah-poisson-value-v1` +9.835 u, ROI +44.7%, strike 68.2% (25 bets, 3
  pushes), raw p 0.0055 — the first positive result in the repository —
  and `ah-market-favourite-v1` −1.595 u, ROI −6.6%. The Holm family is
  now m=13 and the AH value desk's adjusted p is 0.0715 (grew from 0.0605
  when the two 1X2 desks joined the family): NOT significant at 5%.** It
  is the best of 13 strategies on one 27-match sample (the exact selection
  effect the correction guards against); reported as exploratory, never as
  an edge. No edge is claimed anywhere in this repository.
- **Hockey pilot (prediction-only)**: `hockey-elo-v1` graded on **11
  predictions, 7 hits = 63.6%, mean Brier 0.4737** (two disputed DEL rows
  are excluded from grading — review queue owns them; before exclusion the
  number was 13/9 = 69.2%). **Since 2026-09-22 the naive reference exists:
  `hockey-home-v1` scores 11/17 = 64.7% on the same pool — the Elo desk
  does not beat always-home on this pilot, and its hit rate must never be
  quoted without that context** (both numbers sit well inside each other's
  error bars at this sample size). **Since 2026-09-22 the regulation-time
  3-way is a first-class outcome** (derivable from the stored final row's
  `resultTypeKind` — `evaluation.regulation_outcome`): `hockey-reg-poisson-
  v1` grades **8/17 = 47.1%, Brier 0.5672** on the 21-event slice — *below*
  the new always-home 3-way baseline `hockey-reg-home-v1` (11/17 = 64.7%,
  Brier 0.5) — and is reported as-is; the pre-registered next step is the
  full-season run, and the desk stands or falls on it. The pilot itself is
  widening: `capture-pilot` commits the whole 2024/25 DEL season (first CI
  fetch; local runs stay on the 21-event slice until then) and the pipeline
  re-grades on all of it — no code change needed. Hockey **PnL is
  unavailable by construction** (no permissioned odds source): tips are
  `unsettleable`, the leaderboard excludes the desks, never shown as zero.
  Identity `probable` (single source).
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
- **Forward test is LIVE** (`docs/FORWARD-TEST.md`): **63 frozen calls**
  — `hockey-elo-v1` (15, selectivity ≥ 0.55) + `hockey-home-v1`,
  `hockey-reg-home-v1`, `hockey-reg-poisson-v1` (16 each, no selectivity)
  on real DEL games 2026-09-22 → 09-27, issued from the committed capture
  into the append-only ledger; every entry now freezes the desk's **outcome
  mode** (`final` vs `regulation_3way`), so the regulation desks grade the
  3-period result (a regulation draw that loses in OT/SO is a hit).
  Desks warm from **cross-season history** (added this pass): finished
  earlier-season same-league events, released at their own availability
  times, leak-audited, and refused loudly if any starts at/after `as_of`.
  The bl1 desk already sees 27 released 2024/25 history events (the whole
  season lands via CI and widens to ~560). Football desks dormant by design
  (MD5 starts 2026-10-09, outside the 10-day issue horizon); the darts
  desks met their first genuinely live event (the WSDF 2026 final, in play
  at capture → held `postponed` for the next capture, never guessed) and
  activate for the next World Championship (December 2026). 0 leaks;
  issuance idempotent across reruns.

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
  number — since 2026-09-22 each accuracy card also carries a "beats its
  naive baseline?" flag with the point-estimate caveat (own graded pools;
  error bars overlap at these sample sizes; never evidence of skill).

## Hard limitations (do not mistake for bugs)

1. **Sample size.** 27 *dual-source-verified* football matches / 3–27 bets
   per strategy, 21 hockey events (11 graded predictions) *on the local
   slice* — the committed whole 2024/25 DEL season widens the hockey pilot
   automatically at the next CI capture (and the bl1 whole season widens
   the forward Elo pool, not the frozen 27-match PnL pilot, which is
   matchday-pinned) — and 423 darts matches (48 graded predictions). No
   number here can separate skill from luck; every site card carries the
   warning. This is the single biggest limitation.
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
8. **Multiple comparisons.** 13 PnL strategies (9 on 1X2, 2 on O/U 2.5,
   2 on AH) were run on one 27-match sample, and several share the same
   Poisson model and the same matches. Holm correction is applied: twelve
   adjusted p = 1.0; `ah-poisson-value-v1` adjusts to 0.0715 (the family
   grew from 11 to 13 this pass, which *raised* the adjusted p from
   0.0605) — still above 0.05, so **nothing is significant after
   correction** and every pilot result is exploratory, not confirmatory.
   The raw p = 0.0055 of the AH desk is the strongest signal the repo has
   produced and is exactly the kind that most needs the correction before
   anyone quotes it. The design-stage catalog has **not** been run and
   must never be quoted as results.
9. **DST clock-change days.** UK wall times on the two clock-change days
   are refused by `uk_local_to_utc` (ambiguous) rather than guessed. None
   occur in the pilot.
10. **Hockey & darts are single-source.** No independent DEL/PDC
    compilation is attached; identity stays `probable`; accuracy metrics
    are explicitly not verified official outcomes.
11. **Result availability is inferred for hockey and darts.** DEL rows carry
    end-of-season batch-edit timestamps; darts entry mixes live and
    multi-day batch entry. The audit proved OpenLigaDB's
    `lastUpdateDateTime` carries no timezone and is CET/CEST (a capture at
    20:08:53Z contained a row stamped 22:07:50 — `docs/DARTS-AUDIT.md`
    §3.2). *Settled 2026-09-22:* `timeutil.cet_local_to_utc` converts the
    stamps exactly (fold→later reading, gap→later algebraic, aware input
    passes through) and ingest stores `retrieved_at_utc` on it — previously
    the value was treated as UTC, shifting timestamps 1–2 h later
    (conservative for every leakage-relevant read, but lossy). The
    entry-lag bounds behind the availability inferences are restated on
    exact stamps in `docs/HOCKEY-SCHEMA-AUDIT.md` §5 (bl1/2024 same-evening
    entries land ≥1.82 h after kickoff, del/2024 same-evening ≥2.16 h).
    Football availability is the row's exact `lastUpdateDateTime` instant
    (`availability_for` converts with `cet_local_to_utc` since 2026-09-22;
    the stamp used to be parsed as UTC and released results 1–2 h late).
    The
    adapters release hockey/darts results at start+3h / start+12h —
    *conservative constructions* (a desk cannot know a result before the
    match ends, and +12h covers every observed same-day darts entry),
    documented, never a claim about the source's true availability. For
    batch-entered rows the inference is optimistic relative to the API's
    own edit time — a known, bounded caveat of walk-forward ordering.
12. **17 graded hockey predictions per desk, 48 graded darts predictions
    and 63 forward calls are not evidence of skill.** 63.6% on 11 picks
    and 81.25% on 48 picks have large binomial error bars (darts 95% ≈
    68–90%). Since 2026-09-22 the naive baselines exist and must be
    quoted alongside: hockey always-home (2-way) scores 64.7% (the Elo
    desk does not beat it on this pilot), the always-home regulation
    3-way scores 64.7% (the Poisson regulation desk scores 47.1% — below
    its baseline on this slice; the full season is the pre-registered
    verdict), darts listed-first scores 66.3% (the Elo desk does beat it,
    on far fewer selections). There is still no market baseline (no
    permissioned odds), and the forward ledger has graded nothing yet. No
    hockey/darts number may be quoted as profitability.
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
16. **Goal-model desks share the pilot's sample-size problem** (13–27
    bets) and its window-close-inferred odds; the Poisson/Dixon-Coles
    league priors (O/U 1.60/1.30, 1X2 1.35/1.15, hockey 3.1/2.9) are
    generic pre-registered values, not fitted — a different prior would
    move early-season probabilities, and the cold-start slice (first
    ~10 matches at generic rates) is exactly where `hockey-reg-poisson-
    v1` currently under-performs its baseline. The Dixon-Coles ρ=−0.10 is
    likewise pre-registered (R8), with a documented failure mode: a
    negative score cell makes the desk refuse the match rather than
    clamp.
14. **18 sports stay `verification_blocked`.** Each needs a permissioned
    results path before any strategy may run; the registry and site keep
    them visibly blocked.

## Remaining work, in priority order (next session)

1. **Let the forward test speak.** Watch the Monday captures grade the 63
   frozen DEL calls (15 Elo + 16 home + 16 regulation-home + 16
   regulation-Poisson; and resolve the in-play WSDF darts final); the
   regulation 3-way desks grade the 3-period outcome — a regulation draw
   that loses in OT/SO counts as a hit; football MD5 issues automatically
   from the 2026-10-09 window, warmed by the whole 2024/25 season; the
   next darts World Championship (December 2026) becomes the first live
   darts forward capture via the upcoming-first discovery. After ~30
   graded calls per desk, add per-desk calibration (reliability) plots —
   still accuracy-only until an odds path exists. Also verify that the
   CI-fetched whole DEL season widens the hockey pilot as designed (local
   runs stay on the 21-event slice; the kv flag `hockey_pilot_full_season`
   drives the site wording).
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
7. **Model work**: Poisson totals ✔ done; Dixon-Coles tau correction
   ✔ done 2026-09-22 (`dixon-coles-v1`, ρ=−0.10 pre-registered, +5.01 u /
   p_raw 0.475 — not significant; negative-cell refusal tested); rating
   decay ✔ done 2026-09-22 (`elo-decay-v1`, 365-day half-life control,
   identical picks to plain Elo on this sample — expected). The AH desk's
   positive raw p makes an out-of-sample check of the whole Poisson
   family the top model priority once an odds path exists. Next: draw-rate
   calibration, hockey regulation draw-rate prior — each as a new registry
   hypothesis, never a silent parameter change.
8. **Timezone utility** ✔ `cet_offset_at_utc` landed 2026-09-21 and every
   OpenLigaDB row is cross-checked. ✔ done 2026-09-22 (this pass):
   `cet_local_to_utc` (CET/CEST, exact) lands in
   `northstar/timeutil.py` with the fold/gap rules above and is wired into
   ingest: `retrieved_at_utc` and football availability are both restated
   on exact `lastUpdateDateTime` stamps (`availability_for` no longer
   parses the stamp as UTC), and the hockey/darts entry-lag bounds behind
   `start+3h`/`start+12h` are restated on exact stamps
   (docs/HOCKEY-SCHEMA-AUDIT.md §5).
9. **DEL2 / CHL hockey extension** ✔ done 2026-09-22 (this pass): the
   period-row schema audit is `docs/HOCKEY-SCHEMA-AUDIT.md` (DEL2 vs CHL
   probe slices committed and fixture-verified), the goal-list-vs-rows
   `goals_vs_results` rule + anomaly tests land in `parse_matchday`
   (goal-list final = running-score maximum, goal rows arrive out of
   order), and `CURRENT_TARGETS` lists `DEL2` + `CHL` (2026).
10. **Site**: per-tipster sparklines; per-league forward accuracy once the
   four football desks issue; keep the payload free of raw football-data
   rows. ✔ done 2026-09-22 (this pass): the per-card "beats its naive
   baseline?" flag on the accuracy desks (`NAIVE_BASELINE_FOR`,
   `naive_baseline_comparison`) renders with the point-estimate caveat.

## Reproduce everything

```bash
python -m venv .venv && .venv/bin/pip install pytest
python -m pytest                     # 423 tests, offline
python -m northstar.cli run-pipeline --fresh   # rebuild store + site-data/site.json
python -m northstar.cli verify               # re-check fixture hashes + 27/27
python -m northstar.cli capture-pilot --out data/fixtures   # fetch+frozen whole-season pilots (network)
node scripts/site-smoke.mjs          # renders the site payload headlessly
```
