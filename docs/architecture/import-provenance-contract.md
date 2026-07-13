# Import Provenance Contract

`ImportBatch` and `ReceiptManifest` are the W0 boundary between external capital
data and current State Core materialization. The manifest contract applies to
the FinHarness CSV and direct Beancount adapters; the same scalar/time validator
also protects the legacy broker-receipt projection until it migrates to this
manifest path.

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
the source artifact, typed record counts, completeness status, five-clock time
semantics, and structured findings. Full imports replace declared source-owned
domains; delta imports preserve omitted rows and apply explicit tombstones.

## Exact money, currency, and time

- Monetary source values must be decimal strings or `Decimal`; Python/JSON
  binary floats, non-finite values, and malformed decimals fail closed.
- Every monetary position or balance needs an explicit three-letter currency.
  A symbol, commodity, account name, or default currency is never used to infer
  one. Position currency remains in the snapshot projection until #260 adds the
  authoritative valuation schema.
- `effective_at_utc`, `observed_at_utc`, `valued_at_utc`, `ingested_at_utc`, and
  `recorded_at_utc` are distinct canonical UTC clocks. Naive timestamps and
  impossible ordering fail before materialization.
- A valuation more than 24 hours older than its observation is a `blocking`
  finding. Missing/unpriced or omitted source records are `partial` findings.
  `complete`, `partial`, and `blocked` are evidence states, not permission or
  execution states.
- Legacy `as_of_utc` inputs remain readable through an explicit
  `legacy_as_of_projection`/`legacy_time_projection` finding. They are never
  silently presented as fully specified current-state time.

Beancount loader errors abort the import. Operators cannot accidentally accept
a partial ledger merely because `beanquery` can return some rows.

Account and instrument equality is governed by the separate
[`canonical-capital-identities`](canonical-capital-identities.md) contract.
Source-native account IDs are namespaced; ticker symbols never become canonical
instrument IDs on their own. Missing type or venue evidence produces a blocking
`instrument_identity_unresolved` finding.

`ReceiptManifest` binds that batch to the immutable receipt artifact, receipt
hash, compatibility receipt path, snapshot, record counts, and the
`materialized` database state. A manifest row is never written for a failed
transaction.

`capital_import_recovery.audit_capital_imports()` verifies this binding across
the Artifact Store, receipt file, `ImportBatch`, `ReceiptManifest`,
`ReceiptIndex`, and materialized `Snapshot`. A batch is eligible for future
authoritative resolution only when `batch_is_verified()` resolves it from the
report's verified batch set. Missing or corrupt evidence therefore fails closed
even when queryable DB rows remain.

Deterministic recovery can rebuild the Artifact Store index, restore a receipt
file from its hash-valid immutable artifact, rebuild or remove lookup-only
`ReceiptIndex` rows, and replay an unmaterialized receipt while its original
source reference is readable. Every applied run emits both a human-readable
recovery file and an immutable recovery artifact.

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
  not fabricate historical source hashes or manifests. Migration v8 adds time
  and finding columns and labels existing batches `legacy_unknown` instead of
  inventing clocks or completeness.
- Migration v9 adds canonical identity tables and nullable account/position
  bindings. Existing rows remain unresolved; the migration does not hash legacy
  labels or symbols into invented identities.

The compatibility JSON receipt remains for existing operators. Its immutable
Artifact Store descriptor and bytes are the integrity authority for new imports.

Verification:

```bash
uv run python -m unittest tests.test_capital_import_contract tests.test_personal_finance tests.test_beancount_adapter tests.test_statecore_snapshot_ingest tests.test_statecore_store
```
