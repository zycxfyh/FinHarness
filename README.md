# FinHarness

FinHarness is a local-first personal capital review and decision system. It
mirrors capital evidence into a receipt-backed state model, derives bounded
observations and decision candidates, supports governed human review, and keeps
execution on a simulated substrate.

The current product objective is a verified material capital decision review:

```text
trusted capital state
-> admitted evidence
-> reviewable decision candidate
-> human decide / defer / reject
-> outcome review and learning
```

Start with the [Current System](docs/current-system.md) for the shortest accurate
orientation. Use the [documentation task map](docs/README.md) for supported user,
operator, developer, auditor, and architecture routes.

## Current boundary

Current main includes:

- read-only capital import from a FinHarness-contract CSV or Beancount ledger;
- receipt-backed capital state, truth-readiness reporting, exposure, and Daily
  Brief surfaces;
- governed proposal generation and local human review;
- a local read-only cockpit and a separate loopback-only governed review mode;
- a canonical Execution Kernel on a simulated adapter;
- bounded Agent read/explain and candidate-producing surfaces under
  FinHarness-owned admission, authority, receipts, and stop conditions.

Current main does **not** include a real broker SDK, funded account, external
venue submission, live trading, transfer, tax submission, public hosted Product
Agent, or delegated autonomous capital manager.

Product direction is documented separately under [`docs/product/`](docs/product/)
and [`docs/product-north-star.md`](docs/product-north-star.md). Direction is not a
current capability claim.

## Setup

Use the locked project toolchain:

```bash
mise trust
mise install
task setup
task doctor
```

Use existing `task ...` entries rather than ad hoc package-manager or global
Python commands. `task --list` is the canonical command inventory.

## Safe local entrypoints

Import capital evidence:

```bash
task personal-finance:import -- path/to/export.csv
task beancount:import -- path/to/ledger.beancount
```

Build observations and decision candidates:

```bash
task brief:daily
task decisions:scan
```

Start the persistent local cockpit in read-only mode:

```bash
task api:serve
```

Start the loopback-only governed human-review mode:

```bash
task cockpit:review
```

Use the same explicit `--state-db` and `--receipt-root` paths across mode changes
and restarts. Read-only mode rejects every write. Review mode admits only its
bounded human-review actions and still exposes no real execution capability.

For an isolated demonstration of proposal/review/receipt mechanics:

```bash
task decisions:golden-path
```

This demo direct-seeds an isolated temporary workspace. It does not prove
canonical capital import, capital-truth readiness, Daily Brief, persistent
review continuity, or a complete first-capital-review journey.

## Engineering rule

FinHarness owns capital truth, evidence and decision admission, authority,
receipts, review, and recovery. Mature libraries and official tools should own
commodity finance, data, and execution mechanics where they are suitable.

Prefer, in order:

1. delete a duplicate mechanism;
2. use the existing canonical boundary;
3. adopt a standard or mature implementation;
4. add the smallest FinHarness-specific adapter or policy;
5. create a new abstraction only after the earlier options are insufficient.

GitHub Issues and pull requests own mutable work state. Code, `Taskfile.yml`, the
FastAPI route graph, models, tests, and generated views own machine facts.
Maintained prose explains and links to those facts; it does not duplicate them as
another registry.

## Verification

Run the smallest relevant checks while developing. Before a final merge
candidate, run the required exact-head project checks for the changed surface.
The full local gate remains:

```bash
task check
```

Documentation/current-graph checks are available through:

```bash
task docs:current-check
```
