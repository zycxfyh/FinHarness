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

const apiSource = fs.readFileSync(
  path.resolve(__dirname, "..", "api.js"),
  "utf8",
);

function context({
  storage = createSharedStorage(),
  locks = createSerialLockManager(),
} = {}) {
  const dom = new JSDOM("", {
    runScripts: "outside-only",
    url: "https://cockpit.finharness.test/",
  });
  installSharedStorage(dom.window, storage);
  installWebLocks(dom.window, locks);
  dom.window.eval(apiSource);
  return dom;
}

function registry(dom) {
  const key =
    dom.window.FinHarness.api
      .MUTATION_ATTEMPTS_STORAGE_KEY;
  const raw = dom.window.localStorage.getItem(key);
  return raw ? JSON.parse(raw) : null;
}

function successfulMutation(binding, {
  headerBindingId = binding.binding_id,
} = {}) {
  return {
    ok: true,
    status: 200,
    statusText: "OK",
    headers: responseHeaders({
      bindingId: headerBindingId,
      receipt: "identity_mutation_388",
    }),
    json: async () => ({
      execution_allowed: false,
    }),
  };
}

function installDynamicFetch(dom, state) {
  dom.window.fetch = async (requestPath, options = {}) => {
    if (requestPath === BINDING_ENDPOINT) {
      state.bindingCalls += 1;
      if (state.bindingFailure) {
        throw new Error("binding endpoint unavailable");
      }
      return bindingResponse(state.currentBinding);
    }
    state.mutationCalls += 1;
    state.keys.push(options.headers["Idempotency-Key"]);
    state.lastMutationOptions = options;
    if (state.transportFailure) {
      throw new Error("retain before response");
    }
    return successfulMutation(state.currentBinding, {
      headerBindingId: state.responseBindingId,
    });
  };
}

async function retainAttempt(dom, state, endpoint, payload) {
  state.transportFailure = true;
  await assert.rejects(
    dom.window.FinHarness.api.apiMutation(
      "POST",
      endpoint,
      payload,
    ),
    (error) => error.name === "MutationTransportError",
  );
  state.transportFailure = false;
  return registry(dom).attempts[0];
}

(async () => {
  const endpoint = "/proposals/prop_388/review-events";
  const payload = {
    actor: "principal:alice",
    reason: "exact request",
  };
  const alice = mutationBinding();
  const bob = mutationBinding({
    bindingId: "b".repeat(64),
    principalId: "principal:bob",
    epochId: "bob-session-1",
  });
  const alice2 = mutationBinding({
    bindingId: "c".repeat(64),
    epochId: "alice-session-2",
  });

  // New attempts are durable and bound before mutation fetch; same epoch reloads reuse.
  const same = context();
  const sameState = {
    currentBinding: alice,
    bindingCalls: 0,
    mutationCalls: 0,
    keys: [],
  };
  installDynamicFetch(same, sameState);
  const retained = await retainAttempt(
    same,
    sameState,
    endpoint,
    payload,
  );
  assert.equal(
    retained.identity_binding.binding_id,
    alice.binding_id,
  );
  assert.equal(
    sameState.lastMutationOptions.headers[
      "X-FinHarness-Browser-Mutation-Binding"
    ],
    alice.binding_id,
  );
  const firstKey = retained.idempotency_key;
  same.window.eval(apiSource);
  installDynamicFetch(same, sameState);
  const replay = await same.window.FinHarness.api.apiMutation(
    "POST",
    endpoint,
    payload,
  );
  assert.equal(replay.idempotencyKey, firstKey);
  assert.equal(sameState.keys.at(-1), firstKey);

  // Alice's retained attempt cannot be reused or replaced by Bob.
  sameState.currentBinding = bob;
  const beforeBobFetches = sameState.mutationCalls;
  await assert.rejects(
    same.window.FinHarness.api.apiMutation(
      "POST",
      endpoint,
      payload,
    ),
    (error) => {
      assert.equal(error.name, "MutationIdentityBindingError");
      assert.equal(error.reason, "principal_mismatch");
      assert.equal(error.attemptRetained, true);
      assert.doesNotMatch(error.message, new RegExp(firstKey));
      return true;
    },
  );
  assert.equal(sameState.mutationCalls, beforeBobFetches);
  assert.equal(registry(same).attempts[0].idempotency_key, firstKey);

  // The same principal with a rotated authentication epoch also fails closed.
  sameState.currentBinding = alice2;
  await assert.rejects(
    same.window.FinHarness.api.apiMutation(
      "POST",
      endpoint,
      payload,
    ),
    (error) => error.reason === "session_epoch_mismatch",
  );
  assert.equal(sameState.mutationCalls, beforeBobFetches);

  // A copied binding id cannot conceal drift in the stored identity fields.
  const tampered = context();
  const tamperedState = {
    currentBinding: alice,
    bindingCalls: 0,
    mutationCalls: 0,
    keys: [],
  };
  installDynamicFetch(tampered, tamperedState);
  const tamperedAttempt = await retainAttempt(
    tampered,
    tamperedState,
    endpoint,
    payload,
  );
  const tamperedRegistry = registry(tampered);
  tamperedRegistry.attempts[0]
    .identity_binding
    .principal_id = "principal:bob";
  tampered.window.localStorage.setItem(
    tampered.window.FinHarness.api
      .MUTATION_ATTEMPTS_STORAGE_KEY,
    JSON.stringify(tamperedRegistry),
  );
  const beforeTampered = tamperedState.mutationCalls;
  await assert.rejects(
    tampered.window.FinHarness.api.apiMutation(
      "POST",
      endpoint,
      payload,
    ),
    (error) => {
      assert.equal(error.reason, "principal_mismatch");
      assert.equal(
        error.attemptSummary.principal_id,
        "principal:bob",
      );
      assert.equal(error.attemptRetained, true);
      assert.doesNotMatch(
        error.message,
        new RegExp(tamperedAttempt.idempotency_key),
      );
      return true;
    },
  );
  assert.equal(
    tamperedState.mutationCalls,
    beforeTampered,
  );

  // An expired stored binding is retained and never retried.
  const expiredRegistry = registry(same);
  expiredRegistry.attempts[0]
    .identity_binding
    .authentication_expires_at_utc =
      "2026-01-01T00:00:00+00:00";
  same.window.localStorage.setItem(
    same.window.FinHarness.api
      .MUTATION_ATTEMPTS_STORAGE_KEY,
    JSON.stringify(expiredRegistry),
  );
  sameState.currentBinding = alice;
  await assert.rejects(
    same.window.FinHarness.api.apiMutation(
      "POST",
      endpoint,
      payload,
    ),
    (error) => error.reason === "attempt_binding_expired",
  );

  // Legacy and corrupt owners remain inspectable and cannot be reset by a write.
  for (const [raw, reason] of [
    [
      JSON.stringify({
        schema:
          "finharness.cockpit_mutation_attempts.v1",
        attempts: [],
      }),
      "legacy_unbound",
    ],
    ["{not-json", "registry_corrupt"],
    [
      JSON.stringify({
        schema:
          "finharness.cockpit_mutation_attempts.v2",
        attempts: [],
        parallel_registry: [],
      }),
      "registry_corrupt",
    ],
  ]) {
    const blocked = context();
    const blockedState = {
      currentBinding: alice,
      bindingCalls: 0,
      mutationCalls: 0,
      keys: [],
    };
    installDynamicFetch(blocked, blockedState);
    const storageKey =
      blocked.window.FinHarness.api
        .MUTATION_ATTEMPTS_STORAGE_KEY;
    blocked.window.localStorage.setItem(storageKey, raw);
    await assert.rejects(
      blocked.window.FinHarness.api.apiMutation(
        "POST",
        endpoint,
        payload,
      ),
      (error) => error.reason === reason,
    );
    assert.equal(blockedState.mutationCalls, 0);
    assert.equal(
      blocked.window.localStorage.getItem(storageKey),
      raw,
    );
  }

  // Duplicate key or logical-request ownership corrupts the whole registry.
  // No entry is selected, deleted, or rewritten, including for unrelated writes.
  const duplicateFixtures = [
    {
      label: "same key, different logical request",
      attempts: [
        { ...retained },
        {
          ...retained,
          endpoint: "/proposals/prop_388/attest",
          body: JSON.stringify({ decision: "approved" }),
          created_at_utc: "2026-07-17T00:01:00.000Z",
        },
      ],
      request: {
        endpoint: "/proposals/prop_388/attest",
        payload: { decision: "approved" },
      },
    },
    {
      label: "different key, same logical request",
      attempts: [
        { ...retained },
        {
          ...retained,
          idempotency_key:
            "cockpit:duplicate-logical-request",
          created_at_utc: "2026-07-17T00:02:00.000Z",
        },
      ],
      request: { endpoint, payload },
    },
    {
      label: "unrelated request with duplicate elsewhere",
      attempts: [
        { ...retained },
        {
          ...retained,
          idempotency_key:
            "cockpit:duplicate-elsewhere",
          created_at_utc: "2026-07-17T00:03:00.000Z",
        },
      ],
      request: {
        endpoint:
          "/proposals/unrelated/review-events",
        payload: { decision: "defer" },
      },
    },
  ];
  for (const fixture of duplicateFixtures) {
    const corrupt = context();
    const corruptState = {
      currentBinding: alice,
      bindingCalls: 0,
      mutationCalls: 0,
      keys: [],
    };
    installDynamicFetch(corrupt, corruptState);
    const storageKey =
      corrupt.window.FinHarness.api
        .MUTATION_ATTEMPTS_STORAGE_KEY;
    const raw = JSON.stringify({
      schema:
        "finharness.cockpit_mutation_attempts.v2",
      attempts: fixture.attempts,
    });
    corrupt.window.localStorage.setItem(storageKey, raw);
    await assert.rejects(
      corrupt.window.FinHarness.api.apiMutation(
        "POST",
        fixture.request.endpoint,
        fixture.request.payload,
      ),
      (error) => {
        assert.equal(
          error.reason,
          "registry_corrupt",
          fixture.label,
        );
        return true;
      },
    );
    assert.equal(
      corruptState.mutationCalls,
      0,
      fixture.label,
    );
    assert.equal(
      corrupt.window.localStorage.getItem(storageKey),
      raw,
      fixture.label,
    );
  }

  // Missing/mismatched response echo preserves recovery evidence.
  for (const responseBindingId of [
    null,
    "d".repeat(64),
  ]) {
    const echo = context();
    const echoState = {
      currentBinding: alice,
      responseBindingId,
      bindingCalls: 0,
      mutationCalls: 0,
      keys: [],
    };
    installDynamicFetch(echo, echoState);
    await assert.rejects(
      echo.window.FinHarness.api.apiMutation(
        "POST",
        endpoint,
        payload,
      ),
      (error) => {
        assert.equal(
          error.reason,
          responseBindingId
            ? "response_binding_mismatch"
            : "response_binding_missing",
        );
        assert.equal(error.mutationCommitted, true);
        return true;
      },
    );
    assert.equal(registry(echo).attempts.length, 1);
  }

  // Identity rotation before acknowledgement cannot clear a committed attempt.
  const cleanup = context();
  const cleanupState = {
    currentBinding: alice,
    bindingCalls: 0,
    mutationCalls: 0,
    keys: [],
  };
  installDynamicFetch(cleanup, cleanupState);
  const committed =
    await cleanup.window.FinHarness.api.apiMutation(
      "POST",
      endpoint,
      payload,
    );
  cleanupState.currentBinding = bob;
  await assert.rejects(
    committed.acknowledge(),
    (error) => {
      assert.equal(error.name, "MutationAcknowledgementError");
      assert.equal(
        error.cause.reason,
        "cleanup_binding_changed",
      );
      assert.equal(error.mutationCommitted, true);
      return true;
    },
  );
  assert.equal(registry(cleanup).attempts.length, 1);

  // Current binding failure and duplicate exact requests both stop mutation fetch.
  const unavailable = context();
  const unavailableState = {
    currentBinding: alice,
    bindingFailure: true,
    bindingCalls: 0,
    mutationCalls: 0,
    keys: [],
  };
  installDynamicFetch(unavailable, unavailableState);
  await assert.rejects(
    unavailable.window.FinHarness.api.apiMutation(
      "POST",
      endpoint,
      payload,
    ),
    (error) => error.reason === "current_binding_unavailable",
  );
  assert.equal(unavailableState.mutationCalls, 0);

  const ambiguous = context();
  const ambiguousState = {
    currentBinding: alice,
    bindingCalls: 0,
    mutationCalls: 0,
    keys: [],
    transportFailure: false,
  };
  installDynamicFetch(ambiguous, ambiguousState);
  const ambiguousAttempt = await retainAttempt(
    ambiguous,
    ambiguousState,
    endpoint,
    payload,
  );
  const duplicated = registry(ambiguous);
  duplicated.attempts.push({
    ...ambiguousAttempt,
    idempotency_key: "cockpit:duplicate-safe-key",
  });
  ambiguous.window.localStorage.setItem(
    ambiguous.window.FinHarness.api
      .MUTATION_ATTEMPTS_STORAGE_KEY,
    JSON.stringify(duplicated),
  );
  const beforeAmbiguous = ambiguousState.mutationCalls;
  await assert.rejects(
    ambiguous.window.FinHarness.api.apiMutation(
      "POST",
      endpoint,
      payload,
    ),
    (error) => error.reason === "registry_corrupt",
  );
  assert.equal(
    ambiguousState.mutationCalls,
    beforeAmbiguous,
  );

  console.log(
    "mutation_identity_binding.test.cjs: all assertions passed",
  );
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
