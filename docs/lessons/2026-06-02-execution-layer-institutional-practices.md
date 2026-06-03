# Lesson: Execution Layer Institutional Practices

Date: 2026-06-02
Status: draft
Source reviews:
- /root/projects/finharness/docs/reviews/2026-06-02-execution-layer-institutional-practices.md
Source ideas:
- /root/projects/finharness/ideas/2026-06-02-execution-layer-institutional-practices.md
Affected modules:
- 09-execution

## Lesson

Execution should be modeled as an evidence-preserving control workflow, not as
the moment a strategy "places an order". The layer must keep intent, permission,
order request, broker/venue event, and final handoff separate.

## Why It Matters

Layer 9 is adjacent to real broker behavior. If it accepts raw strategy signals
or treats Risk Gate approval as live authorization, the system can accidentally
turn research automation into execution automation.

## Evidence

- /root/projects/finharness/docs/notes/2026-06-02-execution-layer-institutional-practices.md
- /root/projects/finharness/docs/proposals/2026-06-02-execution-layer-institutional-practices.md
- /root/projects/finharness/docs/reviews/2026-06-02-execution-layer-institutional-practices.md

## Rule / Heuristic

Default execution graphs to receipts, not orders. Require Risk Gate lineage,
paper-mode permission, idempotency, and preserved lifecycle events before any
adapter can submit a request.

## Where It Should Live

docs/modules/09-execution.md | tests/test_execution.py | future ADR if live
execution is ever considered
