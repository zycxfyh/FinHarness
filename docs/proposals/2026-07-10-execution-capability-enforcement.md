# Execution Capability Enforcement — mini-RFC

Status: implemented; release gate passed
Logical slice: `EXEC-01`
Date: 2026-07-10

## 1. Change Class

**C3.** This slice changes the canonical execution control boundary. It adds no
network, credential, funded-account, or real-broker capability; it makes the
existing simulated-only defaults enforceable.

## 1b. Product Claim / Layer / Thin Slice

Execution capability flags will become service-layer policy rather than
documentation-only vocabulary. The five public execution mutations will fail
closed before any database, receipt, status, or adapter side effect when their
flag is disabled.

## 1c. Module Placement / System Boundary

- `execution/capabilities.py` owns vocabulary, denial error, and the bounded
  check helper.
- `execution/services.py` owns enforcement for direct Python callers.
- `execution/commands.py` enforces simulated submission before adapter lookup
  and forwards the same capabilities to the service.
- API dependencies inject the deployment capability set; the app translates a
  denial into a stable HTTP 403 response.

Capability enforcement is classical control-plane software. Agents may inspect
the result later, but they do not decide or override these flags.

## 2. Current Behavior

`ExecutionCapabilities` and safe defaults exist, but no runtime module imports
them. All execution services proceed regardless of a supplied deployment
policy because none can receive one.

## 3. Target Behavior

- Create draft, run pre-trade, record approval, stage, and simulated submit
  each check their matching flag as the first service action.
- Existing callers remain source-compatible through the safe default set.
- `submit_order` checks `submit_simulated_order` before database reads, adapter
  resolution, lifecycle receipts, status mutation, or adapter invocation.
- API construction may inject a stricter immutable capability set.
- Denial includes the exact capability name and produces HTTP 403.
- `submit_live_order` and `manage_broker_credentials` remain false and have no
  runtime enablement path.

## 4. Surface Inventory

- **Inputs:** immutable `ExecutionCapabilities`, existing execution request
  arguments.
- **Outputs:** existing success objects or `ExecutionCapabilityDeniedError`.
- **Network:** none.
- **Persistence:** unchanged on success; zero writes on denial.
- **Receipts:** unchanged on success; zero new receipt files/index rows on
  denial.
- **API:** same routes; optional app capability injection and stable 403 body.
- **Excluded:** user roles, authority grants, live adapters, credential stores,
  new receipt kinds, schema changes.

## 5. Default Path Invariant

With `DEFAULT_EXECUTION_CAPABILITIES`, all existing simulated-kernel tests and
route behavior remain unchanged. A live-shaped `ExecutionEnvironment.LIVE`
draft is still legal because substrate capability is determined by the only
registered adapter kind (`simulated`), not by the model label.

## 6. Denial Invariants

For every disabled command:

1. the exact disabled flag is reported;
2. no domain row or ReceiptIndex is added;
3. no existing lifecycle status changes;
4. no receipt file is written;
5. for submission, no adapter is resolved or called.

## 7. Threat-Model Delta

This is a boundary reduction. It adds an explicit fail-closed service gate in
front of an already simulated-only adapter registry. It does not add new trust
boundaries, secrets, external systems, or authority escalation. Any future real
adapter still requires a separate C3 design and threat-model update.

## 8. Traceability Matrix

| Commitment | Code | Test |
| --- | --- | --- |
| Five service gates | capabilities + services | per-command denial tests |
| Adapter untouched on denial | commands | disabled submit spy test |
| API injection and 403 | app/dependency/routes | disabled API route test |
| Default compatibility | default capability set | existing execution suite |
| Debt truth updates | debt register/verifier | debt register tests |

## 9. Test / Gate Plan

First run the new semantic denial suite and execution/debt tests. Then run
execution schema/services/routes/adapter/lifecycle suites, lint, mypy,
documentation-current checks, and the full project gate.

## 10. Not Claimed / Debt

This slice does not implement live submit, broker credentials, account
funding, cancellation capabilities, role-based authorization, or Agent
execution tools.

## 11. Release Decision

Merge now. The six new semantic tests prove per-command denial, zero
database/receipt/status effects, no adapter resolution on denied submit, and
stable API 403 behavior. The existing 47-test execution regression set passes,
the debt verifier marks ENG-DEBT-0010 resolved, and the complete project gate
passes with lint, mypy, 880 unit tests, eight integration tests, frontend and
governance checks, the research experiment, and evaluation smoke at real zero
exit status.
