// FinHarness Cockpit — API helper namespace.

(() => {
"use strict";

const MUTATION_ATTEMPTS_STORAGE_KEY =
  "finharness.cockpit.mutation-attempts.v1";
const MUTATION_ATTEMPTS_SCHEMA =
  "finharness.cockpit_mutation_attempts.v2";
const LEGACY_MUTATION_ATTEMPTS_SCHEMA =
  "finharness.cockpit_mutation_attempts.v1";
const MUTATION_ATTEMPTS_LOCK_NAME =
  "finharness.cockpit.mutation-attempts.lock.v1";
const MUTATION_BINDING_ENDPOINT =
  "/identity/browser-mutation-binding";
const MUTATION_BINDING_HEADER =
  "X-FinHarness-Browser-Mutation-Binding";
const MUTATION_BINDING_SCHEMA =
  "finharness.browser_mutation_identity_binding.v1";
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

class MutationIdentityBindingError extends Error {
  constructor({
    reason,
    attempt = null,
    cause = null,
    mutationCommitted = false,
  }) {
    super(
      mutationCommitted
        ? "The server response requires identity-bound recovery; the local attempt was retained."
        : "The governed write requires identity-bound recovery before it can continue.",
    );
    this.name = "MutationIdentityBindingError";
    this.code = reason;
    this.reason = reason;
    this.cause = cause;
    this.attemptRetained = attempt !== null;
    this.recoveryRequired = true;
    this.mutationCommitted = mutationCommitted;
    this.executionAllowed = false;
    this.attemptSummary = attempt
      ? Object.freeze({
          method: attempt.method,
          endpoint: attempt.endpoint,
          created_at_utc:
            attempt.created_at_utc,
          principal_id:
            attempt.identity_binding &&
            attempt.identity_binding.principal_id,
          binding_status: reason,
        })
      : null;
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
    if (
      error instanceof MutationAttemptStorageError ||
      error instanceof MutationIdentityBindingError
    ) {
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

function hasExactKeys(value, expected) {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return false;
  }
  const actual = Object.keys(value).sort();
  const wanted = [...expected].sort();
  return (
    actual.length === wanted.length &&
    actual.every((key, index) => key === wanted[index])
  );
}

function isNonEmptyString(value) {
  return typeof value === "string" && value.trim().length > 0;
}

function utcTimestamp(value) {
  if (
    !isNonEmptyString(value) ||
    !/(?:Z|\+00:00)$/.test(value)
  ) {
    return null;
  }
  const milliseconds = Date.parse(value);
  return Number.isFinite(milliseconds)
    ? milliseconds
    : null;
}

function validIdentityBinding(binding) {
  return (
    hasExactKeys(binding, [
      "schema",
      "binding_id",
      "principal_id",
      "identity_provider_id",
      "principal_kind",
      "agent_runtime_id",
      "authentication_method",
      "authentication_epoch_id",
      "authentication_expires_at_utc",
    ]) &&
    binding.schema === MUTATION_BINDING_SCHEMA &&
    /^[0-9a-f]{64}$/.test(binding.binding_id) &&
    isNonEmptyString(binding.principal_id) &&
    isNonEmptyString(binding.identity_provider_id) &&
    ["human", "service", "legacy_unknown"].includes(
      binding.principal_kind,
    ) &&
    (binding.agent_runtime_id === null ||
      isNonEmptyString(binding.agent_runtime_id)) &&
    isNonEmptyString(binding.authentication_method) &&
    isNonEmptyString(binding.authentication_epoch_id) &&
    utcTimestamp(
      binding.authentication_expires_at_utc,
    ) !== null
  );
}

function validAttempt(attempt) {
  return (
    hasExactKeys(attempt, [
      "method",
      "endpoint",
      "body",
      "idempotency_key",
      "created_at_utc",
      "identity_binding",
    ]) &&
    ["POST", "PATCH"].includes(attempt.method) &&
    typeof attempt.endpoint === "string" &&
    typeof attempt.body === "string" &&
    typeof attempt.idempotency_key === "string" &&
    /^[A-Za-z0-9._:-]{8,128}$/.test(
      attempt.idempotency_key,
    ) &&
    utcTimestamp(attempt.created_at_utc) !== null &&
    validIdentityBinding(attempt.identity_binding)
  );
}

function validRegistryUniqueness(attempts) {
  const idempotencyKeys = new Set();
  const logicalRequests = new Set();
  for (const attempt of attempts) {
    if (idempotencyKeys.has(attempt.idempotency_key)) {
      return false;
    }
    idempotencyKeys.add(attempt.idempotency_key);

    const logicalRequest = JSON.stringify([
      attempt.method,
      attempt.endpoint,
      attempt.body,
    ]);
    if (logicalRequests.has(logicalRequest)) {
      return false;
    }
    logicalRequests.add(logicalRequest);
  }
  return true;
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
    throw new MutationIdentityBindingError({
      reason: "registry_corrupt",
      cause: error,
    });
  }

  if (
    parsed &&
    parsed.schema ===
      LEGACY_MUTATION_ATTEMPTS_SCHEMA
  ) {
    throw new MutationIdentityBindingError({
      reason: "legacy_unbound",
    });
  }
  if (
    !hasExactKeys(parsed, ["schema", "attempts"]) ||
    parsed.schema !== MUTATION_ATTEMPTS_SCHEMA ||
    !Array.isArray(parsed.attempts) ||
    parsed.attempts.length >
      MAX_PENDING_MUTATION_ATTEMPTS ||
    !parsed.attempts.every(validAttempt) ||
    !validRegistryUniqueness(parsed.attempts)
  ) {
    throw new MutationIdentityBindingError({
      reason: "registry_corrupt",
    });
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

function storedIdentityBinding(binding) {
  return {
    schema: binding.schema,
    binding_id: binding.binding_id,
    principal_id: binding.principal_id,
    identity_provider_id:
      binding.identity_provider_id,
    principal_kind: binding.principal_kind,
    agent_runtime_id: binding.agent_runtime_id,
    authentication_method:
      binding.authentication_method,
    authentication_epoch_id:
      binding.authentication_epoch_id,
    authentication_expires_at_utc:
      binding.authentication_expires_at_utc,
  };
}

function validateCurrentBindingResponse(
  response,
  body,
) {
  if (
    !hasExactKeys(body, [
      "schema",
      "binding_id",
      "principal_id",
      "identity_provider_id",
      "principal_kind",
      "agent_runtime_id",
      "authentication_method",
      "authentication_epoch_id",
      "authentication_expires_at_utc",
      "server_time_utc",
      "capital_authority",
      "execution_allowed",
    ]) ||
    body.capital_authority !== null ||
    body.execution_allowed !== false
  ) {
    throw new MutationIdentityBindingError({
      reason: "current_binding_unavailable",
    });
  }
  const binding = storedIdentityBinding(body);
  const serverTime = utcTimestamp(body.server_time_utc);
  const expiresAt = utcTimestamp(
    body.authentication_expires_at_utc,
  );
  const echoed = responseHeader(
    response,
    MUTATION_BINDING_HEADER,
  );
  if (
    !validIdentityBinding(binding) ||
    serverTime === null ||
    expiresAt === null ||
    serverTime >= expiresAt ||
    echoed !== binding.binding_id
  ) {
    throw new MutationIdentityBindingError({
      reason: "current_binding_unavailable",
    });
  }
  if (Date.now() >= expiresAt) {
    throw new MutationIdentityBindingError({
      reason: "current_binding_expired",
    });
  }
  return Object.freeze(binding);
}

async function resolveCurrentMutationIdentityBinding() {
  let response;
  try {
    response = await fetch(
      MUTATION_BINDING_ENDPOINT,
      {
        method: "GET",
        headers: {
          accept: "application/json",
        },
        credentials: "same-origin",
        cache: "no-store",
      },
    );
  } catch (error) {
    throw new MutationIdentityBindingError({
      reason: "current_binding_unavailable",
      cause: error,
    });
  }
  const body = await responseBody(response);
  if (!response.ok) {
    const code = responseDetailCode(body);
    throw new MutationIdentityBindingError({
      reason:
        code === "browser_mutation_binding_expired"
          ? "current_binding_expired"
          : "current_binding_unavailable",
    });
  }
  return validateCurrentBindingResponse(
    response,
    body,
  );
}

function logicalRequestMatches(
  attempt,
  method,
  endpoint,
  body,
) {
  return (
    attempt.method === method &&
    attempt.endpoint === endpoint &&
    attempt.body === body
  );
}

function requireSameAttemptBinding(
  attempt,
  currentBinding,
) {
  const attemptBinding =
    attempt.identity_binding;
  if (
    Date.now() >=
    utcTimestamp(
      attemptBinding.authentication_expires_at_utc,
    )
  ) {
    throw new MutationIdentityBindingError({
      reason: "attempt_binding_expired",
      attempt,
    });
  }
  const sameCanonicalIdentity =
    attemptBinding.schema ===
      currentBinding.schema &&
    attemptBinding.principal_id ===
      currentBinding.principal_id &&
    attemptBinding.identity_provider_id ===
      currentBinding.identity_provider_id &&
    attemptBinding.principal_kind ===
      currentBinding.principal_kind &&
    attemptBinding.agent_runtime_id ===
      currentBinding.agent_runtime_id &&
    attemptBinding.authentication_method ===
      currentBinding.authentication_method &&
    attemptBinding.authentication_epoch_id ===
      currentBinding.authentication_epoch_id;
  if (
    attemptBinding.binding_id ===
      currentBinding.binding_id &&
    sameCanonicalIdentity
  ) {
    return;
  }
  let reason = "attempt_binding_invalid";
  if (
    attemptBinding.principal_id !==
      currentBinding.principal_id ||
    attemptBinding.identity_provider_id !==
      currentBinding.identity_provider_id
  ) {
    reason = "principal_mismatch";
  } else if (
    attemptBinding.agent_runtime_id !==
    currentBinding.agent_runtime_id
  ) {
    reason = "agent_runtime_mismatch";
  } else if (
    attemptBinding.authentication_epoch_id !==
    currentBinding.authentication_epoch_id
  ) {
    reason = "session_epoch_mismatch";
  }
  throw new MutationIdentityBindingError({
    reason,
    attempt,
  });
}

async function beginMutationAttempt(
  method,
  endpoint,
  body,
  currentBinding,
) {
  return withMutationRegistryLock(() => {
    // Re-read inside the cross-context lock. A registry
    // snapshot obtained before the lock is never trusted.
    const registry = readMutationRegistry();

    const matches = registry.attempts.filter(
      (attempt) =>
        logicalRequestMatches(
          attempt,
          method,
          endpoint,
          body,
        ),
    );

    if (matches.length > 1) {
      throw new MutationIdentityBindingError({
        reason: "registry_ambiguous",
        attempt: matches[0],
      });
    }
    if (matches.length === 1) {
      requireSameAttemptBinding(
        matches[0],
        currentBinding,
      );
      return matches[0];
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
      identity_binding:
        storedIdentityBinding(currentBinding),
    };

    registry.attempts.push(attempt);

    // The attempt is durable before fetch is invoked,
    // while the same-origin cross-context lock is held.
    writeMutationRegistry(registry);
    return attempt;
  });
}

function sameStoredAttempt(candidate, attempt) {
  return (
    candidate.idempotency_key ===
      attempt.idempotency_key &&
    logicalRequestMatches(
      candidate,
      attempt.method,
      attempt.endpoint,
      attempt.body,
    ) &&
    candidate.created_at_utc ===
      attempt.created_at_utc &&
    JSON.stringify(candidate.identity_binding) ===
      JSON.stringify(attempt.identity_binding)
  );
}

async function clearMutationAttempt(
  attempt,
  responseBindingId,
) {
  if (
    responseBindingId !==
    attempt.identity_binding.binding_id
  ) {
    throw new MutationIdentityBindingError({
      reason: responseBindingId
        ? "response_binding_mismatch"
        : "response_binding_missing",
      attempt,
      mutationCommitted: true,
    });
  }
  const currentBinding =
    await resolveCurrentMutationIdentityBinding();
  try {
    requireSameAttemptBinding(
      attempt,
      currentBinding,
    );
  } catch (error) {
    throw new MutationIdentityBindingError({
      reason: "cleanup_binding_changed",
      attempt,
      cause: error,
      mutationCommitted: true,
    });
  }
  return withMutationRegistryLock(() => {
    // Re-read inside the lock so clearing one operation
    // cannot overwrite another context's newly persisted
    // operation.
    const registry = readMutationRegistry();

    const candidates = registry.attempts.filter(
      (candidate) =>
        candidate.idempotency_key ===
          attempt.idempotency_key &&
        candidate.identity_binding.binding_id ===
          attempt.identity_binding.binding_id,
    );
    if (
      candidates.length > 1 ||
      (candidates.length === 1 &&
        !sameStoredAttempt(candidates[0], attempt))
    ) {
      throw new MutationIdentityBindingError({
        reason: "registry_corrupt",
        attempt,
        mutationCommitted: true,
      });
    }
    registry.attempts = registry.attempts.filter(
      (candidate) =>
        !(
          candidate.idempotency_key ===
            attempt.idempotency_key &&
          candidate.identity_binding.binding_id ===
            attempt.identity_binding.binding_id
        ),
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
  const currentBinding =
    await resolveCurrentMutationIdentityBinding();
  const attempt = await beginMutationAttempt(
    normalizedMethod,
    path,
    bodyText,
    currentBinding,
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
        [MUTATION_BINDING_HEADER]:
          attempt.identity_binding.binding_id,
      },
      credentials: "same-origin",
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
  const responseBindingId = responseHeader(
    response,
    MUTATION_BINDING_HEADER,
  );
  if (
    responseBindingId !==
    attempt.identity_binding.binding_id
  ) {
    throw new MutationIdentityBindingError({
      reason: responseBindingId
        ? "response_binding_mismatch"
        : "response_binding_missing",
      attempt,
      mutationCommitted: response.ok,
    });
  }

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
        await clearMutationAttempt(
          attempt,
          responseBindingId,
        );
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
        await clearMutationAttempt(
          attempt,
          responseBindingId,
        );
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
  MutationIdentityBindingError,
  MutationAcknowledgementError,
  MutationTransportError,
  MUTATION_ATTEMPTS_STORAGE_KEY,
  MUTATION_ATTEMPTS_LOCK_NAME,
  MUTATION_BINDING_ENDPOINT,
  MUTATION_BINDING_HEADER,
  resolveCurrentMutationIdentityBinding,
  apiGet,
  apiMutation,
  apiPost,
  apiPatch,
});
})();
