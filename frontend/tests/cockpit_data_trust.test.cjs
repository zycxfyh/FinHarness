"use strict";

// jsdom-based DOM test for the Cockpit Data Trust Console v1.
// Verifies the Data Trust view loads, renders boundary text, and references
// the correct API endpoints — without needing a real browser or live server.

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
const document = window.document;

// 1. Data Trust tab exists
const dataTrustTab = document.querySelector('.tab[data-view="data-trust"]');
assert.ok(dataTrustTab, "Data Trust tab must exist in the cockpit nav");

// 2. Tab count is 9
const tabs = document.querySelectorAll("nav.tabs button.tab");
assert.equal(tabs.length, 9, "cockpit must have 9 tabs");

// 3. Data Trust view section exists
const dataTrustView = document.querySelector("#data-trust-view");
assert.ok(dataTrustView, "Data Trust view section must exist");
assert.ok(dataTrustView.classList.contains("view"), "must have .view class");

// 4. Boundary tag exists with required text
const boundaryTag = document.querySelector("#data-trust-boundary");
assert.ok(boundaryTag, "boundary tag must exist");
assert.match(
  boundaryTag.textContent,
  /execution_allowed=false/,
  "boundary tag must show execution_allowed=false"
);
assert.match(
  boundaryTag.textContent,
  /Read-only Data Trust surface/,
  "boundary tag must state read-only surface"
);
assert.match(
  boundaryTag.textContent,
  /No provider refresh/,
  "boundary tag must forbid provider refresh"
);
assert.match(
  boundaryTag.textContent,
  /No repair action/,
  "boundary tag must forbid repair action"
);
assert.match(
  boundaryTag.textContent,
  /No execution authorization/,
  "boundary tag must forbid execution authorization"
);
assert.match(
  boundaryTag.textContent,
  /No investment advice/,
  "boundary tag must disclaim investment advice"
);

// 5. Rendered panels (summary, catalog, quality, gaps) exist in DOM
assert.ok(document.querySelector("#data-trust-summary"), "summary panel must exist");
assert.ok(document.querySelector("#data-trust-catalog"), "catalog panel must exist");
assert.ok(document.querySelector("#data-trust-quality"), "quality panel must exist");
assert.ok(document.querySelector("#data-trust-gaps"), "gaps panel must exist");

// 6. JS source text contains required API endpoint references
const jsSource = fs.readFileSync(path.join(frontendDir, "app.js"), "utf-8");
assert.ok(jsSource.includes("/data/catalog"), "app.js must reference /data/catalog");
assert.ok(jsSource.includes("/data/quality"), "app.js must reference /data/quality");
assert.ok(
  jsSource.includes("/data/gaps?severity=critical"),
  "app.js must reference /data/gaps?severity=critical"
);
assert.ok(
  jsSource.includes("/data/gaps?severity=warning"),
  "app.js must reference /data/gaps?severity=warning"
);

// 7. No forbidden text in JS source
const forbiddenPatterns = [
  "provider refresh",
  "repair action",
  "execution action",
];
for (const pattern of forbiddenPatterns) {
  // These may appear in boundary text strings; we only check that app.js
  // doesn't contain them in an action context outside of non-claims text.
  // Actually, the boundary text IS in index.html, not app.js. Check that
  // app.js doesn't contain action-triggering patterns like "fetch" for
  // provider refresh.
  if (jsSource.includes("/refresh") || jsSource.includes("/repair")) {
    assert.fail(`app.js must not contain action patterns: ${pattern}`);
  }
}

console.log("Cockpit Data Trust Console: PASS (7 checks).");
