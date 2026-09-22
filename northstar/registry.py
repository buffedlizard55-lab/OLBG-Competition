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

REGISTRY_VERSION = "nr-hypothesis-registry-2026-09-22.3"

HYPOTHESES: List[Dict[str, Any]] = [
    # ------------------- football: full-season no-market accuracy desks
    # Added 2026-09-22 (pass 3).  The whole 2024/25 Bundesliga season is
    # committed (306 finished results), so these desks are graded on real
    # results at 11x the frozen 27-match PnL pilot - no odds are read, so
    # there is no PnL claim and no Holm family membership.
    {
        "sport": "Football", "name": "Always-home season baseline",
        "status": "Pilot-tested", "tested": "football-home-baseline-v1",
        "data": "Whole committed 2024/25 bl1 season (306 finished results)",
        "test": "Walk-forward, 3-way accuracy (no odds)",
        "description": "Always predicts the home side with a flat "
                       "0.50/0.25/0.25 prior. Reference point for the "
                       "full-season football accuracy desks: the Elo desk "
                       "must beat this on the same matches or its hit rate "
                       "is not information.",
        "refs": [],
    },
    {
        "sport": "Football", "name": "Poisson totals season desk",
        "status": "Pilot-tested", "tested": "football-totals-poisson-v1",
        "data": "Whole committed 2024/25 bl1 season (306 finished results)",
        "test": "Walk-forward, over/under 2.5 accuracy (no odds)",
        "description": "Same independent-Poisson construction as the pilot "
                       "totals desk but with no price input: it states the "
                       "more likely side of the 2.5 line for EVERY match, "
                       "so it is comparable match-for-match with the "
                       "always-over baseline over a full season.",
        "refs": ["https://www.researchgate.net/publication/222532726"],
    },
    {
        "sport": "Football", "name": "Always-over 2.5 season baseline",
        "status": "Pilot-tested", "tested": "football-totals-over-v1",
        "data": "Same 306-match season", "test": "Walk-forward, O/U 2.5 "
                                                 "accuracy (no odds)",
        "description": "Always predicts OVER 2.5 with a flat 0.5/0.5 prior "
                       "(Brier 0.5 by construction). The share of over-2.5 "
                       "matches in the pool is the bar the model must "
                       "clear.",
        "refs": [],
    },
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
        "sport": "Football", "name": "Poisson goal totals (O/U 2.5)",
        "status": "Pilot-tested", "tested": "poisson-totals-value-v1",
        "data": "Same verified pilot file - its over/under 2.5 columns "
                "(B365/Avg/Max/BFE), same collection window",
        "test": "Walk-forward O/U 2.5 (half-goal line, no push)",
        "description": "Independent-Poisson goal model (Maher 1982 / "
                       "Dixon-Coles 1997 family): league rates + shrunk "
                       "attack/defence multipliers from released matches "
                       "only; bets over/under 2.5 with a >=3-point edge "
                       "over the margin-removed market. Priors "
                       "pre-registered, not fitted.",
        "refs": [
            "https://research-information.bris.ac.uk/en/publications/"
            "modelling-association-football-scores-and-inefficiencies-in-the-f/",
            "https://doi.org/10.1016/j.ijforecast.2009.10.002",
        ],
    },
    {
        "sport": "Football", "name": "Market totals favourite (O/U baseline)",
        "status": "Pilot-tested", "tested": "market-totals-favourite-v1",
        "data": "Same verified pilot over/under 2.5 prices",
        "test": "Walk-forward O/U 2.5",
        "description": "Always backs the market's more-likely side of "
                       "over/under 2.5. Baseline for the totals family.",
        "refs": [],
    },
    {
        "sport": "Football", "name": "Poisson Asian-handicap value",
        "status": "Pilot-tested", "tested": "ah-poisson-value-v1",
        "data": "Same verified pilot file - its Asian-handicap columns "
                "(AHh line + AvgAHH/AHA prices; the B365/Max/BFE columns "
                "are stored too), same collection window. Column semantics "
                "verified against the source's notes.txt 2026-09-22: "
                "'AHh = Market size of handicap (home team)'.",
        "test": "Walk-forward Asian handicap (quarter-line split, "
                "integer-line push)",
        "description": "The totals desk's independent-Poisson goal model "
                       "evaluated on the priced handicap line: full "
                       "P(win)/P(push)/P(lose) margin distribution, "
                       "quarter lines split half/half exactly as they "
                       "settle. Bets the side whose model EV beats the "
                       "de-margined market EV by >=3% per unit staked, "
                       "only with positive model EV. Pre-registered "
                       "priors, not fitted.",
        "refs": [],
    },
    {
        "sport": "Football", "name": "Market AH favourite (baseline)",
        "status": "Pilot-tested", "tested": "ah-market-favourite-v1",
        "data": "Same verified pilot Asian-handicap prices",
        "test": "Walk-forward Asian handicap",
        "description": "Always backs the margin-removed market favourite "
                       "side of the priced Asian handicap. Baseline for "
                       "the AH family, not a claimed edge.",
        "refs": [],
    },
    {
        "sport": "Football", "name": "Dixon-Coles low-score correction",
        "status": "Pilot-tested", "tested": "dixon-coles-v1",
        "description": "The independent-Poisson model mis-estimates "
                       "low-score dependencies (0-0, 1-0, 0-1, 1-1); "
                       "Dixon-Coles add a tau correction. Implemented as "
                       "a 1X2 value desk with a pre-registered rho=-0.10 "
                       "prior (not fitted); negative score cells reject "
                       "the bet outright. Same verified pilot fixtures "
                       "and released-data construction as the totals "
                       "desk; enters the Holm PnL family.",
        "data": "Verified pilot fixtures/results - same odds columns",
        "test": "Walk-forward 1X2", "refs": [],
    },
    {
        "sport": "Football", "name": "Elo recency decay",
        "status": "Pilot-tested", "tested": "elo-decay-v1",
        "description": "The frozen elo-edge-v1 desk weights every past "
                       "match forever once it has moved a rating. "
                       "Implemented as a control desk sharing the SAME "
                       "rating history (elo_update) but reading ratings "
                       "relaxed toward 1500 with a pre-registered "
                       "365-day half-life (stated before grading, never "
                       "tuned on pilot outcomes). Same 3-way mapping and "
                       "edge rule; enters the Holm PnL family.",
        "data": "Verified pilot fixtures/results - time-stamped odds",
        "test": "Walk-forward 1X2 (vs elo-edge-v1 as control)",
        "refs": [],
    },
    {
        "sport": "Football", "name": "Both teams to score (BTTS)",
        "status": "Blocked",
        "description": "Derived yes/no market from the goal model; "
                       "requires BTTS prices, which the pilot file does "
                       "not carry (no B365>BTTS-style columns exist in "
                       "football-data exports) - a priced BTTS source is "
                       "the gate, not the model.",
        "data": "BTTS odds source - verified results",
        "test": "Walk-forward BTTS", "refs": [],
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
        "sport": "Ice Hockey", "name": "Home-ice naive baseline",
        "status": "Pilot-tested", "tested": "hockey-home-v1",
        "data": "OpenLigaDB DEL pilot fixtures/results (ODbL) - no "
                "permissioned odds",
        "test": "Walk-forward 2-way accuracy (flat 0.5/0.5 prior)",
        "description": "Always predicts HOME with a flat 0.5/0.5 prior "
                       "(uninformative by design: Brier stays 0.5; the hit "
                       "rate is the point). Gives the hockey accuracy "
                       "desks their no-information reference: if the Elo "
                       "desk does not beat the home share, its hit rate is "
                       "not evidence of information. Prediction-only, "
                       "never PnL. Also runs as a forward desk so the live "
                       "calls have a live naive benchmark.",
        "refs": [],
    },
    {
        "sport": "Ice Hockey", "name": "Regulation-time 3-way model",
        "status": "Pilot-tested", "tested": "hockey-reg-poisson-v1",
        "description": "Independent-Poisson goal model (Maher/Dixon-"
                       "Coles lineage, released-data league rates + shrunk "
                       "team multipliers, generic prior 3.1/2.9 until "
                       "10 released matches - all pre-registered) stating "
                       "the regulation-time (3-period) 3-way view for "
                       "every match. Grading needed reliable regulation "
                       "outcomes: the adapter's stored final row carries "
                       "the result kind, so After90Minutes finals give "
                       "the regulation scoreline and AfterExtraTime/"
                       "AfterPenalties finals are proof of a drawn "
                       "regulation (evaluation.regulation_outcome); the "
                       "4 DEL matches with impossible regulation+OT/SO "
                       "layering stay flagged and excluded from grading "
                       "by the review queue. Prediction-only - no "
                       "permissioned DEL odds path.",
        "data": "OpenLigaDB DEL season payloads (ODbL) - kind-based "
                "regulation outcomes, no period-row audit needed",
        "test": "Walk-forward regulation 3-way accuracy/Brier",
        "refs": [],
    },
    {
        "sport": "Ice Hockey", "name": "Regulation home naive baseline",
        "status": "Pilot-tested", "tested": "hockey-reg-home-v1",
        "data": "OpenLigaDB DEL season payloads (ODbL) - no "
                "permissioned odds",
        "test": "Walk-forward regulation 3-way accuracy (flat prior)",
        "description": "Always predicts HOME in regulation time with a "
                       "flat 0.5/0/0.5 prior (uninformative by design). "
                       "The regulation analogue of hockey-home-v1: the "
                       "Poisson 3-way desk must beat the share of "
                       "regulation home wins on the same pool or its "
                       "numbers are not evidence of information. "
                       "Prediction-only, never PnL.",
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
    {
        "sport": "Ice Hockey", "name": "DEL2 / CHL results extension",
        "status": "Ready to source",
        "description": "OpenLigaDB lists DEL2 2026 (leagueId 5962) and CHL "
                       "2026 (4951). Live probe 2026-09-20 of "
                       "getmatchdata/del2/2026/1: matchday finished, but "
                       "period rows are labelled HalfTime/After90Minutes "
                       "and their scores disagree with the goal list (e.g. "
                       "matchID 84080 After90 row 0-0 vs 4-3 in goals). "
                       "Ingest must not grade such rows; a schema audit + "
                       "tests (like docs/DARTS-AUDIT.md) is the gate.",
        "data": "OpenLigaDB (ODbL) - schema audit gate - no odds",
        "test": "Prediction-only 2-way accuracy",
        "refs": ["https://api.openligadb.de/getmatchdata/del2/2026/1"],
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
    {
        "sport": "Darts", "name": "Listed-first naive baseline",
        "status": "Pilot-tested", "tested": "darts-listed-first-v1",
        "data": "OpenLigaDB PDC captures (ODbL), schema-audited - no "
                "permissioned odds",
        "test": "Walk-forward 2-way accuracy (flat 0.5/0.5 prior)",
        "description": "Always predicts the listed-first player with a "
                       "flat 0.5/0.5 prior (uninformative by design). The "
                       "audit found listing order carries no "
                       "home-advantage meaning, so a hit rate far from 50% "
                       "would itself be a data finding about the pool. "
                       "Reference point for the darts Elo accuracy "
                       "numbers. Prediction-only, never PnL.",
        "refs": [],
    },
    {
        "sport": "Darts", "name": "Leg-margin rating",
        "status": "Ready to source",
        "description": "pointsTeam1/2 are decisive leg/set counts "
                       "(audit-verified), so a margin-of-victory rating "
                       "(winning 7-0 says more than 7-6) is sourceable "
                       "from the committed payloads. Pre-register the "
                       "margin transform before grading.",
        "data": "OpenLigaDB PDC captures (ODbL) - leg counts audited",
        "test": "Walk-forward 2-way accuracy", "refs": [],
    },
    # ------------------------------------------------ blocked sports
    {
        "sport": "Ice Hockey",
        "name": "Margin-of-victory Elo (2-way final)",
        "status": "Pilot-tested", "tested": "hockey-elo-mov-v1",
        "data": "OpenLigaDB DEL 2024/25 whole season (ODbL) - no "
                "permissioned odds",
        "test": "Walk-forward 2-way accuracy + Brier (no PnL)",
        "description": "Same expected-score function and home advantage as "
                       "hockey-elo-v1, but the update scales with the goal "
                       "margin (K x g with the World-Football-Elo weights, "
                       "reference R11). Pre-registered control: does the "
                       "size of a win carry information plain W/L Elo "
                       "discards? Prediction-only, graded on accuracy/Brier "
                       "against the hockey-home-v1 baseline.",
        "refs": ["https://www.eloratings.net/about",
                 "https://doi.org/10.1016/j.ijforecast.2009.10.002"],
    },
    {
        "sport": "Ice Hockey",
        "name": "Poisson total goals O/U 5.5",
        "status": "Pilot-tested", "tested": "hockey-totals-poisson-v1",
        "data": "OpenLigaDB DEL 2024/25 whole season (ODbL) - no "
                "permissioned odds",
        "test": "Walk-forward binary accuracy + Brier (no PnL)",
        "description": "Second prediction-only market for hockey: the "
                       "Maher/Dixon-Coles independent-Poisson goal model "
                       "(same league-rate/shrunk-multiplier construction as "
                       "the regulation 3-way desk) states the more likely "
                       "side of the 5.5 total for every match. Graded "
                       "against the always-over baseline "
                       "(hockey-totals-over-v1).",
        "refs": ["https://research-information.bris.ac.uk/en/publications/"
                 "modelling-association-football-scores-and-inefficiencies-"
                 "in-the-f/"],
    },
    {
        "sport": "Ice Hockey",
        "name": "Always-over naive baseline (totals)",
        "status": "Pilot-tested", "tested": "hockey-totals-over-v1",
        "data": "Same verified DEL results",
        "test": "Walk-forward binary accuracy + Brier (no PnL)",
        "description": "Reference bar for the totals desk: always over 5.5 "
                       "goals, flat 0.5/0.5 prior (Brier 0.5 by "
                       "construction; the hit rate is the point).",
        "refs": [],
    },
    {
        "sport": "Darts",
        "name": "Margin-of-victory Elo",
        "status": "Pilot-tested", "tested": "darts-mov-elo-v1",
        "data": "OpenLigaDB PDC captures (ODbL) - no permissioned odds",
        "test": "Walk-forward 2-way accuracy + Brier (no PnL)",
        "description": "The plain darts Elo with the update scaled by the "
                       "stored leg/set margin (same margin weights as the "
                       "hockey MoV desk). The margin unit differs by event "
                       "format and the source does not label it per row - a "
                       "stated weakness, recorded in every model trail. "
                       "Graded against darts-listed-first-v1.",
        "refs": ["https://www.eloratings.net/about"],
    },
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
                       "settlement, no post-selection inputs. Data gate "
                       "checked 2026-09-20: OpenLigaDB carries 'nfl' only "
                       "for 2014-2023 and getmatchdata/nfl/2026 returns an "
                       "empty list - no permitted current results path.",
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
                       "overtime markets. Data gate checked 2026-09-20: "
                       "OpenLigaDB basketball leagues (BBL2010, BBL1718, "
                       "BBBL1 2018) are historical community uploads with "
                       "no current season - no permitted results path.",
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
                       "seven-metre shootouts separated before grading. "
                       "Data gate checked 2026-09-20: OpenLigaDB 'hbl' "
                       "covers 2011-2016 and HBL/HBL23 2023 only; "
                       "getmatchdata/HBL/2026 and /hbl/2025 return empty "
                       "lists - no permitted current results path.",
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
                       "explicit; a missing set is never a loss. Data gate "
                       "checked 2026-09-20: OpenLigaDB lists VBL1/vblf1 "
                       "under sportId 44 ('Test', the same bucket as the "
                       "PDC darts leagues); no season was probed with "
                       "data, so no results path is claimed.",
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
