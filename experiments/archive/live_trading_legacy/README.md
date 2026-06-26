# Archived legacy live-trading experiments

This directory contains archived legacy live-trading experiments.

It is not part of the FinHarness mainline runtime.
It must not be imported by production code, CI safety gates, Agent tools, API routes, or Taskfile tasks.
It provides no execution authorization and no investment advice.
It is retained only for historical reference and possible future redesign as a separately gated, non-mainline capability.

## Why it was moved out of mainline (2026-06-26)

FinHarness mainline is now: personal capital state → IPS → Proposal/Review →
Agent explanation → action simulation. Live order execution is a high-consequence
capability with a different risk profile; keeping it in `src/finharness` kept a
hidden mainline dependency (the deterministic fuzz baseline even fuzzed
`trading_guard`) and a persistent CI / CodeQL / dependency / product-narrative
burden. Moving it here makes the mainline safety boundary explicit:

- No live-execution subsystem in mainline.
- No runtime import path into archived live-trading code.
- No Taskfile / CLI / API route that exposes live execution.

## What is here

| Group | Modules |
| --- | --- |
| `okx/` | `okx_cli`, `okx_live_gate`, `okx_policy`, `okx_redaction`, `okx_symbols` |
| `alpaca/` | `alpaca_client` |
| `trading_guard/` | `trading_guard`, `trading_state_store` |
| `governance/` | `effective_rules`, `effective_ceilings`, `market_access_ledger`, `control_owner` |
| `scripts/` | live OKX/Alpaca read/order scripts, `run_trading_guard`, `run_control_certification` |
| `tests/` | the corresponding test modules (no longer collected by the mainline suite) |

## What stayed in mainline (and why)

- `restricted_symbols` — a security allowlist used by the read-only research path;
  it carried only a tiny symbol-normalization helper from `okx_symbols`, which was
  inlined so it no longer depends on archived code. It has no execution capability.
- `run_fuzz_baseline.py` — the deterministic fuzz baseline; its `trading_guard`
  target was dropped (the remaining `security_surface` and `research_assets`
  targets still run). The `okx`/`alpaca` *path-name* checks remain, so the
  security-surface invariant still flags those paths.

If a read-only market-data capability is wanted later, rebuild it as a fresh
ExternalData adapter — do not inherit from this archived live-trading code.
