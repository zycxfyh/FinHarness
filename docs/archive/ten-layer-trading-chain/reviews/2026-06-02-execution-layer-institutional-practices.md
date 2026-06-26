# Review: Execution Layer Institutional Practices

Date: 2026-06-02
Status: open
Related proposal: /root/projects/finharness/docs/proposals/2026-06-02-execution-layer-institutional-practices.md
Related receipt: /root/projects/finharness/data/receipts/cognitive-graph/20260602T150844Z-execution-layer-institutional-practices.json
Related module: /root/projects/finharness/docs/modules/09-execution.md

## Summary

The cognitive workflow was executed and the placeholder artifacts were upgraded
into Layer 9 Execution research, think, and proposal documents. This is a
research/design review only; no execution code has been implemented yet.

## Expected

The artifacts should make the next Layer 9 implementation action clear while
keeping the execution boundary conservative:

```text
consume only Risk Gate outputs
default to dry-run/paper
block live execution
preserve order lifecycle evidence
avoid overclaiming best execution
```

## Actual

The research now maps public institutional practices into a FinHarness execution
graph contract. Implementation evidence remains pending.

## Evidence

- Idea: /root/projects/finharness/ideas/2026-06-02-execution-layer-institutional-practices.md
- Research note: /root/projects/finharness/docs/notes/2026-06-02-execution-layer-institutional-practices.md
- Think note: /root/projects/finharness/docs/think/2026-06-02-execution-layer-think.md
- Proposal: /root/projects/finharness/docs/proposals/2026-06-02-execution-layer-institutional-practices.md
- Module draft: /root/projects/finharness/docs/modules/09-execution.md
- Cognitive receipt: /root/projects/finharness/data/receipts/cognitive-graph/20260602T150844Z-execution-layer-institutional-practices.json

## Classification

research complete / implementation pending

## Root Causes / Conditions

Layer 9 is sensitive because it is the first layer adjacent to broker/venue
actions. The project needs explicit artifact boundaries before code to prevent
execution semantics from drifting into strategy, sizing, or live-trading
authorization.

## Lessons

Institutional execution patterns are useful because they force separation:
intent, risk approval, order staging, execution events, and post-trade handoff
are different evidence objects.

## Actions

Implement the MVP only after adding tests that prove Risk Gate cannot be
bypassed, live execution is blocked, idempotency is enforced, and partial-fill /
cancel / reject events remain visible in receipts.
