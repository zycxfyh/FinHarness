# Top Wheel Integration Plan

Date: 2026-05-28

Decision: FinHarness should not grow a homemade trading engine.

Use mature wheels for core trading system responsibilities and keep local code
as thin adapters, safety gates, receipts, and workflow glue.

New local implementation is pragmatism-first — Python by default for the
control plane (supersedes Rust-first; see
docs/adr/2026-06-13-pragmatism-first-supersedes-rust-first.md). Heavy domain
capability still belongs to the mature wheel that owns it.

## Current State

Installed and wired:

```text
OpenBB / yfinance: market data path
Backtrader: local event-style backtest path
vectorbt: installed for vectorized research
NautilusTrader: installed for serious backtest/live parity work
Riskfolio-Lib: installed for portfolio construction
QuantStats: installed for performance reporting
OpenAI Agents SDK: tool harness
LangGraph: workflow orchestration
promptfoo / DeepEval: eval harness
```

## Retired Homemade Pieces

Removed:

```text
src/finharness/simple_backtest.py
src/finharness/strategy_engine.py
src/finharness/strategies.py
experiments/first_backtest.py
scripts/strategy_signal_demo.py
tests/test_strategy_engine.py
```

Reason:

```text
These were useful sketches, but they were shallow modules. Backtesting,
portfolio accounting, order simulation, and execution semantics should live in
mature trading engines.
```

## Target Stack

### Research / Fast Screening

Use `vectorbt` for vectorized research, parameter sweeps, and quick idea
triage.

Local role:

```text
OKX/OpenBB data -> vectorbt research notebook/script -> candidate strategy report
```

### Backtesting / Legacy-Compatible Learning

Use `Backtrader` for simple local backtests and learning strategy lifecycle.

Local role:

```text
normalized OHLCV -> Backtrader strategy/analyzers -> risk summary
```

### Production-Grade Research-To-Live Parity

Use `NautilusTrader` for serious event-driven simulation, sandbox, and live
architecture.

Local role:

```text
market data catalog -> Nautilus backtest/sandbox -> execution reconciliation
```

Do not hand-roll order management, portfolio accounting, fill modeling, or live
node semantics.

### Portfolio Optimization

Use `Riskfolio-Lib` for portfolio construction experiments once we have enough
assets and historical returns.

Local role:

```text
returns matrix -> risk model / constraints -> target weights
```

### Performance Reporting

Use `QuantStats` for tear sheets and return diagnostics when strategy returns
are available.

Local role:

```text
strategy returns -> report -> eval checks
```

## Safety Boundary

Local code may do:

```text
credential avoidance
official OKX CLI wrapper with read/write gates
drawdown reset guard
task entrypoints
workflow receipts
eval prompts
adapter glue
```

New local glue should be Python by default (pragmatism-first; see the
2026-06-13 ADR).

Local code must not do:

```text
homemade execution engine
homemade live order router
homemade portfolio accounting
homemade fill model
homemade optimizer
new ad hoc Python trading scripts
```

## Next Step

Use the installed mature wheels in this order:

```text
vectorbt -> QuantStats -> Riskfolio-Lib -> NautilusTrader
```

Do not expand live automation until the signal path has a research report, risk
budget, execution preview, and receipt.

Control-plane shape (pragmatism-first):

```text
Python control plane -> mature-wheel call where the wheel owns the capability
```
