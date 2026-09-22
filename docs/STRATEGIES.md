# Strategy research log — hypotheses, citations, priors, honest results

Every strategy in this repository starts as a **research question** with a
cited prior, is written down with its parameters **before** grading
(pre-registered priors — never fitted on the pilot), and is reported
**as-is**, negative results included. The machine-readable catalog lives in
`northstar/registry.py` (rendered in the site's Integrity view); this
document is the human research log behind it.

Status vocabulary: `design-stage` (hypothesis + verification gate written,
no permissioned data path yet) · `pilot-tested` (walk-forward run on
committed real fixtures) · `forward` (frozen live predictions in
`data/forward/ledger.json`, see `docs/FORWARD-TEST.md`).

## Verified references (all re-checked 2026-09-20)

| # | Source | Used for |
|---|---|---|
| R1 | Snowberg & Wolfers, *Explaining the Favorite-Longshot Bias* (NBER WP 15923) — <https://www.nber.org/papers/w15923> | Favourite/longshot mispricing priors |
| R2 | Holm (1979), *A Simple Sequentially Rejective Multiple Test Procedure*, Scand. J. Stat. 6(2), 65–70 — <https://www.jstor.org/stable/4615733> | Multiple-comparisons correction (`northstar/stats.py`) |
| R3 | *Forecasting soccer matches with betting odds: A tale of two markets*, Int. J. Forecasting (2024) — <https://www.sciencedirect.com/science/article/pii/S0169207024000670> | 1X2 market inefficiency / FLB persistence |
| R4 | *Efficiency of the Football Betting Market* (CBS thesis) — <https://research-api.cbs.dk/ws/portalfiles/portal/60750333/237159_final_digital.pdf> | Home-favourite bias; recent-form information undervalued by odds |
| R5 | *Home advantage in professional soccer and betting market efficiency: The role of spectator crowds* — <https://www.researchgate.net/publication/358982251_Home_advantage_in_professional_soccer_and_betting_market_efficiency_The_role_of_spectator_crowds> | Home-advantage mispricing (ghost-games natural experiment) |
| R6 | Swartz & Arce, *New Insights Involving the Home Team Advantage* (SFU) — <https://www.sfu.ca/~tswartz/papers/hca.pdf> | NHL home-ice advantage ≈ 54.5% regular-season win rate |
| R7 | FiveThirtyEight, *How Our Club Soccer Projections Work* — <https://fivethirtyeight.com/features/how-our-club-soccer-projections-work/> | Rating-based match projection design (Elo/SPI family) |
| R8 | Dixon & Coles (1997), *Modelling Association Football Scores and Inefficiencies in the Football Betting Market*, JRSS-C 46(2), 265–280 — <https://research-information.bris.ac.uk/en/publications/modelling-association-football-scores-and-inefficiencies-in-the-f/> (checked 2026-09-21: Bristol record confirms journal/volume/pages) | Poisson goal-model family for totals; attack/defence multipliers × league rates |
| R9 | Hvattum & Arntzen (2010), *Using ELO ratings for match result prediction in association football*, Int. J. Forecasting 26(3), 460–470 — <https://doi.org/10.1016/j.ijforecast.2009.10.002> (checked 2026-09-21: abstract + intro read; cites Maher 1982 as origin of the independent-Poisson attack/defence model) | Elo-covariate prior; literature lineage Maher → Dixon-Coles |
| R10 | football-data.co.uk, *Notes for Football Data* — <https://www.football-data.co.uk/notes.txt> (fetched and read in full 2026-09-22; quoted verbatim in the Market-3 section) | Asian-handicap column semantics (`AHh`, `AvgAHH/AvgAHA`); window-close collection schedule |
| R11 | World Football Elo Ratings, *About Elo Ratings* — <https://www.eloratings.net/about> (fetched 2026-09-22; the goal-difference weighting is quoted verbatim in `strategies/hockey_more.py` and `strategies/darts_more.py`) | Margin-of-victory weighting for Elo updates: "It is increased by half if a game is won by two goals, by 3/4 if a game is won by three goals, and by 3/4 + (N-3)/8 if the game is won by four or more goals, where N is the goal difference." Implemented as g = 1 / 1.5 / (11+margin)/8 |

References motivate hypotheses; **none of them is evidence about this
repository's results**. Our own numbers come only from committed fixtures
(hash-verified, `python -m northstar.cli verify`).

## Football (Bundesliga pilot — 27 matches, dual-source verified)

Thirteen football strategies now ran walk-forward with strict cutoffs, level
1.0-unit
stakes, bootstrap 95% CIs, and Holm correction across the family (m=13,
R2); ten further desks run prediction-only on hockey (7) and darts (3) and
are deliberately excluded from that family (no odds path → no PnL
hypothesis). **Twelve of thirteen are negative; the one positive desk (Asian-handicap
value) is NOT significant after correction (Holm-adjusted p = 0.0715) and
no edge is claimed.** Raw p-values 0.0055–0.9435. Sample size (27 matches
/ 3–27 bets) is the binding limitation (`docs/STATUS.md` #1).

The full 2024/25 Bundesliga season is captured by `capture-pilot` (whole
season, ODbL-1.0, first fetch on the 2026-09-22 capture run) and ingested
as **forward-desk rating history only** (`bl1_warmup`): the same clubs play
in the 2026/27 forward group, so their 2024/25 results legitimately warm
the rating pool. The frozen 27-match PnL pilot is deliberately **pinned to
matchdays 1/10/20** (`cli.FOOTBALL_PILOT_MATCHDAYS`, guarded by
`tests/test_pilot_scope.py`) so the dual-source-verified pilot can never be
silently widened to a single-source season.

### Market 1 — 1X2 (`match_winner_3way`, seven strategies)

| id | research question | prior | rule (pre-registered) | result |
|---|---|---|---|---|
| `market-favourite-v1` | Do bookmaker favourites win often enough to beat the vig? | R1/R3: favourites are *underbet* — the least-losing naive strategy | bet market favourite @ market avg, every match | −5.08 u, ROI −18.8%, strike 48.1% (27 bets), p_raw 0.2675 |
| `market-longshot-v1` | Is the longshot bias strong enough to *fade*? (probe: bet longshots, expect heavy loss) | R1: longshots systematically overbet | bet longest shot every match (baseline probe) | −7.88 u, ROI −29.2%, strike 18.5% (27 bets) — direction as predicted by R1 |
| `elo-edge-v1` | Does a plain rating model find value vs the market average? | R7: rating systems are competitive baselines | Elo K=40, home adv 60 pts, 3-way logistic; bet when model prob − implied ≥ 3% | −2.73 u, ROI −22.8% (12 bets), p_raw 0.5675 |
| `elo-decay-v1` | Do *recency-decayed* Elo ratings find value that plain Elo misses? (same rule, older matches count less) | R7 (rating family) + the standard argument that form decays; half-life 365 d pre-registered | identical to `elo-edge-v1`, but every stored rating relaxes toward the 1500 seed with elapsed time: R_eff(t) = 1500 + (R−1500)·2^(−Δt/365d) | −2.73 u, ROI −22.8% (12 bets, same picks as `elo-edge-v1` — the pilot spans ~7 months, far inside the half-life, so the correction barely moves ratings; the desk will only diverge as the cross-season history pool grows), p_raw 0.5675 |
| `dixon-coles-v1` | Does the Dixon-Coles low-score correction find 1X2 value that the plain Poisson misses? | R8: the independent-Poisson model systematically *understates draw probability* in football; the ρ correction fixes exactly that | league home/away goal rates (generic 1.35/1.15 until ≥10 released), attack/defence multipliers (6-match shrinkage, same as the O/U desk), 1X2 from the bivariate score matrix truncated at 15 goals per side with the paper's τ correction (R8): τ(0,0)=1−λh·λa·ρ, τ(0,1)=1+λh·ρ, τ(1,0)=1+λa·ρ, τ(1,1)=1−ρ, else 1, renormalised — ρ=−0.10 pre-registered; bet the model-argmax with ≥ 3-pt edge over the margin-removed 1X2 price. Pre-registered failure mode: with ρ=−0.1 the cell τ(0,1)=1−0.1·λh goes negative for λh>10 — the desk refuses the match (raise, never clamp); unreachable in real football data (λ≈0–4) | +5.01 u, ROI +38.5%, strike 38.5% (13 bets, 14 no-bets), p_raw 0.475 → **not significant**; the profit is the second-best of 13 on 27 matches — the same selection caveat as the AH desk, and the argmax rule means most of the "edge" comes from picking the favourite where the price is thin. Hypothesis for out-of-sample testing, nothing more |
| `form-value-v1` | Is recent form undervalued by odds? | R4: recent-results information undervalued | last-5 goals-for/against form score vs implied; bet ≥ threshold edge | −0.49 u, ROI −16.3% (3 bets) — best ROI, tiny n; p_raw 0.5525 |
| `home-edge-v1` | Is home advantage mispriced? | R5: bookmakers over-rated home teams absent crowds → home edge can be over- *or* under-priced | bet home when model home prob (form+venue) − implied ≥ threshold | −3.04 u, ROI −30.4% (10 bets), p_raw 0.694 |
| `draw-value-v1` | Are draws systematically overpriced as longshots? | R3/R4: draw odds show negative longshot bias in some samples | bet draw when model draw prob − implied ≥ threshold | −1.32 u, ROI −16.5% (8 bets), p_raw 0.6145 |
| `draw-no-bet-v1` | Does removing the draw outcome (stake refund on draw) beat 1X2 on this sample? | classic tipster construction — treated purely as a testable hypothesis, no external claim | Elo edge on 2-way DNB projection, decisive matches only | −5.20 u, ROI −22.6% (23 bets), p_raw 0.3395 |

### Market 2 — over/under 2.5 goals (`total_goals_over_under_2_5`, added 2026-09-21)

Same 27 verified matches, same football-data pilot file: its `B365>2.5 /
B365<2.5`, `Avg>2.5 / Avg<2.5`, `Max>2.5 / Max<2.5`, `BFE>2.5 / BFE<2.5`
columns (208 snapshots — BFE is blank on four rows), same collection-window
close timestamp as the 1X2 prices, so no new leakage surface. Settlement
rule `settlement.match_outcome_totals`: 90-minute total ≥ 3 → over wins,
≤ 2 → under wins; a half-goal line cannot push and integer lines are
refused (no guessed push rule; rule version at the time:
`nr-settlement-2026-09-21.1`, superseded 2026-09-22 by the AH rule set).
Actual pilot base rate: 13/27 matches over.

| id | research question | prior | rule (pre-registered) | result |
|---|---|---|---|---|
| `poisson-totals-value-v1` | Does a plain independent-Poisson goal model find value in the O/U 2.5 price? | R8/R9 lineage (Maher → Dixon-Coles): league rate × attack × defence | league home/away rates from released matches (generic prior 1.60/1.30 until ≥10 released), team multipliers shrunk with a 6-match prior weight, P(total ≤ 2) Poisson; bet the side with ≥ 3-pt edge over the margin-removed Avg price | −0.48 u, ROI −1.9%, strike 40.0% (25 bets, 2 no-bets), p_raw 0.9435, CI [−0.51, +0.52] — closest to zero of all nine, still not distinguishable from noise |
| `market-totals-favourite-v1` | Baseline: does the market's favoured side of O/U 2.5 beat the vig? | none — reference | always back the margin-removed favourite side of O/U 2.5 | −4.19 u, ROI −15.5%, strike 55.6% (27 bets), p_raw 0.29 |

### Market 3 — Asian handicap (`asian_handicap`, added 2026-09-22)

The pilot file's Asian-handicap columns became the third settleable
market. Column semantics were verified against the source's own key
(R10): `AHh = Market size of handicap (home team)`,
`AvgAHH/AvgAHA = Market average Asian handicap home/away team odds`
(negative AHh handicaps the home team; the away side's handicap is the
mirror). All 27 rows carry a quarter-grid line (−3.25 … +1.75) and all
four permitted price pairs (B365/Avg/Max/BFE = 216 snapshots; Pinnacle
excluded per the source notice, closing columns excluded per the
no-leakage rule).

Settlement rule `settlement.match_outcome_asian_handicap` (rule version
`nr-settlement-2026-09-22.1`): integer lines push (stake refunded, not
counted in turnover); quarter lines split the stake half/half across the
two neighbouring component lines — win+push settles `half_won`
(pnl = ½·stake·(odds−1)), lose+push `half_lost` (pnl = −½·stake), both
push `push`. Lines off the quarter grid are refused — never guessed. The
leaderboard counts half stakes as half a win / half a loss (weighted
strike rate). All 52 pilot settlements of the two desks below were
re-derived independently from the raw CSV bytes (FTHG/FTAG + AHh +
AvgAHH/AvgAHA) during implementation: 0 mismatches.

| id | research question | prior | rule (pre-registered) | result |
|---|---|---|---|---|
| `ah-poisson-value-v1` | Does the Poisson goal model find value in the AH price? | R8/R9 lineage (same goal model as the totals desk, applied to the margin distribution) | full P(win)/P(push)/P(lose) on the priced line (quarter lines blended exactly as they settle); bet the side whose model EV beats the de-margined market EV by ≥ 3% per unit staked, only with positive model EV | **+9.835 u, ROI +44.7%, strike 68.2% (25 bets, 3 pushes), p_raw 0.0055 → Holm-adjusted 0.0715 — NOT significant at 5%** (family m=13). First positive pilot result in the repository; exploratory only. It is the best of 13 strategies on one 27-match sample (exactly the selection effect Holm guards against), its CIs come from the same tiny sample, and it shares the O/U desk's window-close-inferred odds and unfitted generic priors. Treat as a hypothesis for out-of-sample forward testing — which needs a permissioned current-season odds path that does not exist yet. |
| `ah-market-favourite-v1` | Baseline: does the market's favoured side of the AH line beat the vig? | none — reference | always back the margin-removed favourite side of the priced line | −1.595 u, ROI −6.6%, strike 41.7% (27 bets, 3 pushes), p_raw 0.684 |

Forward desk: `elo-favourite-3way-v1` (3-way Elo favourite, frozen live
predictions; dormant at the 2026-09-20 capture because Bundesliga MD5
starts 2026-10-09 — outside the 10-day issue horizon; first calls issue
automatically once MD5 enters the window).

## Ice hockey (DEL — full-season results pilot, prediction-only)

The pilot now grades **the whole committed 2024/25 DEL season**: 428 events
(407 finished results, 428 hash-verified fixtures), re-graded on every
pipeline run. Four match rows are flagged `RESULT_KIND_INCONSISTENT`
(impossible OT layering in the community source) and are held out of
grading by the review queue; the flagged rows are counted in
`docs/FACTS.md`, never smoothed. DEL has **no permissioned odds path** in
this repository, so every hockey desk is prediction-only: accuracy and
Brier, never PnL.

Two outcome refinements matter here. The 2-way desks grade the *final game*
(incl. OT/shootout), but DEL games are won or lost in regulation — the
regulation-time **3-way** (home win / draw / away win) is a better-defined
outcome and is derivable from the stored data without a new source: the
ingest stores the final-priority row and its `resultTypeKind` tells the
story — `After90Minutes` means the stored scoreline **is** regulation;
`AfterExtraTime`/`AfterPenalties` mean regulation was drawn
(`evaluation.regulation_outcome`). A regulation draw that then loses in OT
or the shootout is a **hit** for a regulation-draw call, never a 2-way miss
— the forward grader and the walk-forward both resolve it this way
(`docs/FORWARD-TEST.md`). The totals desks grade the binary over/under 5.5
line on the final scoreline (`evaluation.totals_outcome`).

| id | research question | prior | rule | result (full DEL 2024/25 season) |
|---|---|---|---|---|
| `hockey-elo-v1` | Does a 2-way Elo (incl. OT/shootout) beat a coin flip on DEL? | R6: home-ice ≈ 54.5% → venue matters but is modest; rating-family prior R7 | Elo K=32, home adv 35 pts, 2-way; selectivity ≥ 0.55 | **243 graded, 66.3%, Brier 0.4462** — clears the always-home baseline (59.8%) |
| `hockey-home-v1` | What does "always predict home" score on the same pool? (no-information reference) | none — deliberate naive baseline, flat 0.5/0.5 prior (Brier 0.5 by construction) | always HOME | 323 graded, 59.8%, Brier 0.5000 |
| `hockey-reg-poisson-v1` | Does a goal-rate model beat the naive baseline on the better-defined **regulation 3-way**? | R8 lineage (Maher → Dixon-Coles, independent Poisson; draws are *expected* here, not an artefact); league regulation rates 3.1/2.9 generic until ≥10 released; 6-match shrinkage | P(reg home/draw/away) from the independent-Poisson matrix; always issue the argmax | **323 graded, 64.7%, Brier 0.4883** — clears its regulation baseline (59.4%) |
| `hockey-reg-home-v1` | The no-information reference for the regulation 3-way (always-home) | none — flat 0.50/0.25/0.25 prior, only the hit rate is a reference | always HOME on the regulation 3-way | 323 graded, 59.4%, Brier 0.5062 |
| `hockey-elo-mov-v1` | Does the **size** of a win carry information the plain W/L update throws away? | R11 World-Football-Elo margin weights, applied with the hockey Elo constants | same model as `hockey-elo-v1`, update scaled by g = 1 / 1.5 / (11+margin)/8 | **255 graded, 65.5%, Brier 0.4540 — does *not* beat plain Elo (66.3%)**; the refinement found nothing on this pool |
| `hockey-totals-poisson-v1` | Does the football totals model transfer to DEL **total goals**? | R8 lineage, explicit cross-sport transfer test; generic prior 3.1/2.9 until ≥10 released | P(total ≥ 6) vs P(total ≤ 5); states a side for every match (no selectivity) | **323 graded, 52.3%, Brier 0.5153 — *below* the always-over baseline (53.6%)**; reported as negative |
| `hockey-totals-over-v1` | Reference point for the totals market: how often does the 5.5 line go over? | none — flat 0.5/0.5 prior (Brier 0.5) | always OVER 5.5 | 323 graded, 53.6%, Brier 0.5000 |

Forward desks (live): **seven** desks issue on the same DEL 2026/27 fixture
window — as of the 2026-09-22 capture the ledger holds **263 frozen calls**
(33 Elo, 32 MoV Elo, 40 home baseline, 40 regulation home, 40 regulation
Poisson, 39 totals Poisson, 39 totals-over), 0 graded, 0 overdue, 0 leaks;
each call freezes its desk's outcome mode. They warm from earlier-season
history when it is committed (the whole del/2024 season, leak-audited). The
graded history is not evidence of skill (`docs/STATUS.md` #12); the forward
test is what will speak, and the full-season numbers above stay attached to
their sample sizes.

## Full-season football accuracy desks (added 2026-09-22, pass 3)

The frozen PnL pilot is 27 matches; the whole 2024/25 Bundesliga season
(306 finished results, OpenLigaDB ODbL) is committed for rating warm-up.
These four desks therefore run over **all 306** matches and read **no odds
at all** — accuracy and Brier only, no PnL, no Holm membership. They are
the same pre-registered models as the pilot and forward desks: this block
buys sample size, not a new hypothesis.

| desk | rule (pre-registered) | result |
|---|---|---|
| `elo-favourite-3way-v1` | the forward desk's 3-way Elo argmax with its 45% selectivity floor | **52.1% on 167 calls**, Brier 0.611 |
| `football-home-baseline-v1` | always home, flat 0.50/0.25/0.25 prior (uninformative by design) | 38.6% on 306 — the Elo desk clears it |
| `football-totals-poisson-v1` | the pilot's Poisson construction with no price input: more likely side of the 2.5 line for every match | **61.1% on 306**, Brier 0.471 |
| `football-totals-over-v1` | always over 2.5, flat 0.5/0.5 (Brier 0.5 by construction) | 59.8% on 306 — the model clears it by 1.3 points |

Both margins are thin, both pools are single-source (`probable`), and
neither carries a significance claim: a 1.3-point accuracy edge on one
season is exactly the size of effect that noise produces. They are listed
because the request is for tested strategies, and a pre-registered desk
that fails to clear its baseline is a result too.

## Second-generation prediction desks (added 2026-09-22)

All four live on **already committed** ODbL result fixtures — no new source,
no new licence question, no refit. Each states its prior before grading and
each carries a naive baseline so no accuracy number is quoted alone.

### Ice hockey — margin-of-victory Elo (`hockey-elo-mov-v1`)

*Question:* does the *size* of a win carry information the plain W/L Elo
update discards? *Prior:* margin-scaled Elo is a standard refinement (R9),
with the World-Football-Elo weights quoted in R11. *Rule (pre-registered):*
identical expected-score function and home advantage to `hockey-elo-v1`,
update scaled by `K × g` with `g = 1 / 1.5 / (11+margin)/8`.
*Result (whole DEL 2024/25 season, single-source `probable`, no odds path):*
**65.5% on 255 calls, Brier 0.454** — *lower* than plain Elo's 66.3% on 243
calls and above the always-home baseline (59.8%). Reported as-is: on this
pool the refinement found nothing.

### Ice hockey — total goals over/under 5.5 (`hockey-totals-poisson-v1`)

*Question:* does the Maher → Dixon-Coles independent-Poisson totals model
transfer from football to DEL total goals? *Prior:* the Poisson family is
this repository's only cited goal model (R8/R9); this is an explicit
cross-sport transfer test, so no hockey-specific fitted prior is claimed.
*Rule (pre-registered):* the same league-rate + shrunk attack/defence
construction as the regulation 3-way desk (generic prior 3.1/2.9 until ≥ 10
released matches), then P(total ≥ 6) vs P(total ≤ 5); the desk states the
more likely side of the **5.5** line for *every* match, which is what makes
it comparable to `hockey-totals-over-v1` (always over, flat 0.5/0.5 prior).
This is the repository's **second prediction-only market**
(`total_goals_over_under_5_5`), graded through a new binary-outcome path in
`northstar/evaluation.py` and frozen into the forward ledger the same way.
*Result:* the desk grades **52.3% (Brier 0.515)** — **below** the always-over
baseline's **53.6% (Brier 0.5 by construction)**. On this season the model
did not beat "always over"; the full-season verdict stands as reported, and
no PnL exists either way (no odds path).

### Darts — margin-of-victory Elo (`darts-mov-elo-v1`)

*Question:* the same question as the hockey MoV desk, on the PDC pool.
*Prior:* identical weights (R11). *Stated weakness (not hidden):* the margin
unit differs by event format (legs in ProTour/EuroTour, sets in World
Championships) and the source does not label which unit a row carries; the
desk therefore uses the raw stored count difference, and says so in every
prediction's model trail. *Result:* **78.4% on 111 calls, Brier 0.358** —
more selections than the plain darts desk (48 calls, 81.25%) at lower
accuracy, still well above the listed-first baseline (66.3% on 421). No
PnL is possible for darts in this repository.

## Darts (PDC — audited 2026-09-20, prediction-only)

| id | research question | prior | rule | result |
|---|---|---|---|---|
| `darts-elo-v1` | Does a player-level Elo select winners in PDC knockouts? | individual-sport Elo conventions; HOME_ADV=0 (listed-first is presentation order); K=24, MIN_PROB=0.60 — priors stated before grading | 2-way player Elo on the decisive leg/set count; select when prob ≥ 0.60; availability start+12h (audit-derived) | **Cold 2025 pool (141 matches): 0 selections** — max observed probability 0.551; the desk stayed silent rather than force bets. **Full pool as captured 2026-09-20 (423 matches, eight events): 48 selections, 39 hits = 81.25%, Brier 0.3489, 0 leaks** — same priors, no refit; large error bar (95% ≈ 68–90%) and no market baseline, so no skill or PnL claim. Full audit: `docs/DARTS-AUDIT.md`. |
| `darts-mov-elo-v1` | Does the **margin** of a darts win (legs/sets) carry information the plain W/L Elo update discards? | R11 margin weights, applied with the darts Elo constants (K=24, no venue adjustment) | update scaled by g = 1 / 1.5 / (11+margin)/8 on the raw stored count difference (units differ by event format — stated weakness, recorded in every prediction trail) | **111 graded, 78.4%, Brier 0.3575** — more selections than `darts-elo-v1` (48) at *lower* accuracy, still above the listed-first baseline (66.3%) |
| `darts-listed-first-v1` | Does listing order carry any signal? (no-information reference, added 2026-09-22) | none — deliberate naive baseline, flat 0.5/0.5 prior (Brier 0.5 by construction); the audit found listed-first is presentation order | predict the listed-first player every eligible match | **421 graded, 279 hits = 66.3%** — listing order correlates with winning in this pool (a genuine data finding; why — e.g. whether the source lists the favourite/seed first — is **not** verified). This is why the Elo desk's 81.25% must be compared against 66.3%, not against 50%; the Elo desk does clear that bar on this sample, with all the error-bar caveats above. |

Known darts limitations found by the audit: player-name identity splits
(`R. van Barneveld` vs `Raymond van Barneveld`, `Mickey/Michael Mansell`)
fragment the rating pool; we do not auto-merge names without a curated
mapping. An abandoned duplicate league (`darts-wm-26`, 52 rows stale since
December 2025, duplicating the complete `PDCWM`) was detected, removed and
excluded by discovery rule; two matches with conflicting duplicate result
entries (matchIDs 79962, 80237) are excluded from grading until reviewed.
Forward desks (both darts desks, added 2026-09-22) activate when an
upcoming event — realistically the next World Championship, December 2026
— enters the 10-day horizon.

## Design-stage hypotheses (21-sport catalog, verification-gated)

`northstar/registry.py` carries the full OLBG sport-family catalog: each
blocked sport has an explicit `verification_blocked` state naming the
missing permissioned data path (18 sports today — e.g. horse racing needs
official results + bookmaker odds; cricket/snooker/MMA need an ODbL or
licensed results feed). Design-stage strategy sketches exist for sports
whose result schemas we can already read (e.g. tennis/match-winner Elo once
a permissioned feed exists). **Nothing in this section has been graded on
any data, and nothing may be rendered as a result until its verification
gate passes** — that ordering is enforced in code (registry → site) and is
the repository's core anti-hallucination rule.

## Multiple comparisons & reporting rules

- Holm step-down (R2) across the PnL-capable family (m=13 football
  strategies since 2026-09-22: 9 × 1X2 + 2 × O/U 2.5 + 2 × AH).
  Adjusted p-values: all 1.0 except `ah-poisson-value-v1` at 0.0715 —
  still above 0.05, so **nothing is significant after correction**.
  (Adding the two 1X2 desks grew the family from 11 to 13, which *raised*
  the AH desk's adjusted p from 0.0605 to 0.0715 — the correction doing
  exactly what it is for.) Implementation + tests: `northstar/stats.py`,
  `tests/test_stats.py`.
- Prediction-only desks (hockey incl. the regulation 3-way pair, darts —
  models and naive baselines) are excluded from the PnL family (they have
  no PnL) and report accuracy/Brier with explicit `pnl_available: false`.
- Every quoted number on the site carries its sample-size warning; CIs are
  bootstrap over the settled sequence; unavailable ≠ zero everywhere.
- The repo's reporting rule for the AH desk, stated once and binding: a
  raw p below 0.05 in a family of 13 on one 27-match sample is an
  exploratory signal, never a claim. Only out-of-sample forward grading
  (which needs a permissioned odds path) can promote it.
