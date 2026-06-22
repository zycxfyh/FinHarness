# Review: FinHarness A-to-B Red-Team Audit

Date: 2026-06-13
Scope: pre-remediation checkout of FinHarness on branch `feat/four-loops-llm-integration`
Mode: adversarial gap audit, not a release approval

## Snapshot Boundary

This review is preserved as a **pre-remediation red-team snapshot**. It was one
of the inputs that led to later fixes, not a statement of the current checkout.

After this audit was drafted, subsequent commits changed several facts it
reports as current:

```text
d356f45  live OKX path moved behind a Python firebreak; Rust-first doctrine
         was retired; the Rust crate was archived; F1-F4/F8-F10 were remediated
         in the live-path follow-up.
f10ec1f  B4 lesson -> rule-change lineage was extended into behavioral-guard
         threshold enforcement and validation/lesson-loop improvements.
```

Read the findings below as historical evidence of the gap that existed at the
time of the audit. Current claims require current command output, not this
snapshot.

Unless a paragraph explicitly says otherwise, command outputs and "current"
wording below refer to the audit-time checkout.

## A / B Frame

### Pre-remediation A, from inspected evidence

At audit time, FinHarness had a large research/governance harness surface:

```text
143 Python files across src/scripts/tests
136 docs files
44 tracked receipt files under data/receipts before ignored test artifacts
Rust CLI still present and still used by OKX live Taskfile entries
```

The codebase has real strengths: typed Pydantic layer objects, a ten-layer
LangGraph chain, explicit fake/paper execution boundaries, many unit tests,
security workflows, red-team corpus tests, and generated receipts.

At audit time, the checkout was not clean and not fully passing:

```text
task test                         PASS, 186 tests
task rust:check                   PASS, 4 Rust tests
task lint                         FAIL, import ordering in tests/test_property_baseline.py
task hardening:gate               FAIL, Trivy reports 1 vulnerability and release_blocked=true
receipt usage audit               43 receipts, 29 consumed, 14 unreferenced,
                                  44 missing receipt references
```

Running the standard tests and hardening gate also recreates a large ignored
runtime surface under `data/`: the file count rose from 72 files after cleanup
to 457 files during this audit. That is evidence that normal verification
pollutes the local evidence surface unless it is cleaned afterward.

### Intended B, from project docs

The strongest B reference available at audit time was stated in
`docs/think/2026-06-12-target-state-b-and-loop-topology.md`:

```text
B1: evidence-on-demand
B2: decision discipline
B3: bounded loss
B4: compounding judgment
B5: boundary: no autonomous trading; READY/PASS never authorizes live action
```

The harsh standard is B3:

```text
No path — human error or AI error — can lose more than the configured budget.
Live write paths require independent multi-party authorization.
```

Measured against that B, the audit-time system was not there.

## Critical Findings

### F1. The real-money path is less governed than the fake path

Severity: Critical

The ten-layer pipeline terminates in fake/paper execution:

```text
src/finharness/execution.py:247-328
FakePaperExecutionAdapter never talks to a real broker.
```

The live OKX path is separate:

```text
Taskfile.yml:314-317
crates/finharness-cli/src/main.rs:447-517
```

That Rust live path does not call the ten-layer risk gate, does not read
`data/state/trading-state.json`, does not enforce `max_paper_notional`, and
does not write a FinHarness live-attempt receipt before the mutation.

Red-team verdict:

```text
The strongest governance is on the path that cannot lose money.
The path that can mutate a live account has fewer project-native controls.
```

### F2. B3's "no path can exceed budget" was false at audit time

Severity: Critical

The Rust OKX path passes user args straight through to the official `okx`
binary after only module/action classification and a small denylist:

```text
crates/finharness-cli/src/main.rs:490-505
command_args.extend(okx_args...)
Command::new("okx").args(command_args)
```

There is no notional cap, no size cap, no price sanity check, no portfolio
budget check, and no persisted behavior-state read on that path.

`risk_gate.py` has notional checks, but those govern paper review decisions:

```text
src/finharness/risk_gate.py:367-371
```

They are not wired to `task okx:live-write`.

### F3. The behavioral guard is advisory, not enforcing

Severity: High

The Rust guard can detect drawdown and loss hard stops:

```text
crates/finharness-cli/src/main.rs:347-435
```

But `run_okx` does not call it:

```text
crates/finharness-cli/src/main.rs:447-517
```

So a hard stop can be printed by one task while the live-write task remains a
separate route. A gate that only prints is not a gate.

### F4. Persisted hard-stop state was weakened by caller-supplied context

Severity: High, fixed during subsequent remediation after the initial finding

Initial evidence showed `merge_into_risk_context` only filled missing keys:

```text
src/finharness/trading_state_store.py:185-201, previous version
context.setdefault(key, value) let a clean hand-fed context override persisted state
```

The remediation work later introduced the correct conservative merge:

```text
src/finharness/trading_state_store.py:190-228
drawdown_pct = min(supplied, persisted)
consecutive_losses = max(supplied, persisted)
behavior_reset_required = supplied OR persisted
```

The tests now assert both directions:

```text
tests/test_trading_state_store.py:83-123
clean explicit context cannot weaken persisted protective state
stricter explicit context can still tighten the gate
uv run python -m unittest tests/test_trading_state_store.py: PASS, 10 tests
```

Remaining audit-time red-team point: this fixed the Python risk-gate merge only.
The live OKX Rust path still did not read this persisted state before mutation,
so B3 was still not achieved at audit time.

### F5. Human attestation is still a bare boolean on non-interactive paths

Severity: High

Interactive risk gate support is real:

```text
src/finharness/risk_gate_graph.py:255-308
```

But non-interactive builders still accept:

```text
context={"human_review_attested": True}
```

with no attester identity, signature, timestamp, durable approval object, or
second party:

```text
src/finharness/risk_gate.py:725-741
tests/test_risk_gate.py:47, 152
tests/test_execution.py:77-78, 162-163
```

This is not independent authorization. It is a boolean override.

### F6. Hardening and release evidence disagreed with audit-time reality

Severity: High

Current command evidence:

```text
task hardening:gate
release_blocked: true
trivy vulnerabilities: 1
exit status: 1
```

But tracked reports still claim stronger, older state:

```text
data/reports/trading-validation-report-v1.json:116 release_ready=true
docs/reports/trading-validation-report-v1.md:13 release_ready: True
docs/reports/trading-validation-report-v1.md:28-30 claims local hardening checks pass
data/receipts/governance-dashboard/latest.json:102 release_ready=true
```

`data/receipts/release-preflight/latest.json` now says `release_ready=false`,
so the repository contains contradictory governance evidence.

Red-team verdict:

```text
Generated reports are stale views unless regenerated and explicitly dated.
They must not be treated as current source truth.
```

## High / Medium Findings

### F7. Validation mostly checks structure, not empirical truth

Severity: High

The validation layer names serious-sounding results, but much of the MVP is
presence and availability checking:

```text
src/finharness/validation.py:308-339 source_ref_presence_check
src/finharness/validation.py:342-368 mechanism_and_assumption_presence_check
src/finharness/validation.py:371-400 event_reaction_input_availability_check
docs/modules/06-validation.md:60 no return/factor/cost/liquidity calculation in MVP
```

This is honest in the module doc, but the system name can make it easy to
overclaim. It can say "bounded and source-linked"; it cannot say "validated
edge" or "strategy works."

### F8. Risk-gate defaults are too optimistic

Severity: Medium

`RiskGateContext` defaults several evidence-like flags to good states:

```text
src/finharness/risk_gate.py:115 liquidity_evidence_present=True
src/finharness/risk_gate.py:121 scenario_review_present=True
src/finharness/risk_gate.py:111 requested_notional=100.0
src/finharness/risk_gate.py:112 max_paper_notional=1000.0
```

That is acceptable for toy local runs, but dangerous as a general control
surface. A risk gate should treat missing liquidity/scenario evidence as
missing, not assume it is present.

### F9. OKX argument filtering is a denylist, not a per-action allowlist

Severity: Medium

Current guards block a few exact tokens:

```text
src/finharness/okx_cli.py:78, 148-152
crates/finharness-cli/src/main.rs:96, 469-473
```

This catches `--live`, but it is not a robust parser or per-action allowlist.
It does not prove that every dangerous `okx` flag shape is blocked.

### F10. Error-output redaction is incomplete

Severity: Medium

Rust redaction covers only a few fields:

```text
crates/finharness-cli/src/main.rs:579-584
uid, mainUid, ip, label
```

The non-zero exit path prints raw stderr:

```text
crates/finharness-cli/src/main.rs:505-511
```

The project policy says no raw secret output in receipts or logs, but this path
does not prove that boundary.

### F11. Tests are numerous but often mock the layer boundaries

Severity: Medium

`task test` passed 186 tests, which is valuable. But high-consequence paths are
mostly unit tests with mocks/fakes:

```text
tests/test_ten_layer_graph.py patches every layer with fake results
tests/test_okx_cli.py patches subprocess.run
execution uses FakePaperExecutionAdapter
post-trade reconciles local ExecutionSnapshot only
```

This is fine for deterministic MVP testing. It does not prove live workflow
safety, broker reconciliation, or external integration correctness.

### F12. Normal checks generate enough ignored artifacts to distort audits

Severity: Medium

After a cleanup, `data/` had:

```text
72 files total, 71 tracked
```

After `task test` and `task hardening:gate`, `data/` had:

```text
457 files total, 71 tracked
```

This means many checks write receipts, normalized snapshots, raw event outputs,
red-team exports, and hardening receipts into the same workspace. The new
receipt usage audit exposed why this matters: runtime evidence can drown out
durable project evidence unless test outputs are isolated or cleaned.

### F13. Receipt governance is not consumption governance yet

Severity: Medium

Current receipt usage audit result:

```text
43 receipts
29 consumed by review/report/governance docs
14 unreferenced
44 missing receipt references from docs
```

This is not a disaster, but it means receipts are not yet a clean evidence
ledger. Some records are orphaned; some docs point at artifacts that are no
longer present.

### F14. Loop 4 exists as draft generation, not learning enforcement

Severity: Medium

`lesson_loop.py` drafts lessons and explicitly requires human promotion:

```text
src/finharness/lesson_loop.py:1-8
src/finharness/lesson_loop.py:69-73
src/finharness/lesson_loop.py:277-296
```

There is no enforced path from promoted lesson to rule change to threshold
change to test update. B4, the project's stated reason to exist, remains mostly
a manual discipline.

## What Holds Up

The red team should not hide strengths:

```text
task test passed 186 tests
task rust:check passed 4 tests
live Alpaca endpoint is not wired; Alpaca client uses paper base URL
OpenAI agent tools are read/data/eval oriented, not order-writing
risk_gate and execution default human_review_attested=False
execution live mode is blocked in Layer 9 MVP
corrupt trading-state file fails closed
many docs correctly state non-claims around alpha, live trading, and advice
```

These are real controls. They just do not cover the highest-consequence path
well enough yet.

## A-to-B Gap Summary

```text
B1 evidence-on-demand:
  Partially true. Observation and evidence packaging exist, but normal checks
  create noisy runtime artifacts and some docs reference missing receipts.

B2 decision discipline:
  Partially true for paper/fake paths. Weak for non-interactive attestation and
  live OKX because discipline is not enforced by one connected gate.

B3 bounded loss:
  Not achieved at audit time. The Python risk-gate state merge had become
  conservative, but the live OKX mutation path still lacked risk gate,
  persisted state read, notional cap, receipt, and multi-party authorization.

B4 compounding judgment:
  Not achieved. Lesson drafts exist; rule-change enforcement and measurable
  improvement lineage are not closed.

B5 no autonomous trading:
  Mostly true for agent and ten-layer paths. Still needs live-write hardening
  because one operator with env access can run live mutation outside the main
  governed pipeline.
```

## Recommended Next C

Do not add another governance graph. The next useful C is smaller and harsher:

```text
1. Fix the current gates before adding capability:
   - make task lint pass
   - resolve or suppress-with-reason the Trivy finding
   - regenerate stale governance reports only after gates are true

2. Harden the live path:
   - move okx live mutation behind one Python entry
   - read persisted trading-state before mutation
   - conservative merge: explicit context may only tighten, never weaken
   - enforce notional/size cap before calling okx
   - write allowed/blocked live-attempt receipt
   - redact stderr/stdout through allowlist-by-default

3. Make attestation a first-class object:
   - attester identity
   - reason
   - timestamp
   - exact action being approved
   - short TTL or interactive echo confirmation

4. Isolate verification artifacts:
   - tests write to temp dirs or explicitly ignored test-output roots
   - release receipts are regenerated intentionally, not as incidental side
     effects of normal unit tests

5. Close B4 only after B3:
   - promoted lesson must link to a rule/threshold/doc/test change
   - a rule change without lesson lineage is rejected
```

## Receipt

Evidence:

```text
task lint: failed on tests/test_property_baseline.py import order
task test: passed 186 tests
task rust:check: passed 4 tests
task hardening:gate: failed; Trivy vulnerability count 1; release_blocked=true
uv run python scripts/run_receipt_usage_audit.py --limit 8:
  43 receipts, 29 consumed, 14 unreferenced, 44 missing refs
uv run python -m unittest tests/test_trading_state_store.py tests/test_risk_gate.py \
  tests/test_risk_gate_interrupt.py tests/test_ten_layer_graph.py:
  PASS, 27 tests
source reads:
  README.md
  CONTEXT.md
  AGENTS.md
  docs/think/2026-06-12-target-state-b-and-loop-topology.md
  src/finharness/risk_gate.py
  src/finharness/risk_gate_graph.py
  src/finharness/execution.py
  src/finharness/post_trade.py
  src/finharness/trading_state_store.py
  src/finharness/okx_cli.py
  crates/finharness-cli/src/main.rs
  src/finharness/validation.py
  src/finharness/lesson_loop.py
  tests/test_trading_state_store.py
```

Not claimed:

```text
This review is not a full broker security assessment, not a profitability
review, not legal/compliance advice, and not proof that no other issues exist.
```

Status:

```text
DEGRADED: enough evidence to block release and live-write confidence claims;
the audit itself is a draft review, not an external seal.
```
