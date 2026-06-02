# Reviews

Use this folder for post-action review records.

Reviews answer:

```text
what happened?
what did we expect?
what surprised us?
what evidence do we have?
what should change next time?
```

This includes workflow failures, bad AI proposals, data quality incidents,
strategy experiments, risk-gate blocks, paper-trade outcomes, and confusing
results.

## Template

```text
# Review: <Title>

Date:
Status: open | actioned | archived
Related proposal:
Related receipt:
Related module:

## Summary

What happened?

## Expected

What did we expect to happen?

## Actual

What actually happened?

## Evidence

Receipts, tests, logs, snapshots, notes, or charts.

## Classification

data issue | hypothesis issue | model issue | risk issue | execution issue |
process issue | behavior issue | unknown

## Root Causes / Conditions

What conditions allowed this outcome?

## Lessons

What should we remember?

## Actions

What should change in code, docs, tests, risk gates, or process?
```
