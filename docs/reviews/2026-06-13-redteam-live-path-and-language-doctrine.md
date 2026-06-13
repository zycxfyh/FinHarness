# Review: Red-Team of the Live Path and the Rust-First Doctrine

Date: 2026-06-13
Kind: red-team / security review
Reviewers: FinHarness project operator and Claude
Scope: authorized review of FinHarness's own control plane. The documented
safety claims are treated as assertions to be falsified against the code.

## Claims under test

```text
B3 (target-state-B): "No path — human error or AI error — can lose more than
  the configured budget. Live write paths require independent multi-party
  authorization."
AGENTS.md Safety: "No agent should own live execution authority. Live write
  paths require explicit environment gates, risk gates, allowlists, and
  receipts."
README: "Human attestation is fail-closed everywhere."
SECURITY.md: "No raw secret output in receipts or logs."
```

## Headline finding

Governance is concentrated on the path that cannot lose money, and the path
that can lose real money is comparatively ungated.

The ten-layer pipeline (proposal → risk gate → execution → post-trade)
terminates in a `fake_paper_adapter` that "never talks to a real broker"
(`src/finharness/execution.py:248-250`). The real money path is a separate
route — `task okx:live-write` → `crates/finharness-cli` `run_okx`
(`crates/finharness-cli/src/main.rs:447-517`) — that does not call the guard,
does not reach the risk gate, does not read persisted behavioral state, and
enforces no notional cap. Controls and risk live on different paths.

Root cause is partly the Rust-first split: two languages produced two sources
of behavioral truth, and the live path uses the weaker (hand-fed) one. This is
why the language doctrine and the security fix are addressed together (see the
2026-06-13 ADR and proposal).

## Findings

Severity: Critical / High / Medium / Low.

### A. Wanted but not done (claim vs missing)

```text
F1 [Critical] Live write path bypasses the risk gate and writes no receipt.
   evidence: main.rs:447-517 vs Taskfile okx:live-write:314-317;
             execution.py:248-250 (ten-layer terminates in fake adapter)
   violates: AGENTS.md Safety (risk gates + receipts on live write paths)

F2 [High] "Independent multi-party authorization" does not exist.
   evidence: main.rs:480-488, okx_cli.py:120-146 — one env var
             (FINHARNESS_OKX_ENABLE_LIVE_MUTATIONS=1) + one task call,
             single actor, single terminal. No second party, signature,
             delay, or out-of-band confirmation.
   violates: B3

F3 [High] Live write path enforces no notional/size cap.
   evidence: order args (incl --sz) passed straight to okx (main.rs:497-499);
             max_notional_check exists only in risk_gate.py:367-371 and governs
             the paper classification, not the live order.
   violates: B3 ("no path can lose more than the configured budget")

F4 [High] The behavioral guard is advisory, not enforcing.
   evidence: guard only prints JSON (main.rs:208-210); run_okx never calls it.
             trading_guard.py:1-5 calls itself a circuit breaker but nothing
             consumes trade_allowed=false to block an order.

F5 [High] Loop 3 feedback edge closes only for fake trades.
   evidence: update_from_post_trade_snapshot (trading_state_store.py:137-163)
             is fed by the fake post-trade path; live OKX writes go through
             Rust and never update data/state/trading-state.json. The state
             meant to bound behavior is blind to the only trades that lose
             real money.
```

### B. Tried but wrong (implementation defects)

```text
F6 [Medium] Persisted hard-stop state can be silently overridden by a hand-fed
   context. merge_into_risk_context uses setdefault
   (trading_state_store.py:185-201): an explicit clean risk_context
   (drawdown=0 / losses=0 / reset=False) wins over persisted tripped state.
   This is the exact "hand-fed risk_context" failure mode the target-state-B
   doc claimed to eliminate.
   STATUS: FIXED & verified 2026-06-13. merge_into_risk_context now takes the
   conservative value — persisted protective state is a floor, never weakened
   by a hand-fed context. The test that encoded the bypass
   (test_merge_fills_missing_keys_but_explicit_keys_win) was replaced by
   test_merge_is_conservative_explicit_keys_cannot_weaken_state and
   test_merge_lets_explicit_keys_make_state_stricter. Evidence:
   tests/test_trading_state_store.py 10 passed; risk-gate + interrupt +
   ten-layer suites 17 passed, no regression.

F7 [Medium] Non-interactive attestation backdoor. The LangGraph interrupt is
   real in interactive mode, but
   build_risk_gate_bundle_from_proposal_snapshot(context={"human_review_attested":
   True}) passes human_review_check with a plain boolean — no identity,
   signature, or audit of who attested (risk_gate.py:725-741, 424-430).
   "fail-closed everywhere" is overstated.

F8 [Medium] OKX arg gate is an exact-match denylist, not an allowlist.
   BLOCKED_ARG_TOKENS (main.rs:96/469-473, okx_cli.py:78/150) blocks five exact
   strings; --live=1, --profile=live, --env=prod, and abbreviations pass
   through to okx. Per-action arg allowlisting is the correct control.

F9 [Medium] Output redaction is naive and the error path leaks.
   redact_okx_output handles only uid/mainUid/ip/label (main.rs:579-585) and
   misses apiKey/secretKey/passphrase/balances; non-zero exit prints raw
   stderr unredacted (main.rs:505-511).
   violates: SECURITY.md "No raw secret output in logs."

F10 [Low] Content "safety" is a bypassable denylist regex.
   BLOCKED_RISK_GATE_LANGUAGE (risk_gate.py:35-60) is en+zh literals only;
   homoglyphs, spacing ("o r d e r"), synonyms, and other languages bypass it.
   It is a lint, not a control. Impact bounded: it only affects paper
   classification.

F11 [Low/Info] Prompt-injection surface: untrusted SEC/event text feeds the
   hermes generator (hermes_bridge.py:1-9). Mitigations present (search-only
   toolset, timeout, deterministic downstream comparator). Residual risk:
   injected content steering hypotheses to dodge F10. Acceptable; logged.
```

### What is actually correct (red teams should say so too)

```text
- Secrets git hygiene: .env.* ignored except .env.example (.gitignore:27-29);
  no live secrets tracked.
- No shell injection: every subprocess/Command uses argv form, no shell=True.
- LLM cannot reach live execution: the OpenAI agent has three read-only tools
  (agent_tools.py:85-98). "No agent owns live execution authority" holds.
- Corrupt trading-state file fails closed (trading_state_store.py:74-81).
```

## Cross-cutting root cause

Two sources of behavioral truth: Python persists trading-state.json; the Rust
guard takes hand-fed CLI flags (main.rs:179-206) and never reads the file. The
live path is wired to the Rust source. Closing Loop 3's feedback edge did not
take effect where it matters. Consolidating on Python (2026-06-13 ADR) removes
the second source so the live path can be wired to the persisted state.

## Lessons (durable)

```text
- A gate that only prints is not a gate. Enforcement must consume the decision.
- Put the heaviest controls on the highest-consequence path, not the easiest
  one to instrument. A simulator does not need a risk gate; the live broker
  call does.
- Language purity can buy negative safety when it splits one control plane into
  two state sources. Prefer one connected plane over two tidy ones.
- "Fail-closed by default" is necessary but not sufficient; a default-False
  boolean with a non-interactive setter is still a backdoor without identity.
```

## Remediation status (2026-06-13, verified)

```text
F1 FIXED  live mutations only run via finharness.okx_live_gate, which writes a
          receipt (data/receipts/okx-live/) for every attempt incl. blocked.
F2 v1     interactive order-echoing confirmation + attestation; env gate kept.
          signed-token 2FA DEFERRED (single-operator; threat is tilt, not a
          compromised automated path — none can reach the live function).
F3 FIXED  hard notional cap; uncomputable notional fails closed.
F4 FIXED  guard now ENFORCES — a non-clear guard decision blocks the order.
F5 FIXED  record_live_order_placed folds a placed live order into trading-state.
F6 FIXED  conservative merge (see above).
F7 FIXED  attestation requires attester + reason; recorded in the receipt.
F8 FIXED  per-action flag allowlist replaces the bypassable denylist.
F9 FIXED  redact_okx_output masks sensitive fields; stderr redacted before raise.
F10/F11   accepted as low/info (bounded impact), logged, not changed.

Verification: ruff clean; full suite 205 passed, 42 subtests (2026-06-13).
Language root cause removed: the Rust crate is archived
(docs/archive/legacy-rust-crate); the live path now shares the one Python
persisted-state source and gate set.
```

## Follow-up

```text
docs/proposals/2026-06-13-consolidate-live-path-on-python-and-harden.md
  maps F1-F9 to concrete Python fixes and an implementation order (all DONE).
```
