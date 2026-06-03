# Workflow Note: Risk Gate Layer Institutional Practices

Date: 2026-06-02
Source idea: /root/projects/finharness/ideas/2026-06-02-risk-gate-layer-institutional-practices.md

## Summary

The cognitive LangGraph flow captured the eighth-layer Risk Gate direction as a
durable project workflow.

The practical project pattern is:

```text
ProposalSnapshot
-> RiskGateDecision
-> RiskGateSnapshot
-> RiskGateReceipt
-> review questions
-> optional handoff to Execution layer later
```

The gate should not create broker orders. It should approve, block, or request
changes to a structured action candidate.

## Immediate Use

Use the institutional-practices note and this proposal as the next action
boundary:

```text
docs/notes/2026-06-02-risk-gate-layer-institutional-practices.md
docs/proposals/2026-06-02-risk-gate-layer-institutional-practices.md
```

## Implementation Posture

Start with a deterministic MVP:

```text
source_config
-> load_proposal_snapshot
-> mandate_check
-> permission_check
-> exposure_limit_check
-> concentration_check
-> liquidity_check
-> drawdown_behavior_check
-> hard_block_decision
-> quality
-> lineage
-> snapshot
-> receipt
-> review_hook
-> final
```

LLM commentary can be reserved through an interface, but the first Risk Gate
must be rule-guided and auditable.
