# FinHarness Documentation

Start with the task you are trying to complete. For the shortest maintained
statement of current capability, boundaries, fact ownership, and restart
context, read [FinHarness Current System](current-system.md).

## Use FinHarness

- Import a FinHarness-contract CSV or Beancount ledger: [How-to guides](how-to/README.md)
- Look up supported commands: [Command Reference](reference/commands.md)
- Inspect API, receipt, and configuration facts: [Reference](reference/README.md)
- Learn proposal/review/receipt mechanics in an isolated demo:
  [Synthetic Golden Path](tutorials/golden-path.md)

The synthetic tutorial is a direct-seeded mechanics demo. It does not prove
canonical capital import, capital-truth readiness, Daily Brief, persistent
review continuity, or a complete first-capital-review journey.

## Operate FinHarness

- Run the local read-only or governed-review cockpit:
  [Command Reference](reference/commands.md)
- Inspect readiness, interfaces, and error boundaries:
  [Interface Reference](reference/interfaces.md)
- Inspect receipts and persistence locations:
  [Receipt Reference](reference/receipts.md)
- Diagnose and recover operational state: [Operations](operations/)

Read-only mode rejects every write. Governed review mode remains loopback-only
and provides no real broker, funded-account, or external execution capability.

## Develop FinHarness

- Set up and verify the locked environment: root [`README.md`](../README.md)
- Follow repository execution rules: [`AGENTS.md`](../AGENTS.md)
- Contribute changes: [`CONTRIBUTING.md`](../CONTRIBUTING.md)
- Inspect current system ownership and runtime roots:
  [System Catalog](architecture/system-catalog.yml)
- Inspect generated module and framework views:
  [Module Map](architecture/module-map.md) and
  [Framework Index](architecture/framework-index.md)

Prefer vertical slices and existing canonical boundaries. Ordinary reversible
implementation details belong in code, tests, Git history, and the owning Issue;
they do not require a new proposal, review, lesson, or module log by default.

## Audit FinHarness

- Current product and capability boundary: [Current System](current-system.md)
- Documentation lifecycle and current graph:
  [Documentation Lifecycle](architecture/documentation-lifecycle.md)
- Documentation fact ownership:
  [Documentation Fact Governance](architecture/documentation-fact-governance.md)
- Security boundary: [Threat Model](security/finharness-threat-model.md)
- Verified engineering debt: [`debt-register.json`](governance/debt-register.json)
- Historical reviews and evidence: [Reviews](reviews/README.md)

## Understand FinHarness

- Current architecture shape: [System Map](architecture/system-map.md)
- Capital and execution layering: [Capital OS Layering](architecture/capital-os-layering.md)
- Product direction: [Product Thesis](product/product-thesis.md) and
  [North Star](product-north-star.md)
- Durable architectural decisions are stored under `docs/adr/` and should be
  read only when their decision context is relevant.

Product direction, proposals, reviews, notes, and old roadmaps are context or
historical evidence. They do not authorize current work or prove current
capability.

## Fact ownership

- GitHub Issue/PR state and labels own mutable work authorization and sequence.
- `Taskfile.yml` owns commands.
- FastAPI routes and models own API facts.
- Source models own schemas and persisted fields.
- `architecture/system-catalog.yml` owns system lifecycle and runtime ownership.
- Maintained prose explains tasks, decisions, and boundaries; it does not become
  a second machine-fact registry.

Current navigation is checked by `task docs:current-check`. Historical material
may preserve old commands and claims as authored evidence, but it must not enter
the maintained task path as current authority.
