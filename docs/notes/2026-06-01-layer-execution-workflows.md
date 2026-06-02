# Layer Execution Workflows

Date: 2026-06-01

Purpose: define the engineering execution process for each FinHarness layer and
how those layers should enter LangGraph workflows.

## Current Judgment

FinHarness already has partial LangGraph workflows:

```text
finance_graph:
  data entry -> risk eval -> final

trade_graph:
  market data -> research -> account -> risk gate -> order plan -> execution
  -> receipt -> final

cognitive_graph:
  idea -> note -> proposal -> implementation plan -> review -> lesson
  -> receipt -> final
```

But the layer-by-layer execution process is not yet fully standardized.

This document defines the standard.

## Universal Layer Contract

Every serious layer should follow the same engineering shape:

```text
1. Source / Input
2. Fetch / Compute
3. Normalize
4. Quality
5. Lineage
6. Snapshot
7. Receipt
8. Consumer Handoff
9. Review Hook
```

The layer may do different domain work, but the workflow shell should stay
consistent.

## Required Objects Per Layer

Each layer should eventually expose:

```text
<Layer>SourceSpec
<Layer>Record or payload model
<Layer>Quality
<Layer>Lineage
<Layer>Snapshot
<Layer>Receipt
```

Examples:

```text
MarketDataSnapshot
IndicatorSnapshot
EventSnapshot
HypothesisSnapshot
ProposalSnapshot
RiskGateReceipt
ExecutionReceipt
ReviewReceipt
```

## Required Permission Boundary

Layers 1-6 describe evidence and reasoning. They do not authorize execution.

```text
1. Market Data:
  execution_allowed = false

2. Indicators:
  execution_allowed = false

3. Events:
  execution_allowed = false

4. Interpretation:
  execution_allowed = false

5. Hypotheses:
  execution_allowed = false

6. Validation:
  execution_allowed = false
```

Only later layers can move toward action, and only through gates:

```text
7. Proposal:
  proposes action, does not execute

8. Risk Gate:
  allows or blocks a proposal

9. Execution:
  executes only if explicit environment, human, and risk gates pass

10. Review:
  evaluates what happened and updates process memory
```

## Current Layer Workflows

### Layer 1: Market Data

Current status: implemented.

Workflow:

```text
source spec
-> fetch raw OHLCV / close data
-> normalize OHLCV
-> quality checks
-> lineage hashes
-> MarketDataSnapshot
-> DataReceipt
-> downstream consumers
```

Current integration:

```text
src/finharness/market_data.py
src/finharness/market_data_graph.py
src/finharness/workflow.py
src/finharness/trade_graph.py
scripts/run_market_data_graph.py
tests/test_market_data_graph.py
task market-data:graph
```

### Layer 2: Indicators

Current status: implemented.

Workflow:

```text
MarketDataSnapshot / normalized OHLCV
-> compute TA-Lib / pandas-ta features
-> indicator quality checks
-> indicator lineage
-> IndicatorSnapshot
-> IndicatorReceipt
-> downstream consumers
```

Current integration:

```text
src/finharness/indicator_layer.py
src/finharness/indicator_graph.py
src/finharness/workflow.py
scripts/run_indicator_graph.py
tests/test_indicator_graph.py
task indicators:graph
```

### Layer 3: Events

Current status: implemented MVP.

Target workflow:

```text
EventSourceSpec
-> fetch raw events
-> normalize EventRecord
-> entity/instrument mapping
-> event quality checks
-> event lineage
-> EventSnapshot
-> EventReceipt
-> human review / hypothesis candidate
```

Current integration:

```text
src/finharness/events.py
src/finharness/events_graph.py
scripts/run_events_snapshot.py
tests/test_events.py
task events:snapshot
```

First slice:

```text
SEC EDGAR filings for:
  AAPL, MSFT, GOOGL, AMZN, NVDA, META, TSLA

market context:
  SPY, QQQ
```

### Layer 4: Interpretation

Current status: implemented MVP.

Target workflow:

```text
InterpretationSourceSpec
-> load EventSnapshot
-> extract candidate events
-> separate facts from inference
-> classify impact paths and horizons
-> build scenarios
-> check counterevidence
-> interpretation quality checks
-> interpretation lineage
-> InterpretationSnapshot
-> InterpretationReceipt
-> hypothesis/review handoff
```

First slice:

```text
SEC EDGAR EventSnapshot interpretation for:
  AAPL, MSFT, GOOGL, AMZN, NVDA, META, TSLA

market context:
  SPY, QQQ
```

Current integration:

```text
src/finharness/interpretation.py
src/finharness/interpretation_graph.py
scripts/run_interpretation_graph.py
tests/test_interpretation.py
task interpretation:graph
```

### Layer 5: Hypotheses

Current status: planned MVP.

Target workflow:

```text
HypothesisSourceSpec
-> load InterpretationSnapshot
-> select hypothesis candidates
-> formulate falsifiable hypotheses
-> attach expected observations
-> attach disconfirming observations
-> attach validation plan
-> hypothesis quality checks
-> hypothesis lineage
-> HypothesisSnapshot
-> HypothesisReceipt
-> validation/review handoff
```

First slice:

```text
SEC EDGAR InterpretationSnapshot hypotheses for:
  AAPL, MSFT, GOOGL, AMZN, NVDA, META, TSLA

market context:
  SPY, QQQ

method:
  rule-guided template first
  LLM drafting only after source-linking and quality gates exist
```

Planned integration:

```text
src/finharness/hypotheses.py
src/finharness/hypotheses_graph.py
scripts/run_hypotheses_graph.py
tests/test_hypotheses.py
task hypotheses:graph
```

## Target LangGraph Shape

The layer execution graph should not be one giant graph at first.

Use composable subgraphs:

```text
cognitive_graph:
  governs ideas, proposals, reviews, lessons.

market_data_graph or node:
  produces market evidence.

indicator_graph or node:
  produces feature evidence.

events_graph or node:
  produces event evidence.

interpretation_graph or node:
  produces source-backed meaning, impact paths, scenarios, and watch questions.

hypotheses_graph or node:
  produces falsifiable hypotheses, disconfirming observations, and validation
  plans.

finance_daily_review_graph:
  combines market, indicators, events, and human review.

trade_graph:
  handles proposal/risk/execution only after earlier evidence exists.
```

## Proposed Daily Virtual Training Graph

For the next week, use this as the operational workflow:

```text
START
-> market_data
-> indicators
-> events
-> interpretation
-> evidence_bundle
-> human_review_prompt
-> review_receipt
-> END
```

Boundary:

```text
no order placement
no live execution
no automatic proposal execution
```

Current implementation:

```text
src/finharness/daily_evidence.py
src/finharness/daily_evidence_graph.py
scripts/run_daily_evidence_graph.py
tests/test_daily_evidence_graph.py
task workflow:daily-evidence
```

Quality routing:

```text
market_quality_gate
indicator_quality_gate
events_quality_gate
interpretation_quality_gate

any failed quality gate:
  -> failed_receipt
  -> review_hook
  -> final
```

This graph is for training the process before real-capital practice resumes.

## Proposed Events MVP Graph

After implementation, Events should have:

```text
START
-> source_config
-> fetch_sec_edgar
-> normalize_filings
-> quality
-> lineage
-> snapshot
-> receipt
-> consumer_handoff
-> review_hook
-> final
-> END
```

## Engineering Process For A New Layer

When adding a new layer:

```text
1. Write or update module doc.
2. Write proposal if the layer is substantial.
3. Define typed models.
4. Implement the smallest source/fetch/compute path.
5. Add normalization.
6. Add quality.
7. Add lineage.
8. Add snapshot + receipt.
9. Add tests.
10. Add script/task.
11. Add LangGraph node or subgraph.
12. Run the smallest relevant check.
13. Update module upgrade log.
14. If surprising, add review/lesson.
```

## Completion Criteria

A layer is not "done" when it can fetch data.

A layer reaches MVP done only when:

```text
typed output exists
quality report exists
lineage exists
receipt exists
tests pass
script/task exists
permission boundary is explicit
module doc upgrade log is updated
```

For user-facing daily practice, it also needs:

```text
human-readable summary
review questions
links to evidence
```

## Current Gap

Need next:

```text
1. Run Events + Interpretation MVPs for three trading days.
2. Review actual filings and generated interpretations manually.
3. Add market/indicator snapshot refs to the Events and Interpretation receipts.
4. Add daily virtual training graph:
   market_data -> indicators -> events -> interpretation -> review.
```
