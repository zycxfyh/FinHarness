"use strict";

// jsdom DOM test for the read-only research-evidence block. Loads the real cockpit
// shell + app.js and asserts renderCandidateDetail actually renders descriptive
// evidence — proving "not empty render" (real text present) and "not misleading
// render" (mandatory disclaimers shown, no action affordances, value whitelist).

const assert = require("node:assert");
const fs = require("node:fs");
const path = require("node:path");
const { JSDOM } = require("jsdom");

const frontendDir = path.resolve(__dirname, "..");

function loadCockpitWindow() {
  const html = fs.readFileSync(path.join(frontendDir, "index.html"), "utf-8");
  const dom = new JSDOM(html, { runScripts: "outside-only" });
  dom.window.fetch = () => Promise.reject(new Error("fetch disabled in test"));
  dom.window.eval(fs.readFileSync(path.join(frontendDir, "api.js"), "utf-8"));
  dom.window.eval(fs.readFileSync(path.join(frontendDir, "state.js"), "utf-8"));
  dom.window.eval(fs.readFileSync(path.join(frontendDir, "actions.js"), "utf-8"));
  dom.window.eval(fs.readFileSync(path.join(frontendDir, "app.js"), "utf-8"));
  return dom.window;
}

function renderDetail(window, evidence) {
  const parent = window.document.createElement("div");
  window.renderCandidateDetail(parent, { evidence });
  return parent;
}

const window = loadCockpitWindow();

const RESEARCH_ITEM = {
  kind: "historical_risk_profile",
  evidence_grade: "historical_market_data",
  claim: "Over the trailing 3 years, SPY's observed realized volatility was 18%.",
  time_window: "trailing_3y",
  value: {
    realized_volatility: 0.18,
    max_drawdown: -0.34,
    conditional_var: -0.03,
    average_volume: 1000000,
    target_price: 500, // non-whitelisted: must never render
  },
  limitations: ["Single-window descriptive statistics, not a forecast."],
  non_claims: [
    "Historical market description, not a prediction.",
    "Not investment advice.",
  ],
  source_refs: ["data/receipts/market-data/spy.json"],
};

// 1. Positive (not empty): grade, claim, every whitelisted value key, every non_claim,
//    and source_refs all render as real text.
const populated = renderDetail(window, {
  dimension: "stock",
  research_evidence: [RESEARCH_ITEM],
});
const text = populated.textContent;
assert.ok(
  text.includes("Research evidence (historical, descriptive)"),
  "expected the research-evidence block header",
);
assert.ok(text.includes("historical_market_data"), "grade must render");
assert.ok(text.includes("observed realized volatility"), "claim must render");
for (const key of [
  "realized_volatility",
  "max_drawdown",
  "conditional_var",
  "average_volume",
]) {
  assert.ok(text.includes(key), `whitelisted value key ${key} must render`);
}
assert.ok(text.includes("Not investment advice."), "non_claims must render");
assert.ok(
  text.includes("Historical market description, not a prediction."),
  "all non_claims must render",
);
assert.ok(text.includes("data/receipts/market-data/spy.json"), "source_refs must render");

// 2. Mandatory disclosure co-located: grade AND non_claims live in the same card as
//    the claim, so the descriptive framing cannot be detached.
const card = populated.querySelector(".research-evidence");
assert.ok(card, "expected a research-evidence card");
assert.ok(card.textContent.includes("historical_market_data"), "grade co-located");
assert.ok(card.textContent.includes("Not investment advice."), "disclaimer co-located");

// 3. Not misleading: no value key outside the whitelist renders, and the block carries
//    no action affordances (no buttons, no links).
assert.ok(!text.includes("target_price"), "non-whitelisted value key must not render");
assert.strictEqual(
  populated.querySelectorAll("button, a").length,
  0,
  "read-only: research block must have no buttons or links",
);

// 4. Gaps render visibly (not a silent empty), and no evidence card is drawn.
const gapsOnly = renderDetail(window, {
  dimension: "stock",
  research_evidence: [],
  research_evidence_gaps: ["market history unavailable for SPY."],
});
assert.ok(gapsOnly.textContent.includes("Data gaps"), "gap header must render");
assert.ok(
  gapsOnly.textContent.includes("market history unavailable for SPY."),
  "gap text must render",
);
assert.strictEqual(
  gapsOnly.querySelectorAll(".research-evidence").length,
  0,
  "no evidence card when only gaps are present",
);

// 5. Fail-closed disclosure: an item missing non_claims must NOT render its claim;
//    it is omitted with a safe notice instead (cockpit is the last anti-misread surface).
const missingNonClaims = renderDetail(window, {
  dimension: "stock",
  research_evidence: [{ ...RESEARCH_ITEM, non_claims: [] }],
});
assert.ok(
  !missingNonClaims.textContent.includes("observed realized volatility"),
  "claim must not render without mandatory disclosure (non_claims)",
);
assert.ok(
  missingNonClaims.textContent.includes("omitted because mandatory disclosure is missing"),
  "a safe omission notice must render instead",
);

// 6. Fail-closed disclosure: same when evidence_grade is missing.
const missingGrade = renderDetail(window, {
  dimension: "stock",
  research_evidence: [{ ...RESEARCH_ITEM, evidence_grade: undefined }],
});
assert.ok(
  !missingGrade.textContent.includes("observed realized volatility"),
  "claim must not render without a grade",
);
assert.ok(
  missingGrade.textContent.includes("omitted because mandatory disclosure is missing"),
  "a safe omission notice must render instead",
);

// 7. Default no-op path: nothing attached -> no research block at all.
const none = renderDetail(window, { dimension: "stock" });
assert.ok(
  !none.textContent.includes("Research evidence (historical, descriptive)"),
  "no research block when nothing is attached (default path unchanged)",
);

console.log("research_evidence.test.cjs: all assertions passed");
