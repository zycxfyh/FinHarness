# Durable Write And API Mutation Semantics Mini-RFC

- Status: implemented on PR #384; merge-gated by exact-head CI and C3 review
- Hardening issue: #383
- Original issue: #352
- Parent: #343

## Decision

FinHarness names two different local-write guarantees:

- `replace_atomic`: readers see either the old or new complete file, but a
  successful return does not claim survival across sudden power loss.
- `power_loss_durable`: file data is flushed before replace or link and the
  relevant directory entries are fsynced before success is returned, on
  filesystems and platforms that honor those primitives.

Existing `atomic_write_*` helpers retain replace-atomic compatibility. Critical
identity receipts use durable writes. The first API mutation claim uses an
exclusive durable link so concurrent requests cannot both own one key.

## Keyed mutation protocol

An authenticated non-read request may supply `Idempotency-Key` using 8–128
characters from the permitted ASCII set. Plaintext keys are not persisted.

The request identity binds:

- authenticated principal and optional agent runtime;
- HTTP method;
- canonical route path and raw query string;
- approved semantic headers, currently `Content-Type` and `If-Match`;
- request-body SHA-256.

Keyed request and response buffering each have a 1 MiB hard limit. An oversized
request fails before the route and creates no identity receipt. An oversized
response cannot be journaled as terminal truth; the receipt remains `pending`
and automatic retry is blocked.

Before the route runs, the server durably records `pending`. After the route
returns, it records `committed` or `rejected` with the exact response body,
content type, status code, and response hash.

All `pending -> terminal` transitions use one cross-process lock and
compare-and-swap protocol. The writer must match both the expected state and
the expected content hash. Terminal receipts preserve
`previous_content_sha256` lineage.

The state transitions are:

```text
absent
  |
  +-- durable exclusive claim --> pending
                                    |
                                    +-- route + durable completion --> committed
                                    |
                                    +-- route rejection -----------> rejected
                                    |
                                    +-- verified typed recovery ---> reconciled_applied
                                    |
                                    +-- crash/write failure --------> pending
```

Protocol behavior:

- A terminal identical retry replays the bound response and does not invoke the
  route again.
- Reusing a key with a different canonical target, semantic header, actor, or
  request body fails before the route.
- Retrying a `pending` key returns `mutation_outcome_ambiguous`; it never
  guesses whether the domain transaction committed.
- Requests without a key retain ordinary non-idempotent request semantics.
  Their post-response actor receipt may still be durable, but they do not gain
  keyed replay guarantees.

This protocol is a mutation journal and actor binding. It is not a parallel
capital, proposal, decision, or execution truth store. Domain records and
their domain receipts remain authoritative.

## Typed reconciliation

`task identity:reconcile -- RECEIPT` is read-only by default.

Applying reconciliation requires:

```text
--apply
--reconciled-by ACTOR
--reason TEXT
[--state-core-db PATH]
[--receipt-root PATH]
```

The operator cannot provide:

- a response file or response bytes;
- an HTTP status code;
- a response content type.

A route-specific resolver must derive the outcome from verified domain truth.
The currently implemented resolver covers keyed `POST /proposals`.

It verifies:

1. the mutation receipt is still `pending`;
2. the route is supported by the resolver;
3. the deterministic Proposal row exists;
4. the Proposal is bound to the mutation receipt through its source reference;
5. the domain receipt resolves inside the configured receipt root;
6. the domain receipt is a Proposal receipt;
7. the database row and receipt Proposal payload agree;
8. the Proposal content hash agrees;
9. the revision context binds the mutation receipt ID and request-body hash.

Only after those checks does the route reconstruct the canonical
`ProposalCreateResponse`. The terminal writer records the resolver ID,
evidence references, domain effect, and
`response_source=canonical_route_reconstruction`, then performs the same
locked CAS transition to `reconciled_applied`.

Unsupported routes, missing effects, unreadable receipts, path escapes,
mismatched rows, invalid hashes, stale operator views, or inconsistent mutation
bindings fail closed. The pending receipt remains unchanged.

## Cockpit mutation-attempt lifecycle

Governed Cockpit writes pass through `ReviewActionShell`.

For one logical operation, the Cockpit:

1. serializes the method, endpoint, and payload;
2. creates or recovers a matching unresolved mutation attempt;
3. persists the attempt in `localStorage` before calling `fetch`;
4. sends its stable `Idempotency-Key`;
5. retains the attempt after transport loss, ambiguous outcomes, or an invalid
   governed response contract;
6. reuses the same key after page reload for the same unresolved operation;
7. removes the attempt only after a terminal response has passed the
   `execution_allowed=false` boundary check.

After terminal acknowledgement, a later user action is a new logical operation
and receives a new key. If durable browser storage is unavailable or corrupt,
the Cockpit fails before sending the write rather than degrading to an
unrecoverable temporary key.

## Recovery evidence

The acceptance suite proves:

- committed replay survives application and SQLite reconstruction;
- a domain effect with a lost terminal response remains blocked after restart;
- typed reconciliation survives a second restart and still replays exactly one
  Proposal;
- cross-process terminal writers have exactly one winner;
- stale reconciliation cannot overwrite committed truth;
- false or incomplete reconciliation evidence leaves the receipt pending;
- a real Cockpit attempt retains and reuses its key across simulated response
  loss and reload.

## Failure and rollback

Failure to persist the initial pending claim prevents the domain route from
running. Failure after the domain commit leaves a detectable pending receipt
and blocks automatic retry.

No identity receipt, replay result, reconciliation record, or Cockpit
idempotency key grants capital authority, decision approval, release approval,
broker authority, or execution authority.
