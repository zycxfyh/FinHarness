"use strict";

// jsdom-based DOM test for the proposal revision history view. Served-shell tests
// only prove the functions exist in the file; this loads the real cockpit shell and
// app.js and asserts renderRevisionHistory actually renders the per-version diff,
// catching "function present but DOM rendering wrong" bugs without a real browser.

const assert = require("node:assert");
const fs = require("node:fs");
const path = require("node:path");
const { JSDOM } = require("jsdom");

const frontendDir = path.resolve(__dirname, "..");

function loadCockpitWindow() {
  const html = fs.readFileSync(path.join(frontendDir, "index.html"), "utf-8");
  const dom = new JSDOM(html, { runScripts: "outside-only" });
  // The cockpit fetches on init; disable it so loading app.js has no network side
  // effects (app.js catches the rejection).
  dom.window.fetch = () => Promise.reject(new Error("fetch disabled in test"));
  dom.window.eval(fs.readFileSync(path.join(frontendDir, "app.js"), "utf-8"));
  return dom.window;
}

function renderRevisions(window, revisions) {
  const parent = window.document.createElement("div");
  window.renderRevisionHistory(parent, { revisions });
  return parent.textContent;
}

function revision(receiptRef, supersedes, claim, evidence) {
  return {
    receipt_ref: receiptRef,
    created_at_utc: "2026-03-02",
    content_hash: "abc123",
    supersedes,
    execution_allowed: false,
    proposal: { claim, evidence },
  };
}

const window = loadCockpitWindow();

// 1. A changed claim and a changed scalar evidence field render a readable diff,
//    and the oldest revision is labelled the initial version.
const changed = renderRevisions(window, [
  revision("r2", "r1", "Cash covers 1.0 months", { cash_runway_months: 1.0 }),
  revision("r1", null, "Cash covers 2.5 months", { cash_runway_months: 2.5 }),
]);
assert.ok(changed.includes("Changes from previous"), "expected a diff header");
assert.ok(changed.includes("cash_runway_months: 2.5 → 1"), "expected the scalar diff line");
assert.ok(changed.includes("Initial version"), "oldest revision should be the initial version");
assert.ok(!changed.includes("execution_allowed=true"), "must stay read-only");

// 2. Identical adjacent content reports no field changes (timestamp-only revision).
const identical = renderRevisions(window, [
  revision("r2", "r1", "same", { x: 1 }),
  revision("r1", null, "same", { x: 1 }),
]);
assert.ok(
  identical.includes("No field changes from previous version"),
  "identical content should report no field changes",
);

// 3. No revisions renders the empty placeholder.
const empty = renderRevisions(window, []);
assert.ok(empty.includes("No revisions recorded"), "empty history should show a placeholder");

console.log("frontend revision history jsdom test: OK");
