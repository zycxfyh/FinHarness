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

const responses = {
  "/dashboard/summary": {
    account_count: 1,
    position_count: 2,
    total_market_value: null,
    liability_count: 2,
    liability_balance_total: null,
    goal_count: 0,
    cashflow_count: 0,
    tax_event_count: 0,
    insurance_policy_count: 0,
    document_count: 0,
    open_proposal_count: 0,
    receipt_count: 0,
    execution_allowed: false,
  },
  "/brief/daily": {
    headline: "Net worth cannot be unified/valued",
    sections: [],
    non_claims: [],
  },
  "/brief/latest": {
    available: false,
    receipt: null,
    non_claims: [],
  },
  "/controls/status": {
    api_execution_endpoints_present: false,
    execution_substrate: "none",
    live_execution_available: false,
    proposal_approval_is_execution_authorization: false,
    execution_allowed: false,
    non_claims: [],
  },
  "/controls/limits": {
    raising_limits_via_api_allowed: false,
  },
};

dom.window.eval(sources[0]);
dom.window.eval(sources[1]);
dom.window.eval(sources[2]);
dom.window.fetch = (endpoint) =>
  Promise.resolve({
    ok: true,
    status: 200,
    json: () => Promise.resolve(responses[endpoint]),
  });
dom.window.eval(sources[3]);

setImmediate(() => {
  const metrics = Object.fromEntries(
    [...dom.window.document.querySelectorAll("#summary-grid .metric")].map(
      (node) => [
        node.querySelector(".metric-label").textContent,
        node.querySelector(".metric-value").textContent,
      ],
    ),
  );
  assert.equal(metrics["Market Value"], "Unknown");
  assert.equal(metrics["Liability Balance"], "Unknown");
  assert.equal(metrics.Liabilities, "2");
  console.log("OK blocked dashboard capital totals render Unknown");
});
