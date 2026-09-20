# OLBG research notes (reverse engineering for review)

Date of study: **2026-09-20** (manual review of the public tips index and
terms pages; no OLBG API, no automated OLBG collection — see
`docs/LICENSING.md`). The earlier 2026-09-19 captures are preserved under
`data/raw/olbg_*.md`; the current page was re-checked for the sport-family
inventory and URL shape, but no new page body is copied into the repository.

## What OLBG is

Online Betting Guide (olbg.com), operated by Invendium Ltd. A public
aggregator of betting tips: users ("tipsters"/"experts") publish selections on
upcoming events; the site aggregates them into per-event consensus tables and
ranks tipsters by displayed annual profit. Profits are *"calculated to a 10
point stake"* per OLBG's own display.

## Sports covered (as listed on olbg.com, 2026-09-20)

The current public tips page says it covers 20+ sports and explicitly lists
these 21 sport families: Horse Racing, Football, Tennis, Golf, American
Football, Baseball, Basketball, Boxing, Cricket, Cycling, Darts, Gaelic
Football, Greyhounds, Handball, Hurling, Ice Hockey, Motor Racing, Rugby
Union, Rugby League, Snooker, and Volleyball.  This is a catalogue of what
OLBG displays, not a claim that Northstar has a verified data path for each.

Observed URL sport segments are `Horse_Racing`, `Football`, `Tennis`, `Golf`,
`American_Football`, `Baseball`, `Basketball`, `Boxing`, `Cricket`, `Cycling`,
`Darts`, `Gaelic_Football`, `Greyhounds`, `Handball`, `Hurling`, `Ice_Hockey`,
`Motor_Racing`, `Rugby_Union`, `Rugby_League`, `Snooker`, and `Volleyball`.
The page also links to Grand National and Cheltenham special sections; those
are event groupings under horse racing, not additional sport families.

Evidence for the inventory and page anatomy: the public page
[OLBG Betting Tips](https://www.olbg.com/betting-tips), manually reviewed
2026-09-20. Do not infer a sport, league, market, tipster identity, or result
from a URL alone; preserve the captured page and source timestamp if a human
imports it.

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
