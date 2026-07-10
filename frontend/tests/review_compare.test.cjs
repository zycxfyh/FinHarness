"use strict";

// jsdom DOM test for the read-only Compare view (R4b): read-only pair selection, no POST
// on selection, side-by-side raw facts, and no verdict wording in the compare chrome.

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
  dom.window.eval(fs.readFileSync(path.join(frontendDir, "app.js"), "utf-8"));
  return dom.window;
}

const window = loadCockpitWindow();

const NON_CLAIMS = [
  "Compare marks are descriptive pairings for review, not a recommendation.",
  "Side-by-side facts do not rank or pick a candidate.",
  "Not execution authorization.",
  "Not investment advice.",
];

function renderPanel(data, onSelect) {
  const parent = window.document.createElement("div");
  window.renderCompareMarksPanel(parent, data, onSelect);
  return parent;
}

// 1. Empty -> empty-state + disclosure, no select control.
const empty = renderPanel({ pairs: [], non_claims: NON_CLAIMS });
assert.ok(empty.textContent.includes("No compare marks"), "empty-state renders");
assert.ok(empty.textContent.includes("not a recommendation"), "non_claims render when empty");
assert.strictEqual(empty.querySelectorAll("select").length, 0, "no select when empty");

// 2. Populated -> a read-only <select> of pairs, missing-side disclosure, non_claims, and
//    NO buttons/links and NO verdict wording in the compare chrome.
const populated = renderPanel({
  pairs: [
    {
      proposal_id: "A",
      compare_with: "B",
      attester: "operator",
      reason: "compare",
      created_at_utc: "2026-06-22T10:00:00Z",
      review_event_id: "rev1",
      proposal_exists: true,
      compare_with_exists: true,
      missing_side: null,
      data_gaps: [],
    },
    {
      proposal_id: "C",
      compare_with: "D",
      attester: "operator",
      reason: "compare",
      created_at_utc: "2026-06-22T09:00:00Z",
      review_event_id: "rev2",
      proposal_exists: true,
      compare_with_exists: false,
      missing_side: "right",
      data_gaps: ["missing right"],
    },
  ],
  non_claims: NON_CLAIMS,
});
const select = populated.querySelector("#compare-pair-select");
assert.ok(select, "pair selector renders");
assert.ok(
  [...select.options].some((o) => o.textContent.includes("A vs B")),
  "a pair option is present (labelled A vs B)",
);
assert.ok(populated.textContent.includes("missing right"), "missing-side disclosure renders");
assert.strictEqual(
  populated.querySelectorAll("button, a").length,
  0,
  "compare chrome has no buttons or links",
);
for (const verdict of ["winner", "recommended", "better", "should pick", "you should"]) {
  assert.ok(
    !populated.textContent.toLowerCase().includes(verdict),
    `compare chrome must not synthesize a verdict: "${verdict}"`,
  );
}

// 3. Read-only selection callback fires with the chosen pair value (the wiring then GETs).
let picked = null;
const withCb = renderPanel({ pairs: [
  { proposal_id: "A", compare_with: "B", attester: "op", reason: "r", created_at_utc: "t", review_event_id: "rev1", proposal_exists: true, compare_with_exists: true, missing_side: null, data_gaps: [] },
], non_claims: NON_CLAIMS }, (pair) => { picked = pair; });
const sel = withCb.querySelector("#compare-pair-select");
sel.value = "0"; // option index, not a delimited id string
sel.dispatchEvent(new window.Event("change", { bubbles: true }));
assert.ok(picked && picked.proposal_id === "A" && picked.compare_with === "B",
  "selection invokes the read-only onSelect with the resolved pair object");

// 4. Side-by-side renders both candidates' own facts; a missing side degrades to a notice.
const cols = window.document.createElement("div");
window.renderCompareSideBySide(
  cols,
  { proposal: { proposal_id: "A", claim: "A claim", kind: "concentration_high", evidence: { dimension: "stock" } } },
  null,
);
assert.ok(cols.textContent.includes("A claim"), "left candidate facts render");
assert.ok(cols.textContent.includes("Candidate unavailable"), "missing side degrades to a notice");

// 5. Full Compare view: selecting a pair issues GETs only — never a POST.
const fetchCalls = [];
window.fetch = (p, opts) => {
  fetchCalls.push([String(p), (opts && opts.method) || "GET"]);
  const body = String(p).includes("/review/compare-marks")
    ? { pairs: [{ proposal_id: "A", compare_with: "B", attester: "op", reason: "r", created_at_utc: "t", review_event_id: "rev1", proposal_exists: true, compare_with_exists: true, missing_side: null, data_gaps: [] }], non_claims: NON_CLAIMS }
    : { proposal: { proposal_id: "A", claim: "x", kind: "k", evidence: {} } };
  return Promise.resolve({ ok: true, json: () => Promise.resolve(body) });
};

window.renderCompare().then(() => {
  const select5 = window.document.querySelector("#compare-pair-select");
  select5.value = "0"; // option index
  select5.dispatchEvent(new window.Event("change", { bubbles: true }));
  setTimeout(() => {
    assert.ok(fetchCalls.length > 0, "compare view fetched");
    for (const [, method] of fetchCalls) {
      assert.strictEqual(method, "GET", "compare view must only GET, never POST");
    }
    console.log("review_compare.test.cjs: all assertions passed");
  }, 0);
});
