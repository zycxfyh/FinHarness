# Execution Abstraction Inventory Rebase — mini-RFC

Status: implemented; release gate passed
Logical slice: `TRUTH-04`
Date: 2026-07-10

## 1. Change Class

**C2.** Documentation, governance verifier, and current-fact tests only. No
runtime behavior changes.

## 2. Current Behavior

The abstraction inventory predates the canonical Execution Kernel. It omits
nine execution facts, services, capabilities, adapter boundaries, routes, and
the legacy bridge. Legacy entries still point toward nonexistent future
`/execution/pretrade-packets/` and `execution/paper/*` surfaces even though the
kernel and bridge already exist.

## 3. Target Behavior

- Canonical execution models are classified as classical facts/gates/traces.
- Services, capabilities, adapter registry, simulated adapter, and legacy
  bridge are classified separately from Agentic artifacts.
- `/execution/*` is the canonical route family.
- Legacy ActionIntent/PaperValidation entries point to current bridge/delete
  paths, not imaginary future routes.
- ENG-DEBT-0009 becomes resolved only when the executable verifier and focused
  inventory tests agree.

## 4. Surface Inventory

- **Inputs:** system catalog, execution models/services/adapter/routes/bridge,
  current inventory and debt register.
- **Outputs:** inventory truth, focused tests, debt/roadmap state update.
- **Runtime/network/database/receipt/frontend:** unchanged.
- **Excluded:** moving code, deleting legacy routes, schema migration, adding
  execution objects or APIs.

## 5. Default Path Invariant

Every Python module and runtime behavior remains byte-for-byte unchanged.

## 6. Test / Gate Plan

Run focused inventory, debt, roadmap, and docs-current tests, then the complete
project gate.

## 7. Release Decision

Merge now. Focused inventory/current-fact tests, the canonical debt verifier,
roadmap consistency, and docs-current checks pass. The complete project gate
passes with lint, mypy, 897 unit tests, eight integration tests,
frontend/governance checks, the research experiment, and evaluation smoke at
real zero exit status. No runtime file changed.
