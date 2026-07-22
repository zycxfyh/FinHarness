# FinHarness Current System

> **Documentation lifecycle:** `current`

This page is the shortest maintained orientation for FinHarness. It answers what
the system is now, which paths are supported, which boundaries remain closed,
and where each kind of fact is owned. It is not a roadmap, architecture catalog,
or copy of mutable Issue state.

## Product identity

FinHarness is a local-first personal capital review and decision system. It
mirrors capital evidence into a receipt-backed state model, derives bounded
observations and decision candidates, supports governed human review, and keeps
execution on a simulated substrate.

The current product objective is the verified material capital decision review
owned by [Program #277](https://github.com/zycxfyh/FinHarness/issues/277):

```text
trusted capital state
-> admitted evidence
-> reviewable decision candidate
-> human decide / defer / reject
-> outcome review and learning
```

GitHub Issue state, labels, relationships, and pull requests own current work
authorization and sequence. Maintained Markdown must not copy changing child
status or maintain a second implementation roadmap.

## Supported current paths

### Capital input and truth inspection

- `task personal-finance:import -- path/to/export.csv` imports a
  FinHarness-contract CSV through the production import boundary.
- `task beancount:import -- path/to/ledger.beancount` mirrors a Beancount ledger
  read-only through `bean-query`.
- `GET /ready/truth` reports capital-truth admission separately from evidence
  integrity and fails closed on missing, corrupt, stale, partial, or blocked
  evidence.

The canonical command list is `Taskfile.yml`; route and response truth belongs
to the effective FastAPI route graph and models, not this page.

### Observation and candidate generation

- `task brief:daily` records the current Daily Brief.
- `task decisions:scan` records capital-allocation candidates as governed
  proposals.
- Exposure, positions, proposals, and timeline evidence are available through
  the local API and cockpit surfaces.

### Human review

- `task api:serve` starts the persistent local cockpit in read-only mode; all
  writes fail closed.
- `task cockpit:review` starts the loopback-only governed human-review mode.
- The same explicit `--state-db` and `--receipt-root` paths must be reused across
  mode changes and restarts.

Review evidence does not grant execution authority.

### Synthetic mechanics demo

`task decisions:golden-path` is an isolated direct-seeded
proposal/review/receipt replay demo. It is useful for learning mechanics, but it
does not prove canonical capital import, capital-truth readiness, Daily Brief,
persistent review continuity, or the first complete capital-review journey.

## Current system shape

```text
external capital evidence
-> production importer
-> receipt-backed State Core
-> exposure / Daily Brief
-> decision candidates
-> governed human review
-> simulated Execution Kernel
-> reconciliation / review evidence
```

A bounded Agent operating cycle and read/explain tool surface exist, but Agent
output remains evidence or a candidate at current authority levels. FinHarness
owns admission, state, authority, dispatch, receipts, stop conditions, and
replay; external model runtimes do not own canonical state or effects.

## Explicit non-capabilities

Current main does not provide:

- a real broker SDK, funded-account connection, or external venue submission;
- live trading, transfers, tax submission, or other funded external effects;
- a public hosted Product Agent or delegated autonomous capital manager;
- cross-cycle Agent session/resume, scheduler, daemon, or general multi-Agent
  runtime;
- an independently verified canonical first-run capital-review journey from
  clean documentation.

Future direction documents may discuss these possibilities. They are not
current capability claims.

## Fact ownership

| Fact | Canonical owner |
| --- | --- |
| Current work authorization and sequence | GitHub Issue/PR state, labels, and native relationships |
| Product objective | Program #277 |
| Runtime behavior | Source code and executable tests |
| Commands | `Taskfile.yml` |
| API operations | FastAPI route graph and OpenAPI/models |
| Configuration | Canonical config models and direct environment reads |
| Schemas | Pydantic/SQLModel/receipt schema sources |
| System ownership and lifecycle | `docs/architecture/system-catalog.yml` |
| Verified engineering debt | `docs/governance/debt-register.json` |
| Product direction | `docs/product/` and `docs/product-north-star.md` |
| Historical decisions and evidence | ADRs, proposals, reviews, notes, and Git history |

A document may explain a machine-owned fact or link to it. It must not become a
second mutable registry.

## Orientation for a new Agent or maintainer

1. Read this page and the root `README.md`.
2. Inspect the exact current `main` commit.
3. Read the active GitHub implementation leaf and its parent objective.
4. Locate the production owner, relevant tests, and current task/API boundary.
5. Treat proposals, reviews, notes, old roadmaps, and archived files as context,
   not current authorization.
6. Prefer deleting or replacing a duplicate mechanism before adding another.
7. Run the smallest relevant checks during development and the required
   exact-head checks before merge.

## Documentation rule

Write or update maintained documentation only when it does at least one of the
following:

- enables a real supported task;
- explains a durable decision or boundary that code cannot express;
- assigns one canonical fact owner;
- preserves unique evidence that Git history alone cannot make discoverable;
- materially reduces future diagnosis or handoff cost.

Ordinary reversible implementation details belong in code, tests, commit
history, and the owning Issue. They do not require a new proposal, module log,
review, lesson, or roadmap entry by default.
