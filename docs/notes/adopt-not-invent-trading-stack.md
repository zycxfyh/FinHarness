# Adopt, Do Not Invent Trading Stack

Date: 2026-05-29

Decision: FinHarness is not a trading-engine project.

We use mature, market-tested projects for the hard parts and keep local code as
thin adapters, risk gates, workflow glue, and receipts.

Second decision (updated 2026-06-13): new local implementation is
pragmatism-first — Python by default for the control plane. The first decision
above (adopt, do not invent; thin local code) is the one that carries the
safety value and is unchanged. The earlier "Rust-first" language mandate is
superseded by docs/adr/2026-06-13-pragmatism-first-supersedes-rust-first.md.

## Why

Homemade trading engines fail in the details:

```text
order state
partial fills
cancel/replace races
position accounting
margin and liquidation semantics
fees and funding
backtest/live drift
data alignment
corporate actions
latency and retry behavior
```

Those are not places to be clever. They are places to adopt serious projects
and official venue tooling.

## Adopted Stack

| Responsibility | Owner | Local Role |
| --- | --- | --- |
| Market and reference data | OpenBB, yfinance, OKX CLI | Normalize input and record source receipts |
| Fast strategy research | vectorbt | Parameter sweeps and candidate rejection |
| Event-style learning backtests | Backtrader | Small lifecycle examples only |
| Backtest/live parity | NautilusTrader | Main serious simulation and execution architecture |
| Portfolio construction | Riskfolio-Lib | Target weights and risk-constrained allocation |
| Performance reporting | QuantStats | Tear sheets and return diagnostics |
| Venue execution | Official OKX CLI, Alpaca API | Thin adapters and safety gates |
| Workflow orchestration | LangGraph | Reproducible stateful workflows |
| Agent tools | OpenAI Agents SDK | Tool exposure, not trading logic |
| Evaluation | promptfoo, DeepEval | Overclaim, risk, and regression checks |

## Local Code Allowed

```text
Venue Adapter
Risk Gate
Receipt
Workflow
symbol normalization
command allowlists
tests around gates and adapters
```

New allowed local code should be Rust by default.

## Local Code Forbidden

```text
homemade strategy engine
homemade order router
homemade portfolio accounting
homemade fill model
homemade optimizer
homemade broker/exchange auth
new ad hoc Python trading scripts
```

Python may remain only as a narrow bridge to adopted Python-native projects
such as vectorbt, Riskfolio-Lib, QuantStats, NautilusTrader Python APIs,
LangGraph, OpenAI Agents SDK, OpenBB, and yfinance.

## Execution Architecture

```text
Data Adapter
-> Strategy Research wheel
-> Portfolio/Risk wheel
-> Execution Engine or Official Venue Adapter
-> Receipt
-> QuantStats / eval report
```

For OKX live trading:

```text
strategy signal
-> risk gate
-> order preview
-> human confirmation
-> official okx CLI
-> status reconciliation
-> receipt
```

FinHarness may decide whether a trade is allowed. It should not pretend to be
the exchange, broker, matching engine, margin engine, or institutional OMS.

## Near-Term Refactor Queue

1. Expand the Rust workspace as the local control plane.
2. Deepen Rust receipt types and risk gates.
3. Keep OKX command gating in Rust while still calling the official OKX CLI.
4. Move Alpaca paper wrappers to Rust.
5. Keep Python-only mature wheels behind isolated bridge commands.
6. Use QuantStats for reports once strategy returns exist.
7. Use Riskfolio-Lib for multi-asset position sizing.
8. Make NautilusTrader the serious simulation/live-parity path before expanding
   automated execution.

See [../adr/2026-06-13-pragmatism-first-supersedes-rust-first.md](../adr/2026-06-13-pragmatism-first-supersedes-rust-first.md)
(supersedes the earlier rust-first-local-implementation.md note).
