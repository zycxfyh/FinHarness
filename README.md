# FinHarness Lab

FinHarness is an **AI-native personal financial judgment layer**: it helps an
individual see their financial state, risk exposure, decision rationale,
reviewable action options, and what actually happened afterward.

The product is meant to move step by step from situational awareness to governed
planning, paper validation, review, and eventually tightly controlled execution
surfaces. The research / evidence / risk **harness** underneath is the engine
room, not the product surface: every meaningful suggestion carries claims with
evidence, assumptions, limitations, and review state, then produces a receipt.
FinHarness is allowed to advise, explain, simulate, and help the operator build
better financial judgment; it must not pretend any claim is a guaranteed edge.

> **Product direction:** [Product Thesis](docs/product/product-thesis.md) ·
> [Product Roadmap](docs/product/product-roadmap.md) ·
> [Capital Workbench Roadmap](docs/product/capital-workbench-roadmap.md) ·
> [North Star](docs/product-north-star.md).
>
> **New here?** Start with the [docs task map](docs/README.md), then run the
> [Golden Path Tutorial](docs/tutorials/golden-path.md). It walks you through a
> safe end-to-end flow and shows the brakes: human review, receipts, and
> `execution_allowed=false`.

> **Need the framework in one screen?** Use the
> [Framework Index](docs/architecture/framework-index.md). It summarizes each
> FinHarness system, its runtime roots, mature-solution posture, and the check
> that protects it. For the engineering layers that prevent future drag, use
> the [Engineering Leverage Map](docs/architecture/engineering-leverage-map.md).

The engineering approach is to learn by assembling top open-source wheels instead
of rebuilding mature tools, then use them to produce governed financial
suggestions.

- finance data and research
- backtesting and risk metrics
- LLM agents and tool calling
- eval harnesses for reliability
- traceable AI-assisted workflows

## Local Wheels

External projects are cloned into `vendor/` and ignored by git. Treat them as reference implementations and upstream tools.

See [docs/wheels.md](docs/wheels.md) for the current map.

## Toolchain

Use the project toolchain consistently:

- Local implementation: **pragmatism-first** — Python by default for the local
  control plane (adapters, gates, receipts, workflow executables), because the
  rest of the control plane is already Python (one language, one source of
  truth). A second language is justified only by a measured need and must share
  the same persisted state and gates. See
  [docs/adr/2026-06-13-pragmatism-first-supersedes-rust-first.md](docs/adr/2026-06-13-pragmatism-first-supersedes-rust-first.md).
- JavaScript/CLI packages: `pnpm`
- Python commands and dependencies: `uv`
- Project tasks: `task`
- Local tool versions and environment: `mise` + `direnv`

Prefer existing `task ...` entries over ad hoc commands. Do not use `npm`,
`npx`, `pip`, or a global Python interpreter for project workflows unless a
tool specifically has no `pnpm`/`uv` path.

Do not add new ad hoc trading scripts. New local control-plane code stays thin
(adapters, guards, receipts, workflows, tests) and must not grow into homemade
strategy, routing, or accounting engines — that boundary, not the language,
is what carries the safety value.

First-time local setup:

```bash
mise trust
mise install
direnv allow
task setup
task check
```

`task setup` only syncs from the existing lockfiles. Use `task check` as the
standard local verification command.

Wheel checks are split into local imports and provider-backed network calls:

```bash
task wheels:check       # local import/version check
task wheels:data-check  # includes OpenBB/yfinance provider call
```

Legacy Rust control-plane code is archived under
`docs/archive/legacy-rust-crate/` as reference history only (see the
2026-06-13 ADR and live-path proposal). The active local control plane is
Python.

## Current Mainline

FinHarness now follows the Capital OS layering:

```text
import -> state -> policy -> proposal/review -> agent explanation
-> action simulation -> retrospective/learning -> cockpit
```

The current executable mainline is personal capital state, IPS policy checks,
governed proposals, review/attestation, receipts, and the local cockpit. The old
ten-layer trading-signal chain and live-trading entry points have been retired
from mainline. Their historical code is archived under
`experiments/archive/live_trading_legacy/` and must not be imported by product
runtime, API routes, Agent tools, or Taskfile tasks.

## Framework At A Glance

| Part | What it owns | Start here |
| --- | --- | --- |
| State Core + Capital Map | Queryable personal capital state, exposure, daily brief, receipt-backed facts | [Framework Index](docs/architecture/framework-index.md), [Module Map](docs/architecture/module-map.md) |
| IPS + Decision Workflow | User policy, candidate detection, governed proposals, and review gates | [Capital OS Layering](docs/architecture/capital-os-layering.md), [Golden Path](docs/tutorials/golden-path.md) |
| Review System | Human attestation, compare, archive/reopen, annual review, lesson-to-rule | [System Map](docs/architecture/system-map.md) |
| Research Evidence + Mature Wheels | Cite-only evidence and mature adapters; external tools are inputs, not authority | [Research Assets](docs/research/README.md), [Mature Wheel Control Plane](docs/architecture/mature-wheel-control-plane.md) |
| Cockpit/API + Agent Explanation | Local read/review product surface and tool-mediated explanations | [Interface Reference](docs/reference/interfaces.md) |
| EOS Governance + Security | Policy registry, docs-current guard, repo intelligence, hardening, release checks | [Documentation Fact Governance](docs/architecture/documentation-fact-governance.md), [Threat Model](docs/security/finharness-threat-model.md) |

If a change makes this table feel wrong, update the Framework Index, System Map,
Module Map, and current entry docs in the same PR, then run
`task docs:current-check`.

The local B0 cockpit is served by the product API. The API is read plus governed
human attestation: it exposes reads and lets a named human attest a proposal, and
nothing else. There is no order, transfer, live execution, or ceiling-raise
endpoint (tests assert the route boundary).

```bash
task api:serve
# open http://127.0.0.1:8765/cockpit/
```

The browser surface shows Overview, Exposure, Proposals, and Timeline views.
Proposal details include candidate evidence, options, attestations, and revision
history. Human attestations are governance evidence recorded with
`execution_allowed=false`.

Personal-finance state can be mirrored without making FinHarness the ledger.
There are two read-only adapters:

- A direct connection to a real Beancount ledger via `bean-query` (no
  intermediate file). This reads Assets holdings and Liabilities balances:

  ```bash
  task beancount:import -- path/to/ledger.beancount
  ```

- A FinHarness-contract CSV import (the CSV shape is defined by FinHarness;
  produce it from your tool of choice). It supports holdings-only files and
  typed rows for liabilities, goals, cashflows, tax events, insurance policies,
  and document refs:

  ```bash
  task personal-finance:import -- path/to/export.csv
  ```

After importing state, build the read-only daily brief and capital-allocation
candidates. If an active Investment Policy Statement exists, the allocation
detectors read its policy thresholds; otherwise they use conservative defaults.

```bash
task brief:daily
task decisions:scan
```

The candidates are recorded as governed proposals, so they appear in the
existing Proposals view with receipts and revision history.

Monetary fields are stored as exact `Decimal` (TEXT-backed so SQLite does not
round-trip through float): personal-finance amounts and `Position`
quantity/market value/cost basis. Snapshot diffs and observations aggregate in
`Decimal` and present `float` at the receipt/API layer.

Human attestation is fail-closed everywhere: an attestation is review evidence
recorded with `execution_allowed=false`. High-risk proposal approval requires
counter-evidence; rejection remains allowed so the review queue never pressures
the system into fabricating a rationale.

For a safe first run, use the isolated synthetic golden path:

```bash
task decisions:golden-path
```

For current task names, use:

```bash
task --list
task docs:current-check
```

## Early Research Milestone

The early research milestone was to build a small AI financial research
assistant that can:

1. Pull market data.
2. Compute returns, volatility, drawdown, and Sharpe ratio.
3. Run a simple backtest.
4. Ask an agent to produce a cited research note.
5. Evaluate whether the note overclaims or misses risk.

See [docs/week-01.md](docs/week-01.md). This remains useful project history,
but the current mainline is the Capital OS loop above.

## Top Wheels

Core strategy, backtesting, portfolio, and any future execution semantics should
come from mature libraries, not local homemade engines. Mainline execution
entry points are currently archived out of the product runtime.

See [docs/notes/top-wheel-integration-plan.md](docs/notes/top-wheel-integration-plan.md).
See [docs/notes/adopt-not-invent-trading-stack.md](docs/notes/adopt-not-invent-trading-stack.md)
for the hard rule: local code is adapters, guards, workflows, and receipts;
core trading semantics belong to mature projects and official venue tooling.
See [docs/adr/2026-06-13-pragmatism-first-supersedes-rust-first.md](docs/adr/2026-06-13-pragmatism-first-supersedes-rust-first.md)
for the pragmatism-first rule for new local implementation (supersedes the
earlier Rust-first note).
