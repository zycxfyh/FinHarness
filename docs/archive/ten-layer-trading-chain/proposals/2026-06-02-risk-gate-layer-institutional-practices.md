# Proposal: Risk Gate Layer Institutional Practices

Date: 2026-06-02
Status: implemented MVP
Related idea: ../../ideas/2026-06-02-risk-gate-layer-institutional-practices.md
Related note: ../notes/2026-06-02-risk-gate-layer-institutional-practices.md
Related think: ../think/2026-06-02-risk-gate-layer-think.md
Related upstream module: ../modules/07-proposal.md
Related implemented module: ../modules/08-risk-gate.md

## Problem

FinHarness can now create structured ProposalCandidates, but it needs an
independent Risk Gate before any execution layer can be considered.

Without this layer, the workflow can drift from:

```text
validated evidence
-> proposal candidate
-> execution urge
```

instead of:

```text
validated evidence
-> proposal candidate
-> independent risk gate
-> explicit decision
-> receipt
-> possible execution handoff later
```

## Goals

```text
consume ProposalSnapshot evidence
evaluate each ProposalCandidate against deterministic risk checks
produce RiskGateDecision objects
hard-block missing mandate, missing human review, live permission, and order language
write RiskGateSnapshot and RiskGateReceipt
preserve execution_allowed=false in MVP
handoff only to review or future execution layer
```

## Non-Goals

```text
no broker orders
no live execution approval
no final position sizing
no leverage instruction
no stop-loss or take-profit order
no active Hermes subprocess/API integration in MVP
no portfolio optimizer in the first slice
```

## Institutional Evidence

Public sources point to these patterns:

```text
BlackRock Aladdin:
  whole-portfolio risk, shared data, stress/scenario analytics

Citadel:
  independent Portfolio Construction and Risk Group

PIMCO:
  investment views translated into specific risk targets

AQR:
  active returns inside a risk-controlled framework

SEC / FINRA:
  market-access controls, preset credit/capital thresholds, hard pre-trade blocks

CME:
  monetary, delta/DV01, position, permission, order blocking, dashboard, audit trail

Interactive Brokers:
  real-time margin, multi-asset risk, automatic pre-trade vetting

Jane Street:
  real-time visibility, human judgment, tail-risk thinking, postmortems

Millennium:
  independent decisions within a rigorous risk framework
```

Primary note:

```text
docs/notes/2026-06-02-risk-gate-layer-institutional-practices.md
```

## Proposed Data Objects

```text
RiskGateSourceSpec
RiskGateContext
RiskGateCheck
RiskGateDecision
RiskGateQuality
RiskGateLineage
RiskGateSnapshot
RiskGateReceipt
RiskGateBundle
```

## Decision Vocabulary

```text
approved_for_paper_review
blocked
needs_more_evidence
needs_human_review
rejected
```

No decision value should imply live execution.

## Proposed Checks

```text
proposal_quality_check
source_linkage_check
mandate_check
instrument_permission_check
paper_or_live_permission_check
max_notional_check
concentration_check
liquidity_check
drawdown_state_check
behavior_reset_check
scenario_check
order_language_check
human_review_check
```

## Proposed LangGraph Shape

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

Failure path:

```text
quality failed
-> blocked_or_failed_receipt
```

## First Slice

Input:

```text
ProposalSnapshot from Layer 7
```

Config:

```text
allowed_action_types:
  watch_only
  research_more
  paper_trade_candidate
  avoid_or_reject

live_execution_allowed:
  false

human_review_required:
  true

max_paper_notional:
  small deterministic cap

allowed_symbols:
  AAPL, MSFT, GOOGL, AMZN, NVDA, META, TSLA, SPY, QQQ
```

Output:

```text
RiskGateSnapshot + RiskGateReceipt
execution_allowed=false
decision reasons
blocking reasons
review questions
```

## Quality Gates

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

## Success Signal

```text
task risk-gate:graph consumes a ProposalSnapshot
RiskGateSnapshot and RiskGateReceipt are written
paper candidates can be approved only for paper review
live execution is blocked
missing mandate or limits produces blocked / needs_more_evidence
quality gates pass
execution_allowed=false
```

## Decision

Build a deterministic Risk Gate MVP.

The first implementation should be a thin governance layer, not a portfolio
optimizer and not an execution engine.

## Implementation Evidence

Implemented files:

```text
src/finharness/risk_gate.py
src/finharness/risk_gate_graph.py
scripts/run_risk_gate_graph.py
tests/test_risk_gate.py
docs/modules/08-risk-gate.md
Taskfile.yml
```

Task:

```text
task risk-gate:graph
```

Verified paths:

```text
default paper-review path:
  decision=approved_for_paper_review
  execution_allowed=false

live-requested path:
  decision=blocked
  execution_allowed=false
```

MVP result:

```text
Risk Gate Graph consumes ProposalSnapshot evidence and writes
RiskGateSnapshot + RiskGateReceipt. It keeps execution_allowed=false, permits
paper review only, and hard-blocks live requests.
```
