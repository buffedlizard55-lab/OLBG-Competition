# Hockey (DEL/DEL2/CHL) period-row schema on OpenLigaDB — audit of 2026-09-22

Scope: how hockey match rows must be read on OpenLigaDB (`api.openligadb.de`),
what `northstar/adapters/openligadb.py` does about it, and where the numbers
in code comments and `docs/STATUS.md` come from. Mirrors the
[Darts audit](DARTS-AUDIT.md) format. All probes via `api.openligadb.de`
(2026-09-22); the two probe payloads are committed and fixture-verified like
every other fixture.

Verified on 2026-09-22 against:

- `https://api.openligadb.de/getavailableleagues`
- `https://api.openligadb.de/getmatchdata/del2/2026/1`
  (committed as `data/fixtures/openligadb_del2_2026_sd1.json`)
- `https://api.openligadb.de/getmatchdata/CHL/2026/1`
  (committed as `data/fixtures/openligadb_chl_2026_sd1.json`)
- `https://api.openligadb.de/getmatchdata/CHL/2026/81927` (single-match
  endpoint: returns `[]` for CHL — only the matchday endpoint serves it)

---

## 0. Summary

1. **Period rows wear football-era labels.** Hockey rows are cumulative
   *period* rows with `resultTypeKind` values `HalfTime`, `HalfTime`,
   `After90Minutes` (+ `AfterExtraTime`): `1./2./3.Drittel` and the overtime
   row under those labels. Only the `resultTypeKind` labels are stable —
   the German descriptions have three dialects across leagues (below).
2. **The goal list is a second representation of the same final score —
   and it disagrees with the rows in real data.** `del/2024` matchID 76236
   (committed fixture): period rows `1.Drittel 0-0 · 2.Drittel 4-2 ·
   3.Drittel 0-0` vs a goal list running to **4-2**. The 3.Drittel row the
   priority rule treats as the final is contradicted by the goal list. New
   `goals_vs_results` rule: quarantine on disagreement (`RESULT_KIND_INCONSISTENT`),
   priority row kept and flagged — never silently repaired.
3. **Goal rows are community-entered out of order** (real: `del2/2026` 84082,
   `CHL/2026` 81929) and `scoreTeam1/2` are per-goal *cumulative running
   scores*: the goal-list final is the running-score **maximum** over goal
   rows — never the last row.
4. **Two 2026-09-22 probes side by side** prove both directions: DEL2
   matchday 1 is systemically defective (5/7 rows-vs-goals disagreements +
   1 impossible OT layering; 1 clean match), while CHL matchday 1 is fully
   consistent (12/12 agree; two overtime games correctly layered with drawn
   regulation rows).
5. **CET/CEST→exact UTC conversion** for `lastUpdateDateTime` /
   `matchDateTime` (STATUS #11): `northstar.timeutil.cet_local_to_utc`, wired
   into ingest. Round-trip-verified on all committed rows.

## 1. League identity (`getavailableleagues`)

| League | leagueId | `leagueShortcut` | `leagueSeason` | note |
|---|---|---|---|---|
| DEL2 Hauptrunde | 5962 | `DEL2` | 2026 | the 2026/27 league we capture |
| DEL2 2025/2026 | 4856 | `del2` | 2025 | prior season, different shortcut case |
| Champions Hockey League 2026/2027 | 4951 | `CHL` | 2026 | the 2026/27 league we capture |
| DEL Eishockey 2026/2027 | 4947 | `del` | 2026 | (2024/25 = leagueId 4827) |
| "1. DEL" / "2. DEL" | 4790 / 4791 | `1. DEL` / `2. DEL` | — | community duplicates — **not used** |
| "HCL" | — | `hcl` | — | EHF **handball** CL, never hockey |

Capture decision (`northstar/capture.py`): `CURRENT_TARGETS` adds
`("DEL2", 2026, "ice_hockey")` and `("CHL", 2026, "ice_hockey")`, writing
`data/fixtures/current/openligadb_del2_2026.json` / `..._chl_2026.json`
(distinct from the committed probe slice names `openligadb_del2_2026_sd1.json` /
`openligadb_chl_2026_sd1.json`; the hockey pilot prefix `openligadb_del_2024`
cannot match `openligadb_del2…` as strings).

## 2. The period-row schema (measured on the probe payloads)

- Every match carries three period rows labelled `HalfTime`, `HalfTime`,
  `After90Minutes` with descriptions `Ergebnis nach Ende der ersten/zweiten
  Halbzeit`, `Ergebnis nach Ende der offiziellen Spielzeit` — these ARE
  `1./2./3.Drittel` (1st/2nd/3rd intermission) for hockey. Overtime games add
  a fourth `AfterExtraTime` row.
- Three description dialects, one label system:
  - `del/2024` (committed): `Ergebnis nach dem 1./2./3.Drittel`, `nach
    Verlängerung`, `nach Penaltyschießen`;
  - `DEL2` probe: football-style `nach Ende der ersten/zweiten Halbzeit` +
    `nach Ende der offiziellen Spielzeit` + `nach Ende der Verlängerung`;
  - `CHL` probe: identical to DEL2 but `...Verlaengerung` (ASCII `ae`).
  **Only `resultTypeKind` may be parsed on; descriptions are cosmetic.**
- `timeZoneID` is unreliable: `W. Europe Standard Time` on `bl1/2024` and
  `del/2024` rows and on 350/364 `del/2026` rows, **null on the other 14
  `del/2026` rows and on every DEL2/CHL probe row** (7 + 12). Parse as German
  local wall time and convert unconditionally.
- Goal rows: `goalID`, `matchMinute`, `scoreTeam1`, `scoreTeam2` where the
  score pair is the cumulative running score **after** the goal. Order of
  entry is not chronological: `del2/2026` 84082 has goalID 147990 entered
  before 147988 (1-3 before 1-2); `CHL/2026` 81929 has the two 17' goals
  entered 0-2 before 0-1. **Goal-list final := elementwise maximum of the
  running scores** (`parse_matchday`), never the last row's.

## 3. The rows-vs-goal-list rule (`goals_vs_results`)

For hockey (`sport="ice_hockey"`): compute the goal-list final as in §2 and
compare it with the score of the selected final row
(`AfterPenalties > AfterExtraTime > After90Minutes`, `FINAL_KIND_PRIORITY`).
Any mismatch ⇒ `RESULT_KIND_INCONSISTENT`, `inconsistency_reason`
`goals_vs_results` (reason priority: `duplicate_conflict` >
`goals_vs_results` > `impossible_layering`; when the goal list also
contradicts another flagged pattern's kept row the goal evidence is appended
to the detail — see `pl/2026` 86559 below). The priority row's score is kept
and the event is quarantined from rating and grading — the queue owns the
resolution; nothing is auto-repaired.

Edge cases (tested in `tests/test_hockey_schema.py`): no goal rows or goal
rows without running scores ⇒ check skipped (never a flag); agreement ⇒
no flag. **Known false-positive class**: if a source ever records a shootout
decider only in the `AfterPenalties` row while the goal list ends level, the
rule flags it for review. That is the designed conservative failure: a real
disagreement must never be silently graded. Not observed in committed data —
both documented shootouts (`del/2024` 76220 Iserlohn–Berlin, 76234) agree.

Scope scanned (2026-09-22, through `parse_matchday` itself): every row of
every committed `openligadb_*` fixture (2,940 rows / 1,409 finished)
including both probe slices. Unique flagged matches:

| reason | count | matches |
|---|---|---|
| `impossible_layering` | 84 | 83 × `del/2024` + `del2/2026` 84085 |
| `goals_vs_results` | 6 | `del/2024` 76236 + 5 × `del2/2026` (84079, 84080, 84082, 84083, 84084) |
| `duplicate_conflict` | 3 | `pl/2026` 86559, `PDCPCF 2025` 79962, `PDCWM 2026` 80237 |

(22 `bl1/2024` matches carry goal rows without running scores — skipped;
`del/2024` slices `_sd{1,20,40}` are strict subsets of the season file and
double-count 4 already-counted layering rows when files are summed.)

## 4. Probe results

### 4.1 DEL2 matchday 1 (`del2/2026/1`, 2026-09-18/19) — the defective side

| matchID | period rows (final row in bold) | goal-list max | rule outcome |
|---|---|---|---|
| 84079 | 0-1 · 2-2 · **2-2** | 2-3 | `goals_vs_results` |
| 84080 | 0-0 · 0-0 · **0-0** | 4-3 | `goals_vs_results` |
| 84081 | 0-0 · 0-1 · **1-4** | 1-4 | clean |
| 84082 | 0-0 · 1-2 · **2-5** | 3-7 | `goals_vs_results` |
| 84083 | 0-1 · 1-1 · **1-2** | 1-3 | `goals_vs_results` |
| 84084 | 0-0 · 0-0 · **0-0** | 4-1 | `goals_vs_results` |
| 84085 | 1-0 · 2-2 · 3-2 · **3-4** | 3-4 | `impossible_layering` (3.Drittel 3-2 decisive yet an OT row 3-4 exists; the goal list shows the 3-3 equaliser at 59') |

6/7 quarantined, 1 clean. As designed: `parse_matchday` quarantines on
disagreement and keeps the row score — the numbers above are the exact
per-match outcomes asserted in `tests/test_hockey_schema.py::TestDel2ProbeSlice`.

### 4.2 CHL matchday 1 (`CHL/2026/1`, 2026-09-03/06) — the clean control

12 finished matches (81924–81933, 81935, 87593): **0 flagged.** Goal lists
agree with the rows everywhere (row 3 == running-score max, including the OT
rows). Both overtime games show correct hockey layering and must stay
unflagged:

| matchID | regulation row | overtime row | goal max |
|---|---|---|---|
| 81928 | 1-1 (draw) | 2-1 | 2-1 |
| 81935 | 2-2 (draw) | 3-2 | 3-2 |

(81929 is the real out-of-order-goal case of §2 — resolved to 2-5.)

Committed-correct layering controls: `del/2024` 76234 (reg 0-0 draw, OT 3-4,
goals agree) and 76504 (reg draw + shootout row). Committed false-positive
control for the *old* always-replace rule: 76220 (reg 5-5 draw, AP 5-6 —
shootout) — hand-verified against the official DEL sheet (STATUS "The DEL
flags were right").

## 5. Entry lags (CET/CEST → exact UTC)

`lastUpdateDateTime` is German local wall time (§2). Converted lags from
kickoff (`matchDateTimeUTC`) on the probes:

- **DEL2**: 2:50–3:18 h same evening (all 7 matches, 2026-09-18/19).
- **CHL**: 3:55–5:17 h for the four same-evening matches; matches 81924–81927
  (played Thu 2026-09-03) were entered in one batch on Sun 2026-09-06
  (lag ≈ 3 d 1–2 h).

Restated on exact stamps (this pass; the pre-audit figures were computed on
UTC-as-written stamps and are 1–2 h too high):

- **`bl1/2024`** (306 finished rows): min **1.82 h** (matchID 72414 — right
  after full time), p25 1.91 h, median 1.95 h, max 80 d; 282/306 rows
  entered the same evening. Football availability uses the exact
  `lastUpdateDateTime` instant itself (`availability_for`, converted with
  `cet_local_to_utc` since this audit; previously parsed as UTC and 1–2 h
  late).
- **`del/2024`** (407 finished rows): min **2.16 h** (matchID 76503), but
  p25 54 d / median 104 d / max 363 d — the season was entered and re-edited
  in end-of-season batches (a reason to pin every re-fetch). The documented
  `start+3h` inferred hockey availability covers the same-evening entries
  (DEL2 2:50–3:18 h is just past it — the row's own `retrieved_at_utc`
  governs what can be read).

The availability constructions are **not** re-fit here: `hockey start+3h` /
`darts start+12h` stay the documented conservative inferences, and football
availability is the row's exact `lastUpdateDateTime` instant (converted with
`cet_local_to_utc`; before this pass the stamp was parsed as UTC and results
released 1–2 h late) — all now backed by exact-stamp measurements instead of
corrupted ones.

`northstar.timeutil.cet_local_to_utc` (CET/CEST with fallback; ambiguous
fold-back hour → the later reading, spring-forward gap → the later algebraic
reading, aware input passes through) is wired into ingest
(`retrieved_at_utc`); round-trip `matchDateTime → UTC == matchDateTimeUTC`
holds on every committed row with both stamps (≥1,000 rows), and 2,921
committed `lastUpdateDateTime` stamps were scanned — none falls in a DST edge
window. The DARTS-AUDIT §3.2 proof case converts `2026-09-20T22:07:50.923` →
`20:07:50.923Z`, one minute *before* the 20:08:53Z capture that retrieved it.

## 6. Verification checklist

| # | Claim | URL | Checked |
|---|---|---|---|
| 1 | the 5962/4951/4790/4791 ids above | `getavailableleagues` | 2026-09-22 |
| 2 | DEL2 md1 rows / goals as in §4.1 | `getmatchdata/del2/2026/1` | 2026-09-22 |
| 3 | CHL md1 rows / goals as in §4.2 | `getmatchdata/CHL/2026/1` | 2026-09-22 |
| 4 | single-match endpoint unusable for CHL | `getmatchdata/CHL/2026/81927` → `[]` | 2026-09-22 |
| 5 | 76236 rows 0-0/4-2/0-0 vs goals 4-2 | `getmatchdata/del/2024/76236` (committed fixture) | 2026-09-22 |
| 6 | CET/CEST conversion + rule counts of §3 | `parse_matchday` over all committed fixtures + both probes (tests) | 2026-09-22 |

## Changelog

- **2026-09-22** — this audit; `goals_vs_results` + `goal_list_final`
  (elementwise-max) rule in `parse_matchday`; `inconsistency_reason`
  + goal-list evidence suffix on `RESULT_KIND_INCONSISTENT`;
  `cet_local_to_utc` conversion of `retrieved_at_utc`; `CURRENT_TARGETS`
  adds DEL2 + CHL (2026); probe slices
  `data/fixtures/openligadb_del2_2026_sd1.json` /
  `openligadb_chl_2026_sd1.json` committed;
  `NAIVE_BASELINE_FOR` + per-card baseline flag for the accuracy-only desks
  (app.js + `naive_baseline_comparison`).
