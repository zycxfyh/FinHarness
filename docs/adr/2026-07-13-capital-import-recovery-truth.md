# ADR: Capital import recovery truth boundary

- Date: 2026-07-13
- Status: accepted
- Issue: #263

## Context

Capital imports span immutable source/receipt artifacts, a readable receipt
file, and an atomic State Core mirror. A crash or manual filesystem/database
change can leave only part of that binding intact. Treating any one mirror as
sufficient would allow stale or unsupported capital rows to appear current.

## Decision

Artifact descriptors and content-addressed bytes remain evidence truth. The
receipt file, `ReceiptIndex`, `ImportBatch`, `ReceiptManifest`, and materialized
snapshot are separately verified bindings. Authoritative consumers must use the
fail-closed verified-batch result rather than infer trust from row existence.

Recovery is allowlisted: rebuild reconstructable indexes, restore a receipt file
from a valid artifact, replay an immutable receipt against its still-readable
source, and remove an orphan lookup row. Missing or corrupt evidence is never
fabricated. Applied recovery emits a new immutable recovery receipt and retains
prior artifacts and database history.

## Consequences

- DB rows remain queryable for audit but cannot become verified when their
  receipt binding is invalid.
- Receipts left before a DB commit can be replayed idempotently.
- Multi-file ledger replay still requires its original source path;
  reconstructing a ledger solely from bundled source evidence is a future
  contract extension.
- The upcoming authoritative resolver (#258) has one explicit admission helper.
