# Rust-First Local Implementation

> SUPERSEDED 2026-06-13 by
> docs/adr/2026-06-13-pragmatism-first-supersedes-rust-first.md.
> The language mandate is now pragmatism-first (Python by default for the local
> control plane). A red-team pass showed the Rust split produced two sources of
> behavioral truth and left the live path decoupled from the guard, the
> persisted state, and any notional cap — the opposite of this note's goal. The
> safety rules below (typed models, explicit errors, control around live
> execution, adopt-not-invent) still stand; only "use Rust for it" is retired.
> This file is kept for history. Do not treat it as current policy.

Date: 2026-05-29

Decision: new FinHarness local implementation should be Rust-first.

Python made the early lab easy to wire together, but it also makes trading
workflows too easy to sprawl into loose scripts. Going forward, local code
should be explicit, typed, compiled, and easier to audit.

## Rule

Use Rust for new local implementation:

```text
Venue Adapter
Risk Gate
Receipt writer
Workflow executable
command wrapper
configuration parser
order preview
reconciliation check
```

Do not add new Python scripts by default.

## Why

Rust is preferred for the local layer because it gives us:

```text
typed domain models
explicit error handling
compiled command binaries
clear module boundaries
less ambient global state
better control around live execution paths
easier review of order/risk/receipt logic
```

This is especially important after a large drawdown. Execution software should
make accidental behavior harder, not easier.

## Python Exception

Python is allowed only as a narrow bridge when the adopted mature tool is
Python-native:

```text
vectorbt
Riskfolio-Lib
QuantStats
NautilusTrader Python APIs
LangGraph
OpenAI Agents SDK
OpenBB
yfinance
promptfoo/DeepEval adjacent harness code
```

Rules for any Python bridge:

```text
must be behind a Taskfile entry or Rust wrapper
must have a receipt or machine-readable output
must not own order routing
must not own portfolio accounting
must not own strategy engine semantics
must not spread business logic across ad hoc scripts
```

## Migration Target

Current Python scripts should be treated as transitional. The target shape is:

```text
Rust CLI/workflow binary
-> official OKX CLI / Alpaca API adapter
-> Python mature-wheel bridge only where unavoidable
-> typed receipt
-> testable risk gate
```

## Current Rust Entry

The first Rust control-plane crate is:

```text
crates/finharness-cli
```

Current Rust-backed commands:

```bash
task rust:check
task trading:reset-check
task okx:live-read -- account config
task okx:demo -- swap orders
task okx:live-write -- swap place ...
task receipt:rust
```

The Rust CLI currently owns:

```text
behavioral trading guard
OKX command allowlist and mutation gate
minimal receipt writer
```

The old Python implementations are transitional until their callers are fully
migrated or removed.

## Near-Term Refactor Order

1. Expand Rust receipt types beyond the minimal writer.
2. Move Alpaca paper account/order wrappers to Rust.
3. Move OKX market snapshot to Rust.
4. Keep vectorbt/Riskfolio/QuantStats/NautilusTrader behind isolated Python
   bridge commands until we replace or embed them through a deliberate design.

## Non-Goal

Rust-first does not mean rebuilding vectorbt, Riskfolio-Lib, QuantStats,
NautilusTrader, OpenBB, LangGraph, or the official OKX tooling. It means our
local glue and execution control plane should stop growing as Python scripts.
