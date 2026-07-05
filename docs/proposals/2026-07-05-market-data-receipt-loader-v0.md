# Market-Data Receipt Loader v0 mini-RFC

*Created: 2026-07-05 | PR: #108 | Change Class: C1*

## 1. Change Class

C1. Internal engineering refactor: consolidate duplicate receipt parsing into a
single-pass loader. No behavior change. No API contract change.

## 1b. Product Claim / Layer / Thin Slice

**Product Claim:** The Data Catalog and Data Quality API keep the same
user-visible behavior while market-data receipt loading becomes single-pass,
deterministic, and easier to extend.

**Layer:** L1 Data Foundation / Engineering Hygiene.

**Thin Slice:** Extract `load_market_data_receipts()` into a dedicated module that
returns both valid receipts and malformed receipt issues in one pass. Update
`build_data_catalog()` to consume this loader instead of scanning receipts twice.

## 1c. Module Placement / System Boundary

**System:** Market Data / Data Foundation.

**Placement:**

- `src/finharness/data_receipt_loader.py` (new)
- `src/finharness/data_catalog.py` (update to use loader)
- `tests/test_data_catalog.py` (update for loader tests)
- `docs/proposals/2026-07-05-market-data-receipt-loader-v0.md` (new)

Does not modify statecore, data_quality, data_quality_policy, API routes,
frontend, Agent, scenario, paper, or execution.

## 2. Current behavior

`discover_market_data_receipts()` scans `receipt_mds_*.json` files and silently
skips malformed ones. `_surface_malformed_as_gaps()` scans the same files again
to surface the skipped malformed ones as `DataGap` objects. Each file is read
and validated twice.

## 3. Target behavior

`load_market_data_receipts()` scans once, returning `ReceiptLoadResult` with
valid `receipts` and `issues`. `build_data_catalog()` consumes this one result.
`_surface_malformed_as_gaps()` is removed. `discover_market_data_receipts()`
becomes a thin compatibility wrapper.

## 4. Surface Inventory

**Inputs:** `receipt_mds_*.json` files in receipt root.

**Outputs:** `ReceiptLoadResult(receipts, issues, source_refs)`.

**External calls:** None.

**Excluded:** No API contract change. No OpenAPI change. No behavior change.

## 5. Default Path Invariant

All catalog, quality, and gaps endpoints return identical responses before and
after this change. All existing tests pass.

## 6. Traceability Matrix

| Design commitment | Code point | Test |
|---|---|---|
| Single-pass parsing | data_receipt_loader.load_market_data_receipts | unit test |
| Malformed → ReceiptLoadIssue | data_receipt_loader | unit test |
| discover wrapper returns only valid | data_catalog.discover | existing tests pass |
| _surface_malformed_as_gaps removed | data_catalog | existing gap tests pass |
| No API/contract change | routes unchanged | test_statecore_api unchanged |

## 7. Test / Gate Plan

- `test_data_catalog.py`: add loader unit tests; existing tests unchanged
- `test_statecore_api.py`: no changes needed

## 8. Not claimed / Debt

- No unified Receipt Fabric.
- No StateCore receipt migration.
- No DataQuality policy change.
- No API contract change.
- No cockpit change.
- No provider refresh.
- No Agent / Scenario / Paper / Broker / Live Execution.

## 9. Release Decision

Merge now.

Reason:
- Engineering value: removes duplicate market-data receipt scanning/validation
  from Data Catalog while preserving user-visible behavior.
- Boundary safety: no API, OpenAPI, DataQuality policy, StateCore, frontend,
  Agent, Scenario, Paper, Broker, or live execution changes.
- Contract confidence: `build_data_catalog()`, `/data/catalog`, `/data/quality`,
  and `/data/gaps` preserve existing behavior and response shape.
- Test confidence: 741 tests pass; loader tests cover valid receipts, malformed
  JSON, deterministic receipt ordering, deterministic source_refs ordering,
  missing directory, and discover wrapper compatibility.
- Future maintainability: one market-data loading path now produces valid
  receipts and load issues, reducing extension risk for future Data Contract /
  Research evidence work.
