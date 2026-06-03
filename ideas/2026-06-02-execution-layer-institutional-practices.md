# Idea: Execution Layer Institutional Practices

idea_id: 2026-06-02-execution-layer-institutional-practices
date: 2026-06-02
source: user-request-institutional-research
layer: 9-execution
status: captured

## Raw Thought

Research how top institutions, traders, brokers, and venues implement the ninth FinHarness layer: execution after Risk Gate. Translate public institutional practices into a typed LangGraph layer with execution intent consumption, broker/venue adapter boundary, order staging, idempotency, pre-submit checks, paper/live permission gates, execution receipts, partial-fill/cancel handling, and post-trade handoff. The layer may prepare and route only permissioned actions; it must not bypass Risk Gate or create autonomous live trading.

## Hypothesis

FinHarness Layer 9 should be an Execution layer, not a strategy or risk layer.
It should consume only Layer 8 Risk Gate outputs, translate approved paper-mode
actions into staged broker/venue order requests, track lifecycle events, and
write receipts that preserve pre-submit checks, idempotency keys, order events,
fills, cancels, rejects, and post-trade handoff state.

## Why It Might Matter

Top institutional execution workflows separate portfolio intent, compliance/risk
approval, order staging, execution management, and post-trade reconciliation.
That separation keeps traders from treating "a good idea" as "an executable
order". FinHarness needs the same boundary: Layer 9 may prepare and route
permissioned actions, but it must not override Layer 8, invent new trades, or
enable autonomous live trading.

## Testable Experiment

Create a typed LangGraph Execution MVP that can run in dry-run/paper mode from a
RiskGateSnapshot. The graph should emit a deterministic ExecutionSnapshot and
ExecutionReceipt for:

```text
risk gate blocked -> no order request submitted
risk gate paper-review-approved -> staged or submitted paper order
missing human review -> blocked before submit
duplicate idempotency key -> no duplicate submission
partial fill / cancel / reject event -> preserved lifecycle event
```

## Success Signal

The next implementation can start from the proposal without re-researching the
institutional model, and tests can prove that execution cannot bypass Risk Gate.

## Risk Or Failure Mode

The main failure mode is accidental authorization creep: an execution module can
quietly become a live-trading agent if it accepts raw strategy signals, ignores
Risk Gate lineage, or treats broker acknowledgement as proof that the action was
safe. The MVP must default to dry-run/paper and keep live execution explicitly
out of scope.

## Links

- Research note: docs/notes/2026-06-02-execution-layer-institutional-practices.md
- Think note: docs/think/2026-06-02-execution-layer-think.md
- Proposal: docs/proposals/2026-06-02-execution-layer-institutional-practices.md
- Review: docs/reviews/2026-06-02-execution-layer-institutional-practices.md
- Lesson: docs/lessons/2026-06-02-execution-layer-institutional-practices.md
