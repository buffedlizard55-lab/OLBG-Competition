# Generated fact sheet (do not edit by hand)

Written by `python -m northstar.cli run-pipeline` / `facts` (nr-facts-2026-09-22.1) from the pipeline payload. `tests/test_facts.py` fails when this file is stale, which is what stops prose numbers from drifting away from the data.

- **Fixtures:** 17 hash-verified payloads, aggregate sha256 `2dfbb756c66a771d2cb4a47797bdb02b8343165ba6911f893dd942cc2e68b9af` (computed from the committed sidecars; reproducible, so a diff here always means the evidence changed)

Nothing above is a clock reading: the sheet is a pure function of the committed fixture hashes and the payload built from them, so a diff always means the evidence changed (never that time passed).
- **441** test functions are counted from the test sources (never remembered); pytest additionally expands parametrised cases.
- **Python lines:** northstar 11446, tests 6826, scripts 53

## Evidence base (what the numbers below are computed from)

| sport | status | results path | odds path |
|---|---|---|---|
| Football | `pilot_verified` | OpenLigaDB (ODbL-1.0), Bundesliga 2024/25 pilot; 2026/27 captures: bl1, pl, bl2, la1 | football-data.co.uk manual pilot; The Odds API licensed connector implemented but inactive |
| Darts | `results_pilot` | OpenLigaDB PDC capture (ODbL-1.0), 425 events (423 finished), schema-audited per docs/DARTS-AUDIT.md; single source, identity 'probable' | none verified - no permissioned darts odds path |
| Ice Hockey | `results_pilot` | OpenLigaDB DEL 2024/25 full season, 428 events (plus hand-audited matchdays 1/20/40), ODbL-1.0; single source, identity stays 'probable' | none verified - no permissioned DEL odds in this repo |
| Horse Racing | `verification_blocked` | none verified in this repository | none verified in this repository |
| Tennis | `verification_blocked` | none verified in this repository | none verified in this repository |
| Golf | `verification_blocked` | none verified in this repository | none verified in this repository |
| American Football | `verification_blocked` | none verified in this repository | none verified in this repository |
| Baseball | `verification_blocked` | none verified in this repository | none verified in this repository |
| Basketball | `verification_blocked` | none verified in this repository | none verified in this repository |
| Boxing | `verification_blocked` | none verified in this repository | none verified in this repository |
| Cricket | `verification_blocked` | none verified in this repository | none verified in this repository |
| Cycling | `verification_blocked` | none verified in this repository | none verified in this repository |
| Gaelic Football | `verification_blocked` | none verified in this repository | none verified in this repository |
| Greyhounds | `verification_blocked` | none verified in this repository | none verified in this repository |
| Handball | `verification_blocked` | none verified in this repository | none verified in this repository |
| Hurling | `verification_blocked` | none verified in this repository | none verified in this repository |
| Motor Racing | `verification_blocked` | none verified in this repository | none verified in this repository |
| Rugby Union | `verification_blocked` | none verified in this repository | none verified in this repository |
| Rugby League | `verification_blocked` | none verified in this repository | none verified in this repository |
| Snooker | `verification_blocked` | none verified in this repository | none verified in this repository |
| Volleyball | `verification_blocked` | none verified in this repository | none verified in this repository |

## Anomalies (flagged, never smoothed)

**153 open anomalies** in the review queue:

- `MISSING_METADATA`: 1
- `RESULT_KIND_INCONSISTENT`: 99
- `SOURCE_EDITED`: 48
- `TIME_CONFLICT`: 5

## Desks (all backtests in the payload)

| desk | sport | market | bets | settled | PnL | ROI | accuracy | n | Brier | vs naive baseline | p (Holm) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| `ah-market-favourite-v1` | football | asian_handicap | 27 | 27 | -1.5950 | -0.0665 | - | - | - | - | 1.0000 |
| `ah-poisson-value-v1` | football | asian_handicap | 25 | 25 | 9.8350 | 0.4470 | - | - | - | - | 0.0715 |
| `darts-elo-v1` | darts | match_winner_2way | 48 | 0 | unavailable (no odds path) | - | 0.8125 | 48 | 0.3488 | darts-listed-first-v1 (0.6627): YES | - |
| `darts-listed-first-v1` | darts | match_winner_2way | 421 | 0 | unavailable (no odds path) | - | 0.6627 | 421 | 0.5000 | - | - |
| `darts-mov-elo-v1` | darts | match_winner_2way | 111 | 0 | unavailable (no odds path) | - | 0.7838 | 111 | 0.3575 | darts-listed-first-v1 (0.6627): YES | - |
| `dixon-coles-v1` | football | match_winner_3way | 13 | 13 | 5.0100 | 0.3854 | - | - | - | - | 1.0000 |
| `draw-no-bet-v1` | football | match_winner_3way | 23 | 23 | -5.2000 | -0.2261 | - | - | - | - | 1.0000 |
| `draw-value-v1` | football | match_winner_3way | 8 | 8 | -1.3200 | -0.1650 | - | - | - | - | 1.0000 |
| `elo-decay-v1` | football | match_winner_3way | 12 | 12 | -2.7300 | -0.2275 | - | - | - | - | 1.0000 |
| `elo-edge-v1` | football | match_winner_3way | 12 | 12 | -2.7300 | -0.2275 | - | - | - | - | 1.0000 |
| `elo-favourite-3way-v1` | football | match_winner_3way | 167 | 0 | unavailable (no odds path) | - | 0.5210 | 167 | 0.6114 | football-home-baseline-v1 (0.3856): YES | - |
| `football-home-baseline-v1` | football | match_winner_3way | 306 | 0 | unavailable (no odds path) | - | 0.3856 | 306 | 0.6822 | - | - |
| `football-totals-over-v1` | football | total_goals_over_under_2_5 | 306 | 0 | unavailable (no odds path) | - | 0.5980 | 306 | 0.5000 | - | - |
| `football-totals-poisson-v1` | football | total_goals_over_under_2_5 | 306 | 0 | unavailable (no odds path) | - | 0.6111 | 306 | 0.4713 | football-totals-over-v1 (0.5980): YES | - |
| `form-value-v1` | football | match_winner_3way | 3 | 3 | -0.4900 | -0.1633 | - | - | - | - | 1.0000 |
| `hockey-elo-mov-v1` | ice_hockey | match_winner_2way | 255 | 0 | unavailable (no odds path) | - | 0.6549 | 255 | 0.4540 | hockey-home-v1 (0.5975): YES | - |
| `hockey-elo-v1` | ice_hockey | match_winner_2way | 243 | 0 | unavailable (no odds path) | - | 0.6626 | 243 | 0.4462 | hockey-home-v1 (0.5975): YES | - |
| `hockey-home-v1` | ice_hockey | match_winner_2way | 323 | 0 | unavailable (no odds path) | - | 0.5975 | 323 | 0.5000 | - | - |
| `hockey-reg-home-v1` | ice_hockey | regulation_3way | 323 | 0 | unavailable (no odds path) | - | 0.5944 | 323 | 0.5062 | - | - |
| `hockey-reg-poisson-v1` | ice_hockey | regulation_3way | 323 | 0 | unavailable (no odds path) | - | 0.6471 | 323 | 0.4883 | hockey-reg-home-v1 (0.5944): YES | - |
| `hockey-totals-over-v1` | ice_hockey | total_goals_over_under_5_5 | 323 | 0 | unavailable (no odds path) | - | 0.5356 | 323 | 0.5000 | - | - |
| `hockey-totals-poisson-v1` | ice_hockey | total_goals_over_under_5_5 | 323 | 0 | unavailable (no odds path) | - | 0.5232 | 323 | 0.5153 | hockey-totals-over-v1 (0.5356): NO | - |
| `home-edge-v1` | football | match_winner_3way | 10 | 10 | -3.0400 | -0.3040 | - | - | - | - | 1.0000 |
| `market-favourite-v1` | football | match_winner_3way | 27 | 27 | -5.0800 | -0.1881 | - | - | - | - | 1.0000 |
| `market-longshot-v1` | football | match_winner_3way | 27 | 27 | -7.8800 | -0.2919 | - | - | - | - | 1.0000 |
| `market-totals-favourite-v1` | football | total_goals_over_under_2_5 | 27 | 27 | -4.1900 | -0.1552 | - | - | - | - | 1.0000 |
| `poisson-totals-value-v1` | football | total_goals_over_under_2_5 | 25 | 25 | -0.4800 | -0.0192 | - | - | - | - | 1.0000 |

## Forward test (append-only ledger, state: live)

- issued 284 frozen pre-kickoff calls (284 awaiting a result)
- graded 0; overdue (started, ungraded) 0
- leak violations: 0
- next kick-off: 2026-09-22T17:30:00Z

| forward desk | issued |
|---|---|
| `hockey-elo-mov-v1` | 35 |
| `hockey-elo-v1` | 36 |
| `hockey-home-v1` | 43 |
| `hockey-reg-home-v1` | 43 |
| `hockey-reg-poisson-v1` | 43 |
| `hockey-totals-over-v1` | 42 |
| `hockey-totals-poisson-v1` | 42 |

## Sport source registry (all 21 OLBG families)

- **Version:** `nr-sport-sources-2026-09-22.1` (evidence fetched 2026-09-22)
- **Gates:** 3 permitted under an open licence, 17 awaiting a licence review, 1 blocked by the source's own robots.txt.
- **Designs:** 46 registered (27 graded). Full detail in `docs/SOURCE-REGISTRY.md` (generated from `data/sources/olbg_sports.json`).

## Automated checks behind these numbers

- fixture sha256 + dual-source agreement: `python -m northstar.cli verify`
- leak audit (no read after a decision cutoff): walk-forward leak_violations per desk, `python -m northstar.cli run-pipeline`
- forward ledger append-only + pre-kickoff issuance: tests/test_forward.py
- sport-source evidence gates: tests/test_sources.py
- documentation links resolve: tests/test_docs_links.py
