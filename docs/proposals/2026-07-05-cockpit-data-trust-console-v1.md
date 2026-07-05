# Cockpit Data Trust Console v1 mini-RFC

*Created: 2026-07-05 | PR: #107 | Change Class: C2*

## 1. Change Class

C2. This slice adds a read-only Data Trust view to the cockpit, closing the
#104–#106 backend-to-user loop without adding backend logic, network calls, or
execution paths.

## 1b. Product Claim / Layer / Thin Slice

**Product Claim:** The operator can inspect dataset readiness, quality findings,
and data gaps from the cockpit without reading raw API JSON or inferring trust
state manually.

**Layer:** L2 Cockpit / Operator Surface.

**Thin Slice:** Add a "Data Trust" tab to the existing cockpit shell. The view
consumes existing `/data/catalog`, `/data/quality`, and `/data/gaps` endpoints
and renders summary, catalog, quality, and gaps panels.

## 1c. Module Placement / System Boundary

**System:** Cockpit / Delivery Surface.

**Placement:**

- `frontend/index.html` — new Data Trust tab + view section
- `frontend/app.js` — renderData view function
- `frontend/styles.css` — minimal new styles if needed
- `frontend/tests/cockpit_data_trust.test.cjs` — jsdom DOM test
- `frontend/tests/browser/cockpit_smoke.test.cjs` — updated tab count + golden path
- `docs/proposals/2026-07-05-cockpit-data-trust-console-v1.md` — this document

Does not modify backend routes, data catalog, quality policy, statecore,
Agent runtime, or execution paths.

## 2. Current behavior

#104–#106 provide Data Catalog, Data Quality Reports, and Data Gaps as GET-only
API surfaces, but the cockpit has no Data view. The operator must read raw API
JSON to understand data trust state.

## 3. Target behavior

**Default path:**

- Cockpit gains a "Data Trust" tab.
- The view renders four panels: Summary, Data Catalog, Quality Reports, Data Gaps.
- All data comes from existing GET endpoints; no new backend requests.
- The page displays `execution_allowed=false` and boundary safety text.

**Opt-in path:**

- Future slices may add contract status, per-dataset drilldown, or refresh controls.
- This slice only adds the read-only view.

## 4. Surface Inventory

**Inputs:**

- `GET /data/catalog` — catalog entries
- `GET /data/quality` — quality reports + data gaps
- `GET /data/gaps?severity=critical` — critical gaps
- `GET /data/gaps?severity=warning` — warning gaps

**Outputs:**

- Rendered HTML in the cockpit shell.

**Excluded surfaces:**

- No new API endpoints.
- No provider refresh.
- No repair workflow.
- No Agent action.
- No broker/live execution.
- No investment advice.
- No backend data quality policy change.

## 5. Default Path Invariant

All existing backend tests, API routes, and cockpit views remain unchanged.
The Data Trust view is additive only.

## 6. Traceability Matrix

| Design commitment | Code point | Test | Gate probe |
|---|---|---|---|
| Cockpit loads Data Trust tab | index.html + app.js | smoke test tab count=8 | browser golden path |
| View references /data/catalog | app.js renderData | jsdom test | grep for `/data/catalog` |
| View references /data/quality | app.js renderData | jsdom test | grep for `/data/quality` |
| View references /data/gaps | app.js renderData | jsdom test | grep for `/data/gaps` |
| execution_allowed=false visible | app.js renderData | jsdom test | boundary line check |
| No backend changes | — | all existing tests pass | unittest suite |
| No provider refresh text | index.html boundary text | jsdom test | grep for "refresh" not appearing |

## 7. Test / Gate Plan

**New tests:** `frontend/tests/cockpit_data_trust.test.cjs`

- cockpit loads with Data Trust tab present
- view includes `execution_allowed=false`
- view includes boundary safety text
- JS references `/data/catalog`
- JS references `/data/quality`
- JS references `/data/gaps`
- JS references `/data/gaps?severity=critical`
- JS references `/data/gaps?severity=warning`
- No provider refresh / repair / execution action text

**Updated:** `frontend/tests/browser/cockpit_smoke.test.cjs`

- tab count updated from 7 to 8

**Validation:**

```bash
PYTHONPATH=src uv run ruff check .
PYTHONPATH=src uv run mypy
PYTHONPATH=src uv run python -m unittest discover -s tests
task test:frontend
task test:browser  # optional, CI
task docs:current-check
git diff --check
```

## 8. Product Surface Review

After this slice, the cockpit operator can see data trust state in the same
application surface as portfolio state, policy, proposals, and timeline.

## 9. Not claimed / Debt

- No contract status display (#108).
- No per-dataset drilldown.
- No provider refresh or repair controls.
- No Agent workspace.

## 10. Release Decision

Keep draft pending independent review.

Reason:
- Product value: closes the #104–#106 backend-to-user data trust loop.
- Boundary safety: no backend changes, no new endpoints, read-only rendering.
- Test confidence: jsdom DOM test + updated browser golden path cover view
  presence, boundary text, and API endpoint references.
- Future maintainability: minimal additive change following existing cockpit
  shell patterns; no framework introduction.
