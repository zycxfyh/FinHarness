# Archived: legacy Rust control-plane crate

Archived 2026-06-13 per
[docs/adr/2026-06-13-pragmatism-first-supersedes-rust-first.md](../../adr/2026-06-13-pragmatism-first-supersedes-rust-first.md).

This was `crates/finharness-cli` plus the root `Cargo.toml` / `Cargo.lock`. It
held the OKX read/write gate, the behavioral guard, and a minimal receipt
writer. A 2026-06-13 red-team showed the Rust split created a second source of
behavioral truth and left the live path decoupled from the persisted
trading-state, the guard, and any notional cap.

Its capabilities now live in Python, wired through the persisted state and gates:

```text
OKX read           -> scripts/run_okx_read.py        (finharness.okx_cli)
OKX live order      -> scripts/okx_live_order.py       (finharness.okx_live_gate)
behavioral guard    -> scripts/run_trading_guard.py    (finharness.trading_guard)
arg allowlist/redact-> finharness.okx_cli
receipts            -> finharness.okx_live_gate writes data/receipts/okx-live/
```

Kept for history only. Not built, not on any Taskfile path, not in the SBOM.
To revive Rust for a real measured need, follow the ADR: a second language must
read the same persisted state and pass the same gates as the Python path.
