# Proposal: Validation Layer MVP

Date: 2026-06-02
Status: implemented MVP
Related module: docs/modules/06-validation.md
Related upstream layer: docs/modules/05-hypotheses.md

## Problem

FinHarness can now convert interpretations into falsifiable hypotheses, but it
needs a separate validation layer before any proposal can be considered.

Without this layer, the workflow can drift from:

```text
hypothesis
-> persuasive narrative
-> proposal urge
```

instead of moving through:

```text
hypothesis
-> validation jobs
-> source checks
-> mechanism checks
-> benchmark context
-> disconfirmation mapping
-> limitations
-> validation receipt
```

## Goals

```text
consume HypothesisSnapshot evidence
create one ValidationJob per hypothesis
produce ValidationCheckResult objects
map disconfirming observations into checks
record source, mechanism, event-reaction, benchmark, and limitation checks
write ValidationSnapshot and ValidationReceipt
preserve Hermes LLM interface for future validation commentary
keep execution permission disabled
```

## Non-Goals

```text
no buy/sell/hold recommendation
no position sizing
no broker instructions
no price target
no automatic proposal generation
no claim that a hypothesis is proven
no active Hermes subprocess/API integration in MVP
no full event-window return/factor/cost/liquidity engine in MVP
```

## First Slice

```text
source:
  HypothesisSnapshot from Layer 5

method:
  rule-guided validation evidence packaging

checks:
  source_validity
  mechanism
  event_reaction input availability
  benchmark_context through SPY / QQQ
  disconfirmation mapping
  limitations
```

## Proposed Data Objects

```text
ValidationSourceSpec
ValidationJob
ValidationCheckResult
ValidationQuality
ValidationLineage
ValidationSnapshot
ValidationReceipt
ValidationBundle
```

## Result Vocabulary

Allowed result values are split by evidence type:

```text
Empirical / hypothesis evidence:
supported          # only for rung-gated empirical evidence such as backtests
weakened
disconfirmed
inconclusive
not_testable

Structural readiness:
linked             # source/reference linkage is present
present            # required context or mechanism field is present
well_formed        # required structure is parseable and complete
```

Structural readiness values do not mean the hypothesis has empirical support,
do not imply an edge, and do not grant trading authorization.

Forbidden language:

```text
validated alpha
ready to trade
buy/sell/hold
position sizing
order instructions
guaranteed
```

## Workflow

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

## LangGraph Shape

```text
src/finharness/validation.py
src/finharness/validation_graph.py
scripts/run_validation_graph.py
tests/test_validation.py
task validation:graph
```

## Quality / Lineage / Receipt

Quality gates:

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

Lineage:

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
transform_version
output_hash
output_ref
```

## LLM Boundary

```text
ValidationDraftProvider protocol
NullValidationDraftProvider default
HermesValidationDraftProvider reserved for /root/projects/hermes-agent
llm_enabled=false by default
```

The MVP does not call Hermes. It only preserves the interface and lineage.

## Consumer Handoff

Allowed outputs:

```text
validation evidence
proposal review prompts
human review prompts
hypothesis rejection reasons
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
task validation:graph produces ValidationSnapshot + Receipt
quality gates pass
execution_allowed=false
each hypothesis has at least one ValidationJob
each hypothesis has disconfirmation checks
each result has limitations
Hermes interface is retained without becoming a runtime dependency
```

## Review Plan

Use Engineering Delivery Graph to audit implementation after:

```text
focused validation tests
task validation:graph
task check
```
