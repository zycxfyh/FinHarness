"use strict";

// jsdom DOM test for proposal scaffold revision UX: current scaffold renders as
// review facts, and the human revision form only PATCHes after explicit confirm.

const assert = require("node:assert");
const fs = require("node:fs");
const path = require("node:path");
const { JSDOM } = require("jsdom");
const {
  installWebLocks,
} = require("./_web_locks.cjs");
const {
  BINDING_ENDPOINT,
  bindingResponse,
  mutationBinding,
  responseHeaders,
} = require("./_mutation_binding.cjs");

const frontendDir = path.resolve(__dirname, "..");

function loadCockpitWindow() {
  const html = fs.readFileSync(path.join(frontendDir, "index.html"), "utf-8");
  const dom = new JSDOM(html, {
  runScripts: "outside-only",
  url: "https://cockpit.finharness.test/",
});
  installWebLocks(dom.window);
  dom.window.fetch = () => Promise.reject(new Error("fetch disabled in test"));
  dom.window.eval(fs.readFileSync(path.join(frontendDir, "api.js"), "utf-8"));
  dom.window.eval(fs.readFileSync(path.join(frontendDir, "state.js"), "utf-8"));
  dom.window.eval(fs.readFileSync(path.join(frontendDir, "actions.js"), "utf-8"));
  dom.window.eval(fs.readFileSync(path.join(frontendDir, "app.js"), "utf-8"));
  return dom.window;
}

const window = loadCockpitWindow();

const scaffoldPanel = window.document.createElement("div");
window.renderDecisionScaffold(scaffoldPanel, {
  decision_scaffold: {
    decision_intent: "Review concentration",
    thesis: "Top holding is high",
    do_nothing_case: "Concentration persists",
    risk_if_wrong: "Trim could forgo upside",
    counter_evidence: "Top holding below 40%",
  },
});
assert.ok(scaffoldPanel.textContent.includes("Decision scaffold"), "scaffold header renders");
assert.ok(scaffoldPanel.textContent.includes("Top holding below 40%"), "counter evidence renders");
assert.strictEqual(
  scaffoldPanel.querySelectorAll("button, a").length,
  0,
  "scaffold facts must have no action affordance",
);

function renderForm() {
  const parent = window.document.createElement("div");
  window.renderScaffoldRevisionForm(parent, "prop_1");
  return parent.querySelector("form");
}

let fetchCalls = [];
const aliceBinding = mutationBinding();
window.fetch = (p, opts = {}) => {
  if (String(p) === BINDING_ENDPOINT) {
    return Promise.resolve(
      bindingResponse(aliceBinding),
    );
  }
  fetchCalls.push([String(p), opts]);
  if (opts.method === "PATCH") {
    return Promise.resolve({
      ok: true,
      status: 200,
      headers: responseHeaders({
        bindingId: aliceBinding.binding_id,
        receipt: "identity_scaffold_revision",
      }),
      json: () => Promise.resolve({ proposal: { proposal_id: "prop_1" }, execution_allowed: false }),
    });
  }
  if (String(p).startsWith("/proposals?")) {
    return Promise.resolve({ ok: true, json: () => Promise.resolve([]) });
  }
  return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
};

window.confirm = () => false;
let form = renderForm();
form.querySelector('[name="counter_evidence"]').value = "Top holding below 40%.";
form.querySelector('[name="reason"]').value = "Add falsification condition.";
form.dispatchEvent(new window.Event("submit", { cancelable: true, bubbles: true }));
assert.strictEqual(fetchCalls.length, 0, "cancelled confirm must not PATCH");

window.confirm = () => true;
form = renderForm();
form.querySelector('[name="counter_evidence"]').value = "Top holding below 40%.";
form.querySelector('[name="reason"]').value = "Add falsification condition.";
form.dispatchEvent(new window.Event("submit", { cancelable: true, bubbles: true }));

setTimeout(() => {
  const patches = fetchCalls.filter(
    ([p, opts]) => p.includes("/proposals/prop_1/decision-scaffold") && opts.method === "PATCH",
  );
  assert.strictEqual(patches.length, 1, "confirmed revision PATCHes exactly once");
  const payload = JSON.parse(patches[0][1].body);
  assert.strictEqual("attester" in payload, false);
  assert.strictEqual(payload.reason, "Add falsification condition.");
  assert.deepStrictEqual(payload.decision_scaffold, {
    counter_evidence: "Top holding below 40%.",
  });
  console.log("scaffold_revision.test.cjs: all assertions passed");
}, 0);
