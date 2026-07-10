"use strict";

// jsdom DOM test for the read-only Retrospective panel (R3b): renders the latest annual
// review summary + rule-change drill-down, shows unclosed lessons as neutral disclosure
// (not a suggestion), always renders the non_claims disclosure, and has no action
// affordances.

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

const window = loadCockpitWindow();

function render(data) {
  const parent = window.document.createElement("div");
  window.renderRetrospectivePanel(parent, data);
  return parent;
}

const NON_CLAIMS = [
  "Retrospective is historical evidence only.",
  "Unclosed lessons are disclosure, not a recommendation or a rule change.",
  "Not execution authorization.",
  "Not investment advice.",
];

// 1. Empty (no annual review receipt yet) -> empty-state + disclosure, no crash.
const empty = render({
  retrospective: null,
  retrospective_receipt_ref: null,
  rule_changes: [],
  data_gaps: [],
  non_claims: NON_CLAIMS,
});
assert.ok(empty.textContent.includes("No annual review yet"), "empty-state renders");
assert.ok(
  empty.textContent.includes("Unclosed lessons are disclosure, not a recommendation"),
  "disclosure non_claims render even when empty",
);

// 2. Populated -> closure summary, source receipt, unclosed lessons as disclosure,
//    rule-change drill-down. No action affordances; disclosure present.
const populated = render({
  retrospective: {
    period_label: "2025",
    lessons_closed: 3,
    lessons_open: ["L1: revisit cash buffer", "L2: tax window"],
    untraceable_rule_changes: ["rulechg_x"],
  },
  retrospective_receipt_ref: "data/receipts/annual-review/receipt_annual_2026.json",
  rule_changes: [
    {
      rule_change_id: "rulechg_traceable",
      rule_target: "guard.hard_stop_drawdown_pct",
      change_kind: "threshold",
      status: "active",
      attester: "operator",
      traceable: true,
    },
  ],
  data_gaps: [],
  non_claims: NON_CLAIMS,
});
const text = populated.textContent;
assert.ok(text.includes("2025"), "period renders");
assert.ok(text.includes("Unclosed lessons (disclosure)"), "unclosed lessons labelled disclosure");
assert.ok(text.includes("L1: revisit cash buffer"), "unclosed lesson text renders");
assert.ok(text.includes("guard.hard_stop_drawdown_pct"), "rule change renders");
assert.ok(text.includes("traceable"), "traceability renders");
assert.ok(
  text.includes("data/receipts/annual-review/receipt_annual_2026.json"),
  "source receipt ref renders (provenance)",
);
assert.ok(text.includes("Not investment advice."), "non_claims disclosure renders");

// 3. Not misleading: read-only, no action affordances, and no suggestive wording that
//    would turn disclosure into a recommendation to act/promote/apply.
assert.strictEqual(
  populated.querySelectorAll("button, a").length,
  0,
  "retrospective panel must have no buttons or links (read-only)",
);
// Phrase-level only: non_claims legitimately says "not a recommendation", so we check
// for imperative suggestions, not the bare words "recommend/promote".
for (const suggestive of ["you should", "apply this", "promote this", "we recommend"]) {
  assert.ok(
    !text.toLowerCase().includes(suggestive),
    `must not suggest action: "${suggestive}"`,
  );
}

console.log("review_retrospective.test.cjs: all assertions passed");
