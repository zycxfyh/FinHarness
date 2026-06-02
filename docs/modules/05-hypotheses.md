# Module: Hypotheses

Status: planned MVP
Owner: FinHarness
Layer: 5 - Hypotheses / thesis generation
Last updated: 2026-06-02

## Purpose

The hypotheses module turns source-backed interpretations into testable,
falsifiable research hypotheses.

It answers:

```text
What exactly would have to be true for this interpretation to matter?
What observable evidence should confirm it?
What observable evidence should disconfirm it?
What horizon is the hypothesis about?
What should the validation layer test next?
```

It does not answer:

```text
Should we trade?
```

## Current Responsibilities

Planned MVP responsibilities:

```text
consume InterpretationSnapshot evidence
promote selected interpretation candidates into HypothesisRecord objects
separate hypothesis text from source facts and validation results
define expected observations and falsification triggers
define validation plan for market, indicator, event, and review checks
require disconfirming evidence before handoff
write HypothesisSnapshot, HypothesisQuality, HypothesisLineage, and
HypothesisReceipt
handoff only to validation and human review
```

## Non-Goals

```text
no trade authorization
no buy/sell/hold recommendation
no position sizing
no broker/exchange instructions
no price target
no claim that a hypothesis is validated
no ranking hypotheses by PnL in the first MVP
no LLM-generated claim without source refs and quality gates
```

## Inputs

Planned inputs:

```text
InterpretationSnapshot
InterpretationReceipt ref
MarketDataSnapshot refs
IndicatorSnapshot refs
EventSnapshot refs
prior reviews / lessons where available
human-selected focus symbols or max hypotheses
```

## Outputs

Planned outputs:

```text
HypothesisRecord
HypothesisSnapshot
HypothesisQuality
HypothesisLineage
HypothesisReceipt
validation_plan
disconfirming_evidence
human review questions
```

Downstream consumers:

```text
Validation layer
Review/reporting workflows
Human virtual training workflow
Proposal layer later, only after validation
```

Runtime artifacts:

```text
data/normalized/hypotheses/
data/receipts/hypotheses/
```

Current implementation:

```text
not implemented yet
```

Tasks:

```text
planned: task hypotheses:graph
```

## Mature Wheels / External Systems

Institutional references:

```text
Man AHL:
  scientific, empirical investing; trade only ideas and theories that can be
  tested and proved.

AQR:
  systematic investing grounded in economic theory; research precision from
  design to implementation; multiple-testing awareness.

Bridgewater:
  idea meritocracy, radical truth/transparency, willingness to expose thoughts
  and be wrong.

BlackRock / Aladdin:
  risk and scenario context; risk models are assumption-bound and cannot
  predict loss under all market conditions.
```

Local first MVP should use:

```text
rules and structured templates first
LLM assistance only as draft text after source-linking exists
quality gates that block recommendation language and untestable claims
```

References:

```text
https://www.man.com/ahl
https://www.aqr.com/What-We-Do/Our-Approach
https://www.aqr.com/Insights/Research/Journal-Article/A-Data-Science-Solution-to-the-Multiple-Testing-Crisis-in-Financial-Research?aqrPDF=1
https://www.bridgewater.com/culture/bridgewaters-idea-meritocracy
https://www.blackrock.com/aladdin/products/aladdin-risk
https://www.blackrock.com/us/individual/literature/whitepaper/alpha-reimagined-en.pdf
```

## Quality / Lineage / Receipt Strategy

Quality should include:

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

Lineage should include:

```text
input_interpretation_snapshot_id
input_interpretation_receipt_ref
input_event_snapshot_id
interpretation_record_ids
event_record_ids
market_snapshot_refs
indicator_snapshot_refs
method
model/provider if any
prompt/template version if any
transform_version
output_hash
output_ref
```

Receipt object:

```text
HypothesisReceipt
```

Permission boundary:

```text
HypothesisSnapshot.execution_allowed = false
```

## Proposed First Slice

```text
source:
  InterpretationSnapshot from SEC EDGAR Interpretation MVP

universe:
  AAPL, MSFT, GOOGL, AMZN, NVDA, META, TSLA
  SPY, QQQ as context only

method:
  rule-guided hypothesis template

max hypotheses:
  10 per run

output:
  HypothesisSnapshot + HypothesisReceipt
  each record contains:
    source-backed hypothesis
    expected observations
    falsification triggers
    validation plan
    review questions
```

## Target Workflow

```text
START
-> source_config
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
-> END
```

## Upgrade Log

### 2026-06-02: Hypotheses Layer Design

Why:

```text
After Interpretation, FinHarness needs a separate layer that converts meaning
into falsifiable research hypotheses without jumping into proposals or trades.
```

What changed:

```text
Added proposed module document, institutional practice scan, and MVP proposal.
```

Evidence:

```text
docs/notes/2026-06-02-hypotheses-layer-institutional-practices.md
docs/proposals/2026-06-02-hypotheses-layer-sec-edgar-mvp.md
```

Risks:

```text
hypotheses can become disguised recommendations
LLM text can mix temporal contexts or overclaim
validation plans can be too vague to test
multiple-testing and selection bias can make weak hypotheses look strong
```

Next:

```text
Implement HypothesisSnapshot and HypothesisReceipt.
Add a strict LangGraph subgraph.
Run it from an InterpretationSnapshot only.
Keep execution permission disabled.
```
