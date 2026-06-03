# Lesson: Post-Trade Layer Institutional Practices

Date: 2026-06-02
Status: draft
Source reviews:
- /root/projects/finharness/docs/reviews/2026-06-02-post-trade-layer-institutional-practices.md
Source ideas:
- /root/projects/finharness/ideas/2026-06-02-post-trade-layer-institutional-practices.md
Affected modules:
- 10-post-trade

## Lesson

Post-trade should convert execution evidence into reconciliation and exceptions,
not into a clean success story.

## Why It Matters

Execution outcomes are messy: staged-only, partial fills, cancels, rejects, and
missing prices all mean different things. If the system flattens those states,
future portfolio and performance layers will learn from false data.

## Evidence

- /root/projects/finharness/docs/notes/2026-06-02-post-trade-layer-institutional-practices.md
- /root/projects/finharness/docs/proposals/2026-06-02-post-trade-layer-institutional-practices.md
- /root/projects/finharness/docs/reviews/2026-06-02-post-trade-layer-institutional-practices.md

## Rule / Heuristic

Never count an order-shaped request as a trade. Reconcile only from execution
events, disclose TCA inputs, and preserve exceptions.

## Where It Should Live

docs/modules/10-post-trade.md | tests/test_post_trade.py | future ADR if
settlement/accounting integrations are added
