# Forward-test protocol (live, frozen predictions)

The forward test is the competition clock the user asked for where
backtesting is unavailable or insufficient: predictions are **frozen before
the events start**, on **real committed captures**, and graded later against
the same verified result path as the backtests. Implementation:
`northstar/forward.py`; ledger: `data/forward/ledger.json` (append-only);
tests: `tests/test_forward.py`; site: the **Forward** view.

## Cadence (how new data and new calls arrive)

- `.github/workflows/capture.yml` runs **Mondays 06:30 UTC** (cron) and on
  pushes touching `northstar/**` or the workflow file (bootstrap trigger so
  captures can run from a branch; `workflow_dispatch` becomes available once
  the workflow is on `main`). It may only touch **permitted** sources —
  today that is OpenLigaDB (ODbL, automated API allowed). OLBG itself is
  **manual-only** (ToS): no automation exists or is permitted; manual OLBG
  snapshots go to `data/raw/` and the drift detector already handles them.
- The workflow captures current-season fixtures (`data/fixtures/current/`
  with `.meta.json` sha256 sidecars + `capture-log.json` recording every
  probe, error and refusal), commits them with the bot identity, then runs
  the full pipeline and commits `site-data/site.json` + the ledger.
- Darts capture is discovery-driven with **upcoming-first priority** and
  abandoned-league demotion (`docs/DARTS-AUDIT.md` §1), so a starting
  tournament is never crowded out by finished history — and stale
  never-finished duplicates (e.g. `darts-wm-26`) never masquerade as
  upcoming fixtures.

## Issue rules (frozen at capture time)

For each captured fixture group, with that capture's own `as_of`:

1. **Horizon:** only events starting within `ISSUE_HORIZON = 10 days` of
   `as_of` are considered (roughly one matchweek + slack). Predicting
   December fixtures from September ratings is not a desk call — it floods
   the ledger with unfalsifiable-in-practice entries. Counted as
   `out_of_horizon` in the issue stats.
2. **Decision cutoff:** `start − 30 min`. The strategy's `predict()` runs
   with `as_of` — it may only read ratings/results available at the capture
   instant (the same `TimeBoundedStore` leakage guard as backtests;
   `TimeLeakageError` aborts issuance).
3. **Selectivity:** the strategy's own pre-registered threshold (e.g.
   hockey prob ≥ 0.55, darts ≥ 0.60, football 3-way Elo favourite).
   Below-threshold matches issue nothing — silence is a valid desk output.
4. **Freeze:** each issued call is appended to the ledger with model
   version, strategy id, sport, event id, teams, start, cutoff, full model
   probabilities, the pick, the source URL and the capture's `as_of`.
   Entries are **never mutated**; re-running issuance is idempotent
   (`already_ledgered`), and grading never rewrites an entry.
5. **Paper tips:** every ledger entry also lands in the store as an
   `unsettleable` prediction-only tip (never in PnL — hockey/darts have no
   permissioned odds path; that is shown as unavailable, never zero).

## Grading rules

- A call grades when the event has a finished, **mutually consistent**
  stored result: `graded` with hit/miss and 3-way Brier from the frozen
  probabilities.
- Results under review (`RESULT_KIND_INCONSISTENT` — disputed duplicates or
  impossible layering) are **held ungraded**; the review queue owns the
  verdict (audit 2026-09-20, `docs/DARTS-AUDIT.md` §3.1).
- Missing results: `awaiting_result` until start + per-sport grace
  (football/hockey 30 h, darts 54 h — mirrors availability inference plus
  slack), then `overdue` (review item; the capture is presumed stale).
- Leak audit: every graded/awaiting entry is re-checked for
  `cutoff < start`, `issued_at ≤ as_of`, and ledger monotonicity;
  violations would fail the pipeline (`leak_violations` must stay empty).

## Current state (2026-09-22, live)

- **Desk `hockey-elo-v1`: 9 frozen calls** on real DEL games 2026-09-22 →
  09-27 (probabilities 0.552–0.639), issued from the committed capture,
  0 graded yet, 0 leaks. These grade automatically at the next capture
  after results land.
- **Desk `hockey-home-v1` (added 2026-09-22): 15 frozen calls** on the
  same DEL window — a naive always-home baseline has no selectivity
  threshold, so it issues for *every* upcoming game. Its graded hit rate
  is the live reference the Elo desk's calls must beat; flat 0.5/0.5
  prior, Brier 0.5 by construction.
- **Desk `elo-favourite-3way-v1` (football): dormant by design.** At the
  capture instant, Bundesliga MD1–4 were finished and MD5 starts
  **2026-10-09** (international break) — outside the horizon. First
  football calls issue at the Monday capture once MD5 enters the window.
  This is the horizon rule working, not a bug.
- **2026-09-21 — football coverage widened to four leagues.** The capture
  now also fetches Premier League (`pl`, 380 fixtures, 40 finished),
  2. Bundesliga (`bl2`, 306 / 54) and LaLiga (`la1`, 380 / 62) 2026/27 —
  each probed live before listing. All four football leagues are in the
  same international break (next kick-offs 2026-10-09/10), so the desk is
  still dormant everywhere; the warm-up history it will rate from is
  already ingested (1,372 football fixtures, 192 finished). The pl payload
  also carried 10 finished-looking matchday-5 fixtures (Sep 18–20) with
  **no result rows at capture time** and la1 7 such rows; both are held
  `postponed` (unresolved) in the review queue until the next capture, and
  pl matchID 86559 (Villa v Forest) is flagged for duplicate conflicting
  result rows — see `docs/STATUS.md`.
- **Desk `darts-elo-v1` (+ `darts-listed-first-v1` baseline, both added to
  the forward desk set 2026-09-22): no upcoming darts payload yet.** The
  captured darts events are finished; the WSDF 2026 final (Smith v Price)
  was **in play** at the 19:33Z capture and is held `postponed` in the
  review queue until the next capture resolves it — the first genuinely
  live event the pipeline has met, handled without guessing. Activation is
  expected with the next World Championship (December 2026) via the
  upcoming-first discovery.

## What would make forward numbers PnL-capable

A permissioned odds path for the sport (licensed historical API key with
terms acceptance, or human manual import). Until then, forward desks report
accuracy/Brier only — a hit rate is **not** profitability, and the site says
so on every row.
