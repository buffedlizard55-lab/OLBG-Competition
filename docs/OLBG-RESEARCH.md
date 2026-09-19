# OLBG research notes (reverse engineering for review)

Date of study: **2026-09-19** (manual browsing + text-render captures; no API,
no automated collection — see `docs/LICENSING.md`). Captures are preserved
under `data/raw/olbg_*.md` with provenance headers.

## What OLBG is

Online Betting Guide (olbg.com), operated by Invendium Ltd. A public
aggregator of betting tips: users ("tipsters"/"experts") publish selections on
upcoming events; the site aggregates them into per-event consensus tables and
ranks tipsters by displayed annual profit. Profits are *"calculated to a 10
point stake"* per OLBG's own display.

## Sports covered (as listed on olbg.com, 2026-09-19)

Football, Horse Racing, Rugby Union, American Football, Baseball,
Motor Racing, Darts, Boxing, Greyhounds (+ specials). These are the sport
families the coverage table on the site mirrors. OLBG URL sport segments
observed: `Football`, `Rugby_Union`, `Boxing`, `Darts`, `Horse_Racing`,
`Baseball`, `American_Football`, `Motor_Racing`, `Greyhounds`.

## URL / page structure (verified against live pages)

- **Tips index**: `https://www.olbg.com/betting-tips`
  - One card per (event, tip) pair. Verified card anatomy
    (`data/raw/olbg_betting_tips_index_2026-09-19.md`):
    1. event link: `[**Event**](https://www.olbg.com/betting-tips/{Sport}/{Region}/{League}/{Event}/{sport_num}?event_id={id})`
    2. league line (football; other sports have none)
    3. time label: `Today HH:MM` / `Tomorrow HH:MM`
    4. selection link: `[**Selection**](same event URL)`
    5. market name (e.g. `Full Time Result`, `Win Fight`, `Win Match 2-way`,
       `Total Goals`)
    6. consensus: `**W/T Win Tips**` + percentage + comments count
    7. state: `Add` (open) or `Expired`
- **Event page**: e.g. `.../Man_City_v_Sunderland/1?event_id=2039511`
  (`data/raw/olbg_event_mancity_sunderland_2026-09-19.md`):
  - title `# {Event} Tips`
  - *"Summary of Tipster comments"* (prose, likely LLM-generated)
  - *"Most Popular Tip"*: a consensus markdown table
    `| • | {Selection} | **wins** / total | pct% |`
  - *"Best Tipster's Tip"*: selection + market + tip text + displayed
    **Annual Profit** and **Annual Strike Rate** (self-reported on OLBG)
- **Tipster pages**: `/tipster/{id}` — robots-disallowed; not studied further
  because the ToS forbids automated access (see below).

## Data-quality observations (real drift, captured)

- **Consensus drift between list and detail page**: the same event's
  consensus counts differ between the index card and the event page within a
  short window (e.g. repo snapshot had Venezia 36/41 and Man City 24/27; the
  2026-09-19 capture shows 38/43 and 25/28 with new tip rows). Counters move
  as tips are added — any scrape must store the capture timestamp, which our
  snapshots do.
- **Tipster statistics are self-reported** ("Profits calculated to a 10 point
  stake"); OLBG does not publish the underlying settlement audit. We treat all
  such numbers as unverified.
- One darts event card on the index had no parsable consensus in the capture
  (flagged in the earlier session's snapshot notes) — non-football cards are
  structurally different (no league line), handled by the adapter.

## Licensing verdict (first-hand, 2026-09-19)

Fetched `https://www.olbg.com/use` in full (Terms of Use, last updated
09 July 2025): §7.1 personal non-commercial use; §7.3 no access without
consent; §9.1 all IP reserved; §9.2 no copying/distribution without written
consent; §13.3 no commercial use. robots.txt additionally disallows
`/api/`, `/sports/`, `/tipster/`, `/premium/`, `/newbg/`.

**Conclusion: automated collection is NOT permitted.** The codebase therefore
has no live OLBG collector: `adapters/olbg.py::auto_fetch()` raises
`PolicyError`, and the only OLBG data in the repo is human-captured snapshots
for manual review. Imported OLBG tips remain `pending` forever (no
permissioned odds, no official result path) and never enter verified PnL.

## How OLBG maps onto this project

| OLBG feature | Our treatment |
|---|---|
| Tips index cards | Parsed from manual snapshots; imported as `pending` tips with source URL + capture hash |
| Event consensus tables | Same; consensus counts stored on the tip's notes (review evidence) |
| "Best Tipster" profile | Imported as an `imported_tipster` entrant with a disclaimer (stats self-reported, unverified) |
| Consensus drift | `CONSENSUS_DRIFT` anomaly detector (`detect_consensus_drift`) compares two manual captures |
| Tipster rankings | **Not** imported into PnL; shown on the site only as external benchmark context with a link |
