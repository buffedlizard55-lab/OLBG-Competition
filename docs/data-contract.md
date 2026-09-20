# Data contract and verification protocol

Status: **implemented for the pilot path** (football, 3-way match market) —
the code in `northstar/` enforces the gates below and `tests/` pins the
behaviour. Sport-specific market rules beyond the 3-way match market are still
design-only (section 2 lists what remains). See `docs/STATUS.md` for the
remaining-work list.

This document is the boundary between a useful paper-trading experiment and an invented track record. A production connector must satisfy this contract before a record can affect the leaderboard.

## 0. Implementation status (pilot)

| Contract section | Where it is enforced | State |
| --- | --- | --- |
| 1. Core entities | `northstar/models.py` (dataclasses), `northstar/db.py` (schema) | implemented; odds retain provider event ids |
| 2. Settlement arithmetic | `northstar/settlement.py::decimal_pnl` | implemented (3-way match market) |
| 3. Verification gates (1–7) | `northstar/settlement.py::settle_tip` (`GateLog`) | implemented |
| 4. Anomaly taxonomy | `northstar/models.py` constants, `northstar/db.py::add_anomaly` | implemented (adds `POLICY_VIOLATION`, `CONSENSUS_DRIFT`, `EVENT_CHANGED`) |
| 5. Research protocol | `northstar/backtest.py` (walk-forward, `TimeBoundedStore`, bootstrap CI) | implemented for football pilot |
| 6. Prediction writing contract | `northstar/predictor.py` (refuses without model/fair/edge evidence) | implemented |
| 7. Minimum test matrix | `tests/` (postponement, voids, duplicates, time leakage, disputes, arithmetic, ordering invariance) | implemented for the listed football cases |

Not yet implemented (design-only): handicap/totals/each-way market rules,
tennis/cricket/motor-racing/esports settlement, live multi-source identity
matching beyond the football pilot, an active organizer-authorized result
feed, and a production tip collector (OLBG collection is deliberately
manual-only — see `docs/LICENSING.md`). The Odds API historical connector is
implemented but cannot run without a paid entitlement and explicit terms
acknowledgement; no provider response is bundled.

## 1. Core entities

### `events`

| Field | Required | Rule |
| --- | --- | --- |
| `event_id` | yes | Stable internal ID; never use a display name as identity. |
| `source_event_ids` | yes | All IDs from the tip source and result source. |
| `sport` | yes | Controlled vocabulary; football and rugby union are not interchangeable. |
| `competition` | yes | League, tour, tournament, race, card, or event. |
| `participants` | yes | Structured participant IDs where possible; retain source display names. |
| `scheduled_start_utc` | yes | Original scheduled time, normalized to UTC. |
| `status` | yes | `scheduled`, `live`, `finished`, `postponed`, `cancelled`, `abandoned`, `disputed`. |
| `identity_confidence` | yes | `verified`, `probable`, or `unmatched`; only `verified` can settle. |
| `source_urls` | yes | Result/source links used for identity review. |

### `tips`

| Field | Required | Rule |
| --- | --- | --- |
| `tip_id` | yes | Immutable ID for one published selection. |
| `tipster_id` | yes | Stable source/user ID, not only a display name. |
| `strategy_id` | yes | `human`, `imported`, or a versioned model identifier. |
| `event_id` | yes | Must resolve to a verified event before settlement. |
| `market` | yes | Controlled market and ruleset, e.g. `match_winner_2way`. |
| `selection` | yes | Exact selection plus normalized participant ID. |
| `published_at_utc` | yes | Time the source exposed the tip. |
| `collected_at_utc` | yes | Time the collector observed it. |
| `cutoff_at_utc` | yes | Last permissible input time for any model feature. |
| `odds_decimal` | yes for PnL | Price captured at or after publication, before event start. |
| `odds_source` | yes for PnL | Permissioned source and market. |
| `stake_units` | yes | Paper stake only; no cash execution. |
| `source_url` | yes | Direct review link to the original selection. |
| `raw_payload_hash` | yes | Detects source edits or changed snapshots. |
| `status` | yes | `open`, `won`, `lost`, `void`, `push`, `pending`, `unsettleable`, `disputed`. |

### `odds_snapshots`

Store every observed price instead of overwriting it:

- `tip_id` (or `event_id` for a market board), `observed_at_utc`, `provider`,
  `source_event_id`, `market_key`, `selection_key`, and `decimal_odds`.
- For a licensed historical API, `observed_at_utc` is the provider's returned
  snapshot timestamp, not the requested timestamp. Reject the row when that
  timestamp is not strictly before the event start; retain the requested time
  in provenance/notes for audit.
- Reject zero, negative, non-finite, or unexplained format conversions.
- Preserve the raw response and its hash.
- A later price can be used for a separately named closing-line metric, never silently as the entry price.

### `results`

- `event_id`, `provider`, `retrieved_at_utc`, `source_url`, `raw_payload_hash`.
- `final_status`, `officially_final_at_utc`, `participants`, and sport-specific result fields.
- Preserve source version/amendment information when the organizer changes a result.
- A result is eligible only when the source is in the registry and the response identifies the same event and competition.

### `settlements`

- `tip_id`, `settled_at_utc`, `settlement_rule_version`, `outcome`, `pnl_units`, `result_id`, `verification_state`, `anomaly_ids`.
- Settlement is append-only. A correction creates a new settlement revision; it does not erase the prior audit record.
- `verification_state` must be `verified` before the PnL is visible on the leaderboard.

## 2. Settlement arithmetic

For a level-stakes decimal-odds bet with stake `s` and odds `o`:

- Won: `pnl = s × (o - 1)`
- Lost: `pnl = -s`
- Void: `pnl = 0` and remove the stake from turnover according to the market rules
- Push: `pnl = 0` and retain the sport-specific market interpretation

Report both `profit_units` and `turnover_units`. Never infer ROI from strike rate. Default leaderboard metrics:

- `ROI = verified_profit_units / verified_turnover_units`
- `strike_rate = wins / (wins + losses)`
- `max_drawdown = peak cumulative verified PnL - subsequent trough`
- `pending` and `unsettleable` records are excluded from both numerator and denominator

Market rules must be versioned for, at minimum: two-way vs three-way match markets, handicaps, totals, dead heats, each-way bets, retirement/non-runner handling, extra time, shootouts, abandoned events, rain-reduced cricket, tennis retirements, motor-racing classifications, and esports map/series settlement.

## 3. Verification gates

A record enters `verified` only when all gates pass:

1. **Identity:** participant names, competition, and start time match across the tip and result sources.
2. **Time:** publication and odds timestamps precede the event cutoff; timestamps are timezone-normalized.
3. **Market:** the selection is valid for the event and the market ruleset is known.
4. **Result:** a primary governing-body, league, or event-organizer source reports a final result.
5. **Reconciliation:** if two trusted sources disagree, stop settlement and create an anomaly.
6. **Integrity:** source hash, parser version, and raw payload are stored.
7. **Arithmetic:** settlement output is reproducible from the stored fields.

Until then, show the record in the review queue with a reason. Never convert uncertainty to a loss.

## 4. Anomaly taxonomy

Create an anomaly instead of guessing when any of these occur:

- `MISSING_ODDS`
- `ODDS_AFTER_START`
- `SOURCE_EDITED`
- `DUPLICATE_TIP`
- `EVENT_UNMATCHED`
- `PARTICIPANT_AMBIGUOUS`
- `COMPETITION_MISMATCH`
- `TIME_CONFLICT`
- `RESULT_NOT_FINAL`
- `RESULT_SOURCE_CONFLICT`
- `VOID_RULE_UNKNOWN`
- `MARKET_RULE_UNKNOWN`
- `TIP_EDITED_AFTER_CUTOFF`
- `JURISDICTION_NOT_COVERED`
- `POLICY_VIOLATION`
- `CONSENSUS_DRIFT`
- `EVENT_CHANGED`
- `RESULT_KIND_INCONSISTENT` — one source reports two mutually impossible
  result layers for the same event (e.g. a decisive "after regulation"
  entry coexisting with an overtime/shootout entry in DEL community rows).
  The priority rule still yields the standard final read, but the conflict
  is kept open for manual review with evidence URLs instead of being
  smoothed over.
- `MISSING_METADATA` — the source omitted a metadata field another row of
  the same payload carries (e.g. DEL matchID 76412 `leagueSeason: null`).
  If a conservative repair from unambiguous peers is applied, the exact
  inference is recorded here; the raw payload keeps the null.

The review queue should expose the raw links, timestamps, hashes, parser version, and an explanation. It should not provide a silent “force settle” path.

## 5. Research protocol

For every strategy and sport:

1. Define the market, population, feature cutoff, stake, odds source, result source, and exclusion rules before looking at performance.
2. Build a chronological dataset. Never randomly split events when time order matters.
3. Keep a final untouched test period and use walk-forward validation for tuning.
4. Compare with a no-edge baseline using market-implied probability; document bookmaker margin treatment.
5. Report sample size, turnover, ROI, strike rate, drawdown, calibration, confidence intervals, and missing-data rate.
6. Test sensitivity to price, stake, cutoff, league, season, and plausible settlement changes.
7. Correct for multiple comparisons when many hypotheses are tried.
8. Publish the exact source URLs and dataset snapshot IDs used by the report.
9. Forward-test in paper mode when no adequate historical odds archive exists. Mark the clock, freeze the selection, and do not backfill.
10. A strategy is not “proven” by a short run, a high strike rate, or an unverified source.

## 6. Prediction writing contract

A future prediction record must include:

- event and market identity;
- forecast or selection with probability and uncertainty, if the model supports it;
- the input cutoff and model/strategy version;
- only statistics whose source URL and retrieval time are stored;
- missing or conflicting inputs;
- an explicit statement that it is paper-only and not financial advice.

Natural-language prose may be clear and tipster-like, but style must never add facts that are absent from the structured evidence.

## 7. Minimum production test matrix

- Duplicate page capture does not duplicate a tip.
- Source edit changes the payload hash and opens an anomaly.
- A postponed event remains pending and does not lose stake.
- A cancelled event does not count in strike rate or turnover.
- A result from the wrong competition cannot settle an event.
- An odds timestamp after start is rejected for entry PnL.
- A tennis retirement follows the stored market rule, not a guess.
- Cricket reduced overs uses the declared competition settlement rule.
- A dead heat and motor-racing classification are reproducible.
- Two conflicting result providers create a review record.
- A result correction creates a settlement revision and auditable leaderboard update.
- A model cannot read a feature published after its cutoff.
