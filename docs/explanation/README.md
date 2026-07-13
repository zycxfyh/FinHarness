# Explanation

Explanation docs answer why the system is shaped this way. They are useful after
the golden path, but they should not be required for a first run.

Current explanation sources:

- Architecture plans and specs: [../architecture/](../architecture/).
- ADRs: [../adr/](../adr/).
- Thinking notes: [../think/](../think/).
- Research and implementation notes: [../notes/](../notes/).
- Documentation plan: [../architecture/documentation-and-onboarding-plan.md](../architecture/documentation-and-onboarding-plan.md).

## Start With These

| Question | Read |
| --- | --- |
| Why use mature wheels instead of local engines? | [Mature Wheel Control Plane](../architecture/mature-wheel-control-plane.md) |
| Why is live execution blocked by default? | [Discipline Layer Baseline](../architecture/discipline-layer-baseline.md) |
| How do policy rules map to code? | [Policy Contract](../architecture/policy-contract.md) |
| What evidence do receipts capture? | [Evidence Inventory](../architecture/evidence-inventory.md) |
| How does the current system fit together? | [System Map](../architecture/system-map.md) |
| How should docs stay usable? | [Documentation & Onboarding Plan](../architecture/documentation-and-onboarding-plan.md) |

## Explanation Index

| Theme | Existing docs |
| --- | --- |
| Architecture and specs | [architecture/](../architecture/) |
| Decisions | [adr/](../adr/) |
| Project thinking | [think/](../think/) |
| Implementation and research notes | [notes/](../notes/) |
| Operating models | [finance operating model](../finance-operating-model.md), [industry operating models](../industry-operating-models.md), [personal governance](../personal-governance.md) |
| Security explanations | [security/](../security/) |
| Testing explanations | [testing/](../testing/) |

The current repository still keeps many explanation files in their historical
locations. This index is the doorway before a larger reclassification. Do not
make a first-time user read explanation docs before running the golden path.
