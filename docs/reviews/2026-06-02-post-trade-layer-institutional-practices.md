# Review: Post-Trade Layer Institutional Practices

Date: 2026-06-02
Status: open
Related proposal: /root/projects/finharness/docs/proposals/2026-06-02-post-trade-layer-institutional-practices.md
Related receipt: /root/projects/finharness/data/receipts/cognitive-graph/20260602T153351Z-post-trade-layer-institutional-practices.json
Related module: /root/projects/finharness/docs/modules/10-post-trade.md

## Summary

The cognitive workflow was executed and the placeholder artifacts were upgraded
into Layer 10 Post-Trade research, think, proposal, and module draft documents.
This is a research/design review only; no post-trade code has been implemented
yet.

## Expected

The artifacts should make the next Layer 10 implementation action clear while
preserving the boundary that post-trade is evidence-only and cannot generate
orders.

## Actual

The research now maps public institutional post-trade practices into a
FinHarness post-trade graph contract. Implementation evidence remains pending.

## Evidence

- Idea: /root/projects/finharness/ideas/2026-06-02-post-trade-layer-institutional-practices.md
- Research note: /root/projects/finharness/docs/notes/2026-06-02-post-trade-layer-institutional-practices.md
- Think note: /root/projects/finharness/docs/think/2026-06-02-post-trade-layer-think.md
- Proposal: /root/projects/finharness/docs/proposals/2026-06-02-post-trade-layer-institutional-practices.md
- Module draft: /root/projects/finharness/docs/modules/10-post-trade.md
- Cognitive receipt: /root/projects/finharness/data/receipts/cognitive-graph/20260602T153351Z-post-trade-layer-institutional-practices.json

## Classification

research complete / implementation pending

## Root Causes / Conditions

Execution evidence is easy to overclaim. Layer 10 needs to preserve staged,
filled, partial, canceled, and rejected states before any portfolio or
performance claims are made.

## Lessons

Post-trade should prefer explicit exceptions over optimistic reconciliation.

## Actions

Implement the MVP only after adding tests that prove staged-only orders are not
positions, partial fills remain exceptions, rejects/cancels remain visible, TCA
inputs are disclosed, and the layer cannot create orders.
