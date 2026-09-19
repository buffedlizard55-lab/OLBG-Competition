/*
 * Northstar Competition Lab
 *
 * This is intentionally a static, source-first research interface. The records
 * below are not a live feed and no record is allowed to look settled without a
 * verified result. Links are kept visible so every displayed claim can be
 * checked manually.
 */

const snapshotDate = "19 Sep 2026";

const tipPreviews = [
  {
    sport: "Football",
    event: "Venezia v Lazio",
    league: "Italy Serie A",
    time: "Today · 14:45",
    market: "Full Time Result",
    pick: "Lazio",
    consensus: "36 / 41",
    percentage: "88%",
    state: "Upcoming",
    experts: "OLBG event page",
    flag: "Count drift: list 35/40; event 36/41",
    url: "https://www.olbg.com/betting-tips/Football/European_Competitions/Italy_Serie_A/Venezia_v_Lazio/1?event_id=2039716"
  },
  {
    sport: "Football",
    event: "Sevilla v Barcelona",
    league: "Spain Primera Liga",
    time: "Today · 15:00",
    market: "Full Time Result",
    pick: "Barcelona",
    consensus: "28 / 35",
    percentage: "80%",
    state: "Upcoming",
    experts: "OLBG public page",
    url: "https://www.olbg.com/betting-tips/Football/European_Competitions/Spain_Primera_Liga/Sevilla_v_Barcelona/1?event_id=2040420"
  },
  {
    sport: "Football",
    event: "Man City v Sunderland",
    league: "England Premier League",
    time: "Tomorrow · 09:00",
    market: "Full Time Result",
    pick: "Man City",
    consensus: "24 / 27",
    percentage: "89%",
    state: "Upcoming",
    experts: "OLBG public page · 1 expert",
    url: "https://www.olbg.com/betting-tips/Football/UK/England_Premier_League/Man_City_v_Sunderland/1?event_id=2039511"
  },
  {
    sport: "Darts",
    event: "Gerwyn Price vs Jim Long",
    league: "OLBG darts event page",
    time: "Today · 14:15",
    market: "Win Match 2-way",
    pick: "Gerwyn Price",
    consensus: "Not found",
    percentage: "—",
    state: "Review",
    experts: "Direct page returned no tips",
    flag: "List showed tip; direct event page returned no tips",
    url: "https://www.olbg.com/betting-tips/Darts/All_Darts/All_Events/Gerwyn_Price_vs_Jim_Long/15?event_id=31644"
  }
];

const strategyRegistry = [
  { sport: "Football", name: "Elo rating + price discipline", description: "Compare a rolling team rating with the market-implied probability; only record a selection when the price timestamp and edge threshold are both present.", status: "Ready to source", data: "Official fixtures/results · time-stamped odds", test: "Walk-forward 1X2" },
  { sport: "Football", name: "Poisson goal totals", description: "Estimate home and away scoring rates from pre-match history and test totals without using information published after kick-off.", status: "Ready to source", data: "Official scores · line-up/time gate · odds", test: "Walk-forward totals" },
  { sport: "Horse Racing", name: "Place probability by field size", description: "Test whether a calibrated place probability remains above the recorded price after separating race type, field size, going, and jurisdiction.", status: "Blocked", data: "Official result + runner/odds archive", test: "Jurisdiction-specific" },
  { sport: "Tennis", name: "Surface-adjusted Elo", description: "Use player ratings split by surface and enforce a match-start cutoff before comparing the forecast with the captured price.", status: "Ready to source", data: "ATP/WTA/ITF results · odds", test: "Match-level Brier + ROI" },
  { sport: "Basketball", name: "Rest and travel-adjusted rating", description: "Separate home advantage, rest days, and travel from team strength; keep overtime treatment explicit in settlement rules.", status: "Ready to source", data: "FIBA/NBA results · schedule · odds", test: "Spread / moneyline" },
  { sport: "Baseball", name: "Starting pitcher and bullpen split", description: "Test pre-game pitcher, bullpen availability, and park effects without leaking post-lineup information into the forecast.", status: "Ready to source", data: "MLB results · lineups · odds", test: "Moneyline / totals" },
  { sport: "American Football", name: "Efficiency differential with injury freshness", description: "Use official game outcomes and a dated injury state; hold out any game where the status was not available before the selection time.", status: "Blocked", data: "NFL/NCAA results · injury archive · odds", test: "Spread / total" },
  { sport: "Cricket", name: "Venue and innings-state model", description: "Model format-specific run rates by venue and innings, with rain-reduced matches and abandoned games handled as explicit exclusions or voids.", status: "Ready to source", data: "ICC/competition results · scorecards", test: "Match / innings markets" },
  { sport: "Golf", name: "Strokes-gained and course fit", description: "Test pre-tournament player form and course-fit features against a dated outright price; define ties and dead heats before running anything.", status: "Blocked", data: "Tour leaderboards · odds archive", test: "Outright / place" },
  { sport: "Rugby", name: "Set-piece and territory rating", description: "Create separate union and league models; never pool their rules, scoring, or official result definitions.", status: "Ready to source", data: "World Rugby/RFL/NRL results", test: "Match / handicap" },
  { sport: "Ice Hockey", name: "Goalie-adjusted expected goals", description: "Estimate shot quality and goalie availability before puck drop; separate shootout results from regulation settlement.", status: "Blocked", data: "IIHF/NHL results · lineups · odds", test: "Moneyline / totals" },
  { sport: "Motor Racing", name: "Qualifying-to-finish delta", description: "Use only information available before the race start and define retirements, classified finish, and each-way places per series.", status: "Ready to source", data: "FIA/F1 results · qualifying · odds", test: "Finish / podium" },
  { sport: "Darts", name: "Throw rate plus checkout profile", description: "Compare dated player performance rates while keeping format, leg distance, and event surface consistent.", status: "Ready to source", data: "PDC results · match format · odds", test: "Match / handicap" },
  { sport: "Boxing / MMA", name: "Opponent-adjusted performance", description: "Keep boxing and MMA separate; use event-organizer results and freeze age, reach, record, and training-state fields at selection time.", status: "Blocked", data: "Organizer results · commission data · odds", test: "Fight winner / method" },
  { sport: "Esports", name: "Map-pool strength with patch lock", description: "Treat game title, tournament, patch, best-of format, and map veto as mandatory identifiers; no cross-title pooling.", status: "Blocked", data: "Organizer results · patch history · odds", test: "Series / map" },
  { sport: "Cycling / Athletics", name: "Course-fit performance delta", description: "Separate timed events from mass-start events and use governing-body results with event-specific classification rules.", status: "Blocked", data: "UCI/World Athletics results", test: "Outright / placement" }
];

const sourceRegistry = [
  { sport: "Football", source: "FIFA / UEFA competition results", url: "https://www.fifa.com/en/tournaments", verifies: "Fixture identity, competition, final result; use the competition owner for each league.", state: "Primary mapped" },
  { sport: "Horse Racing", source: "British Horseracing Authority", url: "https://www.britishhorseracing.com/racing/fixtures-results/", verifies: "UK fixture, race result, non-runner and going fields.", state: "Caveat", caveat: true },
  { sport: "Tennis", source: "ATP Tour scores", url: "https://www.atptour.com/en/scores", verifies: "Men's match schedule and completed match result; add WTA/ITF per event.", state: "Primary mapped" },
  { sport: "Basketball", source: "FIBA competitions", url: "https://www.fiba.basketball/competitions", verifies: "Competition fixtures and results; NBA requires its own league source.", state: "Primary mapped" },
  { sport: "Baseball", source: "MLB scores", url: "https://www.mlb.com/scores", verifies: "Major League fixture and final result; local leagues need an owner source.", state: "Primary mapped" },
  { sport: "American Football", source: "NFL scores", url: "https://www.nfl.com/scores/", verifies: "NFL fixture and final result; NCAA requires its own competition source.", state: "Primary mapped" },
  { sport: "Boxing", source: "World Boxing Council", url: "https://wbcboxing.com/", verifies: "Organizer/federation event context; bout settlement also needs commission/result confirmation.", state: "Caveat", caveat: true },
  { sport: "Cricket", source: "International Cricket Council", url: "https://www.icc-cricket.com/fixtures-results", verifies: "International fixtures, match result and competition context.", state: "Primary mapped" },
  { sport: "Darts", source: "PDC tournament calendar", url: "https://www.pdc.tv/tournament-calendar", verifies: "PDC event schedule and organizer result.", state: "Primary mapped" },
  { sport: "Golf", source: "PGA Tour leaderboard", url: "https://www.pgatour.com/leaderboard", verifies: "Tournament leaderboard and finishing position; tour-specific rules required.", state: "Primary mapped" },
  { sport: "Greyhounds", source: "GBGB racing results", url: "https://www.gbgb.org.uk/racing/results/", verifies: "Great Britain race result and declared runners.", state: "Caveat", caveat: true },
  { sport: "Handball", source: "International Handball Federation", url: "https://www.ihf.info/competitions", verifies: "IHF competition schedule and result; domestic leagues need their organizer.", state: "Primary mapped" },
  { sport: "Motor Racing", source: "FIA events", url: "https://www.fia.com/events", verifies: "Championship/event context and official classification; series adapter required.", state: "Primary mapped" },
  { sport: "Ice Hockey", source: "International Ice Hockey Federation", url: "https://www.iihf.com/en/tournaments", verifies: "IIHF tournament fixtures/results; NHL needs its own league source.", state: "Primary mapped" },
  { sport: "Rugby League", source: "Rugby Football League", url: "https://www.rugby-league.com/fixtures-results", verifies: "RFL fixture and result for covered competitions.", state: "Primary mapped" },
  { sport: "Rugby Union", source: "World Rugby fixtures", url: "https://www.world.rugby/fixtures", verifies: "International fixtures and results; club league owner required.", state: "Primary mapped" },
  { sport: "Cycling", source: "Union Cycliste Internationale", url: "https://www.uci.org/competition-hub", verifies: "UCI event calendar and classification for covered events.", state: "Primary mapped" },
  { sport: "Gaelic Football", source: "GAA fixtures and results", url: "https://www.gaa.ie/fixtures-results", verifies: "GAA fixture and final result.", state: "Primary mapped" },
  { sport: "Hurling", source: "GAA fixtures and results", url: "https://www.gaa.ie/fixtures-results", verifies: "GAA fixture and final result, sport code kept separate.", state: "Primary mapped" },
  { sport: "Volleyball", source: "Volleyball World / FIVB", url: "https://en.volleyballworld.com/volleyball/competitions", verifies: "FIVB/Volleyball World competition schedule and result.", state: "Primary mapped" },
  { sport: "Aussie Rules", source: "AFL fixture", url: "https://www.afl.com.au/fixture", verifies: "AFL fixture, match status and final result.", state: "Primary mapped" },
  { sport: "eSports", source: "League / event organizer", url: "https://lolesports.com/en-US/", verifies: "Organizer-published series/map result; title, patch and format are mandatory.", state: "Caveat", caveat: true },
  { sport: "Snooker", source: "World Snooker Tour results", url: "https://www.wst.tv/results", verifies: "WST event and match result.", state: "Primary mapped" },
  { sport: "MMA / UFC", source: "UFC events", url: "https://www.ufc.com/events", verifies: "UFC event, bout result and method for UFC events; other promotions need their owner.", state: "Primary mapped" },
  { sport: "Athletics", source: "World Athletics results", url: "https://worldathletics.org/competition/calendar-results", verifies: "Meet/event results and marks for covered competitions.", state: "Primary mapped" },
  { sport: "Winter Sports", source: "FIS calendar and results", url: "https://www.fis-ski.com/DB/general/calendar-results.html", verifies: "FIS event, classification and result for covered disciplines.", state: "Primary mapped" },
  { sport: "Specials", source: "Event organizer / OLBG source", url: "https://www.olbg.com/betting-tips", verifies: "Non-sport event source must be attached; no sports-result shortcut is allowed.", state: "Caveat", caveat: true }
];

const escapeHtml = (value) => String(value).replace(/[&<>"']/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;" }[char]));

function renderPreviewCards(targetId, records = tipPreviews) {
  const target = document.getElementById(targetId);
  if (!target) return;
  target.innerHTML = records.map((tip) => `
    <article class="tip-card">
      <span class="tip-sport">${escapeHtml(tip.sport)}</span>
      <span class="tip-status ${tip.state === "Expired" ? "expired" : tip.state === "Review" ? "review" : ""}">${escapeHtml(tip.state)}</span>
      <h3 class="tip-event">${escapeHtml(tip.event)}</h3>
      <p class="tip-league">${escapeHtml(tip.league)} · ${escapeHtml(tip.time)}</p>
      <div class="tip-pick-row">
        <div><div class="tip-pick-label">${escapeHtml(tip.market)}</div><div class="tip-pick">${escapeHtml(tip.pick)}</div></div>
        <div class="tip-consensus">${escapeHtml(tip.consensus)}<br /><span>${escapeHtml(tip.percentage)} tips</span></div>
      </div>
      <a class="tip-source" href="${tip.url}" target="_blank" rel="noreferrer">View source · ${escapeHtml(tip.experts)} ↗</a>
      ${tip.flag ? `<span class="tip-flag">⚑ ${escapeHtml(tip.flag)}</span>` : ""}
    </article>
  `).join("");
}

function renderTipRows() {
  const target = document.getElementById("tip-list");
  if (!target) return;
  const query = document.getElementById("tip-search").value.trim().toLowerCase();
  const sport = document.getElementById("tip-sport").value;
  const state = document.getElementById("tip-state").value;
  const filtered = tipPreviews.filter((tip) => {
    const haystack = `${tip.sport} ${tip.event} ${tip.league} ${tip.market} ${tip.pick}`.toLowerCase();
    return (!query || haystack.includes(query)) && (sport === "All sports" || tip.sport === sport) && (state === "All states" || tip.state === state);
  });
  target.innerHTML = filtered.length ? filtered.map((tip) => `
    <article class="tip-row">
      <div class="row-sport">${escapeHtml(tip.sport)}<strong>${escapeHtml(tip.state)}</strong></div>
      <div class="row-event"><strong>${escapeHtml(tip.event)}</strong><span>${escapeHtml(tip.league)} · ${escapeHtml(tip.time)}</span></div>
      <div class="row-market"><span>${escapeHtml(tip.market)}</span><strong class="row-pick">${escapeHtml(tip.pick)}</strong></div>
      <div class="row-consensus">${escapeHtml(tip.consensus)}<small>${escapeHtml(tip.percentage)} community split</small></div>
      <div class="row-action"><a href="${tip.url}" target="_blank" rel="noreferrer">Review source ↗</a><small>${tip.flag ? `⚑ ${escapeHtml(tip.flag)}` : `Captured ${snapshotDate}`}</small></div>
    </article>
  `).join("") : `<div class="empty-state"><div class="empty-icon">⌕</div><h3>No source preview matches</h3><p>Try a different sport, state, or search term.</p></div>`;
}

function renderStrategies(filter = "All") {
  const target = document.getElementById("strategy-grid");
  if (!target) return;
  target.innerHTML = strategyRegistry.map((strategy) => {
    const hidden = filter !== "All" && strategy.status !== filter ? "hidden" : "";
    return `<article class="strategy-card ${hidden}" data-strategy-status="${escapeHtml(strategy.status)}">
      <div class="strategy-card-top"><span class="strategy-sport">${escapeHtml(strategy.sport)}</span><span class="strategy-state ${strategy.status === "Blocked" ? "blocked" : ""}">${escapeHtml(strategy.status)}</span></div>
      <h3>${escapeHtml(strategy.name)}</h3><p>${escapeHtml(strategy.description)}</p>
      <div class="strategy-meta"><span><strong>Data gate</strong> · ${escapeHtml(strategy.data)}</span><span><strong>Test</strong> · ${escapeHtml(strategy.test)}</span></div>
    </article>`;
  }).join("");
}

function renderSources() {
  const target = document.getElementById("source-table-body");
  if (!target) return;
  target.innerHTML = sourceRegistry.map((entry) => `<tr>
    <td>${escapeHtml(entry.sport)}</td>
    <td><a href="${entry.url}" target="_blank" rel="noreferrer">${escapeHtml(entry.source)} ↗</a></td>
    <td>${escapeHtml(entry.verifies)}</td>
    <td><span class="source-state ${entry.caveat ? "caveat" : ""}">${escapeHtml(entry.state)}</span></td>
  </tr>`).join("");
}

function setView(viewName) {
  document.querySelectorAll("[data-view-panel]").forEach((panel) => panel.classList.toggle("active", panel.dataset.viewPanel === viewName));
  document.querySelectorAll(".nav-item[data-view]").forEach((item) => item.classList.toggle("active", item.dataset.view === viewName));
  const active = document.querySelector(`.nav-item[data-view="${viewName}"]`);
  document.getElementById("page-name").textContent = active ? active.textContent.trim().replace(/\s+\d+$/, "") : "Overview";
  window.scrollTo({ top: 0, behavior: "smooth" });
}

document.addEventListener("DOMContentLoaded", () => {
  renderPreviewCards("overview-tips");
  renderTipRows();
  renderStrategies();
  renderSources();

  document.querySelectorAll(".nav-item[data-view]").forEach((item) => item.addEventListener("click", () => setView(item.dataset.view)));
  document.querySelectorAll("[data-view-target]").forEach((item) => item.addEventListener("click", () => setView(item.dataset.viewTarget)));
  document.getElementById("tip-search").addEventListener("input", renderTipRows);
  document.getElementById("tip-sport").addEventListener("change", renderTipRows);
  document.getElementById("tip-state").addEventListener("change", renderTipRows);
  document.querySelectorAll("[data-strategy-filter]").forEach((button) => button.addEventListener("click", () => {
    document.querySelectorAll("[data-strategy-filter]").forEach((item) => item.classList.toggle("active", item === button));
    renderStrategies(button.dataset.strategyFilter);
  }));
});
