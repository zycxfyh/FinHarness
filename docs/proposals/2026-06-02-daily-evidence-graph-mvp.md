# Proposal: Daily Evidence Graph MVP

Date: 2026-06-02
Status: implemented MVP
Related workflows:

```text
market_data_graph
indicator_graph
events_graph
interpretation_graph
daily_evidence_graph
```

## Problem

The first four FinHarness layers are implemented as independent graphs, but
daily virtual training needs one auditable workflow that bundles them into a
single evidence chain.

Without a total graph, the workflow has gaps:

```text
market and indicator evidence can be disconnected from events
events and interpretations may miss upstream snapshot refs
quality failures can continue downstream without an explicit stop
daily review has no single receipt
```

## Goals

```text
run Layer 1 Market Data for configured market context symbols
run Layer 2 Indicators using the exact MarketDataSnapshot/history already fetched
run Layer 3 Events with linked market and indicator snapshot refs
run Layer 4 Interpretation with linked market and indicator snapshot refs
route quality failures to a failed DailyEvidenceReceipt
write DailyEvidenceSnapshot and DailyEvidenceReceipt
write a docs/reviews daily evidence review draft
keep execution permission disabled
```

## Non-Goals

```text
no trade proposal
no risk approval
no broker/exchange action
no hypothesis validation
no automatic review write-up yet
```

## Workflow

```text
source_config
-> market_data
-> market_quality_gate
-> indicators
-> indicator_quality_gate
-> events
-> events_quality_gate
-> interpretation
-> interpretation_quality_gate
-> evidence_bundle
-> receipt
-> review_hook
-> final
```

Failure route:

```text
any quality_gate failure
-> failed_receipt
-> review_hook
-> final
```

No-event route:

```text
events quality OK but event_count = 0
-> no_events_bundle
-> warning receipt
-> review_hook
-> final
```

## Implementation Evidence

```text
src/finharness/daily_evidence.py
src/finharness/daily_evidence_graph.py
scripts/run_daily_evidence_graph.py
tests/test_daily_evidence_graph.py
task workflow:daily-evidence
docs/reviews/YYYY-MM-DD-daily-evidence-*.md
```

Related fixes:

```text
src/finharness/indicator_graph.py:
  can reuse upstream MarketDataSnapshot/history records.

src/finharness/events_graph.py:
  accepts linked market/indicator snapshot refs.

src/finharness/interpretation_graph.py:
  accepts linked market/indicator snapshot refs.
```

## Success Signal

```text
Daily graph final output includes:
  quality_ok
  failed_layers
  market_snapshot_refs
  indicator_snapshot_refs
  event_snapshot_ref
  interpretation_snapshot_ref
  receipt_ref
  execution_allowed=false
```

## Test Plan

```text
unit:
  graph compiles
  success path links refs through events and interpretation
  indicators reuse market data without calling market graph again
  market quality failure stops downstream layers

integration:
  task workflow:daily-evidence

project checks:
  task lint
  task test
```

## Risks

```text
The graph still runs market/indicator only for configured market context symbols.
The review hook is still a prompt, not an automatic docs/reviews artifact.
Network-backed SEC EDGAR runs can fail from external availability.
```
