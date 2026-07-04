# CapitalObjectiveFit Before OrderTicketCandidate

Status: accepted

Date: 2026-07-04

## Context

After `CapitalMandate`, `AgentAuthorityGrant`, `ActionIntentAuthorityBinding`,
authority-aware preflight, `TradePlanCandidate`, and `TradePlanReviewGate`,
FinHarness had a strong high-consequence governance ladder. That ladder prevents
unsafe progression, but by itself it can make the product read like a permission
firewall: no receipt, no authority, no progression.

The product north star is broader. FinHarness should help the user understand,
protect, and improve their own capital decisions. Mature financial workbenches
and agent systems usually do not jump from research to orders; they produce
reviewable work products, explain risk and objectives, compare alternatives, and
keep humans in the high-consequence loop.

## Decision

Before introducing any `OrderTicketCandidate`, FinHarness adds
`CapitalObjectiveFit` as a receipt-backed review-evidence artifact between
`TradePlanCandidate` and human review gates.

`CapitalObjectiveFit` binds the current:

- `TradePlanCandidate` receipt
- `ActionIntent` receipt
- `ActionIntentSimulationReport` receipt
- recomputed `ActionIntentPreflight` report hash

It records:

- objective alignment: `aligned`, `unclear`, or `conflicted`
- objective basis
- benefit thesis
- risk-budget impact
- liquidity impact
- concentration impact
- reversibility
- opportunity cost
- alternatives considered
- major uncertainties
- user questions
- recommended next safe path

It rejects stale evidence and rejects advice, approval, suitability,
order-ready, broker, and execution markers.

## Non-Claims

`CapitalObjectiveFit` is not:

- investment advice
- suitability certification
- trade-plan approval
- an order ticket
- a broker instruction or broker submission
- execution authorization
- an AuthorityContract

## Consequences

This shifts the next mainline step from "make the plan more executable" to
"make the plan more understandable and reviewable." The hard authority chain
remains intact, but each block or review path can now produce a constructive
next safe path and a user-benefit thesis.

Future work may decide whether `TradePlanReviewGate` must cite a current
`CapitalObjectiveFit` for allowed staging. v0 does not make objective fit a hard
precondition, preserving backward compatibility for the existing review-gate
surface.
