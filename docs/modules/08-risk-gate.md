# Module: Risk Gate

Status: implemented MVP
Owner: FinHarness
Layer: 8 - Risk Gate / independent pre-execution control
Last updated: 2026-06-02

## Purpose

The risk-gate module turns seventh-layer ProposalSnapshot evidence into
permission-aware control decisions.

It answers:

```text
Can this proposal continue to paper review?
Is it blocked by mandate, permission, limit, liquidity, drawdown, or behavior state?
Does it need more evidence or human review?
What reasons and remediation steps should be recorded?
```

It does not answer:

```text
Should an order be placed?
What is the final size?
Is live execution approved?
What broker instruction should be sent?
```

## Current Responsibilities

Implemented MVP responsibilities:

```text
consume ProposalSnapshot evidence
create one RiskGateDecision per ProposalCandidate
evaluate proposal quality, source linkage, mandate, symbol/action permissions,
paper/live permission, paper notional cap, concentration cap, liquidity
evidence, drawdown state, behavior reset, scenario notes, restricted language,
and human review
write RiskGateSnapshot, RiskGateQuality, RiskGateLineage, and RiskGateReceipt
handoff only to paper-review / future execution review
```

## Non-Goals

```text
no broker orders
no live execution approval
no final position sizing
no leverage instruction
no stop-loss or take-profit order
no portfolio optimizer in the first slice
no active Hermes subprocess/API integration in MVP
```

## Inputs

Current inputs:

```text
ProposalSnapshot
ProposalReceipt ref
ProposalCandidate
RiskGateRequest
RiskGateContext
```

Default MVP context:

```text
paper research mandate
allowed symbols:
  AAPL, MSFT, GOOGL, AMZN, NVDA, META, TSLA, SPY, QQQ
live_execution_allowed=false
human_review_attested=true
max_paper_notional=1000
requested_notional=100
max_symbol_concentration_pct=0.10
requested_symbol_concentration_pct=0.02
```

## Outputs

Current outputs:

```text
RiskGateCheck
RiskGateDecision
RiskGateQuality
RiskGateLineage
RiskGateSnapshot
RiskGateReceipt
execution_handoff
review_questions
```

Runtime artifacts:

```text
data/normalized/risk-gates/
data/receipts/risk-gates/
```

Task:

```text
task risk-gate:graph
```

## Decision Vocabulary

```text
approved_for_paper_review
blocked
needs_more_evidence
needs_human_review
rejected
```

No decision value authorizes live execution.

## Quality / Lineage / Receipt Strategy

Quality gates require:

```text
proposal_snapshot_linked
proposal_quality_ok
decision_count_matches_candidate_count
all_decisions_have_checks
hard_blocks_enforced
mandate_present
permission_boundary_present
human_review_required
no_order_language
no_live_execution_authority
no_final_sizing
lineage_complete
receipt_written
```

Lineage records:

```text
input_proposal_snapshot_id
input_proposal_receipt_ref
proposal_ids
proposal_transform_version
method
model/provider if any
prompt/template version if any
transform_version
output_hash
output_ref
```

Permission boundary:

```text
RiskGateSnapshot.execution_allowed = false
```

## Current Workflow

```text
source_config
-> load_proposal_snapshot
-> proposal_quality_check
-> mandate_check
-> instrument_permission_check
-> paper_or_live_permission_check
-> exposure_limit_check
-> concentration_check
-> liquidity_check
-> drawdown_behavior_check
-> scenario_check
-> decision
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
src/finharness/risk_gate.py
src/finharness/risk_gate_graph.py
scripts/run_risk_gate_graph.py
tests/test_risk_gate.py
docs/proposals/2026-06-02-risk-gate-layer-institutional-practices.md
```

## Upgrade Log

### 2026-06-02: Risk Gate Layer MVP

Why:

```text
After Proposal, FinHarness needed an independent control layer that blocks,
rejects, or requests review before any execution-layer work can start.
```

What changed:

```text
Added RiskGateSourceSpec, RiskGateContext, RiskGateCheck, RiskGateDecision,
RiskGateQuality, RiskGateLineage, RiskGateSnapshot, RiskGateReceipt, and
RiskGateBundle.
Added strict LangGraph risk-gate subgraph.
Added task risk-gate:graph.
Added tests for paper approval, live hard block, missing human review,
restricted language, persistence, graph output, and reserved Hermes interface.
```

Result:

```text
Layer 8 can now consume ProposalSnapshot evidence and produce RiskGateSnapshot
+ RiskGateReceipt with execution_allowed=false.
```
