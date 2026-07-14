"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { JSDOM } = require("jsdom");
const {
  installWebLocks,
} = require("./_web_locks.cjs");

const frontendDir = path.resolve(__dirname, "..");
const apiSource = fs.readFileSync(
  path.join(frontendDir, "api.js"),
  "utf8",
);
const actionsSource = fs.readFileSync(
  path.join(frontendDir, "actions.js"),
  "utf8",
);

function response({
  ok,
  status,
  body,
  receipt = null,
  replayed = false,
}) {
  return {
    ok,
    status,
    statusText: ok ? "OK" : "Error",
    headers: {
      get(name) {
        const normalized =
          String(name).toLowerCase();
        if (
          normalized ===
          "x-finharness-identity-receipt"
        ) {
          return receipt;
        }
        if (
          normalized ===
          "x-finharness-idempotent-replay"
        ) {
          return replayed ? "true" : null;
        }
        if (
          normalized ===
          "x-finharness-trace-id"
        ) {
          return "trace_frontend_test";
        }
        return null;
      },
    },
    json: async () => body,
  };
}

function browserDom() {
  const dom = new JSDOM("", {
    runScripts: "outside-only",
    url: "https://cockpit.finharness.test/",
  });
  installWebLocks(dom.window);
  dom.window.console.debug = () => {};
  dom.window.console.error = () => {};
  dom.window.eval(apiSource);
  dom.window.eval(actionsSource);
  return dom;
}

function registry(dom) {
  const key =
    dom.window.FinHarness.api
      .MUTATION_ATTEMPTS_STORAGE_KEY;
  const raw = dom.window.localStorage.getItem(key);
  return raw ? JSON.parse(raw) : null;
}

(async () => {
  const dom = browserDom();
  const payload = {
    reason: "same logical operation",
    execution_allowed: false,
  };
  const endpoint = "/proposals/prop_1/review-events";
  const observedKeys = [];

  dom.window.fetch = async (_path, options) => {
    const stored = registry(dom);
    assert.ok(
      stored,
      "attempt must be durable before fetch",
    );
    assert.equal(stored.attempts.length, 1);
    assert.equal(
      stored.attempts[0].idempotency_key,
      options.headers["Idempotency-Key"],
    );
    observedKeys.push(
      options.headers["Idempotency-Key"],
    );
    throw new Error("simulated response loss");
  };

  await assert.rejects(
    dom.window.FinHarness.ReviewActionShell.post(
      endpoint,
      payload,
    ),
    (error) => {
      assert.equal(
        error.name,
        "MutationTransportError",
      );
      assert.equal(error.attemptRetained, true);
      return true;
    },
  );

  const afterLoss = registry(dom);
  assert.equal(afterLoss.attempts.length, 1);
  const retainedKey =
    afterLoss.attempts[0].idempotency_key;

  // Simulate a page reload by rebuilding the API/action
  // namespaces while keeping the same localStorage.
  dom.window.eval(apiSource);
  dom.window.eval(actionsSource);

  dom.window.fetch = async (_path, options) => {
    observedKeys.push(
      options.headers["Idempotency-Key"],
    );
    return response({
      ok: true,
      status: 200,
      receipt: "identity_mutation_test",
      replayed: true,
      body: {
        execution_allowed: false,
        replayed: true,
      },
    });
  };

  const replayed =
    await dom.window.FinHarness
      .ReviewActionShell.post(
        endpoint,
        payload,
      );

  assert.equal(replayed.replayed, true);
  assert.equal(observedKeys[0], retainedKey);
  assert.equal(observedKeys[1], retainedKey);
  assert.equal(
    registry(dom),
    null,
    "terminal replay must clear the attempt",
  );

  // The same payload after a completed logical operation
  // is a new operation and receives a new key.
  await dom.window.FinHarness.ReviewActionShell.post(
    endpoint,
    payload,
  );
  assert.notEqual(
    observedKeys[2],
    retainedKey,
    "new logical operation must not reuse a completed key",
  );
  assert.equal(registry(dom), null);

  // A successful HTTP response with an invalid governed
  // response contract is not acknowledged.
  dom.window.fetch = async () =>
    response({
      ok: true,
      status: 200,
      receipt: "identity_mutation_bad_contract",
      body: {
        execution_allowed: true,
      },
    });

  await assert.rejects(
    dom.window.FinHarness.ReviewActionShell.patch(
      "/proposals/prop_1/decision-scaffold",
      { reason: "invalid contract" },
    ),
    /unexpected execution_allowed/,
  );
  assert.equal(
    registry(dom).attempts.length,
    1,
    "contract failure must retain the key",
  );

  // A typed terminal validation rejection clears its
  // attempt because the protocol receipt proves terminality.
  dom.window.localStorage.clear();
  dom.window.fetch = async () =>
    response({
      ok: false,
      status: 422,
      receipt: "identity_mutation_rejected",
      body: {
        detail: {
          code: "validation_error",
          message: "invalid input",
        },
      },
    });

  await assert.rejects(
    dom.window.FinHarness.ReviewActionShell.post(
      "/proposals/prop_1/attest",
      { reason: "" },
    ),
    (error) => {
      assert.equal(error.name, "ApiError");
      assert.equal(error.attemptRetained, false);
      return true;
    },
  );
  assert.equal(
    registry(dom),
    null,
    "terminal rejection must clear the attempt",
  );

  // Persistent storage is mandatory. An opaque-origin
  // environment must fail before sending a write.
  const noStorageDom = new JSDOM("", {
    runScripts: "outside-only",
  });
  noStorageDom.window.console.error = () => {};
  noStorageDom.window.eval(apiSource);
  noStorageDom.window.eval(actionsSource);

  let fetchCalls = 0;
  noStorageDom.window.fetch = async () => {
    fetchCalls += 1;
    throw new Error("must not be called");
  };

  await assert.rejects(
    noStorageDom.window.FinHarness
      .ReviewActionShell.post(
        "/review",
        { reason: "no durable storage" },
      ),
    (error) => {
      assert.equal(
        error.name,
        "MutationAttemptStorageError",
      );
      return true;
    },
  );
  assert.equal(fetchCalls, 0);

  console.log(
    "idempotent_mutations.test.cjs: all assertions passed",
  );
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
