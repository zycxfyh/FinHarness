# Durable Write And API Mutation Semantics Mini-RFC

- Status: implemented
- Classification: C3
- Issue: #352
- Parent: #343

## Decision

FinHarness names two different local-write guarantees:

- `replace_atomic`: readers see either the old or new complete file, but a
  successful return does not claim survival across sudden power loss.
- `power_loss_durable`: file data is flushed before replace/link and the relevant
  directory entries are fsynced before success is returned, on filesystems and
  platforms that honor those primitives.

Existing `atomic_write_*` helpers retain replace-atomic compatibility. Critical
identity receipts use `durable_atomic_write_json`; the first API mutation claim
uses an exclusive durable link so concurrent requests cannot both own one key.

## Keyed mutation protocol

An authenticated non-read request may supply `Idempotency-Key` (8–128 safe ASCII
characters). The server derives an opaque receipt ID from authenticated principal,
agent runtime, method, route, and key; plaintext keys are not persisted. Before the
route runs, it durably records `pending` with a request-body hash. After the route
returns, it durably records `committed` or `rejected` plus the exact response body
and hash.

The transitions are:

```text
absent --durable exclusive claim--> pending --domain call--> committed/rejected
                                      |
                                      +--crash/write failure--> pending (ambiguous)
```

- A completed identical retry replays the bound response and does not call the
  route again.
- Reusing a key with different request bytes fails with 409 before the route.
- Retrying a pending key fails with `mutation_outcome_ambiguous`; it never guesses
  whether the domain transaction committed.
- Requests without a key remain compatible. Their post-response actor receipt is
  now power-loss durable, but they do not gain idempotency semantics.

This protocol is a mutation journal and actor binding, not a parallel capital or
decision truth store. Domain records and their receipts remain authoritative.

## Reconciliation

`task identity:reconcile -- RECEIPT` is read-only by default. After an operator
proves the domain effect exists, `--apply` requires operator identity, written
reason, and a verified response file, then closes the pending receipt as
`reconciled_applied`; future identical retries replay that response. If evidence
proves no effect occurred, the pending receipt remains as crash evidence and a new
key may be used only after that review. The tool never deletes ambiguous evidence.

## Failure and rollback

Failure to persist the initial pending claim prevents the domain route from
running. Failure after the domain commit leaves a detectable pending receipt and
blocks automatic retry. Reverting the middleware activation restores legacy API
behavior; existing identity receipts are append-only evidence and need no schema
migration. No identity receipt grants capital authority, release approval, or
execution authority.
