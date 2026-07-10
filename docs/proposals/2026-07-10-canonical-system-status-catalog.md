# Canonical System Status Catalog — mini-RFC

Status: implemented; release gate passed
Logical slice: `TRUTH-02`
Date: 2026-07-10

## 1. Change Class

**C2.** This slice changes the machine-readable architecture status of core,
legacy, and scaffolded systems. It is documentation and test only, but the
result governs future module placement and roadmap eligibility.

## 1b. Product Claim / Layer / Thin Slice

FinHarness will have one catalog that distinguishes canonical, current, thin,
scaffolded, legacy, planned, and archived systems. The slice adds the missing
Execution Kernel and Agent Cognition Runtime entries and aligns the current
module/system maps for the high-risk boundaries.

## 1c. Module Placement / System Boundary

The change belongs to EOS Governance / Quality. `system-catalog.yml` is the
machine-readable status source; `system-map.md`, `module-map.md`, and
`framework-index.md` remain human-readable projections.

## 2. Current Behavior

The catalog omits the canonical Execution Kernel, marks the superseded
ActionIntent and PaperValidation systems as current, and has no entry for the
Agent Cognition Runtime or work-orchestrator scaffold. Existing catalog tests
validate shape and paths but not architecture truth.

## 3. Target Behavior

- Execution Kernel is `canonical`.
- ActionIntent and PaperValidation are `legacy`.
- Agent Cognition Runtime is `scaffolded` until Work Loop semantic closure.
- External mature-wheel integration remains `thin`.
- Tests require these classifications and their matching current-doc markers.

## 4. Surface Inventory

- **Inputs:** current catalog, system map, module map, framework index, runtime
  roots.
- **Outputs:** catalog schema v2 and cross-document truth checks.
- **Network:** none.
- **Failure surfaces:** status drift, missing canonical system, false roadmap
  prerequisites.
- **User-visible:** architecture documentation only.
- **Excluded:** runtime behavior, route removal, schema migration, debt ledger
  consolidation.

## 5. Default Path Invariant

No Python runtime, API, receipt, database, or frontend behavior changes.

## 6. Traceability Matrix

| Commitment | Location | Test | Gate |
| --- | --- | --- | --- |
| Execution is canonical | catalog + maps | `test_required_architecture_statuses` | docs-current |
| Legacy systems cannot return to current | catalog + maps | `test_high_risk_statuses_match_current_docs` | docs-current |
| Agent Work Loop remains scaffolded | catalog + maps | both status tests | docs-current |
| Catalog references real assets | catalog | existing path/check tests | docs-current |

## 7. Test / Gate Plan

Run system catalog tests first, then docs-current, governance, lint, mypy, and
the full project check.

## 8. Product Surface Review

No product surface changes. The catalog prevents future work from extending a
legacy execution substitute or treating a scaffold as a runtime foundation.

## 9. Not Claimed / Debt

This slice does not remove legacy routes, merge debt ledgers, generate docs
from the catalog, or close Work Loop semantics.

## 10. Release Decision

Merge now. The catalog/current-doc assertions, documentation-current checks,
lint, type checking, and full project test suite all pass with real zero exit
status. No runtime behavior changed in this slice.
