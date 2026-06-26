# Module: Post-Trade

Status: implemented MVP
Owner: FinHarness
Layer: 10 - Post-Trade / reconciliation and execution review
Last updated: 2026-06-02

## Purpose

The post-trade module should turn Layer 9 Execution evidence into auditable
reconciliation, cost, exception, and review state.

It answers:

```text
Was anything actually filled?
Was the fill complete, partial, canceled, rejected, or only staged?
What quantity was requested, filled, and left unresolved?
What slippage or implementation-cost evidence can be computed?
What exceptions require review?
What can be handed to portfolio/accounting/performance layers?
```

It does not answer:

```text
Should a new order be created?
Should a rejected order be resubmitted?
Has settlement completed?
Has accounting/custody reconciliation completed?
Was best execution achieved?
Should the portfolio be rebalanced?
```

## Current Responsibilities

Implemented MVP responsibilities:

```text
consume ExecutionSnapshot and ExecutionReceipt lineage
classify final execution lifecycle state
reconcile requested, filled, and remaining quantities
compute conservative slippage/TCA estimates when input prices exist
preserve staged-only, partial-fill, cancel, and reject exceptions
write PostTradeSnapshot and PostTradeReceipt
handoff reviewable state to portfolio/accounting/performance layers
```

## Non-Goals

```text
no order creation
no order modification
no broker or venue calls
no settlement completion claims
no accounting completion claims
no best-execution certification
```

## Inputs

```text
ExecutionSnapshot
ExecutionReceipt ref
ExecutionEvent
PostTradeContext
fee/slippage assumptions
optional account/custody refs
```

## Outputs

```text
PostTradeReconciliation
PostTradeCostEstimate
PostTradeException
PostTradeQuality
PostTradeLineage
PostTradeSnapshot
PostTradeReceipt
```

Runtime artifacts:

```text
data/normalized/post-trade/
data/receipts/post-trade/
```

Task:

```text
task post-trade:graph
```

## State Vocabulary

```text
pending_monitoring
reconciled_filled
reconciled_canceled
reconciled_rejected
partial_fill_exception
staged_no_trade
lineage_failed
needs_human_review
```

## Quality / Lineage / Receipt Strategy

Quality should require:

```text
execution_lineage_present
execution_receipt_present
no_order_creation
final_execution_state_classified
filled_quantity_reconciled
partial_fill_exception_preserved
reject_cancel_exception_preserved
tca_inputs_disclosed
handoff_state_present
receipt_written
```

Lineage should record:

```text
input_execution_snapshot_id
input_execution_receipt_ref
execution_event_ids
execution_final_status
post_trade_status
transform_version
output_hash
output_ref
```

## Current Workflow

```text
source_config
-> load_execution_snapshot
-> lineage_check
-> lifecycle_classification
-> fill_reconciliation
-> tca_estimate
-> settlement_awareness
-> exception_detection
-> performance_handoff
-> quality
-> lineage
-> snapshot
-> receipt
-> review_hook
-> final
```

## Institutional References

```text
DTCC for post-execution trade processing and settlement workflows
Bloomberg AIM for reconciliation and investment book workflows
LSEG TORA for post-trade analytics / TCA / compliance reporting
CFA Institute for transaction cost analysis and implementation shortfall
```

## Next Implementation Slice

Implemented first slice:

```text
src/finharness/post_trade.py
src/finharness/post_trade_graph.py
scripts/run_post_trade_graph.py
tests/test_post_trade.py
task post-trade:graph
```

## Upgrade Log

### 2026-06-02: Post-Trade Layer MVP

Why:

```text
After Execution, FinHarness needed a final evidence layer that reconciles paper
execution lifecycle state without creating orders or overclaiming settlement,
accounting, best execution, or performance.
```

What changed:

```text
Added PostTradeSourceSpec, PostTradeContext, PostTradeReconciliation,
PostTradeCostEstimate, PostTradeException, PostTradeQuality, PostTradeLineage,
PostTradeSnapshot, PostTradeReceipt, and PostTradeBundle.
Added strict LangGraph post-trade subgraph.
Added task post-trade:graph.
Added tests for filled, partial, canceled, rejected, staged-only, missing
receipt lineage, graph output, persistence, and no order creation.
```

Result:

```text
Layer 10 can now consume ExecutionSnapshot evidence and produce
PostTradeSnapshot + PostTradeReceipt while keeping order_creation_allowed=false.
```
