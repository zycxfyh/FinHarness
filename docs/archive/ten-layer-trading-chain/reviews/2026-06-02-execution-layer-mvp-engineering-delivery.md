# Review: Execution Layer MVP Engineering Delivery

Date: 2026-06-02
Status: passed
Related proposal: /root/projects/finharness/docs/proposals/2026-06-02-execution-layer-institutional-practices.md
Related module: /root/projects/finharness/docs/modules/09-execution.md
Related receipt: /root/projects/finharness/data/receipts/engineering-delivery/20260602T152859Z-execution-layer-mvp.json

## Summary

Layer 9 Execution MVP has been implemented as a deterministic LangGraph layer.
It consumes RiskGateSnapshot evidence, stages order-shaped paper requests, uses a
fake paper adapter for submit/fill/cancel/reject lifecycle tests, persists
ExecutionSnapshot and ExecutionReceipt artifacts, and blocks live execution.

## Expected

```text
Risk Gate lineage is required
dry-run stages orders without broker submission
paper execute uses deterministic fake adapter
live execution is blocked before submit
duplicate idempotency does not submit twice
partial fill, cancel, and reject events are preserved
receipts are written
task execution:graph is available
```

## Actual

The implementation satisfies the expected MVP boundary. Live execution returns a
non-zero task result with `final_status=blocked_before_submit`, which is the
intended safety behavior.

## Evidence

Focused checks:

```text
PYTHONPATH=src uv run python -m unittest tests.test_execution
Ran 8 tests - OK

PYTHONPATH=src uv run python -m unittest tests.test_execution tests.test_risk_gate
Ran 14 tests - OK
```

Graph command variants:

```text
task execution:graph
quality_ok=true, mode=dry_run, final_status=staged, order_request_count=10

task execution:graph -- --paper --execute --fake-fill-mode filled
quality_ok=true, mode=paper, final_status=filled, order_request_count=10

task execution:graph -- --paper --execute --fake-fill-mode partial --quantity 4 --cancel-after-submit
quality_ok=true, mode=paper, final_status=canceled, event_count=50

task execution:graph -- --live --execute
quality_ok=false, mode=live, final_status=blocked_before_submit, order_request_count=0

task execution:graph -- --paper --execute --human-review-missing
quality_ok=false, mode=paper, final_status=blocked_before_submit, order_request_count=0

task execution:graph -- --paper --execute --fake-fill-mode reject
quality_ok=true, mode=paper, final_status=rejected, order_request_count=10
```

Project checks:

```text
task lint
All checks passed

task test
Ran 93 tests - OK

task rust:check
4 passed

task check
rust, lint, test, experiments, eval:smoke passed

task wheels:check
core wheels and promptfoo version check passed
```

## Classification

implemented MVP / no scoped debt

## Root Causes / Conditions

Layer 9 needed a fake paper adapter rather than a broker API integration so the
execution boundary could be proven without credentials, live services, or real
orders.

## Lessons

Execution tests should prove both positive lifecycle behavior and safe failure.
The live path should be tested as an intentional command failure, not hidden as
a green submit.

## Actions

Future work can add a real paper broker adapter behind the same interface, but
only after preserving the current Risk Gate, paper-mode, idempotency, and
receipt invariants.
