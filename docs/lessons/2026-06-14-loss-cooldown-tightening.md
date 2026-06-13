# Lesson: Tighten Cooldown After Losing Trades While Evidence Surface Is Noisy

Date: 2026-06-14
Status: promoted
Source draft: docs/lessons/drafts/2026-06-13-lesson_draft_31f5846e7aa9.md
Source receipt: data/receipts/lessons/lesson_draft_31f5846e7aa9.json
Attester: operator chat approval for C1-C4 on 2026-06-14

## Evidence

The 60-day lesson draft scanned 747 receipts and found:

```text
quality failures: 37
lineage/quality failure patterns: 45
human-review attestation blocks: 168
live-boundary blocks: 88
partial-fill outcomes: 8
rejected outcomes: 16
no approved Risk Gate decisions: 8
restricted routing language hits: 8
```

This is not evidence that any strategy has edge. It is evidence that the local
decision/evidence surface is still noisy enough that the behavioral guard should
be stricter after a losing trade.

## Rule Change

Promote a conservative threshold change:

```text
rule_target: guard.min_minutes_between_trades_after_loss
change_kind: threshold
old_value: 30
new_value: 45
```

Rationale:

```text
When the evidence surface contains repeated quality failures, rejection
patterns, and partial-fill outcomes, the next trade after a loss should require
a longer cooldown before any action is even considered. This does not authorize
trading; it only makes the existing guard more conservative.
```

## Non-Claims

```text
This lesson does not prove alpha.
This lesson does not approve any live trade.
This lesson does not close the receipt-quality problem.
This lesson does not replace human review.
```

## Falsification / Revisit

Revisit the 45-minute cooldown only after a later receipt usage audit and
post-trade review show materially fewer unreferenced receipts, fewer rejected
outcomes, and no recurring lineage failures in the recent window.
