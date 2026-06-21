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

New local control-plane code should be Python by default, because the active
state, workflow, guard, receipt, and mature-wheel integration path is already
Python. A second language must be justified by a concrete measured need and
must share the same persisted state and gates.

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

Python remains the active local control-plane language for adopted Python-native
projects such as vectorbt, Riskfolio-Lib, QuantStats, NautilusTrader Python APIs,
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

## Near-Term Implementation Queue

1. Keep the Python control plane connected to one persisted state and one set of gates.
2. Deepen receipt types and risk gates in the Python control plane.
3. Keep OKX command gating in Python while still calling official venue tooling.
4. Keep Alpaca paper wrappers behind the same Python guard/receipt discipline.
5. Keep mature third-party libraries behind thin adapter commands.
6. Use QuantStats for reports once strategy returns exist.
7. Use Riskfolio-Lib for multi-asset position sizing.
8. Make NautilusTrader the serious simulation/live-parity path before expanding
   automated execution.

See [../adr/2026-06-13-pragmatism-first-supersedes-rust-first.md](../adr/2026-06-13-pragmatism-first-supersedes-rust-first.md)
(supersedes the earlier rust-first-local-implementation.md note).
