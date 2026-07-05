# FinHarness Docs

This is the task map for FinHarness documentation. Start with the job you are
trying to do, not with the architecture.

FinHarness is a personal capital governance harness: state, IPS,
proposal/review, evidence, Agent explanation, cockpit surfaces, and the staged
path toward paper validation and controlled capital-action workflows. The docs
should make the product path concrete: understand state, form candidates, review
evidence, validate safely, and learn from outcomes.

## Start Here

- Understand the product direction and category: [Product Thesis](product/product-thesis.md), [Product Roadmap](product/product-roadmap.md), [North Star](product-north-star.md)
- Need the framework in one screen: [Framework Index](architecture/framework-index.md)
- Need the engineering leverage / future-tooling map: [Engineering Leverage Map](architecture/engineering-leverage-map.md)
- New to the project: [Golden Path Tutorial](tutorials/golden-path.md)
- Need to perform one task: [How-to Guides](how-to/README.md)
- Need exact facts, commands, or schemas: [Reference](reference/README.md)
- Need the "why" and design context: [Explanation](explanation/README.md)

## I Want To

| Goal | Use this |
| --- | --- |
| Run the first safe end-to-end flow | [Golden Path Tutorial](tutorials/golden-path.md) |
| See every system's core summary | [Framework Index](architecture/framework-index.md) |
| See which engineering layers prevent future drag | [Engineering Leverage Map](architecture/engineering-leverage-map.md) |
| Understand current architecture layering | [Capital OS Layering](architecture/capital-os-layering.md) |
| Add a mature-wheel adapter | [Add A Mature-Wheel Adapter](how-to/add-mature-wheel-adapter.md) |
| Promote a lesson into a rule | [Promote Lesson To Rule](how-to/promote-lesson-to-rule.md) |
| Understand the mature-wheel migration | [Mature Wheel Control Plane](architecture/mature-wheel-control-plane.md) |
| Check current machine guardrails | `task governance:policies`, [Documentation Fact Governance](architecture/documentation-fact-governance.md) |
| Check current module ownership | [Module Map](architecture/module-map.md) |
| Look up commands | [Command Reference](reference/commands.md) |
| Look up interfaces | [Interface Reference](reference/interfaces.md) |
| Look up receipt fields and locations | [Receipt Reference](reference/receipts.md) |
| Look up config/env vars | [Config And Environment Reference](reference/config-env.md) |
| Understand the system layering (L0–L8) | [Capital OS Layering](architecture/capital-os-layering.md) |
| Keep current docs synchronized with code | [Documentation Fact Governance](architecture/documentation-fact-governance.md) |
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
- `execution_allowed=false` throughout current mainline receipts and records;
- human review before proposal/review promotion;
- external data, Riskfolio/vectorbt-style tools, and research assets are
  evidence, not authority;
- lesson drafts do not become rules until a human promotes them.

Current navigation docs are checked by `task docs:current-check`. Historical
notes, reviews, and archived docs may preserve old commands as historical
evidence; current entry points must match `Taskfile.yml`.
