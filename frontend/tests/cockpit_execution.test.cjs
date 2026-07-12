"use strict";

// jsdom-based DOM test for the Execution Cockpit surface.

const assert = require("node:assert");
const fs = require("node:fs");
const path = require("node:path");
const { JSDOM } = require("jsdom");

const frontendDir = path.resolve(__dirname, "..");

const html = fs.readFileSync(path.join(frontendDir, "index.html"), "utf-8");
const dom = new JSDOM(html, { runScripts: "outside-only" });
const document = dom.window.document;

// 1. Execution is not advertised in ordinary navigation.
assert.equal(document.querySelector('.tab[data-view="execution"]'), null);

// 2. Ordinary Cockpit navigation contains only review/read surfaces.
const tabs = document.querySelectorAll("nav.tabs button.tab");
assert.equal(tabs.length, 8, "cockpit must have 8 ordinary tabs");

// 3. Execution view exists
const execView = document.querySelector("#execution-view");
assert.ok(execView, "Execution view section must exist");
assert.ok(execView.classList.contains("view"), "must have .view class");
assert.ok(execView.hasAttribute("hidden"), "simulated preview must be hidden");
assert.match(execView.textContent, /simulated lifecycle preview/i);

// 4. Order Drafts panel
assert.ok(
  document.querySelector("#execution-drafts"),
  "Order Drafts panel must exist"
);

// 5. Execution Orders panel
assert.ok(
  document.querySelector("#execution-orders"),
  "Execution Orders panel must exist"
);

// 6. Execution Reports panel
assert.ok(
  document.querySelector("#execution-reports"),
  "Execution Reports panel must exist"
);

// 7. JS source references execution API endpoints
const jsSource = fs.readFileSync(path.join(frontendDir, "app.js"), "utf-8");
assert.ok(
  jsSource.includes("/execution/orders"),
  "app.js must reference /execution/orders"
);
assert.ok(
  jsSource.includes("renderExecution"),
  "app.js must define renderExecution"
);

console.log("OK execution cockpit DOM tests passed");
