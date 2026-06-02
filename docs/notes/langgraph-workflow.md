# LangGraph Workflow

## Purpose

LangGraph is now the orchestration layer for the finance workflow.

The OpenAI Agents SDK tool `run_finance_graph_workflow` calls this graph instead of manually chaining steps inside the tool.

## Graph Nodes

`src/finharness/finance_graph.py` defines:

- `data_entry`: runs OpenBB quote, yfinance historical data, metrics, Backtrader, and note generation.
- `risk_eval`: runs promptfoo assertions against the generated risk note.
- `final`: collects the workflow and eval outputs into a compact result.

## Run

```bash
task workflow:data-entry
```

## Cognitive Engineering Workflow

FinHarness also has a LangGraph workflow for project cognition:

```text
idea
-> note
-> proposal
-> implementation plan
-> review
-> lesson
-> receipt
-> final
```

Implementation:

```text
src/finharness/cognitive_graph.py
scripts/run_cognitive_flow.py
tests/test_cognitive_graph.py
```

Run it with:

```bash
task workflow:cognitive -- --topic "Events layer MVP" --thought "Use this flow before building events." --layer events
```

This workflow writes:

```text
ideas/YYYY-MM-DD-*.md
docs/notes/YYYY-MM-DD-*-workflow-note.md
docs/proposals/YYYY-MM-DD-*.md
docs/reviews/YYYY-MM-DD-*.md
docs/lessons/YYYY-MM-DD-*.md
data/receipts/cognitive-graph/*.json
```

Boundary:

```text
It writes project knowledge artifacts only.
It does not authorize trading, mutate broker state, or claim that an idea is
validated.
```

The graph still uses Yahoo Finance/yfinance for historical prices, not TradingView/TV data.

## Layer Execution Standard

The standard layer workflow is:

```text
source / input
-> fetch / compute
-> normalize
-> quality
-> lineage
-> snapshot
-> receipt
-> consumer handoff
-> review hook
```

Current coverage:

```text
market data:
  implemented as a strict subgraph in market_data_graph.py:
  source_config -> fetch_market_data -> normalize_ohlcv -> quality -> lineage
  -> snapshot -> receipt -> consumer_handoff -> review_hook -> final.

indicators:
  implemented as a strict subgraph in indicator_graph.py:
  source_config -> load_market_data -> compute_indicators -> quality -> lineage
  -> snapshot -> receipt -> consumer_handoff -> review_hook -> final.

events:
  implemented in events_graph.py:
  source_config -> fetch_sec_edgar -> normalize_filings -> quality -> lineage
  -> snapshot -> receipt -> consumer_handoff -> review_hook -> final.

interpretation:
  implemented in interpretation_graph.py:
  source_config -> load_event_snapshot -> extract_candidate_events
  -> interpret_impact_paths -> build_scenarios -> check_counterevidence
  -> quality -> lineage -> snapshot -> receipt -> consumer_handoff
  -> review_hook -> final.

daily_evidence:
  implemented in daily_evidence_graph.py:
  source_config -> market_data -> market_quality_gate -> indicators
  -> indicator_quality_gate -> events -> events_quality_gate -> interpretation
  -> interpretation_quality_gate -> evidence_bundle -> receipt -> review_hook
  -> final.

  any quality gate failure routes to:
  failed_receipt -> review_hook -> final.

  review_hook writes:
  docs/reviews/YYYY-MM-DD-daily-evidence-*.md.

hypotheses:
  planned as hypotheses_graph.py:
  source_config -> load_interpretation_snapshot -> select_hypothesis_candidates
  -> formulate_hypotheses -> attach_disconfirming_evidence
  -> attach_validation_plan -> quality -> lineage -> snapshot -> receipt
  -> consumer_handoff -> review_hook -> final.
```

Run the Events graph with:

```bash
task events:snapshot
```

Run the first two layer graphs with:

```bash
task market-data:graph
task indicators:graph
task interpretation:graph
task workflow:daily-evidence
planned: task hypotheses:graph
```

The Events graph writes:

```text
data/raw/events/sec-edgar/
data/normalized/events/sec-edgar/
data/receipts/events/
```

See:

```text
docs/notes/2026-06-01-layer-execution-workflows.md
```
