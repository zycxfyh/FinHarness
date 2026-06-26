# Note: Execution Layer Institutional Practices

Date: 2026-06-02
Layer: 9-execution
Source idea: /root/projects/finharness/ideas/2026-06-02-execution-layer-institutional-practices.md

## Summary

Layer 9 should model institutional execution discipline: approved intent becomes
an order request only after explicit permission, pre-submit checks, idempotency,
adapter selection, and audit capture. Execution is not the place to decide
whether the trade is wise. It is the place to prove that an already-approved
action was staged, submitted, monitored, canceled, rejected, filled, or handed
off with complete lineage.

## Institutional Pattern

Top trading organizations tend to split execution across these functions:

```text
portfolio / strategy intent
-> compliance and risk approval
-> OMS order staging
-> EMS routing and execution
-> broker / venue acknowledgement
-> execution reports and fills
-> cancel / replace / exception handling
-> allocation, reconciliation, and TCA
```

Public institutional platforms use similar language. BlackRock describes
Aladdin for traders as combining order management and trade execution, including
native execution capabilities and fragmented liquidity access from the same
workflow. The useful FinHarness translation is not "copy Aladdin"; it is the
boundary: execution is connected to order management, liquidity access, and
post-trade state, while still depending on upstream controls.

FIX provides the industry message pattern: counterparties exchange orders and
execution information through standard workflows. FinHarness does not need a
full FIX engine for the MVP, but it should preserve FIX-like semantics:
client-order identity, new order request, acknowledgement, execution report,
partial fill, fill, cancel, cancel reject, and final state.

Best execution rules add the trader's quality obligation. FINRA Rule 5310 frames
reasonable diligence around market character, transaction size/type, markets
checked, quote accessibility, and order terms. For FinHarness, this becomes a
receipt obligation: record the routing policy, order type, reference price,
available quote/liquidity context, and reason the request was allowed or blocked.

Broker APIs expose the practical lifecycle. Alpaca documents client order IDs,
order submission, cancel/monitor operations, streaming updates, buying-power
checks, and statuses such as new, partially_filled, filled, canceled, expired,
replaced, accepted, pending_cancel, pending_replace, rejected, suspended, and
calculated. FinHarness should normalize broker-specific statuses into a smaller
internal state machine while preserving the raw broker event.

## Trader Workflow Translation

A disciplined trader or execution desk asks:

```text
What exactly was approved?
What account, instrument, side, quantity, order type, and time-in-force apply?
Is this paper, simulated, or live?
Has risk/compliance/human review allowed submission?
Has this order already been submitted under the same intent?
What did the broker or venue acknowledge?
What changed after partial fills, cancels, rejects, or market events?
What evidence can be reviewed later?
```

The Execution layer should answer those questions mechanically.

## FinHarness Layer 9 Boundary

Layer 9 may:

```text
consume RiskGateSnapshot / RiskGateReceipt lineage
build ExecutionIntent from approved decisions
perform adapter permission checks
stage paper order requests
submit to an explicit paper adapter when execute=true
normalize order lifecycle events
write execution receipts
handoff filled/canceled/rejected state to post-trade layers
```

Layer 9 must not:

```text
create a new strategy signal
change sizing beyond risk-gate-approved intent
override a blocked Risk Gate decision
convert paper approval into live execution
hide broker rejects or partial fills
treat a successful submit as successful execution
```

## Proposed State Machine

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

The state machine should keep both normalized internal status and raw adapter
status. That lets tests stay stable while preserving broker detail for review.

## Proposed LangGraph Shape

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

## Evidence Sources

- BlackRock Aladdin for traders: https://www.blackrock.com/aladdin/benefits/traders
- FINRA Rule 5310, Best Execution and Interpositioning: https://www.finra.org/finramanual/rules/r5310/
- FIX Trading Community overview: https://www.fixtrading.org/what-is-fix/
- Alpaca order lifecycle and client order IDs: https://docs.alpaca.markets/us/docs/orders-at-alpaca

