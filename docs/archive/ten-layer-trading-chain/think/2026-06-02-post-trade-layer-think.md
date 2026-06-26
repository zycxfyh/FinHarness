# Think: Layer 10 Post-Trade

Date: 2026-06-02
Layer: 10-post-trade

## Core Frame

Layer 10 is where execution evidence becomes accountability. Layer 9 answers
"what happened to the order lifecycle?" Layer 10 answers "what does that mean
for reconciliation, cost, exceptions, and review?"

The safest default is conservative classification. A staged order is not a
trade. A partial fill is not a clean success. A reject is not a silent no-op.
Missing lineage is a failed post-trade record.

## Layer Contract

Input:

```text
ExecutionSnapshot
ExecutionReceipt reference
PostTradeContext
optional fee/slippage assumptions
optional account/custody references
```

Output:

```text
PostTradeReconciliation
PostTradeCostEstimate
PostTradeException
PostTradeQuality
PostTradeLineage
PostTradeSnapshot
PostTradeReceipt
```

## Quality Checks

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

## First MVP

The first slice should use the fake-paper ExecutionSnapshot already produced by
Layer 9 tests. It should not require a broker, custodian, or accounting system.

Good first tests:

```text
filled execution produces reconciled_filled
partial fill produces partial_fill_exception
canceled execution produces reconciled_canceled
rejected execution produces reconciled_rejected
staged dry-run produces staged_no_trade
missing receipt lineage fails quality
no output contains order creation language
```

