# Northstar Competition Lab

A source-first, paper-trading competition interface for the OLBG-Competition project.

> **Honesty status:** this repository currently contains a static GitHub Pages research build. It does **not** contain a live tip collector, historical odds archive, official-result ingest, or verified local PnL. The UI intentionally shows zero local entrants and zero tested strategies rather than inventing numbers.

## What is in this pass

- Clean responsive GitHub Pages interface in `index.html`, `styles.css`, and `app.js`.
- Dashboard for paper-only competition state, provenance gates, source previews, and an empty-by-design leaderboard.
- Separate **Tip desk** for upcoming source previews and an explicit separation between published tips and settled results.
- **Strategy lab** with 16 sport-specific research hypotheses and explicit data gates. These are research designs, not claimed betting edges.
- **Source registry** covering 27 sport/event families with links to governing bodies, leagues, event organizers, or the original OLBG page.
- A data contract covering tip identity, timestamps, odds, result verification, settlement, PnL, anomaly flags, and audit requirements.
- A GitHub Actions workflow in `.github/workflows/pages.yml` for GitHub Pages deployment.

## Verify the build locally

This is a dependency-free static site. From the repository root:

```bash
python3 -m http.server 4173 --bind 0.0.0.0
```

Then open `http://localhost:4173`.

The app is designed for GitHub Pages and uses relative local assets. External source links open in a new tab and are shown for manual review.

## Research snapshot and source policy

The four Tip desk records are a clearly labelled **OLBG public-page snapshot captured on 19 September 2026**. One Darts record is intentionally flagged because the list page showed it while its direct event page subsequently returned “No tips found.” They are not a claim that this repository has a live OLBG integration, and they are not counted in Northstar PnL.

The primary source pages manually reviewed for the interface are:

- [OLBG public betting tips](https://www.olbg.com/betting-tips) — current public tip-page structure and sports menu.
- [OLBG best tipsters](https://www.olbg.com/best-tipsters) — public tipster metric structure and profile links.
- [OLBG tipster competition](https://www.olbg.com/tipster-competition) — public competition framing and sport/event families.
- [OLBG home](https://www.olbg.com/) — original source domain.

Sport result links are in the in-app **Source registry** and are intentionally not presented as connected feeds. A linked governing body is not the same as an implemented, permissioned API or a completed verification run.

## Data integrity rules

1. A tip is a prediction record, never a result.
2. Store the original source URL, source event ID, publication time, collection time, selection, market, and odds exactly as observed.
3. Store odds with their timestamp and source. Do not backfill a later price into an earlier tip.
4. Do not settle until an appropriate official league, governing-body, or event-organizer result is available.
5. Pending, postponed, abandoned, void, and disputed outcomes are not losses.
6. Reconcile event identity, competition, start time, participants, market rules, and result before settlement.
7. Preserve the raw response and a content hash so an amended source can be detected.
8. Flag conflicting sources, impossible timestamps, duplicate tips, edits after start time, missing odds, ambiguous participants, and result changes for review.
9. PnL is paper-only, level-stakes by default, and calculated only from verified settled records.
10. Predictions must show their evidence links, input cutoff, uncertainty, and model version. Never call an untested hypothesis a “top tipster” prediction.

See [`docs/data-contract.md`](docs/data-contract.md) for the proposed schema, settlement logic, tests, and implementation sequence.

## What still needs to be built

### Required before a successful production project

- **Licensed or permissioned ingestion:** OLBG terms, robots rules, rate limits, and any API/data-provider terms must be reviewed before collection. Do not silently scrape or republish protected content.
- **Source adapters:** competition-specific connectors for each league/event, with retries, raw-response storage, schema validation, deduplication, and provenance hashes.
- **Historical odds:** a time-stamped, permissioned odds archive. Official sport results alone cannot calculate betting PnL or test price-sensitive strategies.
- **Official-result reconciliation:** adapters for score/result sources, including postponements, voids, ties, dead heats, retirements, shootouts, abandoned matches, reduced-overs cricket, and sport-specific market rules.
- **Persistence and jobs:** a database, queue/scheduler, immutable event log, daily backfills, and an anomaly review queue. The current Pages site is intentionally read-only.
- **Strategy engine:** versioned feature pipelines, strict pre-event cutoffs, train/validation/test splits, walk-forward tests, calibration, multiple-testing controls, and reproducible reports.
- **Prediction writer:** evidence-backed summaries that cite only verified inputs and label missing information; no fabricated probabilities, injuries, lineups, or current form.
- **Authentication and competition controls:** entrant identity, paper bankroll rules, stake limits, clock/time zone policy, and anti-tamper/audit controls.
- **Responsible-use controls:** 18+ messaging, jurisdiction review, no real-money execution, loss-risk disclosures, and a clear separation from bookmaker promotion.

### Known limitations of this static pass

- The UI data is a small source preview, not a live database.
- There are no local competitors, settled tips, historical observations, odds, or PnL metrics yet.
- Source URLs are mapped but no external result is automatically verified by this repository.
- “Official” is sport- and jurisdiction-specific. Boxing, horse racing outside the UK, greyhound racing outside Great Britain, esports, and specials need event-owner adapters.
- A single sport can span many governing bodies and leagues; a generic sport link is never sufficient proof for every event.
- The current date label is a snapshot label, not a promise that the remote OLBG pages remain unchanged.

## Suggested next session

1. Agree a source and licensing matrix for one pilot sport and one league (football Premier League is a practical starting point).
2. Select a permissioned odds source and define the exact market settlement rules.
3. Implement immutable `tips`, `events`, `odds_snapshots`, `results`, `settlements`, and `anomalies` tables from the data contract.
4. Build one result adapter and one odds adapter; replay a small, hand-audited fixture set.
5. Add automated tests for time leakage, duplicate events, postponed fixtures, voids, and settlement arithmetic.
6. Only then run the first walk-forward backtest and publish a linked audit report.
7. Expand sport by sport, retaining a visible “not covered / verification blocked” state until each source path passes.
