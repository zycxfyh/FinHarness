# Module: Validation

Status: implemented MVP
Owner: FinHarness
Layer: 6 - Validation / hypothesis testing
Last updated: 2026-06-02

## Purpose

The validation module tests fifth-layer hypotheses against source linkage,
mechanism sanity, benchmark context, validation-plan coverage, disconfirmation
items, and known limitations.

It answers:

```text
Is the hypothesis source-linked?
Does it have a mechanism and assumptions?
Were validation jobs created?
Were disconfirming observations mapped into checks?
Is SPY / QQQ benchmark context present?
What limitations prevent stronger claims?
Can this move to human proposal review?
```

It does not answer:

```text
Should we trade?
Is this alpha proven?
What size should a position be?
Should an order be placed?
```

## Current Responsibilities

Implemented MVP responsibilities:

```text
consume HypothesisSnapshot evidence
create one ValidationJob per HypothesisRecord
produce ValidationCheckResult objects
map every disconfirming observation into a validation result
record source, mechanism, event-reaction, benchmark, disconfirmation, and
limitations checks
write ValidationSnapshot, ValidationQuality, ValidationLineage, and
ValidationReceipt
handoff only to proposal review and human review
```

## Non-Goals

```text
no trade authorization
no buy/sell/hold recommendation
no proposal generation
no position sizing
no broker/exchange instructions
no claim that a hypothesis is proven
no return/factor/cost/liquidity calculation in MVP
no active Hermes subprocess/API integration in MVP
```

## Inputs

Current inputs:

```text
HypothesisSnapshot
HypothesisReceipt ref
HypothesisRecord.validation_plan
HypothesisRecord.disconfirming_observations
market_snapshot_refs where available
indicator_snapshot_refs where available
universe with SPY / QQQ benchmark context
```

## Outputs

Current outputs:

```text
ValidationJob
ValidationCheckResult
ValidationQuality
ValidationLineage
ValidationSnapshot
ValidationReceipt
proposal_handoff
review_questions
```

Runtime artifacts:

```text
data/normalized/validations/
data/receipts/validations/
```

Task:

```text
task validation:graph
```

## LLM Boundary

Current LLM boundary:

```text
ValidationDraftProvider protocol
NullValidationDraftProvider default
HermesValidationDraftProvider reserved for /root/projects/hermes-agent
llm_enabled=false by default
```

The MVP records the Hermes interface when enabled, but does not call Hermes.

## Quality / Lineage / Receipt Strategy

Quality gates require:

```text
hypothesis_source_linked
validation_jobs_created
source_validity_checked
at_least_one_market_check
at_least_one_disconfirmation_check
benchmark_context_present
no_proposal_or_execution_language
limitations_present
result_not_overclaimed
lineage_complete
```

Lineage records:

```text
input_hypothesis_snapshot_id
input_hypothesis_receipt_ref
hypothesis_ids
interpretation_snapshot_id
event_snapshot_id
market_snapshot_refs
indicator_snapshot_refs
method
model/provider if any
prompt/template version if any
transform_version
output_hash
output_ref
```

Permission boundary:

```text
ValidationSnapshot.execution_allowed = false
```

## Current Workflow

```text
source_config
-> load_hypothesis_snapshot
-> create_validation_jobs
-> source_validity_check
-> mechanism_check
-> event_reaction_check
-> benchmark_context_check
-> disconfirmation_check
-> limitations_check
-> validation_results
-> quality
-> lineage
-> snapshot
-> receipt
-> consumer_handoff
-> review_hook
-> final
```

## Important Files

```text
src/finharness/validation.py
src/finharness/validation_graph.py
scripts/run_validation_graph.py
tests/test_validation.py
docs/proposals/2026-06-02-validation-layer-mvp.md
```

## Upgrade Log

### 2026-06-02: Validation Layer MVP

Why:

```text
After Hypotheses, FinHarness needed a separate validation layer that tests
whether hypotheses are source-linked, bounded, disconfirmation-aware, and ready
for proposal review without jumping to trades.
```

What changed:

```text
Added ValidationSourceSpec, ValidationJob, ValidationCheckResult,
ValidationQuality, ValidationLineage, ValidationSnapshot, ValidationReceipt,
and ValidationBundle.
Added strict LangGraph validation subgraph.
Added task validation:graph.
Added tests for quality gates, persistence, graph output, and reserved Hermes
LLM interface.
```

Result:

```text
Layer 6 can now consume HypothesisSnapshot evidence and produce
ValidationSnapshot + ValidationReceipt with execution_allowed=false.
```

Remaining risks:

```text
MVP maps validation evidence but does not compute empirical returns yet.
Factor, transaction cost, turnover, liquidity, and walk-forward checks are not
implemented yet.
Hermes interface is reserved but not an active subprocess/API integration.
```

## Next Upgrades

```text
1. Add event-window return and volume reaction metrics.
2. Add SPY / QQQ relative return and beta context.
3. Add indicator snapshot checks from layer 2 features.
4. Add multiple-testing and parameter-trial accounting.
5. Add validation reports for proposal-layer promotion.
```
