# ADR: Bind durable browser mutation attempts to current authentication

- Status: accepted
- Issue: #388
- Baseline: `main@2a3381056c0b01e2f5e1bc5fbaf64c084cb32c7d`
- Parent protocol: #383

## Context

The Cockpit persisted one logical mutation attempt under the origin's existing
`localStorage` owner and reused its `Idempotency-Key` after response loss or
reload. Its match key was only method, endpoint, and serialized body. A second
principal—or the same principal after a login/session rotation—could therefore
match an unresolved attempt created under an earlier authentication context.

The protected distinctions are:

```text
transport authentication
!= browser attempt reuse identity
!= domain authority
!= execution capability
```

The browser binding proves only that the current request and retained attempt
share one server-authenticated principal and bounded authentication epoch.
Every response continues to declare `capital_authority = null` and
`execution_allowed = false`.

## Reference-First decision

Adopt:

- [FastAPI dependencies](https://fastapi.tiangolo.com/tutorial/dependencies/)
  to inject the existing authenticated `OperatorContext`;
- [HTTP `Cache-Control: no-store`](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Cache-Control#no-store)
  for the current binding response;
- the existing same-origin
  [`localStorage`](https://developer.mozilla.org/en-US/docs/Web/API/Window/localStorage)
  physical owner, which persists across browser sessions;
- the existing origin-scoped exclusive
  [Web Locks API](https://developer.mozilla.org/en-US/docs/Web/API/Web_Locks_API)
  lifecycle;
- canonical JSON SHA-256 for a non-secret opaque binding ID;
- Playwright Chromium pages sharing one BrowserContext/origin for identity
  rotation and cross-tab acceptance.

Adapt:

- `OperatorContext` with optional server/provider-owned authentication epoch
  and expiry metadata;
- the existing keyed-mutation middleware with a pre-route, pre-body binding
  header check;
- the same browser registry key with a closed v2 logical schema;
- the existing claim/clear lifecycle with exact binding checks.

Own:

- the exact FinHarness binding fields and digest;
- mismatch, expiry, legacy, corruption, response-echo, and cleanup errors;
- the policy that an unresolved exact logical request cannot silently become a
  new operation under another authentication epoch.

Rejected:

- storing access tokens, cookies, or Authorization headers in local storage;
- deriving identity from request payload actor/attester fields;
- using principal ID alone as a session epoch;
- treating AuthorityGrant, CapitalMandate, or execution capability as
  authentication;
- adding a session database, identity registry, second attempt store, second
  idempotency protocol, IndexedDB, Service Worker, or BroadcastChannel.

## Decision

`OperatorContext` may carry `authentication_epoch_id` and
`authentication_expires_at_utc`. They are paired, server-derived, non-secret,
UTC, and deliberately absent from `receipt_binding()`. Existing non-browser
contexts remain valid without them, but cannot publish a reusable Cockpit
binding.

`GET /identity/browser-mutation-binding` returns a closed
`finharness.browser_mutation_identity_binding.v1` response with:

```text
principal + provider + kind + optional agent runtime
+ authentication method + epoch
→ canonical JSON SHA-256 binding_id
```

Expiry and server time are response constraints, not binding identity. The
endpoint is authenticated, accepts no caller identity fields, returns
`Cache-Control: no-store`, and echoes the binding ID in
`X-FinHarness-Browser-Mutation-Binding`.

Cockpit sends that header with its keyed mutation. When present, middleware
derives the current binding again and compares it before route matching,
capability lookup, body consumption, pending receipt creation, or handler
execution. The header remains a Cockpit transport guard: non-browser keyed
clients that omit it retain the existing #387 behavior.

The physical storage key remains
`finharness.cockpit.mutation-attempts.v1`; the logical schema becomes
`finharness.cockpit_mutation_attempts.v2`. New attempts bind the complete
non-secret identity fields. Exact request matches may reuse a key only under
the same unexpired binding. Principal, epoch, agent runtime, legacy, malformed,
corrupt, and ambiguous matches fail before mutation fetch and never mint a
replacement key.

Mutation responses echo the validated binding. Automatic cleanup requires:

```text
exact stored attempt
= key + logical request + binding

response binding
= attempt binding

fresh server binding at cleanup
= attempt binding
```

Failure retains recovery evidence. A committed response followed by identity
rotation is reported as recovery-required, not as a failed server write.

## Compatibility and rollback

The local compatibility provider uses the stable, non-secret epoch
`legacy-local:<operator-id>:browser-epoch-v1` with a finite expiry. It remains a
loopback/process compatibility adapter, not a production login session.

Legacy v1 and corrupt registries are not deleted, reset, upgraded, or assigned
to the current principal. They remain blocked and inspectable for #389.

Server rollback can remove the endpoint, optional fields, header guard, and
response echo without changing #387 capabilities, receipt v2, Proposal
reconciliation, or Authority. Browser rollback must retain a read-only v2
reader or require explicit operator handling; it must not reinterpret v2 as
unbound v1 or discard bindings.

## Non-goals

This ADR does not implement #385 response-loss-after-domain-commit acceptance,
#389 Pending Operations UI, a production OAuth/session framework, session
scoped idempotency for malicious custom API clients, domain authorization, or
execution capability.
