# OLBG manual capture runbook (ToS-compliant recurring cadence)

**Why this exists:** OLBG's Terms of Use (verified 2026-09-19,
<https://www.olbg.com/use> §7.1/§7.3/§9.1/§9.2) forbid automated access
and redistribution. The project therefore has **no OLBG collector** —
`northstar/adapters/olbg.py::auto_fetch()` raises `PolicyError` by design.
Everything OLBG-related in this repository is a **manual, human capture**
for personal review. This runbook is the recurring cadence a human follows
so the tip desk, drift detector and reconciliation table keep working.

**Cadence: weekly, Monday** (after the 06:30 UTC automated capture of the
*permitted* OpenLigaDB fixtures has run, so the reconciliation table is
fresh). The scheduled workflow
[`.github/workflows/olbg-capture-reminder.yml`](../.github/workflows/olbg-capture-reminder.yml)
opens a checklist issue every Monday 07:10 UTC — it never touches
olbg.com; it only reminds the operator. Each cycle takes roughly
10–15 minutes of human time.

## Checklist (one pass)

1. **Open the public tips index manually** in a normal browser:
   <https://www.olbg.com/betting-tips>
   (manual personal review only — no scraping, no API, no automation).
2. **Save a text rendering** of the page to
   `data/raw/olbg_betting_tips_index_YYYY-MM-DD.md` following the existing
   snapshot format: the provenance header comment block first (source URL,
   capture timestamp, mode `manual_snapshot`, review-evidence-only note),
   then the page body as rendered text. Existing examples:
   `data/raw/olbg_betting_tips_index_2026-09-19.md`.
3. **Open 1–2 event pages** (especially football events that also exist in
   the permitted OpenLigaDB fixture lists: Bundesliga, PL, 2. Bundesliga,
   LaLiga, DEL) and save them the same way as
   `data/raw/olbg_event_{slug}_YYYY-MM-DD.md`. The consensus table and
   "Best Tipster's Tip" block are the useful parts; keep the whole render
   so nothing is quoted out of context.
4. **Do not edit the captured bytes.** Captured evidence is immutable; a
   later capture that disagrees is a finding, not a correction.
5. **Re-run the pipeline** (offline, permitted data only):
   ```bash
   python -m northstar.cli run-pipeline --fresh
   ```
   The OLBG adapter parses the manual snapshots, imports cards/tips as
   `pending` (never PnL), the `CONSENSUS_DRIFT` detector compares against
   the previous capture, and `northstar/reconcile.py` cross-checks every
   matchable football event against the official OpenLigaDB kickoff
   (the 2026-09-19 captures produced five 5-hour `TIME_CONFLICT`
   anomalies — the page render's "Today HH:MM" labels were produced in a
   UTC−5 locale; the queue keeps them until reviewed).
6. **Check the review queue** on the site (Integrity view) for new
   anomalies: consensus drift, time conflicts, unmatched events. Resolve
   or annotate them in a commit — never by editing captured bytes.
7. **Commit** the new `data/raw/` snapshots, the regenerated
   `site-data/site.json` and any ledger changes, then close the reminder
   issue with a one-line summary.

## Rules that make a capture valid

- The capture must be a human-initiated browser render, saved by hand.
- The provenance header (source URL + capture timestamp + mode) must be
  present — `parse_index_snapshot` uses it to resolve relative dates.
- Timestamps inside the page ("Today 14:45") are *display labels*, not
  verified kickoff times; reconciliation against OpenLigaDB decides.
- Tipster statistics displayed on OLBG are self-reported and never enter
  PnL; they stay external benchmark context.
- OLBG content is used for private, non-commercial review only; no bulk
  redistribution (ToU §9.1).

## What the capture unlocks downstream

| Artifact | Where it lands |
|---|---|
| Index cards | pending OLBG tips (tip desk view, `pending` forever by design) |
| Event consensus tables | consensus notes on the tip + drift detector input |
| Best-tipster profile | `imported_tipster` entrant, disclaimed |
| Kickoff labels | reconciliation vs OpenLigaDB UTC kickoff (alias table) |

## Current status

- Last completed manual captures: **2026-09-19** (three snapshots in
  `data/raw/`). The cadence above is the standing protocol for every
  following Monday.
- 13 open anomalies are in the review queue (4 DEL impossible layering,
  1 null-season, 2 darts duplicate conflicts, 1 PL duplicate conflict,
  5 OLBG kickoff time conflicts) — see `docs/STATUS.md`.
