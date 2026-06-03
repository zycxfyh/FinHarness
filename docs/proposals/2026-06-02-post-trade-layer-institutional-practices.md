# Proposal: Post-Trade Layer Institutional Practices

Date: 2026-06-02
Status: draft
Related idea: /root/projects/finharness/ideas/2026-06-02-post-trade-layer-institutional-practices.md
Related note: /root/projects/finharness/docs/notes/2026-06-02-post-trade-layer-institutional-practices.md
Related think: /root/projects/finharness/docs/think/2026-06-02-post-trade-layer-think.md
Related module: docs/modules/10-post-trade.md
Related ADR:

## Problem

FinHarness now has a paper Execution layer, but execution evidence still needs a
post-trade layer that classifies lifecycle outcomes, reconciles quantities,
estimates costs where possible, flags exceptions, and hands off reviewable state
to portfolio/accounting/performance workflows.

## User / Workflow

The users are the human operator, future AI agent, and review workflow that need
to know what a paper execution actually means after fills, partial fills,
cancels, rejects, or staged-only states.

## Goals

```text
consume ExecutionSnapshot and ExecutionReceipt lineage
classify final execution lifecycle state
reconcile requested, filled, and remaining quantities
compute simple TCA/slippage estimates where data exists
preserve cancels, rejects, partial fills, and staged-only exceptions
write PostTradeSnapshot and PostTradeReceipt
handoff reviewable state to portfolio/accounting/performance layers
```

## Non-Goals

```text
create, modify, cancel, or resubmit orders
claim settlement completion
claim accounting completion
claim best execution was achieved
hide partial fills, rejects, or cancels
generate portfolio allocation changes
```

## Evidence

- Idea: /root/projects/finharness/ideas/2026-06-02-post-trade-layer-institutional-practices.md
- Research note: /root/projects/finharness/docs/notes/2026-06-02-post-trade-layer-institutional-practices.md
- Think note: /root/projects/finharness/docs/think/2026-06-02-post-trade-layer-think.md
- DTCC institutional trade processing: https://www.dtcc.com/institutional-trade-processing
- Bloomberg AIM: https://www.bloomberg.com/professional/products/asset-management/investment-and-order-management/aim/
- LSEG TORA: https://www.lseg.com/en/data-analytics/investment-solutions/tora
- CFA Institute TCA: https://rpc.cfainstitute.org/research/foundation/2007/transaction-cost-analysis
- Project rule: AGENTS.md

## Design

Implement a typed Post-Trade graph:

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

The graph should default to evidence-only processing. It should not call any
broker or venue adapter and should never produce an order request.

## Inputs / Outputs

Typed inputs:

```text
ExecutionSnapshot
ExecutionReceipt reference
PostTradeContext
fee assumptions
reference price / fill price evidence
optional account/custody references
```

Typed outputs:

```text
PostTradeReconciliation
PostTradeCostEstimate
PostTradeException
PostTradeQuality
PostTradeLineage
PostTradeSnapshot
PostTradeReceipt
```

## Quality / Lineage / Receipt

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

The receipt should record the input ExecutionSnapshot id, input ExecutionReceipt
ref, final post-trade status, reconciliation rows, cost estimates, exception
list, and handoff targets.

## Risks

```text
staged orders are counted as trades
partial fills are flattened into success
rejects/cancels are hidden
TCA numbers are reported without input disclosure
settlement/accounting completion is overclaimed
post-trade layer generates new order intent
```

## Success Signal

Tests prove that filled, partial, canceled, rejected, and staged-only
ExecutionSnapshots produce distinct post-trade states, and no output contains
order-creation authority.

## Review Plan

After implementation, run focused Layer 10 tests, then `task lint`, `task test`,
and `task check`. Update the review with command evidence, scoped debt, and
receipt paths.
