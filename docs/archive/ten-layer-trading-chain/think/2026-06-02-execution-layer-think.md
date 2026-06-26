# Think: Layer 9 Execution

Date: 2026-06-02
Layer: 9-execution

## Core Frame

Layer 9 is the first layer where an approved decision can become an order-shaped
action. That makes it dangerous in a different way from Layer 8. Risk Gate asks
"may this proceed?" Execution asks "what exactly happened when a permissioned
action was staged or submitted?"

The layer should therefore be conservative by design. Its default outcome is a
receipt, not an order. Submission happens only when the upstream decision allows
paper execution, the operator asks for execution, and the adapter confirms the
mode is paper.

## Layer Contract

Input:

```text
RiskGateSnapshot
RiskGateReceipt reference
ExecutionContext
adapter mode
operator execute flag
```

Output:

```text
ExecutionIntent
ExecutionOrderRequest
ExecutionEvent list
ExecutionQuality
ExecutionLineage
ExecutionSnapshot
ExecutionReceipt
```

The contract should be explicit enough that a future broker adapter can be
swapped without changing the institutional guarantees.

## Quality Checks

```text
risk_gate_lineage_present
approved_decision_required
paper_mode_required
human_review_required_when configured
idempotency_key_present
no_live_execution
order_request_matches_approved_intent
raw_adapter_events_preserved
final_state_present
receipt_written
```

## First MVP

The MVP should add a module doc and a typed graph, then wire a Taskfile command
similar to the Proposal and Risk Gate layers. It can use a fake in-memory paper
adapter for deterministic tests, plus an optional Alpaca paper adapter boundary
only when credentials and execute flags are present.

Good first tests:

```text
blocked Risk Gate emits blocked_before_submit
paper-approved Risk Gate emits staged order in dry-run
paper-approved + execute emits submitted_paper through fake adapter
live mode is blocked even when execute=true
duplicate idempotency does not submit twice
partial fill and cancel events are preserved in snapshot and receipt
```

