# Proposal: Execution Layer Institutional Practices

Date: 2026-06-02
Status: draft
Related idea: /root/projects/finharness/ideas/2026-06-02-execution-layer-institutional-practices.md
Related note: /root/projects/finharness/docs/notes/2026-06-02-execution-layer-institutional-practices.md
Related think: /root/projects/finharness/docs/think/2026-06-02-execution-layer-think.md
Related module: docs/modules/09-execution.md
Related ADR:

## Problem

FinHarness currently has Risk Gate as Layer 8, but the next boundary is not just
"send an order". Institutions treat execution as a controlled workflow with
order management, execution management, best-execution evidence, broker/venue
events, and post-trade handoff. FinHarness needs Layer 9 to model that workflow
without introducing autonomous live trading.

## User / Workflow

The users are the human operator, future AI agent, and paper-trading workflow
that need to know whether a risk-approved action was staged, submitted, filled,
canceled, rejected, or blocked before submit.

## Goals

```text
consume Layer 8 RiskGateSnapshot and receipt lineage
build ExecutionIntent only from approved decisions
stage deterministic paper order requests
enforce paper/live permission gates
derive and persist idempotency keys
normalize order lifecycle events
preserve raw adapter events
write ExecutionSnapshot and ExecutionReceipt
handoff final execution state to future post-trade layers
```

## Non-Goals

```text
authorize financial execution
create strategy signals
override Risk Gate
change sizing beyond approved intent
implement a full FIX engine
implement smart order routing
claim best execution is achieved
send live orders
```

## Evidence

- Idea: /root/projects/finharness/ideas/2026-06-02-execution-layer-institutional-practices.md
- Research note: /root/projects/finharness/docs/notes/2026-06-02-execution-layer-institutional-practices.md
- Think note: /root/projects/finharness/docs/think/2026-06-02-execution-layer-think.md
- BlackRock Aladdin for traders: https://www.blackrock.com/aladdin/benefits/traders
- FINRA Rule 5310: https://www.finra.org/finramanual/rules/r5310/
- FIX Trading Community overview: https://www.fixtrading.org/what-is-fix/
- Alpaca order lifecycle: https://docs.alpaca.markets/us/docs/orders-at-alpaca
- Project rule: AGENTS.md

## Design

Implement a typed Execution graph:

```text
source_config
-> load_risk_gate_snapshot
-> select_allowed_decisions
-> build_execution_intent
-> adapter_permission_check
-> pre_submit_check
-> derive_idempotency_key
-> stage_order_request
-> submit_or_dry_run
-> collect_execution_events
-> cancel_or_reconcile
-> quality
-> lineage
-> snapshot
-> receipt
-> review_hook
-> final
```

The graph should default to dry-run. Paper submission requires both an approved
Risk Gate decision and an explicit execute flag. Live mode remains blocked in
the MVP even if an operator sets execute=true.

## Inputs / Outputs

Typed inputs:

```text
RiskGateSnapshot
RiskGateReceipt reference
ExecutionContext
operator execute flag
adapter mode
optional broker adapter config
```

Typed outputs:

```text
ExecutionIntent
ExecutionOrderRequest
ExecutionEvent list
ExecutionQuality
ExecutionLineage
ExecutionSnapshot
ExecutionReceipt
```

## Quality / Lineage / Receipt

ExecutionQuality should include:

```text
risk_gate_lineage_present
decision_was_approved_for_execution_mode
paper_mode_required
live_mode_blocked
human_review_satisfied_when_required
idempotency_key_present
order_request_matches_approved_intent
raw_adapter_events_preserved
final_state_present
receipt_written
```

The receipt must record the upstream Risk Gate receipt, normalized status, raw
adapter events, idempotency key, order request hash, and final handoff state.

## Risks

```text
execution bypasses Risk Gate
paper approval accidentally becomes live execution
broker acknowledgement is mistaken for fill quality
partial fills and cancels are flattened away
duplicate graph runs submit duplicate orders
best-execution language overclaims what the MVP proves
```

## Success Signal

Tests prove that blocked Risk Gate decisions cannot submit, paper-approved
decisions stage deterministic orders, execute=true works only in paper/fake
adapter mode, duplicate idempotency keys do not submit twice, and lifecycle
events are preserved in snapshots and receipts.

## Review Plan

After implementation, run the narrow Layer 9 tests, then `task lint`, `task
test`, and `task check`. Update the review with command evidence, scoped debt,
and receipt paths.
