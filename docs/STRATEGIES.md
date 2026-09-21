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

References motivate hypotheses; **none of them is evidence about this
repository's results**. Our own numbers come only from committed fixtures
(hash-verified, `python -m northstar.cli verify`).

## Football (Bundesliga pilot — 27 matches, dual-source verified)

All nine ran walk-forward with strict cutoffs, level 1.0-unit stakes,
bootstrap 95% CIs, and Holm correction across the family (m=9, R2).
**All nine are negative; every Holm-adjusted p-value is 1.0; no edge is
claimed.** Raw p-values 0.2675–0.9435 — nothing is remotely significant, in
either direction. Sample size (27 matches / 3–27 bets) is the binding
limitation (`docs/STATUS.md` #1).

### Market 1 — 1X2 (`match_winner_3way`, seven strategies)

| id | research question | prior | rule (pre-registered) | result |
|---|---|---|---|---|
| `market-favourite-v1` | Do bookmaker favourites win often enough to beat the vig? | R1/R3: favourites are *underbet* — the least-losing naive strategy | bet market favourite @ market avg, every match | −5.08 u, ROI −18.8%, strike 48.1% (27 bets), p_raw 0.2675 |
| `market-longshot-v1` | Is the longshot bias strong enough to *fade*? (probe: bet longshots, expect heavy loss) | R1: longshots systematically overbet | bet longest shot every match (baseline probe) | −7.88 u, ROI −29.2%, strike 18.5% (27 bets) — direction as predicted by R1 |
| `elo-edge-v1` | Does a plain rating model find value vs the market average? | R7: rating systems are competitive baselines | Elo K=40, home adv 60 pts, 3-way logistic; bet when model prob − implied ≥ 3% | −2.73 u, ROI −22.8% (12 bets), p_raw 0.5675 |
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
refused (no guessed push rule). Rule version bumped to
`nr-settlement-2026-09-21.1`. Actual pilot base rate: 13/27 matches over.

| id | research question | prior | rule (pre-registered) | result |
|---|---|---|---|---|
| `poisson-totals-value-v1` | Does a plain independent-Poisson goal model find value in the O/U 2.5 price? | R8/R9 lineage (Maher → Dixon-Coles): league rate × attack × defence | league home/away rates from released matches (generic prior 1.60/1.30 until ≥10 released), team multipliers shrunk with a 6-match prior weight, P(total ≤ 2) Poisson; bet the side with ≥ 3-pt edge over the margin-removed Avg price | −0.48 u, ROI −1.9%, strike 40.0% (25 bets, 2 no-bets), p_raw 0.9435, CI [−0.51, +0.52] — closest to zero of all nine, still not distinguishable from noise |
| `market-totals-favourite-v1` | Baseline: does the market's favoured side of O/U 2.5 beat the vig? | none — reference | always back the margin-removed favourite side of O/U 2.5 | −4.19 u, ROI −15.5%, strike 55.6% (27 bets), p_raw 0.29 |

Not run: **Asian handicap** — the pilot file has `AHh / AvgAHH / AvgAHA`,
but quarter lines (±0.25/±0.75) split the stake and integer lines push;
that rule set is not written or tested, so it stays `Ready to source`
in the registry rather than being graded with a guessed rule.

Forward desk: `elo-favourite-3way-v1` (3-way Elo favourite, frozen live
predictions; dormant at the 2026-09-20 capture because Bundesliga MD5
starts 2026-10-09 — outside the 10-day issue horizon; first calls issue
automatically once MD5 enters the window).

## Ice hockey (DEL — results pilot, prediction-only)

| id | research question | prior | rule | result |
|---|---|---|---|---|
| `hockey-elo-v1` | Does a 2-way Elo (incl. OT/shootout) beat a coin flip on DEL? | R6: home-ice ≈ 54.5% → venue matters but is modest; rating-family prior R7 | Elo K=32, home adv 35 pts, 2-way; select when prob ≥ 0.55; results released start+3h (documented inference) | **11 graded predictions, 7 hits = 63.6%, mean Brier 0.4737** (2 disputed DEL rows excluded from grading — review queue owns them). No PnL: no permissioned DEL odds path; shown as unavailable, never zero. Single source → identity `probable`. |

Forward desk: `hockey-elo-v1` — **live**: 9 frozen calls on DEL games
2026-09-22 → 09-27 from the real committed capture (append-only ledger,
0 graded yet, 0 leaks). 13 graded historical predictions is not evidence
of skill (`docs/STATUS.md` #12); the forward test is what will speak.

## Darts (PDC — audited 2026-09-20, prediction-only)

| id | research question | prior | rule | result |
|---|---|---|---|---|
| `darts-elo-v1` | Does a player-level Elo select winners in PDC knockouts? | individual-sport Elo conventions; HOME_ADV=0 (listed-first is presentation order); K=24, MIN_PROB=0.60 — priors stated before grading | 2-way player Elo on the decisive leg/set count; select when prob ≥ 0.60; availability start+12h (audit-derived) | **Cold 2025 pool (141 matches): 0 selections** — max observed probability 0.551; the desk stayed silent rather than force bets. **Full pool as captured 2026-09-20 (423 matches, eight events): 48 selections, 39 hits = 81.25%, Brier 0.3489, 0 leaks** — same priors, no refit; large error bar (95% ≈ 68–90%) and no market baseline, so no skill or PnL claim. Full audit: `docs/DARTS-AUDIT.md`. |

Known darts limitations found by the audit: player-name identity splits
(`R. van Barneveld` vs `Raymond van Barneveld`, `Mickey/Michael Mansell`)
fragment the rating pool; we do not auto-merge names without a curated
mapping. An abandoned duplicate league (`darts-wm-26`, 52 rows stale since
December 2025, duplicating the complete `PDCWM`) was detected, removed and
excluded by discovery rule; two matches with conflicting duplicate result
entries (matchIDs 79962, 80237) are excluded from grading until reviewed.
Forward desk activates when an upcoming event — realistically the next
World Championship, December 2026 — enters the 10-day horizon.

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

- Holm step-down (R2) across the PnL-capable family (m=9 football
  strategies). Adjusted p-values: all 1.0. Implementation + tests:
  `northstar/stats.py`, `tests/test_stats.py`.
- Prediction-only desks (hockey, darts) are excluded from the PnL family
  (they have no PnL) and report accuracy/Brier with explicit
  `pnl_available: false`.
- Every quoted number on the site carries its sample-size warning; CIs are
  bootstrap over the settled sequence; unavailable ≠ zero everywhere.
