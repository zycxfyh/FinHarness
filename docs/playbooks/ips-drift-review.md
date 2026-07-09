---
name: ips-drift-review
version: 0.1.0
space: Evaluation
description: Review IPS allocation drift and determine if rebalancing is needed
when_to_use: When IPS allocation exceeds drift threshold or mandate review trigger fires
required_context_packs:
  - current_ips
  - capital_summary
recommended_evaluators:
  - plan_draft_evaluator
side_effects:
  - read
execution_allowed: false
---

## Procedure

1. Load current IPS and capital summary context packs
2. Compare actual allocation vs IPS target allocation
3. Identify drift for each asset class
4. Flag any class exceeding drift threshold
5. Check if rebalance bands are triggered
6. Evaluate tax implications of potential rebalance
7. Generate findings as EvaluationReport
8. If drift exceeds threshold, propose rebalance plan draft
9. Stop if human confirmation not received

## Stop Conditions

- All allocations within IPS bands
- Human reviewer declines rebalance proposal
- Required context packs unavailable
