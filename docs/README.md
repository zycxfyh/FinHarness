# FinHarness Docs

This is the task map for FinHarness documentation. Start with the job you are
trying to do, not with the architecture.

FinHarness is not a trading bot. It is a research, evidence, workflow, risk,
execution, and review harness. The docs should make the safe path easy and the
unsafe path visibly blocked.

## Start Here

- Understand the product direction and category: [Product Thesis](product/product-thesis.md), [Product Roadmap](product/product-roadmap.md), [North Star](product-north-star.md)
- New to the project: [Golden Path Tutorial](tutorials/golden-path.md)
- Need to perform one task: [How-to Guides](how-to/README.md)
- Need exact facts, commands, or schemas: [Reference](reference/README.md)
- Need the "why" and design context: [Explanation](explanation/README.md)

## I Want To

| Goal | Use this |
| --- | --- |
| Run the first safe end-to-end flow | [Golden Path Tutorial](tutorials/golden-path.md) |
| Run one indicator snapshot | [Run A Feature Snapshot](how-to/run-feature-snapshot.md) |
| Run the full layer chain safely | [Run The Ten-Layer Flow Safely](how-to/run-ten-layer-flow.md) |
| Review a paper broker workflow | [Safe Paper-Trade Review](how-to/safe-paper-trade-review.md) |
| Add a mature-wheel adapter | [Add A Mature-Wheel Adapter](how-to/add-mature-wheel-adapter.md) |
| Promote a lesson into a rule | [Promote Lesson To Rule](how-to/promote-lesson-to-rule.md) |
| Understand the mature-wheel migration | [Mature Wheel Control Plane](architecture/mature-wheel-control-plane.md) |
| Check which policy rules protect trading boundaries | [Policy Contract](architecture/policy-contract.md) |
| Check what receipts and lineage already capture | [Evidence Inventory](architecture/evidence-inventory.md) |
| Look up commands | [Command Reference](reference/commands.md) |
| Look up interfaces | [Interface Reference](reference/interfaces.md) |
| Look up receipt fields and locations | [Receipt Reference](reference/receipts.md) |
| Look up config/env vars | [Config And Environment Reference](reference/config-env.md) |
| Inspect the ten-layer system shape | [Ten Layer LangGraph Map](architecture/ten-layer-langgraph-map.md) |
| Read module responsibilities | [Module Docs](modules/README.md) |
| Read runtime operations reports | [Operations](operations/) |
| Read reviews and lessons | [Reviews](reviews/README.md), [Lessons](lessons/README.md) |
| Contribute without letting docs rot | [Contributing](../CONTRIBUTING.md) |

## Documentation Types

| Type | Purpose | Local path |
| --- | --- | --- |
| Tutorial | Learn by following a safe, working path. | `docs/tutorials/` |
| How-to | Complete one job after you know the basics. | `docs/how-to/` |
| Reference | Look up factual commands, interfaces, receipts, and config. | `docs/reference/` |
| Explanation | Understand architecture, trade-offs, decisions, and doctrine. | `docs/explanation/` plus existing `architecture/`, `adr/`, `think/`, and `notes/` |

Runtime evidence such as receipts, reports, reviews, lessons, and operations
outputs is related to documentation, but it is not the same thing as authored
guidance.

## Safety Rule

Tutorials and how-tos must teach the brakes as first-class behavior:

- default no live execution;
- `execution_allowed=false` unless a layer explicitly proves otherwise;
- human review before proposal/risk/execution promotion;
- Riskfolio/vectorbt/indicators are evidence, not authority;
- lesson drafts do not become rules until a human promotes them.
