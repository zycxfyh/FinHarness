"use strict";

const BINDING_ENDPOINT =
  "/identity/browser-mutation-binding";
const BINDING_HEADER =
  "x-finharness-browser-mutation-binding";
const BINDING_SCHEMA =
  "finharness.browser_mutation_identity_binding.v1";

function mutationBinding({
  bindingId = "a".repeat(64),
  principalId = "principal:alice",
  epochId = "alice-session-1",
  agentRuntimeId = null,
  expiresAt = "2099-12-31T23:59:59+00:00",
} = {}) {
  return {
    schema: BINDING_SCHEMA,
    binding_id: bindingId,
    principal_id: principalId,
    identity_provider_id: "test-browser-provider",
    principal_kind: "human",
    agent_runtime_id: agentRuntimeId,
    authentication_method: "test_bearer",
    authentication_epoch_id: epochId,
    authentication_expires_at_utc: expiresAt,
    server_time_utc: "2026-07-17T00:00:00+00:00",
    capital_authority: null,
    execution_allowed: false,
  };
}

function responseHeaders({
  bindingId = null,
  receipt = null,
  replayed = false,
  traceId = "trace_frontend_test",
} = {}) {
  return {
    get(name) {
      const normalized = String(name).toLowerCase();
      if (normalized === BINDING_HEADER) return bindingId;
      if (normalized === "x-finharness-identity-receipt") {
        return receipt;
      }
      if (normalized === "x-finharness-idempotent-replay") {
        return replayed ? "true" : null;
      }
      if (normalized === "x-finharness-trace-id") {
        return traceId;
      }
      return null;
    },
  };
}

function bindingResponse(binding = mutationBinding()) {
  return {
    ok: true,
    status: 200,
    statusText: "OK",
    headers: responseHeaders({
      bindingId: binding.binding_id,
    }),
    json: async () => binding,
  };
}

module.exports = {
  BINDING_ENDPOINT,
  BINDING_HEADER,
  bindingResponse,
  mutationBinding,
  responseHeaders,
};
