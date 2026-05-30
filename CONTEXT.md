# FinHarness Context

FinHarness is a trading research and execution harness.

## Domain Terms

Strategy Research:
  Candidate signal discovery and parameter exploration. This belongs behind
  mature research wheels such as vectorbt, not local strategy engines.

Execution Engine:
  Order management, fill modeling, portfolio accounting, and live execution
  semantics. This belongs behind mature trading engines such as
  NautilusTrader or official venue tooling, not local homemade routers.

Venue Adapter:
  A thin adapter around an official broker or exchange surface. It may normalize
  symbols, enforce allowlists, and record receipts. It must not reimplement
  exchange authentication, matching, portfolio accounting, or order semantics.

Risk Gate:
  A pre-trade control that decides whether a proposed action can continue. It
  may reject trades based on drawdown, leverage, order size, missing thesis, or
  missing human confirmation.

Receipt:
  A durable record of inputs, tool versions, commands, decisions, outputs, and
  known limitations. A receipt is evidence, not proof of future performance.

Workflow:
  A reproducible sequence connecting data, research, risk, execution, and
  reporting. Workflow code should orchestrate mature modules rather than hide
  trading logic inside scripts.

Rust Local Layer:
  The default language for new local FinHarness implementation. Venue adapters,
  risk gates, receipt writers, command wrappers, and workflow executables should
  be written in Rust unless they must directly call a mature Python-only wheel.

Python Bridge:
  A small, isolated bridge used only when a mature Python ecosystem tool is the
  owner of the capability, such as vectorbt, Riskfolio-Lib, QuantStats,
  NautilusTrader Python APIs, LangGraph, or OpenAI Agents SDK. Python bridge
  code must not become strategy logic, order routing, portfolio accounting, or
  long-lived scripts.

## Architecture Rule

FinHarness local code may contain adapters, guards, receipts, workflows, and
tests. It must not grow homemade strategy engines, order routers, portfolio
accounting, fill models, optimizers, or live execution semantics.

New local implementation is Rust-first. Do not add new Python scripts as the
default path. If Python is unavoidable because the mature wheel is Python-only,
keep it behind a narrow Taskfile entry or Rust wrapper and document why the
bridge exists.
