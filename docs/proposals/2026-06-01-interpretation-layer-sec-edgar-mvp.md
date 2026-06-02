# Proposal: Interpretation Layer SEC EDGAR MVP

Date: 2026-06-01
Status: implemented MVP
Related module: docs/modules/04-interpretation.md

## Problem

FinHarness can now produce official EventSnapshot evidence, but it needs a
separate layer to turn events into source-backed meaning without creating trade
recommendations.

## Goals

```text
consume EventSnapshot evidence
separate source facts from inference
classify impact paths, exposures, horizon, materiality, and confidence
generate base/bull/bear scenarios
require counterevidence and watch questions
write InterpretationSnapshot and InterpretationReceipt
keep execution permission disabled
```

## Non-Goals

```text
no buy/sell/hold recommendation
no position sizing
no broker instructions
no price target
no open-ended LLM analysis
no social-media interpretation
```

## Workflow

```text
source_config
-> load_event_snapshot
-> extract_candidate_events
-> interpret_impact_paths
-> build_scenarios
-> check_counterevidence
-> quality
-> lineage
-> snapshot
-> receipt
-> consumer_handoff
-> review_hook
-> final
```

## Implementation Evidence

```text
src/finharness/interpretation.py
src/finharness/interpretation_graph.py
scripts/run_interpretation_graph.py
tests/test_interpretation.py
task interpretation:graph
```

## Success Signal

```text
task interpretation:graph produces InterpretationSnapshot + Receipt
quality gates pass
execution_allowed is false
consumer_handoff excludes execution
review_hook is open for human review
```

## Implementation Evidence

Verified commands:

```text
uv run ruff check src/finharness/events.py src/finharness/interpretation.py src/finharness/interpretation_graph.py scripts/run_interpretation_graph.py tests/test_interpretation.py
PYTHONPATH=src uv run python -m unittest tests.test_interpretation tests.test_events
task interpretation:graph
```

First real run:

```text
workflow: langgraph_interpretation_v1
input_event_snapshot_id: evs_20260601T135723Z_220f609d
record_count: 30
quality_ok: true
execution_allowed: false
receipt_ref: data/receipts/interpretations/receipt_ints_20260601T135723Z_e63b4b27.json
quality gates:
  source_backed_claims: true
  counterevidence_present: true
  no_execution_language: true
  horizon_present: true
  confidence_bounded: true
  claim_evidence_separation: true
```
