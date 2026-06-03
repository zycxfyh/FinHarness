# Proposal: Proposal Layer MVP

Date: 2026-06-02
Status: implemented MVP
Related module: docs/modules/07-proposal.md
Related upstream layer: docs/modules/06-validation.md

## Problem

FinHarness can validate hypotheses, but it needs a separate layer before Risk
Gate so validation evidence does not become an implicit trade urge.

The intended workflow is:

```text
hypothesis
-> validation evidence
-> structured proposal candidate
-> independent risk gate
```

not:

```text
validated-looking narrative
-> action approval
```

## Goals

```text
consume ValidationSnapshot evidence
create structured ProposalCandidate objects
require portfolio role, evidence summary, validation summary, alternatives, and
do-nothing case
create RiskGateRequest handoff
preserve Hermes LLM interface for future proposal drafting
keep execution permission disabled
```

## Non-Goals

```text
no buy/sell/hold recommendation
no approved status
no final sizing
no quantity or leverage
no broker instructions
no automatic Risk Gate approval
no active Hermes subprocess/API integration in MVP
```

## First Slice

```text
source:
  ValidationSnapshot from Layer 6

method:
  rule-guided proposal evidence packaging

allowed action_type:
  watch_only
  research_more
  paper_trade_candidate
  avoid_or_reject
```

## Proposed Data Objects

```text
ProposalSourceSpec
ProposalCandidate
RiskGateRequest
ProposalQuality
ProposalLineage
ProposalSnapshot
ProposalReceipt
ProposalBundle
```

## Action Classification

```text
disconfirmed or weakened evidence:
  avoid_or_reject

more not_testable than supported:
  research_more

at least two supported checks and at most one not_testable check:
  paper_trade_candidate

otherwise:
  watch_only
```

Paper-trade candidate does not mean execution permission. It means the proposal
is structured enough to request independent risk-gate review.

## Workflow

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

## LangGraph Shape

```text
src/finharness/proposal.py
src/finharness/proposal_graph.py
scripts/run_proposal_graph.py
tests/test_proposal.py
task proposal:graph
```

## Quality / Lineage / Receipt

Quality gates:

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

Lineage:

```text
input_validation_snapshot_id
input_validation_receipt_ref
validation_result_ids
hypothesis_ids
validation_transform_version
method
model/provider if any
transform_version
output_hash
output_ref
```

## LLM Boundary

```text
ProposalDraftProvider protocol
NullProposalDraftProvider default
HermesProposalDraftProvider reserved for /root/projects/hermes-agent
llm_enabled=false by default
```

The MVP does not call Hermes. It only preserves the interface and lineage.

## Consumer Handoff

Allowed outputs:

```text
risk gate review request
proposal rejection reasons
human review prompts
```

Forbidden outputs:

```text
orders
final sizing
broker instructions
execution permission
trade approval
```

## Success Signal

```text
task proposal:graph produces ProposalSnapshot + Receipt
quality gates pass
execution_allowed=false
each candidate has invalidation triggers
each candidate has alternatives and do-nothing case
consumer_handoff points only to Risk Gate and review
```

## Risks

```text
paper_trade_candidate can be misread as permission
validation counts are too shallow for real sizing or approval
LLM wording can overclaim
missing account/portfolio context can hide concentration or mandate conflicts
```

## Decision

Build this as a strict, non-execution layer.

Use deterministic templates first. Add LLM drafting later only if the output is
source-linked, quality-gated, and clearly marked as draft reasoning rather than
approval.

## Implementation Evidence

Implemented files:

```text
src/finharness/proposal.py
src/finharness/proposal_graph.py
scripts/run_proposal_graph.py
tests/test_proposal.py
docs/modules/07-proposal.md
Taskfile.yml
```

Task:

```text
task proposal:graph
```

MVP result:

```text
Proposal Graph consumes ValidationSnapshot evidence and writes ProposalSnapshot
+ ProposalReceipt. It preserves risk-gate handoff only, keeps
execution_allowed=false, and blocks order/approval language.
```
