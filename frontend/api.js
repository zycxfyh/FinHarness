// FinHarness Cockpit — API helper namespace.

(() => {
"use strict";

const MUTATION_ATTEMPTS_STORAGE_KEY =
  "finharness.cockpit.mutation-attempts.v1";
const MUTATION_ATTEMPTS_SCHEMA =
  "finharness.cockpit_mutation_attempts.v1";
const MUTATION_ATTEMPTS_LOCK_NAME =
  "finharness.cockpit.mutation-attempts.lock.v1";
const MAX_PENDING_MUTATION_ATTEMPTS = 128;

const RETAINED_MUTATION_CODES = new Set([
  "mutation_outcome_ambiguous",
  "idempotent_response_too_large",
  "invalid_idempotency_contract",
  "idempotency_key_reused_for_different_request",
]);

class ApiError extends Error {
  constructor({
    status,
    detail,
    traceId,
    identityReceiptId = null,
    idempotencyKey = null,
    attemptRetained = false,
  }) {
    const message =
      typeof detail === "string"
        ? detail
        : JSON.stringify(detail || "Request failed");
    super(
      `${status} ${message} ` +
        `(trace: ${traceId || "unavailable"})`,
    );
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
    this.traceId = traceId || null;
    this.identityReceiptId = identityReceiptId;
    this.idempotencyKey = idempotencyKey;
    this.attemptRetained = attemptRetained;
  }
}

class MutationAttemptStorageError extends Error {
  constructor(message, cause = null) {
    super(message);
    this.name = "MutationAttemptStorageError";
    this.cause = cause;
    this.executionAllowed = false;
  }
}

class MutationAcknowledgementError extends Error {
  constructor({
    cause,
    body,
    idempotencyKey,
    identityReceiptId,
  }) {
    super(
      "The governed write was saved, but its local retry " +
        "state could not be cleared.",
    );
    this.name = "MutationAcknowledgementError";
    this.cause = cause;
    this.body = body;
    this.idempotencyKey = idempotencyKey;
    this.identityReceiptId = identityReceiptId;
    this.mutationCommitted = true;
    this.attemptRetained = true;
    this.executionAllowed = false;
  }
}

class MutationTransportError extends Error {
  constructor({ cause, idempotencyKey }) {
    super(
      "Governed write transport failed; the durable client " +
        "attempt was retained for a safe retry.",
    );
    this.name = "MutationTransportError";
    this.cause = cause;
    this.idempotencyKey = idempotencyKey;
    this.attemptRetained = true;
    this.executionAllowed = false;
  }
}

async function responseBody(response) {
  return response.json().catch(() => ({}));
}

function responseHeader(response, name) {
  if (
    !response ||
    !response.headers ||
    typeof response.headers.get !== "function"
  ) {
    return null;
  }
  return response.headers.get(name);
}

function responseDetailCode(body) {
  if (
    body &&
    typeof body === "object" &&
    body.detail &&
    typeof body.detail === "object"
  ) {
    return body.detail.code || null;
  }
  return null;
}

function apiError(
  response,
  body,
  {
    idempotencyKey = null,
    attemptRetained = false,
  } = {},
) {
  return new ApiError({
    status: response.status,
    detail: body.detail || response.statusText,
    traceId: responseHeader(
      response,
      "x-finharness-trace-id",
    ),
    identityReceiptId: responseHeader(
      response,
      "x-finharness-identity-receipt",
    ),
    idempotencyKey,
    attemptRetained,
  });
}

function mutationStorage() {
  try {
    const storage = window.localStorage;
    if (!storage) {
      throw new Error("localStorage is unavailable");
    }
    return storage;
  } catch (error) {
    throw new MutationAttemptStorageError(
      "Governed writes require persistent local mutation storage.",
      error,
    );
  }
}

async function withMutationRegistryLock(operation) {
  const lockManager =
    window.navigator &&
    window.navigator.locks;

  if (
    !lockManager ||
    typeof lockManager.request !== "function"
  ) {
    throw new MutationAttemptStorageError(
      "Governed writes require Web Locks support " +
        "for cross-context mutation serialization.",
    );
  }

  try {
    return await lockManager.request(
      MUTATION_ATTEMPTS_LOCK_NAME,
      { mode: "exclusive" },
      async () => operation(),
    );
  } catch (error) {
    if (error instanceof MutationAttemptStorageError) {
      throw error;
    }

    throw new MutationAttemptStorageError(
      "Could not serialize the persistent " +
        "mutation-attempt lifecycle.",
      error,
    );
  }
}

function emptyMutationRegistry() {
  return {
    schema: MUTATION_ATTEMPTS_SCHEMA,
    attempts: [],
  };
}

function validAttempt(attempt) {
  return (
    attempt &&
    typeof attempt === "object" &&
    ["POST", "PATCH"].includes(attempt.method) &&
    typeof attempt.endpoint === "string" &&
    typeof attempt.body === "string" &&
    typeof attempt.idempotency_key === "string" &&
    /^[A-Za-z0-9._:-]{8,128}$/.test(
      attempt.idempotency_key,
    ) &&
    typeof attempt.created_at_utc === "string"
  );
}

function readMutationRegistry() {
  const storage = mutationStorage();
  let raw;

  try {
    raw = storage.getItem(
      MUTATION_ATTEMPTS_STORAGE_KEY,
    );
  } catch (error) {
    throw new MutationAttemptStorageError(
      "Could not read persistent mutation attempts.",
      error,
    );
  }

  if (raw === null) {
    return emptyMutationRegistry();
  }

  let parsed;
  try {
    parsed = JSON.parse(raw);
  } catch (error) {
    throw new MutationAttemptStorageError(
      "Persistent mutation-attempt state is unreadable.",
      error,
    );
  }

  if (
    !parsed ||
    parsed.schema !== MUTATION_ATTEMPTS_SCHEMA ||
    !Array.isArray(parsed.attempts) ||
    !parsed.attempts.every(validAttempt)
  ) {
    throw new MutationAttemptStorageError(
      "Persistent mutation-attempt state has an invalid contract.",
    );
  }

  return parsed;
}

function writeMutationRegistry(registry) {
  const storage = mutationStorage();

  try {
    if (registry.attempts.length === 0) {
      storage.removeItem(
        MUTATION_ATTEMPTS_STORAGE_KEY,
      );
      return;
    }
    storage.setItem(
      MUTATION_ATTEMPTS_STORAGE_KEY,
      JSON.stringify(registry),
    );
  } catch (error) {
    throw new MutationAttemptStorageError(
      "Could not persist the mutation-attempt lifecycle.",
      error,
    );
  }
}

function mutationRequestBody(payload) {
  const body = JSON.stringify(payload);
  if (typeof body !== "string") {
    throw new TypeError(
      "Governed mutation payload must be JSON serializable.",
    );
  }
  return body;
}

function newIdempotencyKey() {
  if (
    window.crypto &&
    typeof window.crypto.randomUUID === "function"
  ) {
    return `cockpit:${window.crypto.randomUUID()}`;
  }

  const time = Date.now().toString(36);
  const random = Math.random()
    .toString(36)
    .slice(2, 14);
  return `cockpit:${time}:${random}`;
}

async function beginMutationAttempt(
  method,
  endpoint,
  body,
) {
  return withMutationRegistryLock(() => {
    // Re-read inside the cross-context lock. A registry
    // snapshot obtained before the lock is never trusted.
    const registry = readMutationRegistry();

    const existing = registry.attempts.find(
      (attempt) =>
        attempt.method === method &&
        attempt.endpoint === endpoint &&
        attempt.body === body,
    );

    if (existing) {
      return existing;
    }

    if (
      registry.attempts.length >=
      MAX_PENDING_MUTATION_ATTEMPTS
    ) {
      throw new MutationAttemptStorageError(
        "Too many unresolved governed mutation attempts; " +
          "operator reconciliation is required.",
      );
    }

    const attempt = {
      method,
      endpoint,
      body,
      idempotency_key: newIdempotencyKey(),
      created_at_utc: new Date().toISOString(),
    };

    registry.attempts.push(attempt);

    // The attempt is durable before fetch is invoked,
    // while the same-origin cross-context lock is held.
    writeMutationRegistry(registry);
    return attempt;
  });
}

async function clearMutationAttempt(attempt) {
  return withMutationRegistryLock(() => {
    // Re-read inside the lock so clearing one operation
    // cannot overwrite another context's newly persisted
    // operation.
    const registry = readMutationRegistry();

    registry.attempts = registry.attempts.filter(
      (candidate) =>
        candidate.idempotency_key !==
        attempt.idempotency_key,
    );

    writeMutationRegistry(registry);
  });
}

function shouldRetainMutationAttempt(
  response,
  body,
) {
  const code = responseDetailCode(body);
  if (code && RETAINED_MUTATION_CODES.has(code)) {
    return true;
  }

  // A protocol receipt header proves the response travelled
  // through the keyed middleware. Unless its typed code says
  // "ambiguous", that HTTP result is terminal.
  if (
    responseHeader(
      response,
      "x-finharness-identity-receipt",
    )
  ) {
    return false;
  }

  const status = Number(response.status || 0);
  return (
    [408, 409, 425, 429].includes(status) ||
    status >= 500
  );
}

async function apiGet(path) {
  const response = await fetch(path, {
    headers: { accept: "application/json" },
  });
  const body = await responseBody(response);
  if (!response.ok) {
    throw apiError(response, body);
  }
  return body;
}

async function apiMutation(
  method,
  path,
  payload,
) {
  const normalizedMethod = String(method).toUpperCase();
  if (
    !["POST", "PATCH"].includes(normalizedMethod)
  ) {
    throw new Error(
      `Unsupported governed write method: ${normalizedMethod}`,
    );
  }

  const bodyText = mutationRequestBody(payload);
  const attempt = await beginMutationAttempt(
    normalizedMethod,
    path,
    bodyText,
  );

  let response;
  try {
    response = await fetch(path, {
      method: normalizedMethod,
      headers: {
        accept: "application/json",
        "content-type": "application/json",
        "Idempotency-Key":
          attempt.idempotency_key,
      },
      body: bodyText,
    });
  } catch (error) {
    throw new MutationTransportError({
      cause: error,
      idempotencyKey:
        attempt.idempotency_key,
    });
  }

  const body = await responseBody(response);

  if (!response.ok) {
    const terminalResponse =
      !shouldRetainMutationAttempt(
        response,
        body,
      );

    let attemptRetained = !terminalResponse;
    let cleanupError = null;

    if (terminalResponse) {
      try {
        await clearMutationAttempt(attempt);
      } catch (error) {
        // The server result remains terminal. Retaining the
        // attempt is safe because a later retry replays the
        // same terminal response under the same key.
        attemptRetained = true;
        cleanupError = error;
      }
    }

    const error = apiError(response, body, {
      idempotencyKey:
        attempt.idempotency_key,
      attemptRetained,
    });
    error.mutationTerminal = terminalResponse;
    error.cleanupError = cleanupError;
    throw error;
  }

  let acknowledged = false;
  return Object.freeze({
    body,
    idempotencyKey:
      attempt.idempotency_key,
    identityReceiptId: responseHeader(
      response,
      "x-finharness-identity-receipt",
    ),
    replayed:
      responseHeader(
        response,
        "x-finharness-idempotent-replay",
      ) === "true",

    // The action shell calls this only after validating
    // the governed response contract.
    async acknowledge() {
      if (acknowledged) {
        return;
      }

      try {
        await clearMutationAttempt(attempt);
      } catch (error) {
        throw new MutationAcknowledgementError({
          cause: error,
          body,
          idempotencyKey:
            attempt.idempotency_key,
          identityReceiptId: responseHeader(
            response,
            "x-finharness-identity-receipt",
          ),
        });
      }

      acknowledged = true;
    },
  });
}

function apiPost(path, payload) {
  return apiMutation("POST", path, payload);
}

function apiPatch(path, payload) {
  return apiMutation("PATCH", path, payload);
}

window.FinHarness =
  window.FinHarness || {};
window.FinHarness.api = Object.freeze({
  ApiError,
  MutationAttemptStorageError,
  MutationAcknowledgementError,
  MutationTransportError,
  MUTATION_ATTEMPTS_STORAGE_KEY,
  MUTATION_ATTEMPTS_LOCK_NAME,
  apiGet,
  apiMutation,
  apiPost,
  apiPatch,
});
})();
