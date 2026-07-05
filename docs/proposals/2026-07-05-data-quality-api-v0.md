# Data Quality API v0 mini-RFC

*Created: 2026-07-05 | PR: #106 | Change Class: C2*

## 1. Change Class

C2. This slice adds read-only API endpoints for querying data quality reports and
data gaps directly, without changing core quality assessment logic or adding
network calls.

## 1b. Product Claim / Layer / Thin Slice

**Product Claim:** The operator can query dataset quality and readiness directly
through read-only API endpoints, without inferring quality state from the broader
data catalog response.

**Layer:** L1 Data Quality API surface (extends #104, #105).

**Thin Slice:** Add `/data/quality`, `/data/quality/{dataset_key}`, and filtered
`/data/gaps` endpoints. All endpoints are GET-only, read from local receipts,
and reuse existing `DataQualityReport` and `DataGap` models.

## 1c. Module Placement / System Boundary

**System:** Market Data / Data Foundation → API Surface.

**Placement:**

- `src/finharness/api/routes_data_quality.py` (new)
- `src/finharness/api/app.py` (add router)
- `tests/test_data_quality_api.py` (new)
- `tests/test_statecore_api.py` (OpenAPI whitelist)
- `docs/proposals/2026-07-05-data-quality-api-v0.md` (new)

Does not modify data_quality_policy.py, data_catalog.py, Agent, scenario,
paper, frontend, or live/broker/execution.

## 2. Current behavior

Data quality reports and data gaps are only visible indirectly through
`/data/catalog` responses. There is no dedicated endpoint to query quality
reports or filter data gaps by severity or blocked workflow.

## 3. Target behavior

**Default path:**

- `GET /data/quality` returns all quality reports + data gaps.
- `GET /data/quality/{dataset_key}` returns a single report.
- `GET /data/gaps` supports optional `?severity=` and `?blocks=` query filters.
- All endpoints are read-only. No network calls.

**Opt-in path:**

- #107 may add cockpit quality dashboard consuming these endpoints.

## 4. Surface Inventory

**Inputs:**

- `build_data_catalog(receipt_root)` from #104.
- `DataQualityReport` from #105.
- `DataGap` from #104.

**Outputs:**

- `DataQualityListResponse` — reports + gaps.
- `DataQualityDetailResponse` — single report.
- `DataGapsResponse` — filtered gaps.

**External calls / network surface:**

- None.

**Excluded surfaces:**

- No Agent workflow.
- No scenario engine.
- No paper performance review.
- No frontend redesign.
- No provider refresh.
- No broker/live/execution.

## 5. Default Path Invariant

All existing #104 and #105 tests pass unchanged. No modification to
data_quality_policy.py or data_catalog.py.

## 6. Traceability Matrix

| Design commitment | Code point | Test | Gate probe |
|---|---|---|---|
| `/data/quality` returns reports | routes_data_quality.py | API test | status 200 |
| `/data/quality/{dataset_key}` returns single report | routes_data_quality.py | API test | status 200 |
| Missing dataset_key returns 404 | routes_data_quality.py | API test | status 404 |
| `/data/gaps?severity=critical` filters | routes_data_quality.py | API test | check filtered result |
| All read-only | routes_data_quality.py | API test | POST→405 |
| No network | imports | inspection | grep yfinance/httpx |

## 7. Test / Gate Plan

**New tests:** `tests/test_data_quality_api.py`

- quality list endpoint returns 200 + reports + gaps + execution_allowed=false
- quality detail returns one report
- missing dataset_key → 404
- missing receipt dir → no reports + DataGap, not crash
- malformed receipt → DataGap, not crash
- severity filter
- blocks filter
- POST/PATCH → 405
- execution_allowed=false on all responses

**Updated:** `tests/test_statecore_api.py` — OpenAPI whitelist.

**Validation:**

```bash
PYTHONPATH=src uv run ruff check .
PYTHONPATH=src uv run mypy
PYTHONPATH=src uv run python -m unittest tests.test_data_quality_api tests.test_data_quality_policy tests.test_data_catalog tests.test_statecore_api
task docs:current-check
git diff --check
```

## 8. Product Surface Review

After this slice, the operator can query quality and gaps directly through
dedicated API endpoints instead of parsing the larger catalog response.

## 9. Not claimed / Debt

- No cockpit quality dashboard (#107).
- No per-dataset FreshnessPolicy configuration (#108).
- No provider refresh.
- No reconciliation expansion.

## 10. Release Decision

Keep draft pending independent review.

Reason:
- Product value: dedicated quality API endpoints reduce query friction.
- Boundary safety: all endpoints are GET-only, no network calls, reuse existing models.
- Test confidence: API tests cover list, detail, 404, filters, read-only enforcement.
- Future maintainability: thin API surface, no changes to quality logic.
