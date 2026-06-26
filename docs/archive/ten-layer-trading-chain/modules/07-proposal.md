# Module: Proposal

Status: implemented MVP
Owner: FinHarness
Layer: 7 - Proposal / structured action candidate
Last updated: 2026-06-02

## Purpose

The proposal module turns sixth-layer validation evidence into structured action
candidates for independent risk-gate review.

It answers:

```text
Does validated research evidence deserve a governed action candidate?
What portfolio role does the candidate claim?
What evidence, limitations, alternatives, and do-nothing case must be reviewed?
What should Risk Gate check before any approval can be considered?
```

It does not answer:

```text
Should we trade?
Is the action approved?
What size should a position be?
Should an order be placed?
```

## Current Responsibilities

Implemented MVP responsibilities:

```text
consume ValidationSnapshot evidence
select proposal candidates only when validation quality passes
allow only watch_only, research_more, paper_trade_candidate, avoid_or_reject
attach evidence and validation summaries
attach portfolio role, invalidation triggers, constraints, alternatives, and
do-nothing case
write ProposalSnapshot, ProposalQuality, ProposalLineage, and ProposalReceipt
handoff only to independent Risk Gate and human review
```

## Non-Goals

```text
no trade authorization
no buy/sell/hold recommendation
no approved status
no final sizing
no quantity, leverage, stop-loss, or take-profit instruction
no broker/exchange instruction
no active Hermes subprocess/API integration in MVP
```

## Inputs

Current inputs:

```text
ValidationSnapshot
ValidationReceipt ref
ValidationCheckResult groups by hypothesis
HypothesisSnapshot refs through validation lineage
portfolio/account context where available later
human objective or mandate where available later
```

## Outputs

Current outputs:

```text
ProposalCandidate
RiskGateRequest
ProposalQuality
ProposalLineage
ProposalSnapshot
ProposalReceipt
risk_gate_handoff
review_questions
```

Runtime artifacts:

```text
data/normalized/proposals/
data/receipts/proposals/
```

Task:

```text
task proposal:graph
```

## LLM Boundary

Current LLM boundary:

```text
ProposalDraftProvider protocol
NullProposalDraftProvider default
HermesProposalDraftProvider reserved for /root/projects/hermes-agent
llm_enabled=false by default
```

The MVP records the Hermes interface when enabled, but does not call Hermes.

## Quality / Lineage / Receipt Strategy

Quality gates require:

```text
validation_snapshot_linked
validation_quality_ok
evidence_summary_present
validation_summary_present
portfolio_role_present
invalidation_triggers_present
risk_handoff_present
constraints_present
alternatives_considered
do_nothing_case_present
no_execution_authority
no_order_language
no_final_sizing
human_review_required
```

Lineage records:

```text
input_validation_snapshot_id
input_validation_receipt_ref
validation_result_ids
hypothesis_ids
validation_transform_version
method
model/provider if any
prompt/template version if any
transform_version
output_hash
output_ref
```

Permission boundary:

```text
ProposalSnapshot.execution_allowed = false
```

## Current Workflow

```text
source_config
-> load_validation_snapshot
-> select_proposal_candidates
-> build_evidence_summary
-> assign_portfolio_role
-> attach_invalidation_triggers
-> attach_constraints
-> attach_alternatives
-> build_risk_gate_handoff
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
src/finharness/proposal.py
src/finharness/proposal_graph.py
scripts/run_proposal_graph.py
tests/test_proposal.py
docs/proposals/2026-06-02-proposal-layer-mvp.md
```

## Upgrade Log

### 2026-06-02: Proposal Layer MVP

Why:

```text
After Validation, FinHarness needed a separate translation layer that can create
governed action candidates without collapsing validation evidence into trade
permission.
```

What changed:

```text
Added ProposalSourceSpec, ProposalCandidate, RiskGateRequest, ProposalQuality,
ProposalLineage, ProposalSnapshot, ProposalReceipt, and ProposalBundle.
Added strict LangGraph proposal subgraph.
Added task proposal:graph.
Added tests for quality gates, persistence, graph output, and reserved Hermes
LLM interface.
```

Result:

```text
Layer 7 can now consume ValidationSnapshot evidence and produce
ProposalSnapshot + ProposalReceipt with execution_allowed=false.
```
