# Note: Post-Trade Layer Institutional Practices

Date: 2026-06-02
Layer: 10-post-trade
Source idea: /root/projects/finharness/ideas/2026-06-02-post-trade-layer-institutional-practices.md

## Summary

Layer 10 should model the institutional post-trade desk: reconcile what the
execution layer intended with what actually happened, preserve exceptions, and
prepare evidence for portfolio, accounting, performance, and review workflows.
It should not route, amend, cancel, or resubmit orders. Its output is evidence.

## Institutional Pattern

Top institutions generally separate the trade lifecycle into front-office
decisioning, execution, and post-trade operations:

```text
execution events / fills
-> trade capture and allocation
-> confirmation / affirmation
-> clearing and settlement awareness
-> custody / accounting reconciliation
-> exception management
-> transaction cost analysis
-> performance attribution
-> audit and regulatory records
```

DTCC's institutional trade processing material frames post-trade as the area
after execution where operational workflows move trades toward matching,
settlement, and exception resolution. Bloomberg AIM describes investment
management workflows that include reconciliation and IBOR support alongside
order and portfolio management. LSEG TORA positions post-trade analytics around
transaction cost analysis and compliance reporting. CFA Institute material on
transaction cost analysis emphasizes implementation shortfall and measuring the
cost of implementing investment decisions.

For FinHarness, the useful translation is not a full middle-office stack. It is
a typed evidence layer that refuses to lose the distinction between intended
order, submitted order, actual fill, partial fill, cancel, reject, and pending
state.

## Trader / Desk Workflow Translation

A post-trade review asks:

```text
What did Execution intend and stage?
What did the adapter report?
Was anything actually filled?
Was the fill complete, partial, canceled, or rejected?
What quantity remains unresolved?
What reference price was used?
What execution price, slippage, and estimated cost can be measured?
Were fees, commissions, or spread assumptions available?
What settlement/accounting/performance handoff is allowed?
What exceptions require human review?
```

This is how a good trading process turns action into learning. A filled paper
order can feed performance attribution. A partial fill should create an
exception. A rejected order should teach about permissions, liquidity, or
adapter behavior. A staged-only order should not be counted as a position.

## FinHarness Layer 10 Boundary

Layer 10 may:

```text
consume ExecutionSnapshot and ExecutionReceipt lineage
classify final execution state
reconcile requested quantity versus filled quantity
compute simple slippage and implementation-cost evidence when prices exist
preserve rejects, cancels, partial fills, and staged-only states
write PostTradeSnapshot and PostTradeReceipt
handoff to portfolio/accounting/performance review
```

Layer 10 must not:

```text
create orders
modify orders
resubmit rejected orders
turn staged requests into positions
hide partial-fill or cancel state
claim settlement or accounting completion without external evidence
claim best execution was achieved
```

## Proposed State Vocabulary

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

## Proposed Metrics

MVP metrics can be deterministic and conservative:

```text
requested_quantity
filled_quantity
remaining_quantity
reference_price
average_fill_price
slippage_per_unit
slippage_total
gross_notional
estimated_fees
estimated_total_cost
```

If a price is missing, the metric should be null and an exception should explain
why.

## Proposed LangGraph Shape

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

## Evidence Sources

- DTCC institutional trade processing: https://www.dtcc.com/institutional-trade-processing
- Bloomberg AIM investment management: https://www.bloomberg.com/professional/products/asset-management/investment-and-order-management/aim/
- LSEG TORA transaction cost analysis: https://www.lseg.com/en/data-analytics/investment-solutions/tora
- CFA Institute transaction cost analysis overview: https://rpc.cfainstitute.org/research/foundation/2007/transaction-cost-analysis

