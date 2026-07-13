# Capital Imports

## Purpose

Turn immutable source evidence into replayable, queryable capital state without
silently confusing source changes, repairs, or deletions.

## Current Responsibilities

- bind source bytes, `ImportBatch`, receipt artifact, `ReceiptManifest`, and
  State Core materialization in one validated envelope;
- declare `full` or `delta` coverage and the domains covered by the import;
- retain correction lineage with `supersedes_batch_id` and a required reason;
- retain append-only `ImportTombstone` evidence for rows missing from a full
  import and rows explicitly deleted by a delta import;
- make repeated materialization of the same batch deterministic;
- audit receipt artifacts, receipt files, manifests, indexes, and materialized
  snapshots as one consistency boundary;
- fail closed for unverified batches and apply only deterministic repairs with
  a new immutable recovery receipt;
- expose unsupported corporate-action interpretation as a typed data gap.

## Non-goals

- interpreting splits, mergers, symbol changes, spin-offs, or other corporate
  actions;
- replacing the upstream ledger, broker, or accounting system;
- granting proposal, approval, or execution authority.

## Typed Inputs

Immutable source bytes and hash, source identity, adapter/schema version,
coverage mode, covered domains, exact record counts, canonical clocks,
completeness findings, optional correction lineage, and explicit delta
deletions.

## Typed Outputs

`ImportBatch`, `ReceiptManifest`, `ImportTombstone`, immutable artifacts,
receipt index, historical snapshots, and source-owned current-state rows.

## Important Files

- `src/finharness/import_provenance.py`
- `src/finharness/statecore/import_models.py`
- `src/finharness/statecore/store.py`
- `src/finharness/personal_finance.py`
- `src/finharness/beancount_adapter.py`
- `src/finharness/statecore/diff.py`
- `src/finharness/capital_import_recovery.py`
- `scripts/reconcile_capital_imports.py`

## Mature Wheels / External Systems

Beancount and `beanquery` own ledger parsing and balance mechanics. FinHarness
owns only the import contract, evidence binding, governed materialization, and
diff classification.

## Quality, Lineage, and Receipt Strategy

A batch is content-addressed together with its coverage and correction
contract. Full imports replace only their declared source-owned domains; delta
imports merge supplied rows and carry omitted positions from the prior
materialized snapshot. Explicit tombstones remove named source-owned rows while
historical rows and prior batches remain queryable. Receipt payloads repeat the
coverage, correction, completeness, clocks, findings, and corporate-action gap
fields validated by the database envelope.

Snapshot diffs classify changes as `transaction_like`, `price_fx`, `deletion`,
or `correction`. These are descriptive causes, not execution authorization.

Artifact Store descriptors and bytes remain evidence truth. The receipt file,
`ReceiptIndex`, manifest binding, and materialized snapshot are audited mirrors.
`batch_is_verified()` admits a batch only when its complete cross-store binding
is intact. Recovery may rebuild reconstructable indexes, restore a receipt file
from its valid artifact, replay a receipt whose source is still available, or
remove an orphan lookup row; it never invents missing bytes.

## Upgrade Log

- 2026-07-13: added cross-store audit classifications, fail-closed batch
  admission, deterministic replay/repair, stale-index cleanup, crash recovery,
  and immutable recovery receipts for issue #263.
- 2026-07-13: added full/delta materialization semantics, covered domains,
  correction/supersession lineage, append-only tombstones, deterministic delta
  replay, cause-classified diffs, and explicit unsupported corporate-action
  gaps for issue #265.

## Open Risks

- Corporate actions are disclosed but not interpreted.
- Delta deletion callers must name the prior record identity explicitly.
- Replay currently requires the receipt's original `source_ref` to remain
  readable; source-artifact-only reconstruction for multi-file ledgers remains
  an explicit gap.

## Next Upgrades

- Publish verified current/as-of capital projections (#258 and #261).
