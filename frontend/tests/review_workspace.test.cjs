"use strict";

// jsdom DOM test for the Review Workspace (R2c): the read-only merged timeline renders
// real entries with no action affordances, and the human write form never POSTs without
// an explicit confirm. Loads the real cockpit shell + app.js.

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

function renderTimeline(timeline) {
  const parent = window.document.createElement("div");
  window.renderReviewTimeline(parent, timeline);
  return parent;
}

// 1. Empty timeline -> explicit empty-state, not a silent blank.
const empty = renderTimeline({ proposal_id: "p", is_archived: false, entries: [] });
assert.ok(empty.textContent.includes("Review timeline"), "header renders");
assert.ok(empty.textContent.includes("No review activity"), "empty-state renders");

// 2. Populated timeline renders each entry's source_type/kind/attester/reason; archived
//    badge shows; and the read-only timeline has NO action affordances.
const populated = renderTimeline({
  proposal_id: "p",
  is_archived: true,
  entries: [
    {
      source_type: "review_event",
      id: "rev1",
      kind: "annotation",
      created_at_utc: "2026-06-22T10:00:00Z",
      attester: "operator",
      reason: "watch the rate path",
    },
    {
      source_type: "attestation",
      id: "att1",
      kind: "approved",
      created_at_utc: "2026-06-22T09:00:00Z",
      attester: "operator",
      reason: "looks fine",
    },
  ],
});
const text = populated.textContent;
assert.ok(text.includes("[review_event] annotation by operator"), "review event entry");
assert.ok(text.includes("[attestation] approved by operator"), "attestation entry");
assert.ok(text.includes("watch the rate path"), "reason renders");
assert.ok(text.includes("archived"), "archived badge renders");
assert.strictEqual(
  populated.querySelectorAll("button, a").length,
  0,
  "read-only timeline must have no buttons or links",
);

// 3. The write form never POSTs without an explicit confirm.
function renderForm() {
  const parent = window.document.createElement("div");
  window.renderReviewEventForm(parent, "prop_1");
  return parent.querySelector("form");
}

// 3a. confirm() returns false -> no fetch.
let fetchCalls = [];
window.fetch = (p, opts) => {
  fetchCalls.push([p, opts]);
  return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
};
window.confirm = () => false;
let form = renderForm();
form.querySelector('[name="attester"]').value = "operator";
form.querySelector('[name="reason"]').value = "cleanup";
form.dispatchEvent(new window.Event("submit", { cancelable: true, bubbles: true }));
assert.strictEqual(fetchCalls.length, 0, "cancelled confirm must not POST");

// 3b. confirm() returns true -> exactly one POST to the review-events endpoint.
fetchCalls = [];
window.confirm = () => true;
form = renderForm();
form.querySelector('[name="attester"]').value = "operator";
form.querySelector('[name="reason"]').value = "cleanup";
form.dispatchEvent(new window.Event("submit", { cancelable: true, bubbles: true }));
// allow the async submit handler microtasks to run
setTimeout(() => {
  const posts = fetchCalls.filter(
    ([p, opts]) =>
      String(p).includes("/proposals/prop_1/review-events") && opts && opts.method === "POST",
  );
  assert.strictEqual(posts.length, 1, "confirmed action posts exactly once to review-events");
  console.log("review_workspace.test.cjs: all assertions passed");
}, 0);
