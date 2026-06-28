"use strict";

// jsdom DOM test for the read-only IPS Policy view. It loads the real cockpit shell
// + app.js and asserts the active IPS and compliance check render as policy boundaries,
// not advice or an execution affordance.

const assert = require("node:assert");
const fs = require("node:fs");
const path = require("node:path");
const { JSDOM } = require("jsdom");

const frontendDir = path.resolve(__dirname, "..");

function loadCockpitWindow() {
  const html = fs.readFileSync(path.join(frontendDir, "index.html"), "utf-8");
  const dom = new JSDOM(html, { runScripts: "outside-only" });
  dom.window.fetch = () => Promise.reject(new Error("fetch disabled in test"));
  dom.window.eval(fs.readFileSync(path.join(frontendDir, "app.js"), "utf-8"));
  return dom.window;
}

const window = loadCockpitWindow();

const current = {
  available: true,
  execution_allowed: false,
  non_claims: [
    "Investment Policy Statement: the user's own policy, not advice.",
    "Not execution authorization.",
  ],
  ips: {
    ips_id: "ips_v0",
    status: "active",
    liquidity_floor_months: "6",
    max_single_holding_pct: "0.4",
    cash_overweight_pct: "0.6",
    high_interest_rate_pct: "0.08",
    base_currency: "USD",
    allowed_asset_classes: ["cash", "equity"],
    restricted_actions: ["borrow_to_buy"],
    review_cadence: "quarterly",
    source_refs: ["data/receipts/state-core/ips/receipt_1.json"],
    receipt_ref: "data/receipts/state-core/ips/receipt_1.json",
    execution_allowed: false,
  },
};

const check = {
  ips_id: "ips_v0",
  as_of_date: "2026-06-28",
  violations: ["single_holding_cap"],
  blocked: ["liquidity_floor"],
  source_refs: ["data/receipts/state-core/imports/receipt_cash.json"],
  execution_allowed: false,
  non_claims: [
    "A compliance check is descriptive; it is not a recommendation to trade.",
    "Not execution authorization.",
  ],
  results: [
    {
      rule: "single_holding_cap",
      boundary: "top holding <= 40% of invested book",
      observed: "SPY 55%",
      status: "violation",
      detail: "SPY is above the user's cap.",
    },
    {
      rule: "liquidity_floor",
      boundary: "cash runway >= 6.0 months",
      observed: "unverified",
      status: "blocked",
      detail: "No verified cash runway.",
    },
  ],
};

const currentPanel = window.document.createElement("div");
window.renderPolicyCurrent(currentPanel, current);
const currentText = currentPanel.textContent;
assert.ok(currentText.includes("ips_v0"), "active IPS id renders");
assert.ok(currentText.includes("6.0 mo"), "liquidity floor renders as months");
assert.ok(currentText.includes("40.0%"), "single holding cap renders as percent");
assert.ok(currentText.includes("borrow_to_buy"), "restricted actions render");
assert.ok(currentText.includes("Not execution authorization."), "IPS non_claims render");
assert.strictEqual(
  currentPanel.querySelectorAll("button, a").length,
  0,
  "IPS policy panel must not expose action affordances",
);

const checkPanel = window.document.createElement("div");
window.renderPolicyCheck(checkPanel, check);
const checkText = checkPanel.textContent;
assert.ok(checkText.includes("single_holding_cap"), "violation rule renders");
assert.ok(checkText.includes("liquidity_floor"), "blocked rule renders");
assert.ok(checkText.includes("SPY 55%"), "observed value renders");
assert.ok(checkText.includes("receipt_cash.json"), "source refs render");
assert.ok(checkText.includes("Execution allowedfalse"), "execution_allowed=false renders");
assert.ok(checkText.includes("not a recommendation to trade"), "check non_claims render");
assert.strictEqual(
  checkPanel.querySelectorAll("button, a").length,
  0,
  "IPS compliance panel must not expose action affordances",
);

const empty = window.document.createElement("div");
window.renderPolicyCurrent(empty, { available: false, non_claims: current.non_claims });
assert.ok(empty.textContent.includes("No active IPS"), "missing IPS state renders visibly");
assert.ok(empty.textContent.includes("Not execution authorization."), "empty state keeps non_claims");

console.log("ips_policy.test.cjs: all assertions passed");
