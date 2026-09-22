#!/usr/bin/env node
/* Site rendering smoke test: runs app.js against a stub DOM and the real
 * site-data/site.json to catch runtime rendering errors. Usage:
 *   node scripts/site-smoke.mjs
 */
import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";
import vm from "vm";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const siteJson = fs.readFileSync(path.join(root, "site-data/site.json"), "utf8");
const appJs = fs.readFileSync(path.join(root, "app.js"), "utf8");

const ids = new Set();
const selectDefaults = {
  "leaderboard-kind": "All kinds",
  "tip-kind": "All kinds",
  "bets-entrant": "All entrants",
};
function makeEl(id) {
  ids.add(id);
  return {
    id,
    textContent: "",
    innerHTML: "",
    value: selectDefaults[id] || "All",
    hidden: false,
    className: "",
    classList: {
      _set: new Set(),
      add(c) { this._set.add(c); },
      remove(c) { this._set.delete(c); },
      toggle(c, force) {
        if (force === undefined) force = !this._set.has(c);
        if (force) this._set.add(c); else this._set.delete(c);
        return force;
      },
      contains(c) { return this._set.has(c); },
    },
    dataset: {},
    addEventListener() {},
  };
}
const elements = {};
const documentStub = {
  getElementById(id) {
    if (!elements[id]) elements[id] = makeEl(id);
    return elements[id];
  },
  querySelector() { return makeEl("q:" + Math.random()); },
  querySelectorAll() { return []; },
  addEventListener(ev, fn) { if (ev === "DOMContentLoaded") this._domReady = fn; },
};
const windowStub = { scrollTo() {} };

const context = {
  document: documentStub,
  window: windowStub,
  fetch: () => Promise.resolve({
    ok: true,
    status: 200,
    json: () => Promise.resolve(JSON.parse(siteJson)),
  }),
  console,
  Date,
  Number,
  String,
  Promise,
  JSON,
  Math,
};
context.globalThis = context;
vm.createContext(context);
vm.runInContext(appJs, context, { filename: "app.js" });

const ready = documentStub._domReady;
if (!ready) {
  console.error("FAIL: DOMContentLoaded handler not registered");
  process.exit(1);
}
ready();
setTimeout(() => {
  const problems = [];
  const overview = elements["overview-leaderboard"];
  if (!overview || !/entrants|<tr>/.test(overview.innerHTML) && overview.innerHTML === "") {
    problems.push("overview leaderboard empty");
  }
  const lb = elements["leaderboard-body"];
  if (!lb || lb.innerHTML === "") problems.push("leaderboard body empty");
  const desk = elements["tipster-desk"];
  if (!desk || desk.innerHTML === "") problems.push("tip desk empty");
  const placed = elements["placed-bets-body"];
  if (!placed || placed.innerHTML === "") problems.push("placed bets empty");
  const upcoming = elements["upcoming-bets-body"];
  if (!upcoming || upcoming.innerHTML === "") problems.push("upcoming bets empty");
  const backtest = elements["backtest-grid"];
  if (!backtest || backtest.innerHTML === "") problems.push("backtest grid empty");
  const coverage = elements["coverage-body"];
  if (!coverage || coverage.innerHTML === "") problems.push("coverage table empty");
  const sources = elements["source-cards"];
  if (!sources || sources.innerHTML === "") problems.push("source cards empty");
  const captures = elements["captures-body"];
  if (!captures || captures.innerHTML === "") problems.push("captures table empty");
  const preds = elements["prediction-grid"];
  if (!preds || preds.innerHTML === "") problems.push("prediction grid empty");

  // third market + baseline desks must actually render (2026-09-22 pass):
  // Asian-handicap rows with their line, and the naive baseline desks.
  const placedHtml = placed.innerHTML;
  if (!placedHtml.includes("Asian handicap")) {
    problems.push("no Asian-handicap market rows rendered");
  }
  if (!/Asian handicap \(line [-+]?\d/.test(placedHtml)) {
    problems.push("Asian-handicap rows do not show the priced line");
  }
  for (const entrantId of ["ah-poisson-value-v1", "ah-market-favourite-v1",
                           "hockey-home-v1", "darts-listed-first-v1"]) {
    const haystack = (desk.innerHTML || "") + placedHtml;
    if (!haystack.includes(entrantId)) {
      problems.push(`entrant ${entrantId} not rendered anywhere`);
    }
  }

  // every rendered cell must be HTML-escaped: no raw '<' from data
  for (const [id, el] of Object.entries(elements)) {
    if (el.innerHTML && el.innerHTML.includes("undefined")) {
      problems.push(`element ${id} contains literal 'undefined'`);
    }
  }
  if (problems.length) {
    console.error("FAIL:\n - " + problems.join("\n - "));
    process.exit(1);
  }
  console.log(`OK: rendered ${Object.keys(elements).length} elements without errors`);
  console.log("  leaderboard rows:", (lb.innerHTML.match(/<tr>/g) || []).length);
  console.log("  placed bet rows:", (placed.innerHTML.match(/<tr>/g) || []).length);
  console.log("  upcoming rows:", (upcoming.innerHTML.match(/<tr>/g) || []).length);
}, 50);
