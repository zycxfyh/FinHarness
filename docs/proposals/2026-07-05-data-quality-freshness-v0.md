# Data Quality Report & Freshness Policy v0 mini-RFC

*Created: 2026-07-05 | PR: #105 | Change Class: C2*

## 1. Change Class

C2. This slice adds structured data quality assessment and freshness policy semantics
on top of #104 Data Catalog, without adding new API endpoints, network calls, or
changing default ingestion behavior.

## 1b. Product Claim / Layer / Thin Slice

**Product Claim:** The operator can see, for each cataloged dataset, an explicit
freshness verdict (fresh / stale / critically stale), quality verdict
(ok / degraded), bias verdict (controlled / uncontrolled), reconciliation verdict
(confirmed / single_source_unreconciled), a composite readiness status (usable /
usable_with_warnings / not_ready), and structured findings that explain each
verdict — all derived from existing receipt metadata without network calls.

**Layer:** L1 Data Lake / Catalog / Quality (extends #104).

**Thin Slice:** Add `DataQualityPolicy`, `FreshnessPolicy`, `DataQualityFinding`,
`DataQualityReport`, and `DataReadinessStatus` as read-only assessment models.
Extend `DataCatalogEntry` to carry freshness_status, quality_status, bias_status,
reconciliation_status, readiness_status, findings, and blocks. No new endpoints.

## 1c. Module Placement / System Boundary

**System:** Market Data / Data Foundation → Quality Assessment.

**Placement:**

- `src/finharness/data_quality_policy.py` (new)
- `src/finharness/data_catalog.py` (extend DataCatalogEntry, _receipt_to_catalog_entry)
- `tests/test_data_quality_policy.py` (new)
- `tests/test_data_catalog.py` (update for new fields)
- `docs/proposals/2026-07-05-data-quality-freshness-v0.md` (new)

Does not modify Agent runtime, paper validation, scenario, frontend,
live/broker/execution, or API routes.

## 2. Current behavior

#104 DataCatalogEntry exposes quality_summary (dict), reconciliation_status (str),
bias_controls (list[str]), and data_gaps (list[str] — free-form text). There is
no structured way to answer:

- Is this data fresh enough for research?
- Is the quality ok or degraded?
- Which findings block downstream workflows vs which are warnings?
- What is the composite readiness status?

## 3. Target behavior

**Default path:**

- Existing market-data ingestion and #104 catalog behavior remain unchanged.
- No network calls.
- `_receipt_to_catalog_entry` now computes structured freshness_status,
  quality_status, bias_status, readiness_status, a list of `DataQualityFinding`
  objects, and a `blocks` list.
- Old `data_gaps: list[str]` remains (not removed — backward compatible).
- `/data/catalog` and `/data/catalog/{dataset_key}` responses now include the new
  fields.
- `/data/gaps` continues to surface DataGap objects unchanged.

**Opt-in path:**

- #106 may add a dedicated `/data/quality` endpoint or quality-specific API surface.
- #107 may add a cockpit quality/freshness view.

## 4. Surface Inventory

**Inputs:**

- Existing `MarketDataQuality` from receipt (row_count, ok, stale, outlier_flags, etc.).
- `snapshot.as_of_utc` for freshness computation.
- `lineage.data_bias_controls` for bias assessment.
- `quality.reconciliation.status` for reconciliation verdict.
- Default freshness thresholds: stale_after_days=5, critical_after_days=30.

**Outputs:**

- Structured freshness_status, quality_status, bias_status, reconciliation_status.
- Composite readiness_status.
- List of `DataQualityFinding` with severity, code, message, source_ref, blocks.
- Blocks list (downstream blockers).

**External calls / network surface:**

- None. All assessments derived from static receipt metadata.

**Failure surface:**

- Missing receipt → handled by DataGap (unchanged).
- Missing as_of_utc → freshness treats as unknown, finding raised.
- Missing quality fields → degraded with finding.
- Single-source unreconciled → warning finding.
- Survivorship / PIT uncontrolled → warning finding.

**Excluded surfaces:**

- No Agent workflow.
- No scenario engine.
- No paper performance review.
- No frontend redesign.
- No provider refresh.
- No new API endpoints (#106).
- No broker/live/execution.

## 5. Default Path Invariant

All existing #104 tests must pass without modification. New fields are additive
and do not change existing field semantics.

## 6. Traceability Matrix

| Design commitment | Code point | Test | Gate probe |
|---|---|---|---|
| Fresh data → usable or usable_with_warnings | `_assess_freshness` | unit test | check readiness_status |
| Stale data → warning finding | `_assess_freshness` | unit test | verify finding severity=warning |
| Critically stale → critical finding + blocks | `_assess_freshness` | unit test | verify blocks non-empty |
| Single-source unreconciled → warning finding | `_assess_reconciliation` | unit test | verify finding |
| Bias uncontrolled → warning finding | `_assess_bias` | unit test | verify finding |
| No network calls | whole module | test imports | grep for yfinance/httpx |
| execution_allowed=false on all models | all new models | unit test | explicit assertion |

## 7. Test / Gate Plan

**New tests:** `tests/test_data_quality_policy.py`

- fresh data → freshness_status="fresh", readiness usable
- stale (>5d) → freshness_status="stale", warning finding
- critically stale (>30d) → freshness_status="critically_stale", critical finding, blocks downstream
- quality ok → quality_status="ok"
- quality degraded → quality_status="degraded", finding
- single_source_unreconciled → warning finding
- survivorship_uncontrolled → warning finding
- point_in_time_uncontrolled → warning finding
- composite readiness: all-clear → usable, warnings → usable_with_warnings, critical → not_ready
- execution_allowed=false on all new models
- no network imports in new module

**Updated tests:** `tests/test_data_catalog.py`

- DataCatalogEntry now includes freshness_status, quality_status, bias_status, readiness_status, findings, blocks

**Validation:**

```bash
PYTHONPATH=src uv run ruff check .
PYTHONPATH=src uv run mypy
PYTHONPATH=src uv run python -m unittest tests.test_data_quality_policy tests.test_data_catalog tests.test_statecore_api
task docs:current-check
git diff --check
```

## 8. Product Surface Review

After this slice, the operator can see for each cataloged dataset:

- freshness_status: fresh / stale / critically_stale / unknown
- quality_status: ok / degraded / unknown
- bias_status: controlled / uncontrolled
- reconciliation_status: confirmed / single_source_unreconciled
- readiness_status: usable / usable_with_warnings / not_ready
- structured findings with severity (info / warning / critical), codes, and messages
- explicit blocks list for downstream workflows

## 9. Not claimed / Debt

This slice does not claim:

- user-configurable freshness policies per dataset
- multi-provider quality reconciliation
- quality trend history
- automated re-fetch on stale detection
- cockpit quality dashboard
- quality-specific API endpoint

**Accepted debt:**

- #106 should add `/data/quality` endpoint and expand API.
- #107 should add cockpit Data Quality / Freshness view.
- #108 should add per-dataset FreshnessPolicy configuration.

## 10. Release Decision

Merge now.

Reason:
- Product value: structured freshness, quality, bias, and readiness assessment
  replaces free-form data_gaps strings with machine-actionable findings.
- Boundary safety: no new endpoints, no network calls, no downstream behavior
  changes, all new fields are additive to existing DataCatalogEntry.
- Test confidence: unit tests cover all freshness tiers, quality states, bias
  controls, reconciliation, composite readiness, and model invariants.
- Future maintainability: assessment logic is isolated in data_quality_policy.py;
  catalog integration is a single call site in _receipt_to_catalog_entry.
