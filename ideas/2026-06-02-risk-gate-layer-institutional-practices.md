# Idea: Risk Gate Layer Institutional Practices

idea_id: 2026-06-02-risk-gate-layer-institutional-practices
date: 2026-06-02
source: user-request-institutional-research
layer: 8-risk-gate
status: captured

## Raw Thought

Research how top institutions and trading venues implement the eighth FinHarness layer: independent risk gate checks between Proposal and Execution. Translate public institutional practices into a typed LangGraph layer with mandate, sizing, liquidity, concentration, drawdown, behavior, market-access, and human-review gates. The layer must approve, block, or request changes; it must not place orders.

## Hypothesis

FinHarness will become safer and more institution-like if the eighth layer is
an independent Risk Gate that consumes ProposalSnapshot evidence and produces a
bounded decision before any execution adapter can be considered.

The gate should decide:

```text
approved_for_paper_review
blocked
needs_more_evidence
needs_human_review
rejected
```

It should not place orders or approve live execution.

## Why It Might Matter

Top institutional patterns separate idea generation from risk authority. Public
examples from BlackRock Aladdin, Citadel, PIMCO, SEC/FINRA market-access rules,
CME pre-trade controls, Interactive Brokers, Jane Street, and Millennium all
point to the same pattern:

```text
proposal
-> independent risk and mandate checks
-> limits and hard blocks
-> audit trail
-> only then possible execution handoff
```

## Testable Experiment

Build a RiskGateSnapshot MVP that consumes ProposalSnapshot and records one
RiskGateDecision per ProposalCandidate.

Minimum checks:

```text
proposal_quality
mandate
instrument_permission
paper_or_live_permission
max_notional
concentration
liquidity
drawdown_state
behavior_reset
order_language_absent
human_review
```

## Success Signal

`task risk-gate:graph` can consume a ProposalSnapshot, write RiskGateSnapshot
and RiskGateReceipt, keep `execution_allowed=false`, and block any candidate
missing mandate, limit, or human-review evidence.

## Risk Or Failure Mode

The layer can become fake safety if it only warns. Institutional pre-trade
controls need hard blocks for threshold breaches and an audit trail for
changes.

## Links

- Proposal: docs/proposals/2026-06-02-risk-gate-layer-institutional-practices.md
- Institutional practices: docs/notes/2026-06-02-risk-gate-layer-institutional-practices.md
- Think note: docs/think/2026-06-02-risk-gate-layer-think.md
- Review: docs/reviews/2026-06-02-risk-gate-layer-institutional-practices.md
- Lesson: docs/lessons/2026-06-02-risk-gate-layer-institutional-practices.md
