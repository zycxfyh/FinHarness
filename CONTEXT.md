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

Local Control Plane:
  The language choice for new local FinHarness implementation is
  pragmatism-first: Python by default, because the rest of the control plane
  (LangGraph, risk gate, trading-state store, receipts, mature wheels) is
  already Python — one language, one source of truth. Venue adapters, risk
  gates, receipt writers, command wrappers, and workflow executables live here.
  A second language is justified only by a measured need (performance,
  isolation, a language-only dependency), never by language preference, and it
  must read the same persisted state and pass the same gates as the Python
  path. See docs/adr/2026-06-13-pragmatism-first-supersedes-rust-first.md.

Mature Wheel Boundary:
  Heavy domain capability stays in the mature tool that owns it — vectorbt,
  Riskfolio-Lib, QuantStats, NautilusTrader Python APIs, LangGraph, OpenAI
  Agents SDK, OpenBB. Local code adapts and governs these; it must not become
  strategy logic, order routing, portfolio accounting, or long-lived ad hoc
  scripts.

## Architecture Rule

FinHarness local code may contain adapters, guards, receipts, workflows, and
tests. It must not grow homemade strategy engines, order routers, portfolio
accounting, fill models, optimizers, or live execution semantics.

New local implementation is pragmatism-first: Python by default for the control
plane, kept thin and behind Taskfile entries. The rule that carries the safety
value is the boundary above (adapters/guards/receipts/workflows/tests, no
homemade engines), not the language. A second language must be justified by a
measured need and must share the same persisted state and gates.
