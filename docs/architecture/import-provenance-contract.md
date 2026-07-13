# Import Provenance Contract

`ImportBatch` and `ReceiptManifest` are the W0 boundary between external capital
data and current State Core materialization. The contract applies to both the
FinHarness CSV adapter and the direct Beancount adapter.

## Evidence and materialization

An import has two distinct layers:

1. The shared Artifact Store owns immutable source bytes and immutable receipt
   bytes. Its descriptors carry the content hashes and can be audited or rebuilt
   independently of SQLite.
2. State Core owns the query projection. It commits the `ImportBatch`, its one
   `ReceiptManifest`, the `ReceiptIndex`, and all imported records in one
   transaction. A production import snapshot or source-owned record cannot use
   the generic write/upsert helpers.

`ImportBatch` has a stable ID over source kind, logical source ID, content hash,
adapter version, and import schema version. It records `full` or `delta` coverage,
the source artifact, and typed record counts. Both current adapters declare
`full`; W0 defines but does not yet implement delta reconciliation.

`ReceiptManifest` binds that batch to the immutable receipt artifact, receipt
hash, compatibility receipt path, snapshot, record counts, and the
`materialized` database state. A manifest row is never written for a failed
transaction.

## Replay and failure behavior

- Re-importing identical content reuses the same evidence, batch, manifest, and
  receipt bytes.
- A crash after artifact persistence but before the SQLite commit leaves
  auditable evidence. Retrying resumes from those immutable artifacts and commits
  the same identities.
- Missing or changed artifact bytes fail closed before materialization.
- Changed source content creates a new batch and receipt; full-coverage source
  rows are reconciled in the same transaction.
- Receipts created before W0 remain readable and resolve explicitly as
  `legacy_unmanifested`. Migration v7 creates empty provenance tables and does
  not fabricate historical source hashes or manifests.

The compatibility JSON receipt remains for existing operators. Its immutable
Artifact Store descriptor and bytes are the integrity authority for new imports.

Verification:

```bash
uv run python -m unittest tests.test_personal_finance tests.test_beancount_adapter tests.test_statecore_store
```
