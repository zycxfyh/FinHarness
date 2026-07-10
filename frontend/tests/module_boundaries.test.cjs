"use strict";

const assert = require("node:assert");
const fs = require("node:fs");
const path = require("node:path");
const { JSDOM } = require("jsdom");

const frontendDir = path.resolve(__dirname, "..");
const html = fs.readFileSync(path.join(frontendDir, "index.html"), "utf-8");
const apiSource = fs.readFileSync(path.join(frontendDir, "api.js"), "utf-8");
const appSource = fs.readFileSync(path.join(frontendDir, "app.js"), "utf-8");
const stateSource = fs.readFileSync(path.join(frontendDir, "state.js"), "utf-8");
const actionsSource = fs.readFileSync(path.join(frontendDir, "actions.js"), "utf-8");
const dom = new JSDOM(html, { runScripts: "outside-only" });

dom.window.eval(apiSource);
dom.window.eval(stateSource);
dom.window.eval(actionsSource);

assert.strictEqual(dom.window.FinHarness.state.activeView, "overview");
assert.ok(Object.isSealed(dom.window.FinHarness.state), "shared state is a real sealed state object");
assert.ok(!stateSource.includes("placeholder"), "state.js must not be a boundary marker");
assert.ok(!appSource.includes("const state = {"), "app.js must consume state.js");
assert.ok(!appSource.includes("await apiPost("), "writes must not bypass ReviewActionShell");
assert.ok(!appSource.includes("await apiPatch("), "writes must not bypass ReviewActionShell");
assert.strictEqual(
  (appSource.match(/ReviewActionShell\.(post|patch)\(/g) || []).length,
  3,
  "all three governed review forms use the shared action shell",
);

const browserLikeDom = new JSDOM(html, { runScripts: "outside-only" });
browserLikeDom.window.fetch = () => Promise.reject(new Error("fetch disabled in test"));
assert.doesNotThrow(
  () => browserLikeDom.window.eval([apiSource, stateSource, actionsSource, appSource].join("\n")),
  "classic scripts must share one global scope without duplicate declarations",
);

const requests = [];
dom.window.fetch = (endpoint, options) => {
  requests.push([endpoint, options]);
  return Promise.resolve({
    ok: true,
    json: () => Promise.resolve({ execution_allowed: false }),
  });
};

(async () => {
  await dom.window.FinHarness.ReviewActionShell.post("/review", { reason: "test" });
  assert.strictEqual(requests.length, 1);
  assert.strictEqual(requests[0][1].method, "POST");

  dom.window.fetch = () =>
    Promise.resolve({
      ok: true,
      json: () => Promise.resolve({ execution_allowed: true }),
    });
  await assert.rejects(
    dom.window.FinHarness.ReviewActionShell.patch("/review", {}),
    /unexpected execution_allowed/,
  );
  console.log("module_boundaries.test.cjs: all assertions passed");
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
