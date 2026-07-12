"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const source = fs.readFileSync(path.resolve(__dirname, "..", "api.js"), "utf8");
const context = {
  window: {},
  fetch: async () => ({
    ok: false,
    status: 503,
    statusText: "Service Unavailable",
    headers: { get: (name) => name === "x-finharness-trace-id" ? "trace_negative_path" : null },
    json: async () => ({ detail: { code: "state_unavailable", message: "store offline" } }),
  }),
};
vm.createContext(context);
vm.runInContext(source, context);

(async () => {
  await assert.rejects(
    context.window.FinHarness.api.apiGet("/broken"),
    (error) => {
      assert.equal(error.name, "ApiError");
      assert.equal(error.status, 503);
      assert.equal(error.traceId, "trace_negative_path");
      assert.match(error.message, /store offline/);
      assert.match(error.message, /trace_negative_path/);
      return true;
    },
  );
  console.log("OK typed API errors retain visible trace IDs");
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
