# Canonical Engineering Debt Register — mini-RFC

Status: implemented; release gate passed
Logical slice: `TRUTH-03`
Date: 2026-07-10

## 1. Change Class

**C2.** This slice changes governance truth, tests, and a read-only verifier.
It does not change application runtime behavior.

## 1b. Product Claim / Layer / Thin Slice

FinHarness will have one current engineering-debt register. Every debt status
will be checked by a named repository verifier, and the former Execution Spine
ledger will remain available only as superseded historical evidence.

## 1c. Module Placement / System Boundary

The register belongs to EOS Governance / Quality. The verifier belongs to
repository tooling and may read committed source, tests, documentation, and
configuration, but it must not mutate them or access the network.

## 2. Current Behavior

Two ledgers both claim `current`. The general register still says that the API
write gate and receipt-backed write inventory are missing even though code,
tests, and commits prove they exist. The Execution Spine ledger contains
mostly resolved history plus two partially addressed debts that are absent
from the general register. Existing debt tests validate JSON shape, not the
truth of status claims.

## 3. Target Behavior

- `debt-register.json` v2 is the only current engineering-debt source.
- The Execution Spine ledger is marked `superseded` and points to the register.
- Resolved API write-gate and receipt-registry debts carry resolution evidence.
- The missing Execution inventory and capability-enforcement debts enter the
  canonical register.
- Every current entry names one bounded verifier. The verifier must agree with
  whether the entry is `resolved`.

## 4. Audited Debt State

| Debt | Audited state | Repository evidence |
| --- | --- | --- |
| API write capability | resolved | `local_operator.py`, route dependencies, `WriteCapabilityGateTest`, #113 |
| Paper legacy boundary | active | legacy/write gates exist; dedicated threat/removal boundary is incomplete |
| Receipt write registry | resolved | current registry, executable registry tests, #112/#128-131/#144 |
| Task check layering | active | `task check` remains one flat all-surface sequence |
| Dependency grouping | active | research/agent/eval packages remain in main dependencies |
| StateCore model split | active | `models.py` remains 1,798 lines |
| Frontend shell split | active | `app.js` remains 1,526 lines; no `api.js`/`state.js` shell split |
| Toolchain policy | active | local Node 26.2 vs CI Node 22; Rust CI install remains unexplained |
| Execution abstraction inventory | active | canonical Execution Kernel objects/services are absent from inventory |
| Execution capability enforcement | active | capability vocabulary has no service consumer |

## 5. Surface Inventory

- **Inputs:** both debt ledgers, referenced source/tests/configuration, local git
  history.
- **Outputs:** canonical register v2, read-only verifier, updated governance
  tests, historical-ledger markers.
- **Network:** none.
- **Failure surfaces:** verifier false positives, status drift, parallel current
  ledgers.
- **User-visible:** governance documentation only.
- **Excluded:** paying down the eight active debts, runtime refactors, dependency
  changes, frontend extraction, capability enforcement.

## 6. Default Path Invariant

No API, database, receipt, execution, Agent, or frontend runtime behavior
changes. The verifier performs read-only repository inspection.

## 7. Traceability Matrix

| Commitment | Location | Test / Gate |
| --- | --- | --- |
| One current ledger | both governance ledgers | debt register tests |
| Status matches repository | verifier + canonical entries | verifier agreement test |
| Evidence paths are real | canonical entries | evidence path test |
| Historical execution debt remains readable | superseded ledger | supersession test |

## 8. Test / Gate Plan

Run the debt verifier and debt/registry tests first, then governance checks,
lint, type checking, and the full project check.

## 9. Not Claimed / Debt

This slice does not claim the eight active debts are paid down. In particular,
`ExecutionCapabilities` remains vocabulary-only until `EXEC-01` wires it into
the service boundary with fail-closed tests.

## 10. Release Decision

Merge now. The named verifier reports truthful agreement for all ten entries;
the debt and receipt-registry tests pass; documentation-current checks pass;
and the complete project gate passes with lint, mypy, 873 unit tests, eight
integration tests, frontend/governance checks, the research experiment, and
the evaluation smoke all at real zero exit status.
