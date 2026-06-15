# FinHarness Lab

AI finance decision and research harness for evidence-bound financial judgment.

> **New here? Start with the [User Guide](docs/GUIDE.md).** It walks you through what
> FinHarness is (and is not) and has you run the golden path yourself in ~30 minutes —
> no brokerage account or API key required.

The goal is to learn by assembling top open-source wheels instead of rebuilding mature tools,
then use them to produce governed financial suggestions: claims with evidence,
assumptions, rejected alternatives, risk notes, receipts, and human authority
boundaries. FinHarness is allowed to advise; it is not allowed to pretend its
advice is a guaranteed edge or an execution authorization.

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

## Loops

The ten layers are organized as four real loops plus deterministic steps.
Target state B and the topology rationale live in
[docs/think/2026-06-12-target-state-b-and-loop-topology.md](docs/think/2026-06-12-target-state-b-and-loop-topology.md).

```bash
task cockpit:market          # one-screen watchlist: data, indicators, broken paths, reviews
task workflow:daily-evidence   # Loop 1: observation (also on hermes cron, weekday mornings)
task hypotheses:graph -- --llm-enabled   # Loop 2 generator seat: hermes drafts, gates check
task trading-state:show        # Loop 3 feedback edge: persisted behavioral state
task lessons:draft             # Loop 4 v0: draft lesson candidates; a human promotes
```

The cockpit writes `docs/operations/market-cockpit-latest.md` and
`data/receipts/market-cockpit/latest.json`. It is review evidence only:
`execution_allowed` stays false and it does not produce orders, position
changes, or execution authority. It may surface evidence-bound suggestions,
warnings, and review prompts; those must remain conditional, auditable, and
separate from any broker action.

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

The OKX read/write gate runs through Python (`finharness.okx_cli` /
`finharness.okx_live_gate`); the legacy Rust crate is archived under
docs/archive/legacy-rust-crate (2026-06-13 ADR).

Every live mutation passes through the fail-closed gate
([scripts/okx_live_order.py](scripts/okx_live_order.py)): the behavioral guard
evaluated against persisted trading-state, a notional cap (uncomputable notional
fails closed), attestation, and a receipt for every attempt.

A live write now requires **two** independent, deliberate opt-ins:

- `FINHARNESS_OKX_LIVE_WRITE_ARMED=1` — the hard kill-switch. It defaults to
  disarmed (fail-closed) and is the compensating control for deployments without
  an OKX IP allowlist (e.g. a rotating-IP VPN): a leaked key cannot place orders
  through the harness while it stays disarmed. Reads are never affected.
- `FINHARNESS_OKX_ENABLE_LIVE_MUTATIONS=1` — the original env gate.

Authorization is then an interactive confirmation that echoes the order:

```bash
export FINHARNESS_OKX_LIVE_WRITE_ARMED=1
export FINHARNESS_OKX_ENABLE_LIVE_MUTATIONS=1
task okx:live-write -- swap place --instId BTC-USDT-SWAP --side buy --ordType limit \
  --sz 0.01 --tdMode isolated --px 1 \
  --attester "you" --reason "written plan ref" --thesis
```

Leave `FINHARNESS_OKX_LIVE_WRITE_ARMED` unset to keep OKX effectively read-only
(the intended posture when execution runs on Alpaca paper instead).

Add `--dry-run` to see the gate decision without touching the broker. The gate
refuses before reaching the okx binary on hard-stop drawdown/loss state, an
over-cap notional, a missing thesis, or missing attestation. See the 2026-06-13
red-team review and live-path proposal under docs/. Do not run live write
commands from emotion or without a written plan.

## Top Wheels

Core strategy, backtesting, portfolio, and execution semantics should come from
mature libraries, not local homemade engines.

See [docs/notes/top-wheel-integration-plan.md](docs/notes/top-wheel-integration-plan.md).
See [docs/notes/adopt-not-invent-trading-stack.md](docs/notes/adopt-not-invent-trading-stack.md)
for the hard rule: local code is adapters, guards, workflows, and receipts;
core trading semantics belong to mature projects and official venue tooling.
See [docs/adr/2026-06-13-pragmatism-first-supersedes-rust-first.md](docs/adr/2026-06-13-pragmatism-first-supersedes-rust-first.md)
for the pragmatism-first rule for new local implementation (supersedes the
earlier Rust-first note).
