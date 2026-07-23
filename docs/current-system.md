# FinHarness Current System

> **Documentation lifecycle:** `current`

This page is the shortest maintained orientation for FinHarness. It answers what the system is now, which paths are supported, which boundaries remain closed, and where each kind of fact is owned. It is not a roadmap, architecture catalog, or copy of mutable Issue state.

## Product identity

FinHarness is a local-first personal capital Agent system. It mirrors capital evidence into a receipt-backed Capital World, carries durable Missions and bounded Delegations, and executes only registered simulated Effects through a recoverable local Runtime. Governed human review remains available while the new Agent-native path becomes the primary product trunk.

The current product objective is the verified material capital decision review owned by [Program #277](https://github.com/zycxfyh/FinHarness/issues/277):

```text
trusted Capital World
-> durable Mission and Belief
-> bounded Delegation
-> admitted registered Effect
-> recoverable Job / Attempt
-> simulated execution and reconciliation
-> Consequence, report, and learning
```

The current request or assigned task owns the immediate result. GitHub Issues, labels, relationships, and pull requests coordinate durable shared work when useful; they are not a per-change permission system. Maintained Markdown must not copy changing child status or maintain a second implementation roadmap.

## Supported current paths

### Capital input and truth inspection

- `task personal-finance:import -- path/to/export.csv` imports a FinHarness-contract CSV through the production import boundary.
- `task beancount:import -- path/to/ledger.beancount` mirrors a Beancount ledger read-only through `bean-query`.
- `GET /ready/truth` reports capital-truth admission separately from evidence integrity and fails closed on missing, corrupt, stale, partial, or blocked evidence.
- Production capital imports bind a stable logical source identity, immutable raw and normalized Projection Artifacts, and one deterministic Capital World selected by business and knowledge time.
- Exposure, Daily Brief, Cockpit, Decision scan, Agent capital context, readiness, and Scenario admission consume or bind the server-resolved Capital World rather than selecting independent latest snapshots.

The canonical command list is `Taskfile.yml`; route and response truth belongs to the effective FastAPI route graph and models, not this page.

### Observation and candidate generation

- `task brief:daily` records the current Daily Brief.
- `task decisions:scan` records capital-allocation candidates as governed proposals.
- Exposure, positions, proposals, and timeline evidence are available through the local API and cockpit surfaces.

### Local Agent Shell

- `task agent:shell` builds the recoverable Runtime and serves the loopback-only product shell at `/agent-ui/`.
- The process creates one explicit local Principal and AgentRuntimeIdentity, reads provider/model configuration from environment only, and never asks the browser for an API key.
- The supported journey is: inspect the admitted Capital World → start one idempotent Mission and Delegation → use read-only conversation → submit a structured offline paper Effect → inspect Runtime Job/Attempt and reconciliation results.
- Free-text conversation cannot create Effects. The browser cannot select an executable, environment, credential, authoritative price, or pre-trade position. Live external execution remains unavailable.
- Paper Effects create an identity-bound pending domain receipt before Runtime dispatch and atomically complete it after reconciliation. If either domain-receipt completion or the outer identity terminal acknowledgement is lost, the identity receipt remains pending; the typed resolver observes the same Runtime Job, verifies Mission, EffectIntent, Admission, ExecutionReport, PositionDelta, and matched Reconciliation, completes the domain receipt, and reconstructs the original response without redispatching the Runtime.

### Canonical synthetic acceptance

- `task acceptance:agent-shell` proves the first product-complete local journey through authenticated HTTP and the real Rust Runtime: bootstrap → Mission replay → read-only conversation → structured paper Effect → systemd Worker → reconciliation → idempotent replay. It also proves browser secret input and live execution remain closed.

- `task acceptance:capital-runtime` proves the first real Agent-native execution trunk:
  authenticated Principal and Agent Runtime → admitted Effect → registered Rust Runtime operation
  → idempotent Job/Attempt → systemd/cgroup-owned Python Worker → simulated Execution Kernel
  → PositionDelta and Reconciliation → Effect bound back to its Runtime Job. The caller cannot
  select an executable, environment, pre-trade position, or authoritative reference price.

- `task acceptance:capital-agent-core` proves the thin personal-capital path:
  admitted Capital World → immutable Constitution → durable Mission and Belief
  checkpoint → bounded Delegation → idempotent simulated Effect → Execution Kernel
  → updated Capital World → Consequence → checkpoint/restart/close. It also proves
  stale-world rejection, revocation, duplicate suppression, and explicit claimed-effect
  reconciliation. It uses isolated synthetic state and has no live external effect.

- `task acceptance:capital-review` proves canonical CSV import, admitted truth,
  Exposure, Daily Brief, Decision scan, governed human review, blocked valuation,
  stable source identity across a path move, historical/current Capital World
  resolution, missing-FX suppression, durable receipts, application restart,
  Artifact replay, and backup-restore identity preservation.
- It uses checked-in synthetic templates with runtime clocks and never connects a
  broker or grants execution authority.
- `task dogfood:scf-capital` downloads the pinned Federal Reserve 2022 Survey of
  Consumer Finances public extract, verifies its archive digest, selects one
  deterministic first-implicate household near weighted-median net worth, maps its
  aggregate balance sheet into the production importer, and verifies the resulting
  Capital World and Agent context. It is a mature public-data interoperability
  dogfood, not a current household truth claim or a production workload benchmark.
- `task dogfood:capital-readonly` extends the pinned SCF path through the bounded
  read-only Agent Work Loop, preserves budgeted typed observations, emits a
  `CapitalWorldAudit` with Observed/Inferred/Unsupported claims and semantic stop
  conditions, replays the same audit from persisted tool artifacts, and proves that
  the logical StateCore digest and domain receipts do not change.
- `task agent:run` applies the same bounded audit to the local StateCore, writes Agent
  evidence only under ignored `.artifacts/agent-runs/`, verifies the StateCore and
  domain receipt tree are unchanged, and attempts one OpenAI-compatible JSON review
  using `OPENAI_API_KEY`, optional `OPENAI_BASE_URL`, and `FINHARNESS_AGENT_MODEL`.
- `task benchmark:capital-world` reports bounded local resolver latency for explicit
  synthetic source counts. It is not a production SLO and must not be generalized to
  concurrent, remote-Artifact, or all-workload performance.

### Human review

- `task api:serve` starts the persistent local cockpit in read-only mode; all writes fail closed.
- `task cockpit:review` starts the loopback-only governed human-review mode.
- The same explicit `--state-db` and `--receipt-root` paths must be reused across mode changes and restarts.

Review evidence does not grant execution authority.

### Synthetic mechanics demo

`task decisions:golden-path` is an isolated direct-seeded proposal/review/receipt replay demo. It is useful for learning mechanics, but it does not prove canonical capital import, capital-truth readiness, Daily Brief, persistent review continuity, or the first complete capital-review journey.

## Current system shape

```text
external capital evidence
-> receipt-backed State Core and Capital World
-> Mission / Belief / Delegation
-> registered Effect admission
-> recoverable Rust Job / Attempt
-> systemd-owned Python capital Worker
-> simulated Execution Kernel
-> reconciliation / Consequence / report
```

A bounded read/explain Agent loop remains available. The personal-capital core now connects durable Mission/checkpoint/resume, selected Belief artifacts, a single-principal simulated-order Delegation, world-bound Effect admission, and system-derived position/price facts to a transplanted Rust execution kernel. The kernel owns idempotent Job/Attempt dispatch, process-tree ownership, cancellation, bounded Artifacts, terminal commit, and restart/orphan recovery; Python retains Capital World, Mission, Delegation, Risk, broker reconciliation, Consequence, and reports. No model runtime gains live external authority.

## Explicit non-capabilities

Current main does not provide:

- a real broker SDK, funded-account connection, or external venue submission;
- live trading, transfers, tax submission, or other funded external effects;
- a public hosted Product Agent, multi-user login system, or live delegated autonomous capital manager; the current Agent Shell is one explicit loopback-only local session;
- a scheduler, daemon, automatic trigger engine, or general multi-Agent runtime; explicit local Mission checkpoint/resume is the only cross-cycle Agent state;
- a longitudinal real-user capital-review pilot with outcome follow-up;
- a real household Capital World and longitudinal outcome review; provider-backed
  model acceptance currently uses public-data dogfood or a typed empty-world stop.

Future direction documents may discuss these possibilities. They are not current capability claims.

## Fact ownership

| Fact | Canonical owner |
| --- | --- |
| Immediate requested result | Current user or assigned task |
| Durable shared work coordination | GitHub Issues, pull requests, labels, and native relationships when used |
| Product objective | Program #277 |
| Runtime behavior | Source code and executable tests |
| Commands | `Taskfile.yml` |
| API operations | FastAPI route graph and OpenAPI/models |
| Configuration | Canonical config models and direct environment reads |
| Schemas | Pydantic/SQLModel/receipt schema sources |
| System ownership and lifecycle | `docs/architecture/system-catalog.yml` |
| Product direction | `docs/product/product-thesis.md` and `docs/product-north-star.md` |
| Historical decisions and evidence | ADRs, proposals, reviews, notes, old roadmaps, and Git history |

A document may explain a machine-owned fact or link to it. It must not become a second mutable registry.
The stable engineering responsibility model is linked once in [`Agentic Engineering Principles`](engineering/agentic-abstraction-principles.md).

## Orientation for a new Agent or maintainer

1. Read this page and the root `README.md`.
2. Inspect the exact current `main` commit.
3. Read the relevant Issue or PR when one exists; do not create one merely to unlock reversible work.
4. Locate the production owner, relevant tests, and current task/API boundary.
5. Treat proposals, reviews, notes, old roadmaps, and archived files as context, not current capability.
6. Prefer deleting or replacing a duplicate mechanism before adding another.
7. Run the smallest useful checks during development and the required exact-head checks before merge.

## Documentation rule

Write or update maintained documentation only when it:

- enables a real supported task;
- explains a durable decision or boundary that code cannot express;
- assigns one canonical fact owner;
- preserves unique evidence that Git history alone cannot make discoverable;
- materially reduces future diagnosis or handoff cost.

Ordinary reversible implementation details belong in code, tests, commit history, and optionally a coordinating Issue. They do not require a new proposal, module log, review, lesson, or roadmap entry by default.
