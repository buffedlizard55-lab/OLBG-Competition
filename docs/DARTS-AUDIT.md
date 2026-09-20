# Darts (PDC) schema audit — OpenLigaDB payloads

Audit date: **2026-09-20**, performed on the three real committed capture
payloads listed below (no synthetic fixtures were used for any finding).
Every claim here is reproducible from the committed files and the URLs in
the verification checklist at the end.

## 1. Why darts needs discovery (not a fixed shortcut)

The repository originally documented `PDCWSDF/2024` as the darts pilot
source. On 2026-09-20 that endpoint returned an **empty list** (`[]`) — the
league exists but carries no matches. All automated darts ingest is
therefore discovery-driven:

1. `GET /getavailableleagues` → keep leagues whose shortcut/name matches
   `dart*`/`pdc*` (the darts heuristic in `northstar/capture.py`).
2. `GET /getavailableseasons/{shortcut}` → **HTTP 404 for every darts
   league observed** (8 candidates, all recorded in the capture log). This
   is a real source behaviour, not a transient error: it reproduced on two
   independent CI runs (35530789056, 35531161198).
3. Fallback (implemented after observing the 404s): probe
   `GET /getmatchdata/{shortcut}/{season}` directly for the last three
   seasons. An empty list means "no data for that season"; matches mean the
   season exists.

Darts leagues present in the live league index on 2026-09-20 (names as
returned by the source):

| shortcut | leagueName | leagueId |
|---|---|---|
| PDCMP | PDC World Matchplay 2025 | 4864 |
| bsdo | Baltic Sea Darts Open 2025 | 4861 |
| PDCPCF | Players Championship Finals 2025 | 4892 |
| darts-wm-26 | Darts WM 2026 | 4893 |
| PDCWM | PDC Darts-WM | 4894 |
| PDCEDC | European Darts Championship 2025 | 4886 |
| PDCWGP | (World Grand Prix — name per league index) | see log |
| pdcfdt | (PDC Players Championship / FD T — name per league index) | see log |

**Upcoming-first priority:** the league index lists finished 2025 events
before `darts-wm-26`, so discovery sorts candidates by *unfinished matches
in the latest season* (descending) before applying `max_leagues=4`. Without
this, the December 2026 World Championship — the payload the forward desk
actually needs — would be permanently crowded out by finished history.
Covered by `test_upcoming_leagues_outrank_finished_history`.

## 2. The three committed payloads

| fixture | event | matches | finished | rounds (groupOrderID) |
|---|---|---|---|---|
| `data/fixtures/current/openligadb_pdcmp_2025.json` | PDC World Matchplay 2025 | 31 | 31 | 1. Runde(16), Achtelfinale(8), Viertelfinale(4), Halbfinale(2), Endspiel(1) |
| `data/fixtures/current/openligadb_bsdo_2025.json` | Baltic Sea Darts Open 2025 | 47 | 47 | + 2. Runde(16) — six rounds |
| `data/fixtures/current/openligadb_pdcpcf_2025.json` | Players Championship Finals 2025 | 63 | 63 | six rounds, 32-player draw |

All rows: `leagueSeason=2025`, `matchIsFinished=true`, `location=null`,
one `goals` array entry mirroring the final score (except matchID 79962,
see §3.1).

## 3. Schema findings (all from the real payloads)

### 3.1 Result encoding
- Exactly one result entry per match in 140/141 rows:
  `resultTypeKind="After90Minutes"`, `resultName="Endergebnis"`,
  `resultTypeID=2`. `pointsTeam1/2` are the **legs won** (e.g. World
  Matchplay R1 best-of-19: Wade 10–3 Cullen; BSDO R1 best-of-11: 6–3;
  PCF R1 best-of-11: Cross 2–6 Bialecki). Draws never occur.
- **One irregular match — matchID 79962** (PCF 2025 Halbfinale,
  Gerwyn Price v Luke Littler, 2025-11-23T19:15Z): *three* `After90Minutes`
  entries with consecutive resultIDs (120595/96/97): `8-11`, `0-0`, `0-0`.
  The single `goals` entry corroborates `8-11`. Handling per the data
  contract (`docs/data-contract.md`): the first entry is stored, the match
  is flagged `RESULT_KIND_INCONSISTENT` ("conflicting duplicate result
  entries"), and flagged events are **excluded from walk-forward rating
  updates, from accuracy grading, and held ungraded in forward grading**
  until a human resolves the review item. Nothing is silently chosen.
  Manual review: <https://api.openligadb.de/getmatchdata/79962> and the
  official PDC results at <https://www.pdc.tv/>.

### 3.2 Entry-lag / availability
`lastUpdateDateTime` − `matchDateTimeUTC` across the 141 rows:

| event | min | median | max | same-day (<12 h) rows |
|---|---|---|---|---|
| PDCMP | 2.7 h | 3.0 h | 109.8 h | 28/31 (same-day max 10.46 h) |
| BSDO | 2.1 h | 27.6 h | 54.5 h | 14/47 (weekend batch entry) |
| PCF | 1.2 h | 1.7 h | 3.0 h | 63/63 |

Because entry behaviour mixes live per-match entry with multi-day batch
entry, `lastUpdateDateTime` is unusable as the availability signal. The
adapter uses a documented conservative construction:
**availability = start + 12 h** (`INFERRED_GAME_DURATION["darts"]`), which
covers every observed same-day entry (max 10.46 h) and actual match end
(≤ ~4 h), while still releasing a round before the next day's first
decision cutoff. This is an inference about when a desk *could have known*,
not a claim about the source's timestamps — same convention as DEL hockey
(+3 h), see `docs/STATUS.md`.

### 3.3 Player identity (a real limitation, not fixed by guessing)
Players are stored in `team1/team2` with `teamName` as the player name.
Across the three events there are 79 distinct names; 40 appear in more than
one event. **The same player can appear under different names**:

- `R. van Barneveld` (BSDO) vs `Raymond van Barneveld` — same person.
- `D. van Duijvenbode` (BSDO) vs `Dirk van Duijvenbode` — same person.
- `Michael Mansell` vs `Mickey Mansell` — same person, nickname split
  (not detectable by an abbreviation rule).
- `Michael Smith` vs `Ross Smith` — genuinely different players: a naive
  surname merge would be *wrong*.

The Elo pool keys on exact `teamName`, so these splits fragment rating
history. We deliberately do **not** auto-merge: identity resolution needs a
curated, reviewed mapping (a future `data/aliases/darts.json`-style
artifact), and merging on heuristics would violate the no-silent-correction
contract. Effect today: slightly compressed rating gaps — which biases the
desk toward *silence*, never toward false confidence.

### 3.4 Other checks
- No walkover/retirement pattern found: zero finished rows with all-zero or
  null scores other than the 79962 duplicates (§3.1).
- `group.groupOrderID` is present and strictly ordered by round in all
  three events — walk-forward ordering (round, then start, then event id)
  is sound.
- Timezone: all starts in `matchDateTimeUTC`; sessions cluster at 11:00–
  13:00Z (afternoon) and 18:00–19:15Z (evening).

## 4. Pilot result — darts-elo-v1 (pre-registered priors, no refit)

Strategy (priors stated in code *before* any grading, see
`northstar/strategies/darts.py`): 2-way player Elo, K=24, initial 1500,
HOME_ADV=0 (listed-first is presentation order in darts), selectivity
MIN_PROB=0.60, decision cutoff start−30 min. Prediction-only: no
permissioned darts odds path exists, so grading is accuracy/Brier, never
PnL (never shown as zero).

**Result on 141 finished matches: 0 selections, 0 graded.** Every
prediction fell below the selectivity threshold; the maximum model
probability observed across all 141 was **0.5510** (95th pct 0.5345), and
the pool's highest rating by the end of PCF 2025 was ≈1556.

Root cause is structural, not a coding fault: the pool is cold-started at
the first captured event (July 2025) with no prior history, K=24 moves
ratings slowly, and knockout fields pair similarly-rated qualifiers, so
rating gaps never reached the ~71 points needed for a 0.60 favourite.
The honest reading: **the desk stayed silent rather than force bets** —
which is the pre-registered behaviour. We did not lower MIN_PROB or raise
K after seeing the data; that would be fitting the pilot.

The forward desk (`darts-elo-v1` in the forward registry) activates when an
upcoming darts event enters the 10-day issue horizon — realistically the
PDC World Championship (`darts-wm-26`, December 2026), which discovery
already ranks first once it carries unfinished matches.

## 5. Verification checklist (manual review links)

- League index: <https://api.openligadb.de/getavailableleagues>
- Seasons 404 evidence (darts): e.g.
  <https://api.openligadb.de/getavailableseasons/PDCMP> → HTTP 404
  (reproduced 2026-09-20; recorded in
  `data/fixtures/current/capture-log.json` → `darts_discovery[*].seasons_endpoint_error`)
- Captured payloads (fetch and compare sha256 against the `.meta.json`
  sidecars):
  - <https://api.openligadb.de/getmatchdata/PDCMP/2025> — `ddd45869f59c827bac57076be4796673178b5b6d0ed9ff9d5de28de03c633517`
  - <https://api.openligadb.de/getmatchdata/bsdo/2025> — `f22027d138baf2d7776ac68b46758c3aae796f976fba4875fc33297f1a2ff08b`
  - <https://api.openligadb.de/getmatchdata/PDCPCF/2025> — `724ce36c64be66733387ef5024fc3c45e55dde68fa908867d82ce042f197c3f1`
- The irregular match: <https://api.openligadb.de/getmatchdata/79962>
- Capture runs (GitHub Actions, branch history):
  <https://github.com/buffedlizard55-lab/OLBG-Competition/actions/workflows/capture.yml>
- Licence: OpenLigaDB data is ODbL — see `docs/LICENSING.md`.
