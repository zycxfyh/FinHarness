# Module: Execution

Status: implemented MVP
Owner: FinHarness
Layer: 9 - Execution / paper order lifecycle control
Last updated: 2026-06-02

## Purpose

The execution module should turn Layer 8 Risk Gate outputs into auditable
order-lifecycle state.

It answers:

```text
What approved intent was selected from Risk Gate?
Was execution allowed for the requested mode?
Was the order staged, submitted, accepted, partially filled, filled, canceled,
rejected, or blocked before submit?
What idempotency key, adapter events, and receipt prove what happened?
What state should be handed to post-trade review?
```

It does not answer:

```text
Should this trade exist?
Is the strategy good?
May live execution occur?
Should risk limits be overridden?
What is the final portfolio allocation?
```

## Proposed Responsibilities

Implemented MVP responsibilities:

```text
consume RiskGateSnapshot and RiskGateReceipt lineage
select only approved paper-review decisions
build ExecutionIntent
perform adapter permission and pre-submit checks
derive deterministic idempotency keys
stage ExecutionOrderRequest
submit only through a paper/fake adapter when explicitly requested
normalize order lifecycle events
preserve raw adapter events
write ExecutionSnapshot and ExecutionReceipt
handoff final state for post-trade layers
```

## Non-Goals

```text
no live execution in MVP
no strategy generation
no risk override
no final sizing beyond approved intent
no full FIX engine
no smart order router
no claim of achieved best execution
```

## Inputs

```text
RiskGateSnapshot
RiskGateReceipt ref
RiskGateDecision
ExecutionContext
operator execute flag
adapter mode
```

## Outputs

```text
ExecutionIntent
ExecutionOrderRequest
ExecutionEvent
ExecutionQuality
ExecutionLineage
ExecutionSnapshot
ExecutionReceipt
```

Runtime artifacts:

```text
data/normalized/executions/
data/receipts/executions/
```

Task:

```text
task execution:graph
```

## State Vocabulary

```text
not_submitted
staged
submitted_paper
accepted
partially_filled
filled
cancel_requested
canceled
rejected
blocked_before_submit
reconciled
```

## Quality / Lineage / Receipt Strategy

Quality should require:

```text
risk_gate_lineage_present
approved_decision_required
paper_mode_required
live_mode_blocked
human_review_satisfied_when_required
idempotency_key_present
order_request_matches_approved_intent
raw_adapter_events_preserved
final_state_present
receipt_written
```

Lineage should record:

```text
input_risk_gate_snapshot_id
input_risk_gate_receipt_ref
decision_ids
adapter_name
adapter_mode
idempotency_key
order_request_hash
transform_version
output_hash
output_ref
```

## Current Workflow

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

## Institutional References

```text
BlackRock Aladdin for integrated order/execution workflow
FIX for standard order and execution message semantics
FINRA Rule 5310 for best-execution evidence expectations
Alpaca order docs for paper broker lifecycle and client order IDs
```

## Next Implementation Slice

Implemented first slice:

```text
src/finharness/execution.py
src/finharness/execution_graph.py
scripts/run_execution_graph.py
tests/test_execution.py
task execution:graph
```

## Upgrade Log

### 2026-06-02: Execution Layer MVP

Why:

```text
After Risk Gate, FinHarness needed an auditable execution layer that can stage
or paper-submit only approved decisions while blocking live execution.
```

What changed:

```text
Added ExecutionSourceSpec, ExecutionContext, ExecutionIntent,
ExecutionOrderRequest, ExecutionEvent, ExecutionQuality, ExecutionLineage,
ExecutionSnapshot, ExecutionReceipt, and ExecutionBundle.
Added strict LangGraph execution subgraph.
Added fake paper adapter for deterministic tests.
Added task execution:graph.
Added tests for dry-run staging, paper submit, live hard block, blocked Risk
Gate input, idempotency, partial fill, cancel, graph output, and persistence.
```

Result:

```text
Layer 9 can now consume RiskGateSnapshot evidence and produce ExecutionSnapshot
+ ExecutionReceipt while keeping execution_allowed=false and live execution
blocked.
```
