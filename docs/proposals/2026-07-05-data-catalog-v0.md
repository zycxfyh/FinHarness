# Data Catalog v0 mini-RFC

*Created: 2026-07-05 | PR: #104 | Change Class: C2*

## 1. Change Class

C2. This slice adds a new read-oriented data catalog surface and API, but does not change default market-data ingestion, Agent behavior, paper validation, scenario behavior, or live/execution behavior.

## 1b. Product Claim / Layer / Thin Slice

**Product Claim:** The operator can see which data sources exist, what they cover, how fresh/complete/reconciled they are, and which data gaps must be considered before research, scenario, or Agent workflows depend on them.

**Layer:** L0 Data Ingestion & Connectors + L1 Data Lake / Catalog / Quality.

**Thin Slice:** Add DataSourceRegistry and DataCatalog v0 as read-oriented models and API surfaces over existing market-data receipt primitives.

## 1c. Module Placement / System Boundary

**System:** Market Data / Data Foundation.

**Placement:**

- `src/finharness/data_catalog.py`
- `src/finharness/api/routes_data_catalog.py`
- `tests/test_data_catalog.py`
- `tests/test_statecore_api.py`
- `docs/proposals/2026-07-05-data-catalog-v0.md`

This slice reuses existing `market_data.py` concepts: `SourceSpec`, `MarketDataQuality`, `MarketDataLineage`, `MarketDataSnapshot`, and `DataReceipt`.

It does not modify Agent runtime, paper validation runtime, scenario code, frontend tabs, or live/broker/execution surfaces.

## 2. Current behavior

FinHarness can persist market-data receipts and snapshots with source, quality, lineage, payload refs, and bias controls, but there is no central read surface that lets the operator or future Agent workflows ask:

- which sources exist;
- what datasets they cover;
- what the latest known receipt is;
- what quality and bias limitations apply;
- which data gaps remain.

## 3. Target behavior

**Default path:**

- Existing market-data ingestion behavior remains unchanged.
- No network call is triggered by reading the data catalog.
- Data catalog API reads existing registry definitions and discovered local market-data receipts only.

**Opt-in path:**

- Future slices may add provider refresh, multi-provider reconciliation, and cockpit views.
- This slice does not implement those.

## 4. Surface Inventory

**Inputs:**

- Existing market-data receipt files under `data/receipts/market-data`.
- Existing `market_data.py` source, quality, lineage, and snapshot contracts.
- Static registry definitions for known local providers such as yfinance and optional OpenBB reconciliation.

**Outputs:**

- Data source registry entries.
- Data catalog entries.
- Data gap records.
- Read-only API responses.

**External calls / network surface:**

- None. Catalog reads must not fetch network data.

**Failure surface:**

- Missing receipt directory.
- Malformed receipt JSON.
- Receipt missing snapshot fields.
- Single-source unreconciled data.
- Point-in-time or survivorship controls not assured.
- Stale or incomplete data.

**User-visible surface:**

- API endpoints for listing data sources, catalog entries, specific catalog entries, and data gaps.

**Excluded surfaces:**

- No Agent workflow.
- No scenario engine.
- No paper performance review.
- No frontend redesign.
- No provider refresh.
- No broker/live/execution path.

## 5. Default Path Invariant

Existing market-data ingestion, StateCore, paper validation, Agent runtime, and cockpit routes must behave the same.

**Verification:**

- `task docs:current-check`
- `git diff --check`
- targeted data catalog unit/API tests
- OpenAPI whitelist update
- no changes to paper, agent, scenario, or execution code

## 6. Traceability Matrix

| Design commitment | Planned code point | Test | Gate probe |
|---|---|---|---|
| Catalog reads do not trigger network calls | `data_catalog.py` only reads registry constants and local receipts | unit test with temp receipt root | check no yfinance/OpenBB call in catalog read path |
| Data source entries disclose provider, access method, coverage, freshness, bias controls | `DataSourceRegistryEntry` | unit test default registry fields | inspect model fields |
| Catalog entries expose latest receipt and data gaps | `DataCatalogEntry`, `DataGap` | unit test discovered receipt -> catalog entry | verify receipt ref and gap text |
| API exposes read-only catalog surfaces | `routes_data_catalog.py` | API test | OpenAPI whitelist |
| No runtime/execution expansion | no live/broker route names | OpenAPI forbidden-token test | grep route paths |

## 7. Test / Gate Plan

**Required tests:**

`tests/test_data_catalog.py`:

- default registry contains yfinance close/history source;
- registry entries include bias controls and freshness policy;
- catalog discovery reads a local receipt without network;
- malformed receipt becomes a data gap, not an exception;
- single-source unreconciled status is surfaced as a gap.

`tests/test_statecore_api.py`:

- add `/data/sources`, `/data/catalog`, `/data/catalog/{dataset_key}`, `/data/gaps` to OpenAPI whitelist.

**Validation commands:**

- `PYTHONPATH=src uv run ruff check .`
- `PYTHONPATH=src uv run mypy`
- `PYTHONPATH=src uv run python -m unittest tests.test_data_catalog tests.test_statecore_api`
- `task docs:current-check`
- `git diff --check`

## 8. Product Surface Review

After this slice, the operator can see:

- what data sources FinHarness knows about;
- what datasets each source covers;
- whether data is stale, incomplete, unreconciled, or bias-limited;
- which receipt backs the latest known market-data snapshot;
- which gaps must be resolved before research, scenario, or Agent workflows rely on the data.

This is product progress because it makes data trust visible before adding more advanced workflows.

## 9. Not claimed / Debt

This slice does not claim:

- complete multi-provider data catalog;
- real-time provider refresh;
- point-in-time safe institutional data;
- survivorship-bias-controlled security master;
- frontend Data Catalog page;
- Agent use of the catalog;
- scenario consumption of the catalog.

**Accepted debt:**

- #105 should add stronger DataQualityReport / FreshnessPolicy semantics.
- #106 should expand API/data gaps if needed.
- #107 should add a cockpit Data Catalog / Data Gaps page.

## 10. Release Decision

Merge now.

Reason:
- Product value: exposes known data sources, local market-data receipts, quality
  summaries, reconciliation status, bias controls, and data gaps as a read-only
  catalog surface.
- Boundary safety: all API routes are GET-only, catalog reads do not trigger
  network calls, and all responses keep `execution_allowed=false`.
- Test confidence: unit, discovery, API, and OpenAPI whitelist tests cover
  registry, receipt discovery, malformed receipt handling, data gaps, read-only
  endpoints, and schema exposure.
- Future maintainability: accepted debt is explicitly deferred to #105
  DataQualityReport / FreshnessPolicy, #106 expanded API/data gaps, and #107
  cockpit Data Catalog / Data Gaps page.
