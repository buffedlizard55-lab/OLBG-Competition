# OLBG sport source register (generated)

Version `nr-sport-sources-2026-09-22.1` · evidence fetched 2026-09-22 · rendered from `data/sources/olbg_sports.json` by `python -m northstar.cli facts`. Do not edit by hand: `tests/test_sources.py` revalidates the file and this document is regenerated with it.

**21 sport families · 46 registered strategy designs (27 graded) · 3 permitted automatically, 17 awaiting a licence review, 1 blocked by robots.txt.**

Reading rules: a robots.txt verdict is the site's crawling policy, **not** a licence. `licence: not_reviewed` means no permission has been established, so no collection happens. The only sources with `permitted_open_licence` are those already recorded and tested in `northstar/policy.py`.

## Horse Racing

- **Coverage today:** none - verification_blocked
- **Automation gate:** `blocked_pending_licence_review`
- **Registered designs:** 2 (0 graded)

| candidate result source | link | robots.txt | licence |
|---|---|---|---|
| [British Horseracing Authority (BHA) - official regulator](https://www.britishhorseracing.com/) *(deep link unverified)* | [evidence](https://www.britishhorseracing.com/terms-and-conditions/) | [robots.txt](https://www.britishhorseracing.com/robots.txt) · `partial` · fetched 2026-09-22 | `not_reviewed` |

- **British Horseracing Authority (BHA) - official regulator** robots.txt says (verbatim):

  ```text
  User-agent: *
  Disallow: /wp-admin/
  Disallow: /feeds/
  crawl-delay: 10
  ```

Strategy designs (pre-registered, gate-checked):

- design-stage — *Market-favourite baseline (reference desk)*: Favourites in UK/IRE flat and jumps races are systematically underbet relative to longshots; the desk must first reproduce the documented favourite-longshot bias on this jurisdiction's data before any fade is tested. Rule: Level-stake the margin-removed market favourite in every race of the selected jurisdiction; report strike rate, ROI and the longshot half of the same sample as the control. Gate: Needs a permissioned race-result source (declared runners, going, dead heats) plus a licensed odds archive; dead heats and non-runners must be defined before the first bet.
  - prior: https://www.nber.org/papers/w15923
- design-stage — *Place-probability calibration by field size*: Place probability is mis-modelled when field size and each-way terms are pooled; calibration by field size will show where the market's place prices drift. Rule: Fit place probabilities separately for each field-size band and race type, then grade calibration (reliability curve) against official placings; no bet is placed until calibration beats the pooled model out of sample. Gate: Same result-source gate as above, plus official each-way terms per race.

**Next action:** Human decision on a licensed racing-results/odds provider (e.g. an official race-data licence); nothing may be collected from the regulator's site without a licence review.

## Football

- **Coverage today:** pilot_verified for the 27-match Bundesliga 1 2024/25 PnL pilot (dual-source result check), prediction-only forward desks on bl1/pl/bl2/la1 2026/27
- **Automation gate:** `permitted_open_licence`
- **Registered designs:** 17 (17 graded)

| candidate result source | link | robots.txt | licence |
|---|---|---|---|
| [OpenLigaDB (community results database)](https://api.openligadb.de/getmatchdata/bl1/2024) | [evidence](https://openligadb.de/lizenz) | [robots.txt](https://api.openligadb.de/robots.txt) · `allows_results` · fetched 2026-09-20 | `open_licence_verified` |
| [League/organizer official sites (DFL, Premier League, LaLiga) as cross-check](https://www.bundesliga.com/) *(deep link unverified)* | [evidence](https://www.bundesliga.com/en/bundesliga/service/terms-of-use) | [robots.txt](https://www.bundesliga.com/robots.txt) · `unknown` · fetched 2026-09-22 | `not_reviewed` |

- **OpenLigaDB (community results database)** robots.txt says: `No robots restrictions are imposed by the API host; the documented limit is 60 requests/minute/IP (api.openligadb.de front page).`
- **League/organizer official sites (DFL, Premier League, LaLiga) as cross-check** robots.txt says: `not fetched - recorded here only as the human-review candidate for an independent cross-check`

Strategy designs (pre-registered, gate-checked):

- **graded** `market-favourite-v1` — *Market favourite (baseline)*: Bookmaker favourites are the least-losing naive strategy on the verified pilot. Rule: Level-stake the market-average favourite every match. Gate: passed (football-data.co.uk manual pilot import + OpenLigaDB ODbL results)
  - prior: https://www.nber.org/papers/w15923
- **graded** `elo-edge-v1` — *Elo value edge*: A plain Elo rating finds value against the margin-removed market average. Rule: Elo K=40, home advantage 60, 3-way logistic; bet only with a >= 3-point model edge. Gate: passed
  - prior: https://doi.org/10.1016/j.ijforecast.2009.10.002
- **graded** `dixon-coles-v1` — *Dixon-Coles 1X2 value*: The Dixon-Coles low-score correction finds 1X2 value the independent Poisson misses. Rule: Bivariate score matrix with the tau correction (rho=-0.10 pre-registered); bet the argmax with a >= 3-point edge. Gate: passed
  - prior: https://research-information.bris.ac.uk/en/publications/modelling-association-football-scores-and-inefficiencies-in-the-f/
- **graded** `poisson-totals-value-v1` — *Poisson totals value (O/U 2.5)*: A league-rate Poisson goal model finds value in the over/under 2.5 price. Rule: League rates + shrunk attack/defence multipliers from released matches; bet a >= 3-point edge. Gate: passed
- **graded** `ah-poisson-value-v1` — *Poisson Asian-handicap value*: The Poisson goal model finds value on the priced Asian handicap line. Rule: Same Poisson model evaluated on the stored AH line; quarter lines split the stake; positive EV and a >= 3% edge required. Gate: passed
- **graded** `elo-favourite-3way-v1` — *Football Elo favourite (forward desk)*: No-market Elo picks beat the home baseline on the current season's results. Rule: 3-way Elo argmax with a 45% selectivity floor; frozen pre-start in the append-only forward ledger. Gate: results-only (OpenLigaDB 2026/27 captures); no permissioned odds path, so accuracy/Brier only
  - prior: https://doi.org/10.1016/j.ijforecast.2009.10.002
- **graded** `market-longshot-v1` — *Market longshot (baseline probe)*: If the documented favourite-longshot bias is present, backing the longest shot should lose heavily - a direction check on the pilot data, not a strategy. Rule: Level-stake the longest-priced outcome in every match. Gate: passed (baseline probe)
  - prior: https://www.nber.org/papers/w15923
- **graded** `elo-decay-v1` — *Recency-decay Elo control*: Older matches carry less information; ratings that relax toward the 1500 seed on a 365-day half-life improve on plain Elo. Rule: Identical to elo-edge-v1 with R_eff(t) = 1500 + (R-1500)*2^(-dt/365d). Gate: passed (control desk)
  - prior: https://doi.org/10.1016/j.ijforecast.2009.10.002
- **graded** `draw-value-v1` — *Draw mispricing probe*: Draws are systematically over-priced as longshots in some samples (returning value when the model's draw probability exceeds the fair price). Rule: Bet DRAW when model draw probability minus margin-removed price >= 3 points. Gate: passed
  - prior: https://www.sciencedirect.com/science/article/pii/S0169207024000670
- **graded** `home-edge-v1` — *Home-advantage value probe*: Home advantage is mispriced when crowd effects change (ghost games), in either direction. Rule: Bet HOME only with a >= 5-point model edge over the fair price. Gate: passed
  - prior: https://www.researchgate.net/publication/358982251_Home_advantage_in_professional_soccer_and_betting_market_efficiency_The_role_of_spectator_crowds
- **graded** `form-value-v1` — *Form + price floor*: Recent-form information is undervalued by odds (tipster rule, made auditable). Rule: Back the better recent-form side (>= 1.0 pts/match gap over last 3 released matches) only at price >= 1.80. Gate: passed
  - prior: https://research-api.cbs.dk/ws/portalfiles/portal/60750333/237159_final_digital.pdf
- **graded** `draw-no-bet-v1` — *Draw-No-Bet decisive form*: Removing the draw from a 3-way price is a testable construction, not automatically an edge. Rule: Elo edge on the 2-way DNB projection, decisive matches only. Gate: passed
- **graded** `market-totals-favourite-v1` — *Market totals favourite (baseline)*: Reference desk for the O/U 2.5 market: does the market's own favourite beat a goal model? Rule: Always back the margin-removed market favourite side of the 2.5 line. Gate: passed (baseline)
- **graded** `ah-market-favourite-v1` — *Market AH favourite (baseline)*: Reference desk for the Asian-handicap market. Rule: Always back the margin-removed market favourite side of the priced AH line (quarter lines split the stake). Gate: passed (baseline)
- **graded** `football-home-baseline-v1` — *Always-home season baseline*: The full-season no-market desks must beat 'always home' on the same 306 matches or their hit rate is not information. Rule: Always predict the home side; flat 0.50/0.25/0.25 prior stated before grading (never fitted). Gate: passed (baseline, added 2026-09-22)
- **graded** `football-totals-poisson-v1` — *Poisson totals season desk*: The independent-Poisson totals model's 2.5-line argmax beats the always-over baseline over a whole committed season. Rule: Same Poisson construction as the pilot totals desk with no price input; states the more likely side of 2.5 for every match. Gate: passed (added 2026-09-22); no odds path, accuracy/Brier only
  - prior: https://www.researchgate.net/publication/222532726
- **graded** `football-totals-over-v1` — *Always-over 2.5 season baseline*: The share of over-2.5 matches in the pool is the bar the totals model must clear; if it does not, the model has shown no information. Rule: Always predict OVER 2.5; flat 0.5/0.5 prior (Brier 0.5 by construction). Gate: passed (baseline, added 2026-09-22)

**Next action:** Keep the forward desks running; add a second independent result source for the current season and a licensed odds path before any 2026/27 PnL exists.

## Tennis

- **Coverage today:** none - verification_blocked
- **Automation gate:** `blocked_pending_licence_review`
- **Registered designs:** 1 (0 graded)

| candidate result source | link | robots.txt | licence |
|---|---|---|---|
| [ITF (International Tennis Federation) - official](https://www.itftennis.com/) *(deep link unverified)* | [evidence](https://www.itftennis.com/en/terms-and-conditions/) | [robots.txt](https://www.itftennis.com/robots.txt) · `allows_results` · fetched 2026-09-22 | `not_reviewed` |

- **ITF (International Tennis Federation) - official** robots.txt says (verbatim):

  ```text
  #robots.txt
  User-agent: *
  Disallow: /umbraco/
  Allow: /
  Sitemap: https://www.itftennis.com/en/sitemap/general-xml-sitemap/
  ```

Strategy designs (pre-registered, gate-checked):

- design-stage — *Surface-adjusted Elo*: Player strength is surface-specific; a surface-split Elo beats a single-rating Elo on match-winner accuracy and on price value. Rule: Maintain separate hard/clay/grass ratings updated from completed matches only; bet the model favourite only when the model edge over the margin-removed price exceeds a pre-registered threshold; grade accuracy and (with odds) ROI. Gate: Needs a permissioned ATP/WTA/ITF result feed with a documented retirement/walkover rule and a licensed odds archive.
  - prior: https://doi.org/10.1016/j.ijforecast.2009.10.002

**Next action:** Read the ITF/ATP/WTA terms and decide on a licensed results+odds path; nothing is collected today.

## Golf

- **Coverage today:** none - verification_blocked
- **Automation gate:** `blocked_pending_licence_review`
- **Registered designs:** 1 (0 graded)

| candidate result source | link | robots.txt | licence |
|---|---|---|---|
| [DP World Tour (European Tour) - official](https://www.europeantour.com/) *(deep link unverified)* | [evidence](https://www.europeantour.com/terms-of-use/) | [robots.txt](https://www.europeantour.com/robots.txt) · `partial` · fetched 2026-09-22 | `not_reviewed` |

- **DP World Tour (European Tour) - official** robots.txt says (verbatim):

  ```text
  User-Agent: *
  Allow: /api/images/
  ...
  Disallow: /dist/
  Disallow: /api/
  Disallow: /mobile/
  Disallow: /search/
  Disallow: /test/
  Disallow: /library/
  Sitemap: https://www.europeantour.com/sitemap-index.xml
  ```

Strategy designs (pre-registered, gate-checked):

- design-stage — *Course-fit and strokes-gained form*: Strokes-gained approach/putting form plus course fit predicts outright and place finishes better than world ranking alone. Rule: Build pre-tournament features only from rounds completed before the entry cutoff; grade calibration on outright win and place markets; ties and dead heats defined by the organizer's published result (playoff vs shared place). Gate: Needs a permissioned leaderboard feed with the organizer's official final classification and a licensed odds archive.

**Next action:** Licence review of the tour's leaderboard terms; define tie/playoff settlement rules first.

## American Football

- **Coverage today:** none - verification_blocked
- **Automation gate:** `blocked_pending_licence_review`
- **Registered designs:** 1 (0 graded)

| candidate result source | link | robots.txt | licence |
|---|---|---|---|
| [NFL - official](https://www.nfl.com/) *(deep link unverified)* | [evidence](https://www.nfl.com/legal/terms) | [robots.txt](https://www.nfl.com/robots.txt) · `partial` · fetched 2026-09-22 | `not_reviewed` |

- **NFL - official** robots.txt says (verbatim):

  ```text
  User-agent: *
  Disallow: /_ctv/
  Disallow: /_fantasy-app/
  Disallow: /_libraries/
  Disallow: /_mobile-app/
  Disallow: /_mobileview/
  Disallow: /_phs/
  Disallow: /_sponsors/
  Disallow: /account/
  Disallow: /nfl-films-beta/
  Disallow: /search/
  Sitemap: https://www.nfl.com/sitemap-index.xml
  ```

Strategy designs (pre-registered, gate-checked):

- design-stage — *Efficiency differential with injury freshness*: Dated injury reports and rest differential move spread/total outcomes beyond a pure rating model. Rule: Freeze injury state at the published report deadline; never use post-selection information; grade against margin and total settlements including overtime rules. Gate: Needs a permissioned result + dated injury feed and a licensed odds archive.

**Next action:** Licence review; then a dedicated NFL settlement rule set (ties/OT) before any grading.

## Baseball

- **Coverage today:** none - verification_blocked
- **Automation gate:** `blocked_pending_licence_review`
- **Registered designs:** 1 (0 graded)

| candidate result source | link | robots.txt | licence |
|---|---|---|---|
| [MLB - official](https://www.mlb.com/) *(deep link unverified)* | [evidence](https://www.mlb.com/official-information/terms-of-use) | [robots.txt](https://www.mlb.com/robots.txt) · `partial` · fetched 2026-09-22 | `not_reviewed` |

- **MLB - official** robots.txt says (verbatim):

  ```text
  User-agent: *
  Disallow: /test/
  Disallow: /api/
  Disallow: /app/
  Disallow: /embed/
  Disallow: /en/
  Disallow: /mlb/
  Disallow: /share/
  Disallow: /tokens/
  Disallow: /tv/
  Disallow: /web/
  ...
  ```

Strategy designs (pre-registered, gate-checked):

- design-stage — *Starting pitcher and bullpen split*: Pre-game announced starters plus bullpen availability explain moneyline/total value beyond team rating. Rule: Only pre-game information (announced starter, park, weather cutoff); grade on final score including extra innings, with suspended games excluded. Gate: Needs a permissioned schedule/lineup/result feed and a licensed odds archive.

**Next action:** Licence review of an official MLB data path (the public stats API is disallowed by robots.txt for automated use).

## Basketball

- **Coverage today:** none - verification_blocked
- **Automation gate:** `blocked_pending_licence_review`
- **Registered designs:** 1 (0 graded)

| candidate result source | link | robots.txt | licence |
|---|---|---|---|
| [NBA - official](https://www.nba.com/) *(deep link unverified)* | [evidence](https://www.nba.com/termsofuse) | [robots.txt](https://www.nba.com/robots.txt) · `partial` · fetched 2026-09-22 | `not_reviewed` |

- **NBA - official** robots.txt says (verbatim):

  ```text
  User-Agent: *
  Disallow: /amp/
  Disallow: /api/*
  Disallow: /mediacentral/*
  Disallow: /search
  ...
  User-agent: anthropic-ai
  Disallow: /
  ```

Strategy designs (pre-registered, gate-checked):

- design-stage — *Rest and travel-adjusted rating*: Rest days, travel distance and back-to-back spots are under-priced relative to pure team strength. Rule: Features frozen at tip-off; grade against spread/total with overtime included; back-to-backs flagged explicitly. Gate: Needs a permissioned result/schedule feed (NBA's own API is robots-disallowed for this project) and a licensed odds archive.

**Next action:** Only a licensed data provider (or written permission) can open this sport - the site's robots.txt blocks AI agents explicitly.

## Boxing

- **Coverage today:** none - verification_blocked
- **Automation gate:** `blocked_by_robots`
- **Registered designs:** 1 (0 graded)

| candidate result source | link | robots.txt | licence |
|---|---|---|---|
| [BoxRec (record archive)](https://boxrec.com/) *(deep link unverified)* | [evidence](https://boxrec.com/en/terms) | [robots.txt](https://boxrec.com/robots.txt) · `blocks_results` · fetched 2026-09-22 | `not_reviewed` |

- **BoxRec (record archive)** robots.txt says (verbatim):

  ```text
  User-agent: *
  User-agent: AdsBot-Google
  Disallow: /v6branch/
  Disallow: /v3/
  Disallow: /v51static/
  ...
  Disallow: /list_bouts.php
  Disallow: /show_display.php
  Disallow: /schedule.php
  Disallow: /search.php
  Disallow: /ratings.php
  Disallow: /title_search.php
  ```

Strategy designs (pre-registered, gate-checked):

- design-stage — *Opponent-adjusted performance*: Adjusting a fighter's record for opponent quality and inactivity beats raw win-loss record at predicting bout winners. Rule: Freeze record/weight class/rounds at the announced bout; a no-contest, draw, retirement or disqualification is never silently mapped to a loss. Gate: Needs a permissioned boxing result source (commission or promoter export) - the public archive is robots-disallowed.

**Next action:** Approach a sanctioning body/promoter for a written result feed; nothing is collectable from BoxRec.

## Cricket

- **Coverage today:** none - verification_blocked
- **Automation gate:** `blocked_pending_licence_review`
- **Registered designs:** 1 (0 graded)

| candidate result source | link | robots.txt | licence |
|---|---|---|---|
| [Cricsheet (ball-by-ball archive, CC-licensed project)](https://cricsheet.org/) | [evidence](https://cricsheet.org/downloads/) | [robots.txt](https://cricsheet.org/robots.txt) · `allows_results` · fetched 2026-09-22 | `not_reviewed` |
| [ICC - official](https://www.icc-cricket.com/) *(deep link unverified)* | [evidence](https://www.icc-cricket.com/about/cricket/terms) | [robots.txt](https://www.icc-cricket.com/robots.txt) · `unknown` · fetched 2026-09-22 | `not_reviewed` |

- **Cricsheet (ball-by-ball archive, CC-licensed project)** robots.txt says (verbatim):

  ```text
  # robotstxt.org/
  
  # Don't index the actual data files.
  User-agent: *
  Allow: /
  Disallow: /data/
  
  # Where does the sitemap file live?
  Sitemap: https://cricsheet.org/sitemap.xml
  ```
- **ICC - official** robots.txt says: `not fetched - listed as the official-body candidate for a human licence review`

Strategy designs (pre-registered, gate-checked):

- design-stage — *Venue and innings-state run-rate model*: Format-specific run rates by venue and innings state predict match winners and totals; rain-reduced matches need explicit rules. Rule: Per-format models (T20/ODI/Test), Duckworth-Lewis-Stern-adjusted targets recorded as official, abandoned matches void (never graded as losses). Gate: Needs the Cricsheet licence decision (or an ICC/board feed) plus a licensed odds archive.

**Next action:** Transcribe and legally review the Cricsheet licence; if it permits research use, ingest ball-by-ball data for a match-winner model. This is the most promising new sport path in the registry.

## Cycling

- **Coverage today:** none - verification_blocked
- **Automation gate:** `blocked_pending_licence_review`
- **Registered designs:** 1 (0 graded)

| candidate result source | link | robots.txt | licence |
|---|---|---|---|
| [UCI - official governing body](https://www.uci.org/) *(deep link unverified)* | [evidence](https://www.uci.org/terms-of-use) | [robots.txt](https://www.uci.org/robots.txt) · `allows_results` · fetched 2026-09-22 | `not_reviewed` |
| [ProCyclingStats (results archive)](https://www.procyclingstats.com/) *(deep link unverified)* | [evidence](https://www.procyclingstats.com/info.php?id=terms) | [robots.txt](https://www.procyclingstats.com/robots.txt) · `partial` · fetched 2026-09-22 | `not_reviewed` |

- **UCI - official governing body** robots.txt says (verbatim):

  ```text
  User-agent: *
  Allow: /
  ```
- **ProCyclingStats (results archive)** robots.txt says (verbatim):

  ```text
  User-agent: *
  Content-Signal: search=yes,ai-train=no,use=reference
  Allow: /
  ...
  User-agent: ClaudeBot
  Disallow: /
  ```

Strategy designs (pre-registered, gate-checked):

- design-stage — *Course-fit performance delta*: Climber/sprinter/time-trialist profile fit predicts one-day and stage outcomes better than overall ranking. Rule: Separate time trials from mass-start races; official classifications (including relegations/penalties) are the settlement source; abandons are never graded as losses in outright markets unless the market rule says so. Gate: Needs a permissioned classification feed (organizer/UCI export) and a licensed odds archive.

**Next action:** Ask UCI/race organizers for a permitted classification feed; the public archive forbids this project's collection.

## Darts

- **Coverage today:** results_pilot - prediction-only (accuracy/Brier), no odds path
- **Automation gate:** `permitted_open_licence`
- **Registered designs:** 3 (3 graded)

| candidate result source | link | robots.txt | licence |
|---|---|---|---|
| [OpenLigaDB PDC darts endpoints (ODbL-1.0)](https://api.openligadb.de/getmatchdata/PDCWM/2025) | [evidence](https://openligadb.de/lizenz) | [robots.txt](https://api.openligadb.de/robots.txt) · `allows_results` · fetched 2026-09-20 | `open_licence_verified` |
| [PDC (Professional Darts Corporation) - official](https://www.pdc.tv/tournaments/) | [evidence](https://www.pdc.tv/terms-conditions/) | [robots.txt](https://www.pdc.tv/robots.txt) · `partial` · fetched 2026-09-22 | `not_reviewed` |

- **OpenLigaDB PDC darts endpoints (ODbL-1.0)** robots.txt says: `No robots restrictions are imposed by the API host; the documented limit is 60 requests/minute/IP (api.openligadb.de front page).`
- **PDC (Professional Darts Corporation) - official** robots.txt says (verbatim):

  ```text
  User-agent: meta-externalagent
  Allow: /
  
  User-agent: ozone/1.0
  Allow: /
  ```

Strategy designs (pre-registered, gate-checked):

- **graded** `darts-elo-v1` — *Player Elo favourite*: A plain player Elo beats the listed-first baseline on PDC match winners. Rule: K=24, no venue adjustment, selectivity floor 0.60; graded on accuracy/Brier only. Gate: passed (OpenLigaDB ODbL darts captures); no odds path
- **graded** `darts-listed-first-v1` — *Listed-first naive baseline*: The source's listing order carries no home-advantage meaning, so it should score near 50%; a large deviation would itself be a data finding. Rule: Always the listed-first player, flat 0.5/0.5 prior. Gate: passed (baseline)
- **graded** `darts-mov-elo-v1` — *Margin-of-victory Elo*: Scaling the Elo update by the stored leg/set margin beats the plain W/L update. Rule: K x g with the World-Football-Elo margin weights; raw stored count difference as margin (stated weakness). Gate: passed (added 2026-09-22); no odds path
  - prior: https://www.eloratings.net/about

**Next action:** Wait for the next PDC event inside the 10-day forward horizon (World Championship, December 2026); no odds path exists, so darts stays accuracy-only.

## Gaelic Football

- **Coverage today:** none - verification_blocked
- **Automation gate:** `blocked_pending_licence_review`
- **Registered designs:** 1 (0 graded)

| candidate result source | link | robots.txt | licence |
|---|---|---|---|
| [GAA (Gaelic Athletic Association) - official fixtures & results](https://www.gaa.ie/fixtures-results/) | [evidence](https://www.gaa.ie/terms-and-conditions/) | [robots.txt](https://www.gaa.ie/robots.txt) · `allows_results` · fetched 2026-09-22 | `not_reviewed` |

- **GAA (Gaelic Athletic Association) - official fixtures & results** robots.txt says (verbatim):

  ```text
  User-agent: *
  Disallow: /_libraries/
  Disallow: /_test/
  ```

Strategy designs (pre-registered, gate-checked):

- design-stage — *Score-difference rating*: Gaelic football scoring (goals = 3 points) makes score-difference ratings informative beyond win/loss, especially across counties in different divisions. Rule: Model separately from hurling and from association football; competition-specific rules (replay/extra time) defined before grading; provincial and All-Ireland series kept separate. Gate: Needs GAA terms review + a licensed odds archive; results page link is verified for manual review.

**Next action:** Human review of GAA terms; if permitted for research use, start a fixture/result capture for one competition only.

## Greyhounds

- **Coverage today:** none - verification_blocked
- **Automation gate:** `blocked_pending_licence_review`
- **Registered designs:** 1 (0 graded)

| candidate result source | link | robots.txt | licence |
|---|---|---|---|
| [GBGB (Greyhound Board of Great Britain) - official regulator](https://www.gbgb.org.uk/) *(deep link unverified)* | [evidence](https://www.gbgb.org.uk/terms-and-conditions/) | [robots.txt](https://www.gbgb.org.uk/robots.txt) · `partial` · fetched 2026-09-22 | `not_reviewed` |

- **GBGB (Greyhound Board of Great Britain) - official regulator** robots.txt says (verbatim):

  ```text
  User-Agent: *
  Allow: /wp-content/uploads/
  Disallow: /wp-content/plugins/
  Disallow: /wp-admin/
  Disallow: /readme.html
  Disallow: /refer/
  ```

Strategy designs (pre-registered, gate-checked):

- design-stage — *Trap and track pace profile*: Trap bias plus recent sectional speed predicts race outcomes beyond the market's own trap adjustment. Rule: Freeze trap/distance/going/non-runners at the pre-race declaration; voids for abandoned races; photo-finish revisions are source edits and must be flagged. Gate: Needs a permissioned race-result feed (GBGB or track operator) and a licensed odds archive.

**Next action:** Ask GBGB/ARC for a permitted result feed; terms review first.

## Handball

- **Coverage today:** none - verification_blocked
- **Automation gate:** `blocked_pending_licence_review`
- **Registered designs:** 1 (0 graded)

| candidate result source | link | robots.txt | licence |
|---|---|---|---|
| [IHF (International Handball Federation) - official](https://www.ihf.info/) *(deep link unverified)* | [evidence](https://www.ihf.info/legal-notice) | [robots.txt](https://www.ihf.info/robots.txt) · `partial` · fetched 2026-09-22 | `not_reviewed` |

- **IHF (International Handball Federation) - official** robots.txt says (verbatim):

  ```text
  User-agent: *
  # CSS, JS, Images
  Allow: /core/*.css$
  ...
  Disallow: /core/
  Disallow: /profiles/
  Disallow: /search/
  Disallow: /user/register/
  Disallow: /user/login/
  ```

Strategy designs (pre-registered, gate-checked):

- design-stage — *Possession and pace split*: Fast-break rate and seven-metre conversion predict totals and handicaps better than league position. Rule: League and tournament rules separated; extra time and seven-metre shootouts never graded as regulation outcomes; a shootout loss is not a match loss where the market is regulation-only. Gate: Needs a permissioned federation/league result feed and a licensed odds archive.

**Next action:** Licence review of IHF/EHF/league data; define extra-time and shootout settlement rules first.

## Hurling

- **Coverage today:** none - verification_blocked
- **Automation gate:** `blocked_pending_licence_review`
- **Registered designs:** 1 (0 graded)

| candidate result source | link | robots.txt | licence |
|---|---|---|---|
| [GAA (Gaelic Athletic Association) - official fixtures & results](https://www.gaa.ie/fixtures-results/) | [evidence](https://www.gaa.ie/terms-and-conditions/) | [robots.txt](https://www.gaa.ie/robots.txt) · `allows_results` · fetched 2026-09-22 | `not_reviewed` |

- **GAA (Gaelic Athletic Association) - official fixtures & results** robots.txt says (verbatim):

  ```text
  User-agent: *
  Disallow: /_libraries/
  Disallow: /_test/
  ```

Strategy designs (pre-registered, gate-checked):

- design-stage — *Venue-adjusted scoring rate*: Hurling's high scoring and wind-exposed venues (e.g. Thurles/Ennis) create venue-specific totals effects that the market under-adjusts. Rule: Competition-specific scoring rules; replays and extra time explicit; never pooled with Gaelic football. Gate: Needs GAA terms review + a licensed odds archive; results page link is verified for manual review.

**Next action:** Same as Gaelic football: terms review, then a single-competition capture.

## Ice Hockey

- **Coverage today:** results_pilot - prediction-only (accuracy/Brier) on the whole DEL 2024/25 season plus DEL2/CHL 2026/27 forward captures; no odds path
- **Automation gate:** `permitted_open_licence`
- **Registered designs:** 7 (7 graded)

| candidate result source | link | robots.txt | licence |
|---|---|---|---|
| [OpenLigaDB DEL/DEL2/CHL endpoints (ODbL-1.0)](https://api.openligadb.de/getmatchdata/del/2024) | [evidence](https://openligadb.de/lizenz) | [robots.txt](https://api.openligadb.de/robots.txt) · `allows_results` · fetched 2026-09-20 | `open_licence_verified` |
| [IIHF - official governing body](https://www.iihf.info/) *(deep link unverified)* | [evidence](https://www.iihf.com/en/statichub/legal) | [robots.txt](https://www.iihf.info/robots.txt) · `unknown` · fetched 2026-09-22 | `not_reviewed` |

- **OpenLigaDB DEL/DEL2/CHL endpoints (ODbL-1.0)** robots.txt says: `No robots restrictions are imposed by the API host; the documented limit is 60 requests/minute/IP (api.openligadb.de front page).`
- **IIHF - official governing body** robots.txt says: `not fetched - listed as the candidate independent cross-check for DEL identity (the pilot is single-source 'probable')`

Strategy designs (pre-registered, gate-checked):

- **graded** `hockey-elo-v1` — *2-way Elo favourite*: A 2-way Elo beats the always-home baseline on the OT/SO-aware final. Rule: K=32, home advantage 35 Elo pts, floor 0.55. Gate: passed (ODbL results); no odds path
  - prior: https://www.sfu.ca/~tswartz/papers/hca.pdf
- **graded** `hockey-home-v1` — *Home-ice naive baseline*: Home ice is worth about 54.5% of regular-season wins (reference bar for every hockey desk). Rule: Always home, flat 0.5/0.5 prior. Gate: passed (baseline)
  - prior: https://www.sfu.ca/~tswartz/papers/hca.pdf
- **graded** `hockey-reg-poisson-v1` — *Poisson regulation 3-way*: An independent-Poisson goal model adds information about the 60-minute 3-way outcome. Rule: League rates + shrunk multipliers; argmax of the regulation 3-way. Gate: passed
- **graded** `hockey-elo-mov-v1` — *Margin-of-victory Elo*: Scaling the Elo update by the goal margin beats the plain W/L update (added 2026-09-22). Rule: K x g with the World-Football-Elo margin weights; same ratings pool as the plain desk. Gate: passed
  - prior: https://www.eloratings.net/about
  - prior: https://doi.org/10.1016/j.ijforecast.2009.10.002
- **graded** `hockey-totals-poisson-v1` — *Poisson totals O/U 5.5*: The Maher/Dixon-Coles Poisson totals model transfers to DEL total goals over/under 5.5 (second prediction-only market, added 2026-09-22). Rule: P(total >= 6) from the same league-rate/attack/defence construction; states the more likely side for every match. Gate: passed
- **graded** `hockey-totals-over-v1` — *Always-over baseline*: Reference point for the totals desk: the share of DEL games over 5.5 goals. Rule: Always over, flat 0.5/0.5 prior. Gate: passed (baseline)
- **graded** `hockey-reg-home-v1` — *Regulation home naive baseline*: Reference bar for the regulation 3-way desks: the share of 60-minute home wins. Rule: Always home in regulation, flat 0.5/0/0.5 prior. Gate: passed (baseline)

**Next action:** Add an independent cross-check source (IIHF or a league export) and a licensed odds path; until then hockey can never show PnL.

## Motor Racing

- **Coverage today:** none - verification_blocked
- **Automation gate:** `blocked_pending_licence_review`
- **Registered designs:** 1 (0 graded)

| candidate result source | link | robots.txt | licence |
|---|---|---|---|
| [Formula 1 - official results](https://www.formula1.com/en/results/2026/races) | [evidence](https://www.formula1.com/en/information/terms-and-conditions) | [robots.txt](https://www.formula1.com/robots.txt) · `allows_results` · fetched 2026-09-22 | `not_reviewed` |

- **Formula 1 - official results** robots.txt says (verbatim):

  ```text
  Sitemap: https://www.formula1.com/sitemap.xml
  User-Agent: *
  Disallow: /en/latest/tags/*
  Allow: /
  ```

Strategy designs (pre-registered, gate-checked):

- design-stage — *Qualifying-to-finish delta*: Grid position plus track-specific overtaking difficulty explains finishing position better than recent form alone. Rule: Pre-race information only (qualifying classification, grid penalties); retirements/pit incidents classified per the official result; each-way/podium places defined per market. Gate: Needs a licence decision on F1 result data + a licensed odds archive; the results link is verified for manual review.

**Next action:** Terms review, then (if permitted) a per-race result capture with the official classification as the settlement source.

## Rugby Union

- **Coverage today:** none - verification_blocked
- **Automation gate:** `blocked_pending_licence_review`
- **Registered designs:** 1 (0 graded)

| candidate result source | link | robots.txt | licence |
|---|---|---|---|
| [World Rugby - official fixtures & results](https://www.world.rugby/tournaments/fixtures-results/results) | [evidence](https://www.world.rugby/organisation/legal/terms-of-use) | [robots.txt](https://www.world.rugby/robots.txt) · `allows_results` · fetched 2026-09-22 | `not_reviewed` |

- **World Rugby - official fixtures & results** robots.txt says (verbatim):

  ```text
  # All robots allowed
  User-agent: *
  Disallow:
  
  # Sitemap files
  Sitemap: https://www.world.rugby/en/news/sitemap.xml
  ```

Strategy designs (pre-registered, gate-checked):

- design-stage — *Set-piece and territory rating*: Scrum/lineout dominance and territory/possession predict handicaps beyond league position. Rule: Union kept separate from league; competition-specific bonus points and abandoned-match rules explicit; a match abandoned before 60 minutes is void unless the competition declares a result. Gate: Needs a permissioned union result feed (World Rugby or league export) + a licensed odds archive; the results link is verified for manual review.

**Next action:** Terms review; pick one competition (e.g. Six Nations) for a first capture.

## Rugby League

- **Coverage today:** none - verification_blocked
- **Automation gate:** `blocked_pending_licence_review`
- **Registered designs:** 1 (0 graded)

| candidate result source | link | robots.txt | licence |
|---|---|---|---|
| [NRL - official](https://www.nrl.com/) *(deep link unverified)* | [evidence](https://www.nrl.com/terms-and-conditions/) | [robots.txt](https://www.nrl.com/robots.txt) · `allows_results` · fetched 2026-09-22 | `not_reviewed` |
| [Super League (UK) - official](https://www.superleague.co.uk/) *(deep link unverified)* | [evidence](https://www.superleague.co.uk/terms) | [robots.txt](https://www.superleague.co.uk/robots.txt) · `unknown` · fetched 2026-09-22 | `not_reviewed` |

- **NRL - official** robots.txt says (verbatim):

  ```text
  User-agent: *
  
  #Sitemap
  Sitemap: https://www.nrl.com/sitemap/sitemap.xml
  ```
- **Super League (UK) - official** robots.txt says: `not fetched - listed as the UK-league alternative for a human licence review`

Strategy designs (pre-registered, gate-checked):

- design-stage — *Tackle/territory rating*: Completion rate and metres-per-set differentials predict margins better than ladder position late in the season. Rule: Rugby codes never pooled; golden-point and abandoned-match rules explicit. Gate: Needs a permissioned league result feed + a licensed odds archive.

**Next action:** Terms review (NRL/Super League); nothing collected today.

## Snooker

- **Coverage today:** none - verification_blocked
- **Automation gate:** `blocked_pending_licence_review`
- **Registered designs:** 1 (0 graded)

| candidate result source | link | robots.txt | licence |
|---|---|---|---|
| [WST (World Snooker Tour) - official](https://www.wst.tv/matches) *(deep link unverified)* | [evidence](https://www.wst.tv/terms-conditions) | [robots.txt](https://www.wst.tv/robots.txt) · `no_robots_file` · fetched 2026-09-22 | `not_reviewed` |
| [WPBSA (World Professional Billiards and Snooker Association)](https://wpbsa.com/) *(deep link unverified)* | [evidence](https://wpbsa.com/terms-of-use/) | [robots.txt](https://wpbsa.com/robots.txt) · `unknown` · fetched 2026-09-22 | `not_reviewed` |

- **WST (World Snooker Tour) - official** robots.txt says: `HTTP 404 - no robots.txt is served; the fetched URL returned the site's 404 page ('Sorry, it looks like the page you are looking for isn't available right now').`
- **WPBSA (World Professional Billiards and Snooker Association)** robots.txt says: `not fetched - listed as the governing-body candidate for a licence review`

Strategy designs (pre-registered, gate-checked):

- design-stage — *Frame-strength and break profile*: Frame-winning rate and century frequency predict match winners and frame handicaps better than world ranking alone. Rule: Match format (best-of-N) and walkovers recorded explicitly; features frozen before the first frame. Gate: Needs a permissioned result feed (WST/WPBSA export) + a licensed odds archive.

**Next action:** Licence review; the missing robots.txt must not be treated as consent.

## Volleyball

- **Coverage today:** none - verification_blocked
- **Automation gate:** `blocked_pending_licence_review`
- **Registered designs:** 1 (0 graded)

| candidate result source | link | robots.txt | licence |
|---|---|---|---|
| [Volleyball World (FIVB commercial arm) - official](https://en.volleyballworld.com/) *(deep link unverified)* | [evidence](https://en.volleyballworld.com/legal/) | [robots.txt](https://en.volleyballworld.com/robots.txt) · `partial` · fetched 2026-09-22 | `not_reviewed` |

- **Volleyball World (FIVB commercial arm) - official** robots.txt says (verbatim):

  ```text
  User-Agent: *
  Disallow: /assets/
  Disallow: /addon/
  Disallow: /_libraries/
  Disallow: /errors/
  Disallow: /sitecore/
  Disallow: /login/
  Disallow: /mobileapp/
  Disallow: /test/
  Disallow: */images/download/
  Disallow: *?id=
  Disallow: */en/*
  Disallow: */api/*
  Sitemap: https://en.volleyballworld.com/sitemap-index.xml
  ```

Strategy designs (pre-registered, gate-checked):

- design-stage — *Set differential rating*: Set-level differentials carry information that match-level win/loss ratings discard, especially across pools. Rule: Best-of format, golden-set and walkover rules explicit; a missing set is never a loss. Gate: Needs a permissioned federation/league result feed + a licensed odds archive.

**Next action:** Licence review; check whether the CEV or a national league publishes an open result feed.
