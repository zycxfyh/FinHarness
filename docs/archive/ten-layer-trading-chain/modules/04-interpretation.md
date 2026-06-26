# Module: Interpretation

Status: active MVP
Owner: FinHarness
Layer: 4 - Interpretation
Last updated: 2026-06-01

## Purpose

The interpretation module turns structured evidence into source-backed meaning,
impact paths, scenarios, counterevidence, and watch questions.

It answers:

```text
What might this event mean?
Which business or market mechanisms could it affect?
What horizon does it matter on?
What could prove this interpretation wrong?
What should be watched next?
```

It does not answer:

```text
Should we trade?
```

## Current Responsibilities

Current MVP responsibilities:

```text
consume EventSnapshot evidence
link interpretation claims back to EventRecord ids and payload refs
separate source facts from inference
classify impact paths and affected exposures
generate base/bull/bear or confirm/fade scenarios
require counterevidence and watch questions
write InterpretationSnapshot, InterpretationQuality, InterpretationLineage,
and InterpretationReceipt
handoff only to hypotheses, review, and risk notes
```

## Non-Goals

```text
no trade authorization
no buy/sell/hold recommendation
no position sizing
no broker/exchange instructions
no price target generation in the first MVP
no open-ended social-media interpretation
no claim that LLM output is evidence
```

## Inputs

Planned inputs:

```text
EventSnapshot
MarketDataSnapshot refs
IndicatorSnapshot refs
watchlist context
prior reviews / lessons where available
```

## Outputs

Planned outputs:

```text
InterpretationRecord
InterpretationSnapshot
InterpretationQuality
InterpretationLineage
InterpretationReceipt
watch questions
hypothesis candidates
risk review prompts
```

Downstream consumers:

```text
Hypothesis layer
Validation layer
Proposal layer later
Review/reporting workflows
Human virtual training workflow
```

## Mature Wheels / External Systems

Institutional references:

```text
BlackRock Aladdin:
  scenario, stress, and portfolio risk context.

MSCI Barra:
  factor exposures, risk decomposition, and what-if analysis.

FactSet / S&P Capital IQ / AlphaSense / LSEG:
  source-backed document intelligence, filings/transcripts/news workflow,
  sentiment/topic organization, analyst productivity.
```

Local first MVP should use:

```text
rules and structured templates first
LLM assistance only after source-linking and quality gates exist
```

Runtime artifacts:

```text
data/normalized/interpretations/
data/receipts/interpretations/
```

Current implementation:

```text
src/finharness/interpretation.py
src/finharness/interpretation_graph.py
scripts/run_interpretation_graph.py
tests/test_interpretation.py
```

Tasks:

```text
task interpretation:graph
task test
```

## Quality / Lineage / Receipt Strategy

Quality should include:

```text
source_backed_claims
counterevidence_present
no_execution_language
horizon_present
confidence_bounded
claim_evidence_separation
missing_required_fields
```

Lineage should include:

```text
input_event_snapshot_id
input_event_receipt_ref
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
InterpretationReceipt
```

Permission boundary:

```text
InterpretationSnapshot.execution_allowed = false
```

## Proposed First Slice

```text
source:
  EventSnapshot from SEC EDGAR Events MVP

universe:
  AAPL, MSFT, GOOGL, AMZN, NVDA, META, TSLA
  SPY, QQQ as context only

event types:
  8-K, 10-Q, 10-K

method:
  rule-guided interpretation template

output:
  InterpretationSnapshot + InterpretationReceipt
  impact paths
  scenarios
  counterevidence
  watch questions
```

## Target Workflow

```text
START
-> source_config
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
-> END
```

## Upgrade Log

### 2026-06-01: Interpretation Layer Institutional Scan

Why:

```text
After Events, FinHarness needs a layer that turns official events into
source-backed meaning without jumping to trade recommendations.
```

What changed:

```text
Added proposed module document and institutional practice scan.
```

Evidence:

```text
docs/notes/2026-06-01-interpretation-layer-institutional-practices.md
```

Risks:

```text
LLM interpretation may overclaim.
Interpretation can accidentally become recommendation language.
Business impact paths can be wrong or too generic.
Counterevidence may be weak if not enforced.
```

Next:

```text
Write a proposal before implementation.
Build rule-guided interpretation over EventSnapshot.
Add InterpretationSnapshot/Receipt tests.
Keep execution permission disabled.
```

### 2026-06-01: SEC EDGAR Interpretation MVP

Why:

```text
The third layer could produce official EventSnapshot evidence. The project
needed a fourth layer to convert those events into source-backed meaning,
impact paths, scenarios, counterevidence, and watch questions.
```

What changed:

```text
Added InterpretationSourceSpec, InterpretationRecord, InterpretationQuality,
InterpretationLineage, InterpretationSnapshot, InterpretationReceipt, and
InterpretationBundle.
Added rule-guided interpretation over EventSnapshot records.
Added quality gates:
  source-backed claims
  counterevidence present
  no execution language
  horizon present
  confidence bounded
  claim/evidence/inference separation.
Added LangGraph interpretation subgraph:
  source_config -> load_event_snapshot -> extract_candidate_events
  -> interpret_impact_paths -> build_scenarios -> check_counterevidence
  -> quality -> lineage -> snapshot -> receipt -> consumer_handoff
  -> review_hook -> final.
```

Evidence:

```text
src/finharness/interpretation.py
src/finharness/interpretation_graph.py
scripts/run_interpretation_graph.py
tests/test_interpretation.py
task interpretation:graph
```

Risks:

```text
Rules are intentionally conservative.
Expectation/consensus is still marked needs_human_review.
No fundamentals, transcript, or factor model yet.
No LLM prompt governance yet because first MVP does not use LLMs.
```

Next:

```text
Run interpretation during daily virtual training.
Review whether impact paths are useful or too generic.
Promote useful interpretation patterns into hypothesis templates.
```

## Open Risks

```text
No prior expectation/consensus model yet.
No company fundamentals layer yet.
No analyst transcript layer yet.
No factor exposure model yet.
No LLM prompt/version governance yet.
```

## Next Upgrades

```text
1. Create proposal for Interpretation SEC EDGAR MVP.
2. Define InterpretationRecord/Snapshot/Receipt models.
3. Add source-backed claim quality checks.
4. Add no-execution-language guard.
5. Add LangGraph interpretation subgraph.
```
