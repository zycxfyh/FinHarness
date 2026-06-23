# Debt Cleanup Plan (post B0 cockpit + Decimal slice)

Status: draft
Date: 2026-06-19
Scope: sequence and clear the debts identified while reviewing and extending the
B0 cockpit slice (cockpit BFF, personal-finance adapters, Decimal migration).

This is a planning + execution artifact. It does not authorize live trading,
broker writes, ceiling increases, or compliance claims. Adopt mature tools
before building; only build the thin local glue.

## A / B / C / R

A: The slice shipped a product BFF, two read-only personal-finance adapters
(`bean-query` + FinHarness-contract CSV), and a money→`Decimal` migration. Review
plus runtime probes found one correctness regression and several smaller debts.

B: Clear the debts in correctness-first order, each behind `task check`, each with
a regression test, adopting mature tools where they materially reduce risk and
keeping local code as thin glue.

C: Use this document as the execution order. Mark each item done with evidence as
it lands. Larger adopt decisions (OpenTelemetry, browser E2E) stay gated until the
small/correctness debts are clear.

R: Evidence gathered by runtime probes (see each item) and `task check`.

## Debt Inventory (prioritised)

### Tier 1 — correctness (blocking)

**D1. Decimal corruption on pre-existing databases.**
- Problem: `DecimalText` stores `str(value)` as TEXT, but `ensure_state_core_schema`
  (`create_all`) does not alter existing tables. On a database created before this
  slice, `positions`/liability money columns keep REAL affinity, so SQLite coerces
  the written text back to REAL and reads return a float; `Decimal(float)` then
  yields a corrupted long value.
- Evidence (probe): on a REAL-affinity `positions` table, `market_value=Decimal("0.1")`
  reads back as `Decimal('0.1000000000000000055511151231257827021181583404541015625')`,
  and `0.1 + 0.2 != 0.3`. Raw `typeof(market_value)` is `real`.
- Fix:
  - D1a (immediate, defensive): `DecimalText.process_result_value` normalises any
    driver return (str/float/int) via `Decimal(str(value))`, so reads are clean even
    on legacy REAL columns. Add a regression test that simulates a REAL-affinity table.
  - D1b (proper): add an idempotent migration path that rebuilds money columns as
    TEXT, casting existing values to canonical decimal strings. For a single local
    SQLite file, native `PRAGMA user_version` migration is sufficient now; adopt
    Alembic later if migration count or deployment topology grows.

### Tier 2 — data integrity / adapter fidelity

**D2. Stale accumulation on re-import.** Re-importing an export/ledger that dropped a
liability/goal leaves the old row; counts drift. Add source-scoped reconciliation
(replace the rows owned by a given source/snapshot lineage) instead of pure upsert.

**D3. bean-query `include` hashing.** `_file_hash` only hashes the top `.bean` file.
Hash the full set of files beancount actually loaded (it reports them) so a change in
an included file changes the snapshot id / receipt.

**D4. bean-query unpriced commodities.** When a commodity has no `price`, `value()`
returns the units in the commodity currency; the adapter currently stores that count
as money. Detect when the value currency is not a money currency and record a data gap
(market value omitted), rather than presenting units as market value.

### Tier 3 — scaling / polish

**D5. In-memory timeline/brief.** `/timeline` (and the brief lookup) load whole tables
then slice in Python. Push ordering and `limit` into SQL per source, then merge.

**D6. "Read-only cockpit" wording.** The cockpit can POST attestations (governed,
non-execution). Tighten docs/labels to "read + attest", keeping the non-claims.

### Tier 4 — larger adopt decisions (gated)

**D7. OpenTelemetry traces/metrics.** D7a standardizes the local trace context and
trace-to-receipt index; D7b adds a local-only OTel SDK provider. External exporter
or telemetry upload remains gated on explicit C3 approval.

**D8. Browser E2E / visual regression for the cockpit.** Needs a tooling decision
(e.g. Playwright). New tooling — needs a go-ahead.

## Execution Order

1. D1a → D1b (correctness; D1a unblocks immediately, D1b makes storage exact).
2. D2, D3, D4 (adapter/data fidelity).
3. D5, D6 (scaling/polish).
4. D7, D8 only after explicit approval (new deps/tooling).

Each item: implement → add/adjust a regression test → `task check` green → update docs.

## Non-Claims

- This plan does not prove investment, tax, accounting correctness, or production
  readiness.
- SQLite-native migration is not a replacement for a reviewed production migration
  process if FinHarness later grows beyond a local single-user database.

## Progress Log

- DONE D1a — `DecimalText.process_result_value` normalises any driver return via
  `Decimal(str(value))`; regression test reads a legacy REAL-affinity table back
  as clean Decimals. (`task check` green, 432 tests.)
- DONE D1b — `PRAGMA user_version` migration (`migrate_state_core`, run from
  `ensure_state_core_schema` + `task db:migrate`) rebuilds legacy `positions`
  REAL money columns as TEXT with Python `str()` conversion; idempotent; regression
  test covers it. Chose SQLite-native versioning over Alembic for this single-file
  tool (see chat rationale). (`task check` green, 432 tests.)
- DONE D2 — added a `SourcedStateCoreBase` with a `source` column (migration #2,
  native `ALTER TABLE ADD COLUMN`) to the six personal-finance tables; both adapters
  now call `replace_source_records`, which deletes the import's prior `source` rows
  before upserting, so a re-import drops rows removed upstream. Positions/snapshots
  still accumulate as history. Regression test re-imports without a liability and
  asserts it is gone. (`task check` green, 433 tests.)
- DONE D3 — the beancount content hash now covers every file beancount loads
  (`options_map["include"]`), not just the top `.bean`; the receipt records the
  file set. A change in an included file changes the snapshot/receipt id (test).
  (`task check` green, 435 tests.)
- DONE D4 — unpriced beancount holdings (value currency == commodity, not an
  operating currency) are no longer stored as money: quantity is kept, market
  value is 0, and the symbol is disclosed under `data_gaps_unpriced` in the
  snapshot/receipt. Cash and priced holdings are unaffected. (`task check` green,
  435 tests.)
- DONE D5 — the timeline merges per-source SQL queries each ordered newest-first
  and `LIMIT`-ed, instead of loading whole tables and slicing in Python; the brief
  lookup and dashboard receipt count are single SQL queries. Behaviour unchanged
  (existing tests) plus a `limit=1` test. (`task check` green, 436 tests.)
- DONE D6 — corrected the "read-only API/cockpit" wording: it is read **plus**
  governed human attestation (no execution), in the README and lifecycle plan;
  non-claims and `execution_allowed=false` kept.
- D7a/D7b — trace context contract + local-only OpenTelemetry adapter implemented:
  API trace header handling uses the shared contract, malformed/secret-like trace
  input fails soft, Golden Path writes a separate `observability_trace_index`
  receipt linking trace id to proposal/review receipts, API requests create
  bounded local spans, and governance policies lock the no-default-exporter path.
  D7c (external exporter / telemetry upload) still needs explicit C3 approval.
- (gated) D8 — browser E2E / visual regression. Needs approval (new tooling).

All of Tier 1–3 (D1–D6) cleared; D7a/D7b are implemented with no default exporter.
D7c and D8 still await explicit go-ahead because they add an external export path
or new browser tooling.
