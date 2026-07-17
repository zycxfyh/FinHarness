# ADR: Admit keyed mutations only through explicit route recovery capabilities

- Status: accepted
- Issue: #387
- Baseline: `main@9b2368224fd4a8eaa5c833ff984e9edc8d128efc`
- Parent protocol: #383

## Context

The authenticated keyed-mutation middleware previously claimed a durable
pending receipt before it knew whether the eventual FastAPI route had a safe
response-loss resolver. Only four Proposal routes had typed domain
reconciliation. Any other authenticated write could therefore commit a domain
effect and leave an ambiguous receipt that no route owner could resolve.

The protected distinction is:

```text
transport authentication
!= domain authority
!= route recovery capability
```

A capability says only how the keyed transport protocol can recover a response.
It never authorizes the domain mutation or execution.

## Reference-First decision

Adopt:

- FastAPI's effective `APIRoute` metadata as the route owner, including the
  included-router contexts introduced by FastAPI 0.137;
- Starlette route matching, method handling, URI-template path parameters, and
  route priority rather than a local path parser;
- Pydantic closed models with forbidden extra fields;
- the existing identity claim, locked terminal CAS, replay, and Proposal domain
  resolvers.

Primary references:

- [FastAPI path-operation metadata](https://fastapi.tiangolo.com/advanced/path-operation-advanced-configuration/)
- [FastAPI 0.137 router preservation release notes](https://fastapi.tiangolo.com/release-notes/#01370)
- [Starlette routing, parameters, methods, mounts, and priority](https://www.starlette.io/routing/)
- [Pydantic model extra-data policy](https://docs.pydantic.dev/latest/concepts/models/#extra-data)

Adapt:

- one JSON registry parsed into a closed model;
- a pre-body route-capability admission step;
- v2 identity and domain bindings;
- one capability-driven dispatcher plus a narrow historical v1 adapter;
- one audit over the actual runtime route graph.

Own:

- the three FinHarness recovery modes;
- which routes participate;
- resolver and domain ownership;
- request/response bounds;
- capability evidence and replay compatibility.

Rejected:

- OpenAPI as runtime admission truth, because it is a representation and can
  exclude internal routes;
- decorators, plugin systems, gateways, or policy engines, because the current
  boundary is a closed 29-route inventory;
- reusing the receipt-backed-write inventory, because DB/receipt durability is
  not response-loss recoverability;
- function-name, module-name, receipt-kind, or path-segment inference;
- adding resolvers merely to populate every mode.

## Decision

`config/keyed-mutation-route-capabilities.json` is the only registry data
owner. Runtime and audit parse the same file through
`keyed_mutation_capabilities.py`.

Every non-safe FastAPI route has exactly one entry:

```text
typed_domain_reconciliation
terminal_replay_only
keyed_mutation_prohibited
```

The initial inventory is:

```text
29 non-safe routes
4 typed Proposal routes
0 terminal-only routes
25 prohibited routes
```

The middleware order is:

```text
authenticate OperatorContext
→ match the effective FastAPI route
→ derive method and canonical template server-side
→ resolve the registry capability
→ reject missing/prohibited routes
→ only then read the bounded body
→ create a capability-bound pending receipt
→ invoke the handler
```

No route or method match preserves normal 404/405 behavior and creates no
receipt. An existing unregistered route and a prohibited route return distinct
typed denials before handler execution.

The four typed entries bind exactly:

```text
POST  /proposals
  → finharness.api.proposal_create.v1
POST  /proposals/{proposal_id}/attest
  → finharness.api.attestation_create.v1
PATCH /proposals/{proposal_id}/decision-scaffold
  → finharness.api.proposal_scaffold_revision.v1
POST  /proposals/{proposal_id}/review-events
  → finharness.api.review_event_create.v1
```

The registry's typed resolver IDs must equal the dispatcher's keys. There is no
unknown-resolver or path-guessing fallback.

## Evidence evolution

New receipts use `finharness.api_mutation_identity_receipt.v2`. The receipt
binds the entire capability record plus its canonical SHA-256. Capability
identity participates in the outer receipt integrity hash and same-request
comparison.

Proposal domain evidence uses
`finharness.api_domain_mutation_binding.v2` and repeats the capability ID,
digest, canonical path template, and resolver ID. Reconciliation requires exact
agreement among:

```text
identity receipt
= current registry
= domain receipt
= dispatcher
```

Recomputed attacker-controlled hashes do not make a changed capability current.

Historical v1 receipts are never rewritten. Terminal v1 receipts remain
readable and replayable without a capability claim. Pending v1 receipts can use
the old exact four-route parser only as a compatibility adapter. Unsupported v1
pending receipts remain blocked. Removal of the adapter requires an audited
absence or explicit migration of all remaining v1 pending receipts.

## Authority coordination

All Authority routes are initially `keyed_mutation_prohibited`. A keyed request
cannot create an identity receipt or an Authority effect. The same unkeyed
routes continue to apply #391's human administrator, current assertion,
assurance, server-owned reduction time, CAS, and kill-switch semantics.

## Consequences and rollback

Adding or deleting a non-safe APIRoute now requires an explicit registry
decision. Unknown fields, modes, identities, routes, bounds, and resolver drift
fail validation or architecture CI.

Rollback is a single-PR revert of the registry, loader, preflight, v2 binding,
dispatcher, tests, and documentation. Existing v2 receipts must remain
inspectable before rollback; reverting runtime readers without an explicit v2
compatibility plan is not safe.

## Non-goals

This ADR does not add Execution reconciliation, browser identity binding,
real-browser response-loss acceptance, pending-operation UX, stale-version CAS,
or a generic authorization/recovery framework.
