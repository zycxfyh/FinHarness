"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { JSDOM } = require("jsdom");
const {
  createSerialLockManager,
  createSharedStorage,
  installSharedStorage,
  installWebLocks,
} = require("./_web_locks.cjs");
const {
  BINDING_ENDPOINT,
  bindingResponse,
  mutationBinding,
  responseHeaders,
} = require("./_mutation_binding.cjs");

const frontendDir = path.resolve(__dirname, "..");
const apiSource = fs.readFileSync(
  path.join(frontendDir, "api.js"),
  "utf8",
);

function response(receipt, bindingId) {
  return {
    ok: true,
    status: 200,
    statusText: "OK",
    headers: responseHeaders({
      bindingId,
      receipt,
    }),
    json: async () => ({
      execution_allowed: false,
    }),
  };
}

function apiContext({
  storage,
  lockManager = null,
}) {
  const dom = new JSDOM("", {
    runScripts: "outside-only",
    url: "https://cockpit.finharness.test/",
  });

  installSharedStorage(
    dom.window,
    storage,
  );

  if (lockManager) {
    installWebLocks(
      dom.window,
      lockManager,
    );
  }

  dom.window.eval(apiSource);
  return dom;
}

function registry(dom) {
  const storageKey =
    dom.window.FinHarness.api
      .MUTATION_ATTEMPTS_STORAGE_KEY;
  const raw =
    dom.window.localStorage.getItem(
      storageKey,
    );
  return raw ? JSON.parse(raw) : null;
}

(async () => {
  const sharedStorage = createSharedStorage();
  const sharedLocks = createSerialLockManager();

  const first = apiContext({
    storage: sharedStorage,
    lockManager: sharedLocks,
  });
  const second = apiContext({
    storage: sharedStorage,
    lockManager: sharedLocks,
  });
  const third = apiContext({
    storage: sharedStorage,
    lockManager: sharedLocks,
  });

  const sameOperationKeys = [];
  const aliceBinding = mutationBinding();
  const bobBinding = mutationBinding({
    bindingId: "b".repeat(64),
    principalId: "principal:bob",
    epochId: "bob-session-1",
  });
  const currentBindings = new Map([
    [first, aliceBinding],
    [second, aliceBinding],
    [third, bobBinding],
  ]);
  let thirdMutationCalls = 0;

  for (const dom of [first, second, third]) {
    dom.window.fetch = async (requestPath, options) => {
      const currentBinding =
        currentBindings.get(dom);
      if (requestPath === BINDING_ENDPOINT) {
        return bindingResponse(currentBinding);
      }
      if (dom === third) {
        thirdMutationCalls += 1;
      }
      sameOperationKeys.push(
        options.headers["Idempotency-Key"],
      );
      return response(
        "identity_same_operation",
        currentBinding.binding_id,
      );
    };
  }

  const [firstResult, secondResult] =
    await Promise.all([
      first.window.FinHarness.api.apiMutation(
        "POST",
        "/proposals/prop_1/attest",
        {
          decision: "approved",
          reason: "same operation",
        },
      ),
      second.window.FinHarness.api.apiMutation(
        "POST",
        "/proposals/prop_1/attest",
        {
          decision: "approved",
          reason: "same operation",
        },
      ),
    ]);

  assert.equal(
    sameOperationKeys.length,
    2,
  );
  assert.equal(
    sameOperationKeys[0],
    sameOperationKeys[1],
    "two contexts must reuse one key for one operation",
  );

  assert.equal(
    registry(first).attempts.length,
    1,
    "one logical operation has one durable attempt",
  );

  await assert.rejects(
    third.window.FinHarness.api.apiMutation(
      "POST",
      "/proposals/prop_1/attest",
      {
        decision: "approved",
        reason: "same operation",
      },
    ),
    (error) => error.reason === "principal_mismatch",
  );
  assert.equal(
    thirdMutationCalls,
    0,
    "cross-identity tab must stop before mutation fetch",
  );

  currentBindings.set(first, bobBinding);
  await assert.rejects(
    firstResult.acknowledge(),
    (error) =>
      error.name === "MutationAcknowledgementError" &&
      error.cause.reason === "cleanup_binding_changed",
  );
  assert.equal(
    registry(first).attempts.length,
    1,
    "Bob cannot clear Alice's shared attempt",
  );
  currentBindings.set(first, aliceBinding);

  await Promise.all([
    firstResult.acknowledge(),
    secondResult.acknowledge(),
  ]);

  assert.equal(
    registry(first),
    null,
    "duplicate terminal acknowledgements converge",
  );

  const differentOperationKeys = [];

  for (const dom of [first, second]) {
    dom.window.fetch = async (requestPath, options) => {
      if (requestPath === BINDING_ENDPOINT) {
        return bindingResponse(aliceBinding);
      }
      differentOperationKeys.push(
        options.headers["Idempotency-Key"],
      );
      return response(
        "identity_different_operation",
        aliceBinding.binding_id,
      );
    };
  }

  const [attestation, revision] =
    await Promise.all([
      first.window.FinHarness.api.apiMutation(
        "POST",
        "/proposals/prop_1/attest",
        {
          decision: "approved",
          reason: "operation A",
        },
      ),
      second.window.FinHarness.api.apiMutation(
        "PATCH",
        "/proposals/prop_1/decision-scaffold",
        {
          reason: "operation B",
          decision_scaffold: {
            counter_evidence: "new evidence",
          },
        },
      ),
    ]);

  assert.notEqual(
    differentOperationKeys[0],
    differentOperationKeys[1],
    "different operations require different keys",
  );

  assert.equal(
    registry(first).attempts.length,
    2,
    "concurrent different operations must both survive",
  );

  await attestation.acknowledge();

  const afterOneClear = registry(first);
  assert.equal(
    afterOneClear.attempts.length,
    1,
    "clearing one attempt must preserve the other",
  );
  assert.equal(
    afterOneClear.attempts[0].idempotency_key,
    revision.idempotencyKey,
  );

  await revision.acknowledge();
  assert.equal(registry(first), null);

  // No Web Locks means no governed fetch.
  const noLocksStorage = createSharedStorage();
  const noLocks = apiContext({
    storage: noLocksStorage,
  });

  let noLocksFetchCalls = 0;
  noLocks.window.fetch = async (requestPath) => {
    if (requestPath === BINDING_ENDPOINT) {
      return bindingResponse(aliceBinding);
    }
    noLocksFetchCalls += 1;
    return response(
      "must_not_execute",
      aliceBinding.binding_id,
    );
  };

  await assert.rejects(
    noLocks.window.FinHarness.api.apiMutation(
      "POST",
      "/review",
      { reason: "no Web Locks" },
    ),
    (error) => {
      assert.equal(
        error.name,
        "MutationAttemptStorageError",
      );
      assert.match(
        error.message,
        /Web Locks support/,
      );
      return true;
    },
  );

  assert.equal(
    noLocksFetchCalls,
    0,
    "missing Web Locks must fail before fetch",
  );

  // A successful server mutation remains committed when
  // local acknowledgement cleanup fails.
  const cleanupStorage = createSharedStorage();
  const cleanupLocks = createSerialLockManager();
  const cleanup = apiContext({
    storage: cleanupStorage,
    lockManager: cleanupLocks,
  });

  cleanup.window.fetch = async (requestPath) =>
    requestPath === BINDING_ENDPOINT
      ? bindingResponse(aliceBinding)
      : response(
          "identity_cleanup_failure",
          aliceBinding.binding_id,
        );

  const committed =
    await cleanup.window.FinHarness.api.apiMutation(
      "POST",
      "/review",
      { reason: "cleanup failure" },
    );

  cleanupStorage.failNextRemove(
    new Error("simulated remove failure"),
  );

  await assert.rejects(
    committed.acknowledge(),
    (error) => {
      assert.equal(
        error.name,
        "MutationAcknowledgementError",
      );
      assert.equal(
        error.mutationCommitted,
        true,
      );
      assert.equal(
        error.attemptRetained,
        true,
      );
      assert.equal(
        error.identityReceiptId,
        "identity_cleanup_failure",
      );
      return true;
    },
  );

  assert.equal(
    registry(cleanup).attempts.length,
    1,
    "cleanup failure retains the safe replay key",
  );

  console.log(
    "mutation_registry_concurrency.test.cjs: " +
      "all assertions passed",
  );
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
