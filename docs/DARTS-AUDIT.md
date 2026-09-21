# Darts (PDC) schema audit — OpenLigaDB payloads

Audit date: **2026-09-20** (two capture generations, 19:06Z and 19:33Z),
performed on the real committed capture payloads listed below (no synthetic
fixtures were used for any finding). Every claim is reproducible from the
committed files and the URLs in the verification checklist at the end.

## 1. Why darts needs discovery (not a fixed shortcut)

The repository originally documented `PDCWSDF/2024` as the darts pilot
source. On 2026-09-20 that endpoint returned an **empty list** (`[]`) —
`PDCWSDF` turned out to be the *2026* World Series of Darts Finals league
(leagueId 6009, created for this season; the 2026 season carries 31
matches). All automated darts ingest is therefore discovery-driven:

1. `GET /getavailableleagues` → keep leagues whose shortcut/name matches
   `dart*`/`pdc*` (29 darts leagues in the live index on 2026-09-20).
2. `GET /getavailableseasons/{shortcut}` → **HTTP 404 for every darts
   league observed** (all 29+ candidates, recorded in the capture log).
   This is a real source behaviour, not a transient error: it reproduced
   across independent CI runs (35530789056, 35531161198, 35532480596).
3. Fallback (implemented after observing the 404s): probe
   `GET /getmatchdata/{shortcut}/{season}` directly for the last three
   seasons. An empty list means "no data for that season"; matches mean the
   season exists. The probe also counts unfinished matches and splits them
   into **future** (start after the probe instant) and **past**.

### Capture priority (refined against two live findings)

- **Upcoming-first:** leagues whose latest season carries *future*
  unfinished matches are captured first — otherwise finished history
  permanently crowds out the events the forward desk needs.
- **Abandoned-league demotion:** `darts-wm-26` ("Darts WM 2026", leagueId
  4893) was captured once and found to be an **abandoned duplicate** of the
  complete `PDCWM` league: 64 rows for the same World Championship, of
  which 12 finished rows match PDCWM rows **12/12 on teams+score** (9 also
  on exact start time), while **52 unfinished rows have start times from
  December 2025** — nine months stale. Its fixture was removed from
  `data/fixtures/current/` (git history retains it; the capture log records
  the episode); the discovery sort now demotes any league with
  ≥ 10 past-unfinished rows (`ABANDONED_PAST_UNFINISHED`) below cleanly
  entered leagues, so it is not re-captured. Covered by
  `test_abandoned_league_with_stale_unfinished_rows_is_demoted`.
- **Awaiting-refresh rank:** a league with a small number of *recent*
  unfinished rows (e.g. the WSDF 2026 final, in play at capture time)
  outranks fully-finished leagues even when none of its matches are in the
  future — otherwise a stale on-disk fixture freezes an unresolved result
  forever. Covered by `test_awaiting_refresh_league_outranks_finished_history`.
- **Case-insensitive shortcut validation:** `getmatchdata/pdcfdt/2026`
  answers with payload `leagueShortcut: "PDCFDT"` (observed live; a strict
  comparison refused the payload and logged the refusal). Validation now
  compares case-insensitively and records the payload's canonical spelling;
  genuine league mismatches are still refused.
- `max_leagues=4` (payloads are small: ≤ 127 matches).

Captured on 2026-09-20 in three CI generations (all committed with
`.meta.json` sha256 sidecars): `PDCMP/2025`, `bsdo/2025`, `PDCPCF/2025`;
then `PDCWSDF/2026`, `PDCWM/2026` (`pdcfdt` refused on the case mismatch,
fix landed after the run); then `pdcfdt/2026` (payload `PDCFDT`),
`pdccdo/2026` (payload `PDCCDO`), `PDCWOMA/2026`. Cross-fixture duplicate
scan (start time + both player names): **0 collisions** across all eight
events — unlike `darts-wm-26`/`PDCWM`, these are genuinely distinct
tournaments.

## 2. The committed payloads

| fixture | event | matches | finished | score unit |
|---|---|---|---|---|
| `openligadb_pdcmp_2025.json` | PDC World Matchplay 2025 | 31 | 31 | legs |
| `openligadb_bsdo_2025.json` | Baltic Sea Darts Open 2025 | 47 | 47 | legs |
| `openligadb_pdcpcf_2025.json` | Players Championship Finals 2025 | 63 | 63 | legs |
| `openligadb_pdcwm_2026.json` | PDC Darts-WM (World Championship, 2025-12-11 → 2026-01-03) | 127 | 127 | **sets** |
| `openligadb_pdcwoma_2026.json` | PDC World Masters 2026 (2026-01-29 → 02-01) | 31 | 31 | legs |
| `openligadb_pdccdo_2026.json` | Czech Darts Open 2026 (2026-09-04 → 09-06) | 47 | 47 | legs |
| `openligadb_pdcfdt_2026.json` | Flanders Darts Trophy 2026 (2026-09-11 → 09-13) | 47 | 47 | legs |
| `openligadb_pdcwsdf_2026.json` | World Series of Darts Finals 2026 (2026-09-17 → 09-20) | 31 | 30 (+1 in play at capture; refresh pending) | legs |

Pool totals: **424 matches, 423 finished**, July 2025 → September 2026.

Common shape: `leagueSeason` constant per file, `location=null`, round
groups (`1. Runde` … `Endspiel`) with strictly ordered `groupOrderID`,
starts clustered in afternoon (11:00–15:30Z) and evening (17:00–21:00Z)
sessions.

## 3. Schema findings (all from the real payloads)

### 3.1 Result encoding
- One result entry per match in 422/424 rows:
  `resultTypeKind="After90Minutes"`, `resultName="Endergebnis"`,
  `resultTypeID=2`. `pointsTeam1/2` are a **decisive count** — legs in
  ProTour/EuroTour/World-Series events (e.g. Wade 10–3 Cullen, best-of-19
  legs), **sets** in World Championship events (e.g. 7-1, 6-3 scorelines in
  PDCWM). The Elo model only compares the counts, so both encodings are
  valid inputs; draws never occur.
- **Two irregular matches — conflicting duplicate result entries** (same
  pattern, consecutive resultIDs, one real entry plus stale `0-0`
  duplicates):
  1. **matchID 79962** — PDCPCF 2025 Halbfinale, Gerwyn Price v Luke
     Littler, 2025-11-23T19:15Z: `8-11`, `0-0`, `0-0`
     (resultIDs 120595/96/97); the single `goals` entry corroborates
     `8-11`.
  2. **matchID 80237** — PDCWM 2026 Viertelfinale, Luke Littler v
     Krzysztof Ratajski, 2026-01-01T19:15Z: four entries — `5-0` (sets;
     corroborated by the single `goals` row) plus three stale `0-0`
     duplicates (consecutive resultIDs 121750–53).
  Handling per the data contract (`docs/data-contract.md`): the first entry
  is stored, the match is flagged `RESULT_KIND_INCONSISTENT`, and flagged
  events are **excluded from walk-forward rating updates, from accuracy
  grading, and held ungraded in forward grading** until a human resolves
  the review item. Nothing is silently chosen.
  Manual review: <https://api.openligadb.de/getmatchdata/79962>,
  <https://api.openligadb.de/getmatchdata/80237>, official PDC results at
  <https://www.pdc.tv/>.

### 3.2 Entry-lag / availability — and the `lastUpdateDateTime` timezone finding
**`lastUpdateDateTime` carries no timezone suffix and is German local
time (CET/CEST), not UTC.** Proof from the live WSDF final: the fixture
captured at **2026-09-20T20:08:53Z** contains a row last-updated
`22:07:50.923` — impossible if that value were UTC (a capture cannot
contain an edit from its own future); as CEST it is 20:07:50Z, one minute
before the capture. Consequence: the lag table below (computed as
`lastUpdateDateTime` − `matchDateTimeUTC`, treating the former *as if*
UTC) **overstates true entry lag by 1–2 h** (CET/CEST offset). The +12 h
availability bound is therefore conservative with extra margin — treating
local time as UTC shifts every availability *later*, never earlier, so no
walk-forward can see a result before the match could have ended. The
shift is documented as a known caveat (`docs/STATUS.md` #11); a proper
CET/CEST→UTC conversion utility is backlog work, deliberately not rushed
into this pass.

Lags as computed (UTC-assumed; true values 1–2 h smaller):

| event | min | median | max | same-day (<12 h) rows |
|---|---|---|---|---|
| PDCMP 2025 | 2.7 h | 3.0 h | 109.8 h | 28/31 (same-day max 10.46 h) |
| BSDO 2025 | 2.1 h | 27.6 h | 54.5 h | 14/47 (weekend batch entry) |
| PCF 2025 | 1.2 h | 1.7 h | 3.0 h | 63/63 |
| PDCWM 2026 | 1.5 h | 2.2 h | 11.7 h | 127/127 (same-day max 11.73 h) |
| WSDF 2026 | 2.5 h | 3.0 h | 9.3 h | 30/30 |
| World Masters 2026 | 1.3 h | 1.6 h | 10.5 h | 31/31 |
| Czech Darts Open 2026 | 2.2 h | 2.4 h | 92.0 h | 46/47 (same-day max 4.95 h) |
| Flanders Darts Trophy 2026 | 2.3 h | 2.6 h | 10.3 h | 47/47 |

Because entry behaviour mixes live per-match entry with multi-day batch
entry, `lastUpdateDateTime` is unusable as the availability signal. The
adapter uses a documented conservative construction:
**availability = start + 12 h** (`INFERRED_GAME_DURATION["darts"]`), which
covers every observed same-day entry across all eight events (max 11.73 h
as computed above — true lags are 1–2 h smaller per the timezone finding,
so the margin is larger than the table suggests) and
actual match end, while still releasing a round before the next day's first
decision cutoff. This is an inference about when a desk *could have known*,
not a claim about the source's timestamps — same convention as DEL hockey
(+3 h), see `docs/STATUS.md`.

### 3.3 In-play matches at capture time
The WSDF 2026 **final (Ross Smith v Gerwyn Price, 2026-09-20T19:30Z) had
already started** at the 19:33Z capture. Per the ingest contract it is
recorded `postponed` (unfinished at/before `as_of` → review queue, never
guessed) and resolves automatically to `finished` at the next capture.
The 20:08:53Z same-evening re-capture (awaiting-refresh priority, §1)
caught the source **mid-match**: a live `7-5` score row (last updated
20:07:50Z per §3.2 — 38 minutes into the best-of-21-leg final) with
`matchIsFinished` still `false`. The contract kept the match ungraded and
`postponed` rather than trusting an unflagged in-play score. This is the
pipeline meeting a genuinely live event for the first time — the flags
worked as designed; the next capture resolves it once the source flips the
finished flag.

### 3.4 Player identity (a real limitation, not fixed by guessing)
Players are stored in `team1/team2` with `teamName` as the player name.
**The same player appears under different names**:

- `R. van Barneveld` (BSDO) vs `Raymond van Barneveld` — same person.
- `D. van Duijvenbode` (BSDO) vs `Dirk van Duijvenbode` — same person.
- `Michael Mansell` vs `Mickey Mansell` — same person, nickname split
  (not detectable by an abbreviation rule).
- `Michael Smith` vs `Ross Smith` — genuinely different players: a naive
  surname merge would be *wrong*.

We deliberately do **not** auto-merge on heuristics — that would violate
the no-silent-correction contract. **Since 2026-09-21 a curated,
evidence-linked table exists: `data/aliases/darts.json`**
(`northstar/aliases.py`). It merges exactly the three verified splits
above (each entry carries the OpenLigaDB `teamId`s, the payloads it was
seen in and a link a reviewer can open: the 2025 Baltic Sea Darts Open
entry list for the two abbreviated Dutch names; the Mansell infobox for the
nickname split). The loader refuses a table with a missing evidence link, a
raw name mapping to two canonicals, or a canonical that is itself an alias.
Only the **rating key** is canonicalised — stored events keep the source's
raw spelling and the applied aliases are written into every model trail
(`model.identity.applied`). `tests/test_aliases.py` also asserts every raw
and canonical name in the table exists in a committed payload.

Effect on the pilot: **none of the 48 graded selections changed** (still
39/48 = 81.25 %, Brier 0.349) — the three merged players' extra history did
not move any probability across the 0.60 threshold. Unlisted splits (if
any) still fragment history and bias the desk toward silence, never toward
false confidence.

### 3.5 Other checks
- No walkover/retirement pattern found: zero finished rows with all-zero or
  null scores other than the duplicate-entry rows (§3.1).
- `group.groupOrderID` present and strictly round-ordered in every event.
- Timezone: all starts in `matchDateTimeUTC`.

## 4. Pilot result — darts-elo-v1 (pre-registered priors, never refitted)

Strategy (priors stated in code *before* any grading, see
`northstar/strategies/darts.py`): 2-way player Elo, K=24, initial 1500,
HOME_ADV=0 (listed-first is presentation order in darts), selectivity
MIN_PROB=0.60, decision cutoff start−30 min, availability start+12h.
Prediction-only: no permissioned darts odds path exists, so grading is
accuracy/Brier, never PnL (never shown as zero).

Chronology of the honest result:

1. **2025-only pool (141 matches: PDCMP/BSDO/PCF): 0 selections.** Every
   prediction fell below the threshold; max observed model probability
   **0.5510**. Root cause: cold-start pool (no history before July 2025),
   K=24 moves ratings slowly, knockout fields pair similarly-rated
   qualifiers. The desk stayed silent rather than force bets, and the
   priors were **not** adjusted after seeing this.
2. **Extended pool (298 finished matches, five events): 21 selections,
   16 hits = 76.2%, Brier 0.3922, 0 leaks.** The selections appeared
   exactly where the cold-start explanation predicts — 1 in late PCF 2025
   (Price v Bialecki, 2025-11-22, first player with cross-event history
   meeting a debutant), 10 in the World Championship (Dec 2025–Jan 2026),
   10 in WSDF 2026 (Sep 2026).
3. **Full pool as captured 2026-09-20 (423 finished matches, eight events,
   2025-07 → 2026-09): 48 selections, 48 graded, 39 hits = 81.25%, mean
   Brier 0.3489, 0 leak violations** — per competition: PCF 2025: 1,
   World Championship: 10, World Masters 2026: 6, Czech Darts Open 2026:
   12, Flanders Darts Trophy 2026: 8, WSDF 2026: 11. Same priors
   throughout; more data, no refit. Walk-forward ordering for the pooled
   run is start-chronological across events (engine change documented in
   `northstar/backtest.py`; identical ordering for single-competition
   pilots). These numbers **re-grade at every capture** as the pool grows —
   the site (`site-data/site.json`) is the authoritative live view.

**Interpretation guard:** 81.25% on 48 predictions has a large binomial
error bar (95% ≈ 68–90%), and darts favourites win often — without a
market baseline or odds, a hit rate says nothing about profitability. It
demonstrates the pipeline end-to-end on real outcomes, **not** skill, and
there is no PnL claim of any kind. The two
disputed duplicate-entry matches (§3.1) are excluded from grading and from
rating updates while they sit in the review queue.

The forward desk (`darts-elo-v1` in the forward registry) issues calls when
an upcoming darts event enters the 10-day horizon with a warm pool — the
next World Championship (December 2026) is the realistic activation, and
discovery ranks any league carrying future unfinished matches first.

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
  - <https://api.openligadb.de/getmatchdata/PDCWM/2026> — `a250b67aba7c2f98d8275b84e48aa343acaed162c1e4553d13e7a3261ea09e6a`
  - <https://api.openligadb.de/getmatchdata/PDCWSDF/2026> — `9c8aec47b7a9f630c6aeada2bb86e482bde0c3015d69a2f890ef2473c965ca1f`
  - <https://api.openligadb.de/getmatchdata/PDCWOMA/2026> — `7e3b06073fdc4b71f231ec8bc6650e6f2ac55ad29d198f1e6305e51690985b40`
  - <https://api.openligadb.de/getmatchdata/pdccdo/2026> — `36f420bc4630436d60254939bce6f7414bef86284e59e24e81c545f3fa7a8731`
  - <https://api.openligadb.de/getmatchdata/pdcfdt/2026> — `e75dcb5535d20a12b4f98bc5a0ab3099f4b8877ace5cdf912a5aac2888c273d9`
- The irregular matches: <https://api.openligadb.de/getmatchdata/79962>,
  <https://api.openligadb.de/getmatchdata/80237>
- The abandoned duplicate (removed fixture, kept for review):
  <https://api.openligadb.de/getmatchdata/darts-wm-26/2026> vs
  <https://api.openligadb.de/getmatchdata/PDCWM/2026>
- Capture runs (GitHub Actions, branch history):
  <https://github.com/buffedlizard55-lab/OLBG-Competition/actions/workflows/capture.yml>
- Licence: OpenLigaDB data is ODbL — see `docs/LICENSING.md`.
