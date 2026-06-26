# Proposal: Hypotheses Layer SEC EDGAR MVP

Date: 2026-06-02
Status: implemented MVP
Related module: docs/modules/05-hypotheses.md

## Problem

FinHarness can now turn official events into source-backed interpretations, but
it still needs a separate layer to convert those interpretations into
falsifiable research hypotheses.

Without this layer, the workflow can drift from:

```text
evidence -> interpretation
```

directly into:

```text
narrative -> trade urge
```

That is exactly what this project should avoid.

## Goals

```text
consume InterpretationSnapshot evidence
promote hypothesis candidates into HypothesisRecord objects
state a mechanism and horizon
state expected confirming observations
state disconfirming observations
state a validation plan for layer 6
write HypothesisSnapshot and HypothesisReceipt
keep execution permission disabled
```

## Non-Goals

```text
no buy/sell/hold recommendation
no position sizing
no broker instructions
no price target
no validation result
no automatic proposal generation
no open-ended LLM thesis without source refs
```

## First Slice

```text
source:
  InterpretationSnapshot from SEC EDGAR Events + Interpretation MVP

universe:
  AAPL, MSFT, GOOGL, AMZN, NVDA, META, TSLA
  SPY, QQQ as context only

method:
  rule-guided hypothesis template

limit:
  max 10 hypotheses per run
```

## Proposed Data Objects

```text
HypothesisSourceSpec
HypothesisRecord
HypothesisQuality
HypothesisLineage
HypothesisSnapshot
HypothesisReceipt
HypothesisBundle
```

## Proposed Record Fields

```text
hypothesis_id
source_interpretation_ids
source_event_ids
symbol
mechanism
hypothesis
horizon
expected_observations
disconfirming_observations
validation_plan
assumptions
confidence_prior
status
created_at_utc
```

## Quality Gates

```text
source_backed_hypotheses
testable_predictions_present
disconfirming_evidence_present
horizon_present
validation_plan_present
no_execution_language
no_recommendation_language
claim_not_marked_validated
temporal_context_separated
duplicate_hypothesis_check
missing_required_fields
```

## Workflow

```text
source_config
-> load_interpretation_snapshot
-> select_hypothesis_candidates
-> formulate_hypotheses
-> attach_disconfirming_evidence
-> attach_validation_plan
-> quality
-> lineage
-> snapshot
-> receipt
-> consumer_handoff
-> review_hook
-> final
```

## LangGraph Shape

```text
src/finharness/hypotheses.py
src/finharness/hypotheses_graph.py
scripts/run_hypotheses_graph.py
tests/test_hypotheses.py
task hypotheses:graph
```

## Consumer Handoff

Allowed outputs:

```text
validation plans
watch questions
human review prompts
hypothesis candidates for layer 6
```

Forbidden outputs:

```text
orders
position sizing
broker instructions
execution permission
trade recommendation
```

## Success Signal

```text
task hypotheses:graph produces HypothesisSnapshot + Receipt
quality gates pass
execution_allowed is false
consumer_handoff points only to validation/review
each hypothesis has at least one disconfirming observation
each hypothesis has a concrete validation plan
```

## Test Plan

```text
unit:
  quality blocks execution/recommendation language
  quality fails if no disconfirming observations
  quality fails if no validation plan
  bundle persists snapshot and receipt

graph:
  graph compiles
  graph runs with a mocked InterpretationSnapshot
  final reports workflow, quality_ok, execution_allowed=false, receipt_ref

integration:
  run from real task interpretation:graph output
```

## Risks

```text
LLM wording can overclaim
hypotheses can become disguised recommendations
validation plans can be too vague
multiple-testing can produce false confidence
current quote and historical context can be mixed
```

## Decision

Build this as a strict, non-execution layer.

Use deterministic templates first. Add LLM drafting later only if the output is
source-linked, quality-gated, and clearly marked as draft reasoning rather than
evidence.

## Implementation Evidence

Implemented files:

```text
src/finharness/hypotheses.py
src/finharness/hypotheses_graph.py
scripts/run_hypotheses_graph.py
tests/test_hypotheses.py
docs/modules/05-hypotheses.md
Taskfile.yml
```

Task:

```text
task hypotheses:graph
```

LLM boundary:

```text
HypothesisDraftProvider protocol
NullHypothesisDraftProvider default
HermesHypothesisDraftProvider reserved for /root/projects/hermes-agent
llm_enabled=false by default
```

MVP result:

```text
Hypotheses Graph consumes InterpretationSnapshot evidence and writes
HypothesisSnapshot + HypothesisReceipt. It preserves validation handoff only,
keeps execution_allowed=false, and blocks recommendation/execution language.
```
