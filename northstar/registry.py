"""Hypothesis registry - the single source of truth for the strategy lab.

Previously this catalogue lived only inside app.js; it now lives in code so
tests can assert that every "Pilot-tested"/"Forward-live" entry maps to a
registered strategy and every registered strategy appears here.  Statuses:

- ``Pilot-tested``      walk-forward backtest on committed verified pilot
                        fixtures (PnL where an odds path exists, accuracy
                        where it does not);
- ``Forward-live``      prediction-only forward-test desk issuing frozen
                        pre-start calls on current-season captures;
- ``Ready to source``   designed, data gate identified, not yet run;
- ``Blocked``           no permissioned results path in this repository.

``refs`` are links a human reviewer can open to check the design rationale
or the data gate; they are verified before being listed (docs/STRATEGIES.md
records what was checked and when).  A design is not a proven edge.
"""
from __future__ import annotations

from typing import Any, Dict, List

REGISTRY_VERSION = "nr-hypothesis-registry-2026-09-20.2"

HYPOTHESES: List[Dict[str, Any]] = [
    # ------------------------------------------------ football: backtested
    {
        "sport": "Football", "name": "Market favourite (baseline)",
        "status": "Pilot-tested", "tested": "market-favourite-v1",
        "data": "Verified pilot fixtures/results - time-stamped odds",
        "test": "Walk-forward 1X2",
        "description": "Always backs the margin-removed market favourite. "
                       "Reference baseline: the market's own answer.",
        "refs": [],
    },
    {
        "sport": "Football", "name": "Market longshot (baseline probe)",
        "status": "Pilot-tested", "tested": "market-longshot-v1",
        "data": "Same verified pilot odds", "test": "Walk-forward 1X2",
        "description": "Always backs the least-favoured team outcome; "
                       "measures the favourite-longshot bias on the pilot.",
        "refs": [],
    },
    {
        "sport": "Football", "name": "Elo rating + price discipline",
        "status": "Pilot-tested", "tested": "elo-edge-v1",
        "data": "Verified pilot fixtures/results - time-stamped odds",
        "test": "Walk-forward 1X2",
        "description": "Elo 3-way model vs margin-removed market; bets the "
                       "model argmax only with a >=3-point edge.",
        "refs": [],
    },
    {
        "sport": "Football", "name": "Draw-No-Bet decisive form",
        "status": "Pilot-tested", "tested": "draw-no-bet-v1",
        "data": "Same verified pilot odds", "test": "Walk-forward 3-way "
                                                   "(DNB rule)",
        "description": "Backs the 2-way Elo leader in decisive-looking "
                       "games; a draw loses (DNB behaviour on 3-way odds).",
        "refs": [],
    },
    {
        "sport": "Football", "name": "Draw mispricing probe",
        "status": "Pilot-tested", "tested": "draw-value-v1",
        "data": "Same verified pilot odds", "test": "Walk-forward 1X2",
        "description": "Backs DRAW when the model's draw probability "
                       "exceeds the fair market draw probability by >=3 "
                       "points (retail under-buying of draws).",
        "refs": [],
    },
    {
        "sport": "Football", "name": "Home-advantage value probe",
        "status": "Pilot-tested", "tested": "home-edge-v1",
        "data": "Same verified pilot odds", "test": "Walk-forward 1X2",
        "description": "Backs HOME only on a >=5-point model edge over the "
                       "fair price - tests whether the market under- or "
                       "over-prices home advantage.",
        "refs": [],
    },
    {
        "sport": "Football", "name": "Form + price floor",
        "status": "Pilot-tested", "tested": "form-value-v1",
        "data": "Same verified pilot odds", "test": "Walk-forward 1X2",
        "description": "Classic tipster rule made auditable: back the "
                       "better recent-form side (last <=3 released "
                       "matches, >=1.0 pts/match gap) only at price >=1.80.",
        "refs": [],
    },
    {
        "sport": "Football", "name": "Football Elo favourite (forward desk)",
        "status": "Forward-live", "tested": "elo-favourite-3way-v1",
        "data": "OpenLigaDB current-season captures (ODbL) - no permissioned "
                "odds path for the current season",
        "test": "Forward ledger - accuracy/Brier as results arrive",
        "description": "No-market 3-way Elo argmax with a 45% selectivity "
                       "floor; frozen pre-start predictions for upcoming "
                       "Bundesliga fixtures.",
        "refs": [],
    },
    {
        "sport": "Football", "name": "Poisson goal totals",
        "status": "Ready to source",
        "description": "Estimate home and away scoring rates from "
                       "pre-cutoff history and test totals/handicap markets "
                       "once a permissioned odds path covers them.",
        "data": "Verified scores - line-up/time gate - licensed odds",
        "test": "Walk-forward totals", "refs": [],
    },
    # ------------------------------------------------ ice hockey
    {
        "sport": "Ice Hockey", "name": "Hockey Elo favourite (no-market)",
        "status": "Pilot-tested", "tested": "hockey-elo-v1",
        "data": "OpenLigaDB DEL pilot fixtures/results (ODbL) - no "
                "permissioned odds",
        "test": "Walk-forward 2-way accuracy",
        "description": "2-way Elo (final incl. OT/shootout) as a no-price "
                       "baseline; graded on accuracy/Brier because no "
                       "permissioned DEL odds path exists.",
        "refs": [],
    },
    {
        "sport": "Ice Hockey", "name": "Hockey Elo forward desk",
        "status": "Forward-live", "tested": "hockey-elo-v1",
        "data": "OpenLigaDB DEL current-season captures (ODbL)",
        "test": "Forward ledger - accuracy as results arrive",
        "description": "Same 2-way Elo model issuing frozen pre-start "
                       "predictions for upcoming DEL fixtures once the "
                       "current-season capture lands.",
        "refs": [],
    },
    {
        "sport": "Ice Hockey", "name": "Goalie-adjusted expected goals",
        "status": "Blocked",
        "description": "Estimate shot quality and goalie availability "
                       "before puck drop; separate regulation, overtime "
                       "and shootout settlement.",
        "data": "Federation/league results - licensed odds",
        "test": "Moneyline / totals", "refs": [],
    },
    # ------------------------------------------------ darts
    {
        "sport": "Darts", "name": "Darts Elo favourite (no-market)",
        "status": "Pilot-tested", "tested": "darts-elo-v1",
        "data": "OpenLigaDB PDC captures (ODbL), schema-audited - no "
                "permissioned odds",
        "test": "Walk-forward 2-way accuracy",
        "description": "2-way player Elo on the decisive leg/set count (K=24, "
                       "no venue adjustment - research priors stated "
                       "before grading); prediction-only until a "
                       "permissioned darts odds path exists. Pilot "
                       "2026-09-20: 0 selections on the cold 2025 pool "
                       "(141 matches, max prob 0.551), then 48 graded "
                       "(39 hits, 81.25%, Brier 0.349) on the full "
                       "423-match 2025-26 pool - same priors, no refit; "
                       "large error bar, no market baseline, no skill "
                       "claim; see docs/DARTS-AUDIT.md.",
        "refs": [],
    },
    {
        "sport": "Darts", "name": "Throw rate plus checkout profile",
        "status": "Blocked",
        "description": "Compare dated player rates while keeping format, "
                       "leg distance and event rules consistent; walkovers "
                       "are not losses.",
        "data": "Organizer results - format rules - licensed odds",
        "test": "Match / handicap",
        "refs": [],
    },
    # ------------------------------------------------ blocked sports
    {
        "sport": "Horse Racing", "name": "Place probability by field size",
        "status": "Blocked",
        "description": "Calibrate place probability separately by race "
                       "type, field size, going, jurisdiction and declared "
                       "non-runners; define dead heats before testing.",
        "data": "Organizer result - runner archive - licensed odds",
        "test": "Jurisdiction-specific", "refs": [],
    },
    {
        "sport": "Tennis", "name": "Surface-adjusted Elo",
        "status": "Blocked",
        "description": "Player ratings split by surface, match-start "
                       "cutoff, retirements defined before any test.",
        "data": "Governing-body/organizer results - licensed odds",
        "test": "Match-level Brier + ROI", "refs": [],
    },
    {
        "sport": "Golf", "name": "Strokes-gained and course fit",
        "status": "Blocked",
        "description": "Pre-tournament form and course-fit features vs a "
                       "dated outright price; ties/dead heats defined "
                       "first.",
        "data": "Tour organizer leaderboards - licensed odds",
        "test": "Outright / place", "refs": [],
    },
    {
        "sport": "American Football",
        "name": "Efficiency differential with injury freshness",
        "status": "Blocked",
        "description": "Dated injury state, explicit regulation/overtime "
                       "settlement, no post-selection inputs.",
        "data": "League results - dated injury archive - licensed odds",
        "test": "Spread / total", "refs": [],
    },
    {
        "sport": "Baseball", "name": "Starting pitcher and bullpen split",
        "status": "Blocked",
        "description": "Pre-game pitcher, bullpen availability and park "
                       "effects without leaking post-lineup information.",
        "data": "League results - lineups - licensed odds",
        "test": "Moneyline / totals", "refs": [],
    },
    {
        "sport": "Basketball", "name": "Rest and travel-adjusted rating",
        "status": "Blocked",
        "description": "Separate home advantage, rest days, travel and "
                       "overtime from team strength; explicit regulation/"
                       "overtime markets.",
        "data": "League results - schedule - licensed odds",
        "test": "Moneyline / spread", "refs": [],
    },
    {
        "sport": "Cricket", "name": "Venue and innings-state model",
        "status": "Blocked",
        "description": "Format-specific run rates by venue and innings; "
                       "rain-reduced matches, declarations and abandoned "
                       "games handled explicitly.",
        "data": "Competition scorecards - format rules - licensed odds",
        "test": "Match / innings markets", "refs": [],
    },
    {
        "sport": "Cycling", "name": "Course-fit performance delta",
        "status": "Blocked",
        "description": "Time trials vs mass-start events; governing-body "
                       "classifications with a pre-start feature cutoff.",
        "data": "Organizer classifications - licensed odds",
        "test": "Outright / placement", "refs": [],
    },
    {
        "sport": "Gaelic Football", "name": "Score-difference rating",
        "status": "Blocked",
        "description": "Gaelic football modelled separately from rugby; "
                       "venue/scoring rules with postponed and replayed "
                       "fixtures explicit.",
        "data": "Competition organizer results - licensed odds",
        "test": "Match / handicap", "refs": [],
    },
    {
        "sport": "Greyhounds", "name": "Box/track pace profile",
        "status": "Blocked",
        "description": "Trap, distance, going, field and non-runner state "
                       "frozen at selection time; voids and photo-finish "
                       "revisions defined.",
        "data": "Track/organizer results - licensed odds",
        "test": "Win / place", "refs": [],
    },
    {
        "sport": "Handball", "name": "Possession and pace split",
        "status": "Blocked",
        "description": "League vs tournament rules, extra time and "
                       "seven-metre shootouts separated before grading.",
        "data": "Federation results - licensed odds",
        "test": "Match / total", "refs": [],
    },
    {
        "sport": "Hurling", "name": "Venue-adjusted scoring rate",
        "status": "Blocked",
        "description": "Competition-specific scoring and replay rules; "
                       "never pooled with Gaelic or association football.",
        "data": "Competition organizer results - licensed odds",
        "test": "Match / handicap", "refs": [],
    },
    {
        "sport": "Motor Racing", "name": "Qualifying-to-finish delta",
        "status": "Blocked",
        "description": "Pre-race information only; retirements, classified "
                       "finish, penalties, podium and each-way places "
                       "defined per series.",
        "data": "Series organizer results - licensed odds",
        "test": "Finish / podium", "refs": [],
    },
    {
        "sport": "Rugby Union", "name": "Set-piece and territory rating",
        "status": "Blocked",
        "description": "Union and league kept separate; competition rules, "
                       "extra time and abandoned matches explicit.",
        "data": "Union organizer results - licensed odds",
        "test": "Match / handicap", "refs": [],
    },
    {
        "sport": "Rugby League", "name": "Tackle/territory rating",
        "status": "Blocked",
        "description": "Rugby codes not pooled; golden-point, abandoned "
                       "and handicap rules defined before backtesting.",
        "data": "League organizer results - licensed odds",
        "test": "Match / handicap", "refs": [],
    },
    {
        "sport": "Snooker", "name": "Frame-strength and break profile",
        "status": "Blocked",
        "description": "Match format, walkovers and frame handicaps "
                       "separated; ranking/form features frozen pre-match.",
        "data": "Tour organizer results - licensed odds",
        "test": "Match / frame handicap", "refs": [],
    },
    {
        "sport": "Volleyball", "name": "Set differential rating",
        "status": "Blocked",
        "description": "Best-of format, golden-set rules and walkovers "
                       "explicit; a missing set is never a loss.",
        "data": "Federation results - licensed odds",
        "test": "Match / set handicap", "refs": [],
    },
    {
        "sport": "Boxing", "name": "Opponent-adjusted performance",
        "status": "Blocked",
        "description": "Organizer/commission results; record, weight class "
                       "and bout rules frozen at selection time; MMA kept "
                       "separate.",
        "data": "Organizer results - licensed odds",
        "test": "Fight winner / method", "refs": [],
    },
]


def registry_payload() -> Dict[str, Any]:
    return {"version": REGISTRY_VERSION, "hypotheses": HYPOTHESES}


def tested_ids() -> List[str]:
    return [h["tested"] for h in HYPOTHESES if h.get("tested")]
