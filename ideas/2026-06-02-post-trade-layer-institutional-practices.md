# Idea: Post-Trade Layer Institutional Practices

idea_id: 2026-06-02-post-trade-layer-institutional-practices
date: 2026-06-02
source: user-request-institutional-research
layer: 10-post-trade
status: captured

## Raw Thought

Research how top institutions, trading desks, brokers, custodians, and asset managers implement the tenth FinHarness layer after Execution: post-trade processing, reconciliation, transaction cost analysis, allocation, settlement awareness, exception management, performance attribution, and audit receipts. Translate public institutional practices into a typed LangGraph layer that consumes ExecutionSnapshot and ExecutionReceipt, never creates new orders, preserves fills/cancels/rejects, reconciles intended versus executed state, computes slippage and cost evidence where data exists, flags exceptions, writes post-trade receipts, and hands off to portfolio/accounting/performance review.

## Hypothesis

FinHarness Layer 10 should be a Post-Trade layer that consumes ExecutionSnapshot
evidence and turns executed, canceled, rejected, or staged order lifecycle data
into reconciliation, transaction-cost, exception, and performance-review
receipts. It must never create, modify, or resubmit orders.

## Why It Might Matter

Institutional trading workflows do not end at execution. Trading desks,
operations teams, brokers, custodians, and portfolio managers reconcile intended
orders against actual fills, allocations, settlement state, fees, slippage,
exceptions, and portfolio/accounting records. FinHarness needs this layer so
paper execution evidence becomes reviewable learning rather than a pile of raw
events.

## Testable Experiment

Create a typed LangGraph Post-Trade MVP that can consume an ExecutionSnapshot
and emit:

```text
staged-only execution -> pending_monitoring exception
filled execution -> fill reconciliation + slippage/TCA estimate
partial fill -> partial_fill exception + remaining quantity
canceled execution -> canceled reconciliation
rejected execution -> rejection exception
missing execution receipt -> lineage failure
```

## Success Signal

The next implementation can start from the proposal without re-researching
post-trade practice, and tests can prove Layer 10 cannot generate orders or hide
execution exceptions.

## Risk Or Failure Mode

The main failure mode is false reconciliation: treating a staged order as a
trade, flattening partial fills, ignoring rejects, or reporting performance from
incomplete lifecycle data. The MVP should prefer explicit exceptions over
optimistic accounting.

## Links

- Research note: docs/notes/2026-06-02-post-trade-layer-institutional-practices.md
- Think note: docs/think/2026-06-02-post-trade-layer-think.md
- Proposal: docs/proposals/2026-06-02-post-trade-layer-institutional-practices.md
- Review: docs/reviews/2026-06-02-post-trade-layer-institutional-practices.md
- Lesson: docs/lessons/2026-06-02-post-trade-layer-institutional-practices.md
