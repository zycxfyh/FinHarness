# FinHarness Lab

AI finance research and harness engineering lab.

The goal is to learn by assembling top open-source wheels instead of rebuilding mature tools:

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

- Local implementation: Rust-first for new adapters, gates, receipts, and
  workflow executables
- JavaScript/CLI packages: `pnpm`
- Python commands and dependencies: `uv`, only for adopted Python-native wheels
  and narrow bridge commands
- Project tasks: `task`
- Local tool versions and environment: `mise` + `direnv`

Prefer existing `task ...` entries over ad hoc commands. Do not use `npm`,
`npx`, `pip`, or a global Python interpreter for project workflows unless a
tool specifically has no `pnpm`/`uv` path.

Do not add new ad hoc Python trading scripts. New local control-plane code
should be Rust unless it is only bridging an adopted Python-native tool.

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

Rust local control-plane checks:

```bash
task rust:check
cargo run -q -p finharness-cli -- guard --drawdown-pct -3 --consecutive-losses 3 --thesis
```

## Loops

The ten layers are organized as four real loops plus deterministic steps.
Target state B and the topology rationale live in
[docs/think/2026-06-12-target-state-b-and-loop-topology.md](docs/think/2026-06-12-target-state-b-and-loop-topology.md).

```bash
task workflow:daily-evidence   # Loop 1: observation (also on hermes cron, weekday mornings)
task hypotheses:graph -- --llm-enabled   # Loop 2 generator seat: hermes drafts, gates check
task trading-state:show        # Loop 3 feedback edge: persisted behavioral state
task lessons:draft             # Loop 4 v0: draft lesson candidates; a human promotes
```

Human attestation is fail-closed everywhere: risk-gate and execution runs
stay at needs_human_review until a human attests with a written reason
(`scripts/run_risk_gate_graph.py --interactive` pauses at a real LangGraph
interrupt).

## First Milestone

Build a small AI financial research assistant that can:

1. Pull market data.
2. Compute returns, volatility, drawdown, and Sharpe ratio.
3. Run a simple backtest.
4. Ask an agent to produce a cited research note.
5. Evaluate whether the note overclaims or misses risk.

See [docs/week-01.md](docs/week-01.md).

## Trading Reset

When drawdown or consecutive losses start changing behavior, stop using the
project as an execution aid and switch it into review mode:

```bash
task trading:reset-check
```

See [docs/notes/drawdown-reset-protocol.md](docs/notes/drawdown-reset-protocol.md).

## Alpaca Paper

Alpaca is wired as a paper-first regulated-broker sandbox:

```bash
task alpaca:paper-check              # account, positions, open orders
task alpaca:paper-capabilities       # account config, recent orders, activities
task alpaca:paper-config-dry-run     # show broad paper experiment config
task alpaca:paper-config-experiment  # apply broad paper experiment config
task alpaca:paper-assets             # active US equity assets
task alpaca:paper-crypto-assets      # active crypto assets
task alpaca:paper-option-contracts   # SPY option contracts
task alpaca:paper-order-cycle        # tiny paper limit order then cancel
```

The live Alpaca endpoint is intentionally not wired.

## OKX Live

OKX is wired through the official CLI with explicit read/write gates:

```bash
task okx:market
task okx:live-status
task okx:live-read -- account balance
task okx:live-read -- account config
task okx:live-read -- swap positions
task okx:live-read -- swap orders
task okx:demo -- swap orders
```

The OKX read/write gate is now Rust-backed through `finharness-cli`.

Live mutating commands are connected but require both the task and an
environment gate:

```bash
export FINHARNESS_OKX_ENABLE_LIVE_MUTATIONS=1
task okx:live-write -- swap place --instId BTC-USDT-SWAP --side buy --ordType limit --sz 0.01 --tdMode isolated --px 1
```

Do not run live write commands from emotion or without a written plan.

## Top Wheels

Core strategy, backtesting, portfolio, and execution semantics should come from
mature libraries, not local homemade engines.

See [docs/notes/top-wheel-integration-plan.md](docs/notes/top-wheel-integration-plan.md).
See [docs/notes/adopt-not-invent-trading-stack.md](docs/notes/adopt-not-invent-trading-stack.md)
for the hard rule: local code is adapters, guards, workflows, and receipts;
core trading semantics belong to mature projects and official venue tooling.
See [docs/notes/rust-first-local-implementation.md](docs/notes/rust-first-local-implementation.md)
for the Rust-first rule for new local implementation.
