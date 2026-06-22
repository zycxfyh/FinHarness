# Module Docs

Module docs describe each FinHarness layer: purpose, boundaries, inputs,
outputs, receipts, mature wheels, and next upgrades. Use them after the golden
path when you need to understand where a behavior lives.

## Ten-Layer Chain

| Layer | Module doc | Primary task |
| --- | --- | --- |
| 1 | [Market Data](01-market-data.md) | `task market-data:graph` |
| 2 | [Indicators](02-indicators.md) | `task indicators:graph`, `task feature:macd`, `task feature:squeeze` |
| 3 | [Events](03-events.md) | `task events:snapshot` |
| 4 | [Interpretation](04-interpretation.md) | `task interpretation:graph` |
| 5 | [Hypotheses](05-hypotheses.md) | `task hypotheses:graph` |
| 6 | [Validation](06-validation.md) | `task validation:graph` |
| 7 | [Proposal](07-proposal.md) | `task proposal:graph` |
| 8 | [Risk Gate](08-risk-gate.md) | `task risk-gate:graph` |
| 9 | [Execution](09-execution.md) | `task execution:graph` |
| 10 | [Post Trade](10-post-trade.md) | `task post-trade:graph` |

## Delivery Support

- [Engineering Delivery](engineering-delivery.md) describes the project delivery
  graph and governance checks.

## Reading Order

New users should run [the golden path tutorial](../tutorials/golden-path.md)
first. Module docs are reference/context, not the first-run tutorial.
