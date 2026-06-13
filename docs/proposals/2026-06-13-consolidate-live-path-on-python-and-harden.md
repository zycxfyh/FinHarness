# Proposal: Consolidate the Live Path on Python and Harden It

Date: 2026-06-13
Status: proposed
Author: FinHarness project operator and Claude
Depends on: docs/adr/2026-06-13-pragmatism-first-supersedes-rust-first.md
Closes: F1-F9 from docs/reviews/2026-06-13-redteam-live-path-and-language-doctrine.md

## Charter

The live OKX write path must be the most-gated path in the system, not the
least. Today it is a thin Rust wrapper decoupled from the guard, the persisted
behavioral state, and any notional cap. This proposal moves the live path onto
Python (per the 2026-06-13 ADR) and wires it through the same gates every other
decision passes.

## Boundary

In scope:

```text
- one Python live-path entry that reads data/state/trading-state.json
- a fail-closed behavioral guard call before any mutation
- a hard notional/size cap on live orders
- a receipt for every live attempt (allowed or blocked)
- per-action argument allowlisting (replace the denylist)
- complete output redaction + no raw stderr leak
- a conservative trading-state merge (protective state cannot be weakened)
- attestation hardened beyond a bare boolean
- re-point Taskfile okx:* and guard tasks to Python; archive the Rust crate
```

Non-goals (unchanged boundaries):

```text
- no autonomous trading; READY/PASS never authorizes a live order
- no homemade order routing, matching, or portfolio accounting
- the ten-layer execution layer stays a fake paper adapter; real orders only
  ever come from the explicit live-path entry below
```

## Fix design (finding → change)

```text
F6  merge_into_risk_context: protective state must never be weakened by a
    hand-fed context. Take the more conservative value:
      drawdown_pct        = min(persisted, supplied)   # more negative wins
      consecutive_losses  = max(persisted, supplied)
      behavior_reset_required = persisted OR supplied
    Explicit keys may only make state stricter, never cleaner.
    STATUS: implemented & verified 2026-06-13 (conservative min/max/OR merge;
    bypass test replaced; trading-state suite 10 passed, risk-gate + ten-layer
    17 passed, no regression).

F1/F4/F5  New module finharness/okx_live_gate.py (Python) that every live
    mutation must pass through:
      1. load_trading_state()  -> evaluate_trading_state() (guard)
         hard_stop => refuse, write a blocked receipt, exit non-zero.
      2. enforce a notional cap derived from order args (size * price or an
         explicit --max-notional), refuse + receipt on breach.
      3. on success, write a receipt AND fold the attempt into trading-state
         so live activity updates the bounding state (closes F5).
    run_okx_live_mutation_command becomes a thin caller of this gate.

F2  Authorization v1 (DECIDED 2026-06-13): ship interactive out-of-band
    confirmation that echoes the exact order + attestation identity/reason
    (see F7); the env gate FINHARNESS_OKX_ENABLE_LIVE_MUTATIONS=1 stays.
    Signed-token 2FA is DEFERRED, not built now, because:
      - the realistic threat here is operator tilt (human error), which an
        order-echoing confirmation + the guard hard-stop + a notional cap close
        directly; a self-minted token does not stop a tilted operator.
      - the automated/compromised-process threat is currently unreachable: no
        agent toolset contains the live function (agent_tools.py:85-98).
      - a token the same operator signs from the same terminal is two-factor by
        one party, not independent authorization — ceremony, not security.
      - matches target-state-B section 5: "escalate complexity only on failure
        threshold, never preemptively."
    TRIGGER to revisit: the day any automated path can reach live execution.
    At that point build a TRUE second factor (hardware key / separate device),
    not a self-minted token.

F3  Hard notional cap (above). Default conservative; overridable only upward
    with an explicit flag that is itself recorded in the receipt.

F7  Attestation carries an attester identity + reason + timestamp, recorded in
    the receipt; the non-interactive path requires all three, not a bare bool.
    Keep the interactive LangGraph interrupt as the primary path.

F8  Replace BLOCKED_ARG_TOKENS with a per-(module,action) allowlist of
    permitted argument flags; reject anything not explicitly allowed. Handles
    --flag=value and abbreviation forms by construction.

F9  Redaction allowlist of fields that may appear; everything else redacted by
    default. Never print raw stderr — redact it the same way before surfacing.
```

## Implementation order

```text
1. DONE  F6 conservative merge + tests.
2. DONE  okx_live_gate.py: guard + notional cap + receipt + trading-state
         writeback (F1/F3/F4/F5). src/finharness/okx_live_gate.py +
         tests/test_okx_live_gate.py (13 tests). record_live_order_placed added
         to trading_state_store.py for the F5 writeback.
3. DONE  Per-action arg allowlist + full redaction in okx_cli.py (F8/F9):
         validate_command_args / allowed_flags / redact_okx_output / redact_text
         + tests in tests/test_okx_cli.py.
4. DONE  Attestation identity/reason + interactive confirmation (F2 v1 / F7) in
         scripts/okx_live_order.py; signed-token 2FA deferred (see F2).
5. DONE  Taskfile okx:live-read/okx:demo/okx:live-write/trading:reset-check/
         guard:interactive re-pointed to Python (scripts/run_okx_read.py,
         scripts/okx_live_order.py, scripts/run_trading_guard.py); rust:check and
         receipt:rust removed; crates/finharness-cli + Cargo.* archived under
         docs/archive/legacy-rust-crate/; SBOM/dependabot/CODEOWNERS updated.
```

All verified 2026-06-13: ruff clean; full suite 205 passed, 42 subtests.

## Verification

```text
task check passes.
New tests cover: guard hard_stop blocks a live mutation; notional breach
  blocks; blocked attempts still write a receipt; a successful (demo) mutation
  updates trading-state; arg allowlist rejects --live=1 and --profile=live;
  redaction covers apiKey/secretKey/passphrase and stderr.
Manual: a simulated hard_stop state makes `task okx:live-write` refuse before
  reaching the okx binary.
```

## Decisions (2026-06-13)

```text
- F2 signed-token 2FA: DEFERRED (see F2 above). Interactive confirmation +
  attestation identity ship now; true second factor only when an automated
  path can reach live execution.
- crates/finharness-cli: ARCHIVE (not delete) under docs/archive once the
  Python path is at parity.
```
