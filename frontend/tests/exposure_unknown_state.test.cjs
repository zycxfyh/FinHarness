"use strict";

const assert = require("node:assert");
const fs = require("node:fs");
const path = require("node:path");
const { JSDOM } = require("jsdom");

const frontendDir = path.resolve(__dirname, "..");
const html = fs.readFileSync(path.join(frontendDir, "index.html"), "utf-8");
const sources = ["api.js", "state.js", "actions.js", "app.js"].map((name) =>
  fs.readFileSync(path.join(frontendDir, name), "utf-8"),
);
const dom = new JSDOM(html, {
  runScripts: "outside-only",
  url: "https://cockpit.finharness.test/",
});

dom.window.eval(sources[0]);
dom.window.eval(sources[1]);
dom.window.eval(sources[2]);
dom.window.FinHarness.state.activeView = "exposure";
dom.window.fetch = (endpoint) => {
  assert.equal(endpoint, "/exposure");
  return Promise.resolve({
    ok: true,
    status: 200,
    json: () =>
      Promise.resolve({
        net_worth: null,
        total_assets: null,
        total_liabilities: null,
        cash_total: null,
        cash_runway_months: null,
        top_holding_weight: null,
        concentration_hhi: null,
        interest_bearing_debt_total: null,
        weighted_avg_interest_rate: null,
        annual_interest_estimate: null,
        holdings: [{ symbol: "SPY", market_value: 100, weight: null }],
        upcoming_obligations: [],
        insurance_review_gaps: [],
        tax_review_gaps: [],
        data_gaps: ["capital valuation blocked: mixed_valuation_currencies"],
      }),
  });
};
dom.window.eval(sources[3]);

setImmediate(() => {
  const values = [
    ...dom.window.document.querySelectorAll("#exposure-grid .metric-value"),
  ].map((node) => node.textContent);
  assert.equal(values.length, 10);
  assert.ok(values.every((value) => value === "Unknown"));
  assert.match(
    dom.window.document.querySelector("#exposure-holdings").textContent,
    /SPY.*Unknown/,
  );
  assert.match(
    dom.window.document.querySelector("#exposure-gaps").textContent,
    /mixed_valuation_currencies/,
  );
  console.log("OK blocked capital exposure renders Unknown without false precision");
});
