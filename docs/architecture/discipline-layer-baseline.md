# Discipline-Layer Baseline (regression guard for mature-wheel work)

This is the **护栏 / regression baseline** for the
[mature wheel control plane](mature-wheel-control-plane.md). Any replacement step
that touches `risk_gate`, `execution`, the lesson→rule path, or receipts —
especially the deepening steps that feed research/portfolio/execution wheels into
the decision flow — must re-verify every invariant in §2 **before and after** the
change. A mature finance/security/policy wheel may compute or store, but it must
never acquire the authority described here.

Phase 0 of the verified sequencing in
[mature-wheel-control-plane.md](mature-wheel-control-plane.md): establish this
baseline first, because it protects the boundary-touching phases (research and
portfolio integration into the gates, and the execution fake→Nautilus swap).

## 1. Classification: replace / assist / deepen

| Module | Role | Verdict | Why |
| --- | --- | --- | --- |
| `trading_guard` | behavioral circuit breaker (drawdown / consecutive-loss / cooldown / thesis) | **Never replace** | Project-specific behavior stops; no generic wheel encodes this. |
| `risk_gate` | mandate / permission / caps / human-review / no-live authority | **Never replace** | This is the authority decision. A policy engine may *express* rules; it must not *own* the decision. |
| `execution` live-block + attestation gate | non-live default, human-attestation gate, idempotency | **Never replace** | The no-live boundary and human-in-the-loop are the safety value, not the order mechanics. |
| `rule_change_ledger` + `lesson_loop` | lesson→rule lineage; AI drafts, human promotes | **Never replace** | The traceability predicate (`is_traceable`) and the human comparator are project-defining. |
| receipt semantics (`post_trade`, `receipt_usage_audit`, governance graphs) | claim / evidence / non-claim distinction | **Never replace** | "Evidence of use, not proof of correctness" is FinHarness's own semantics. |
| `PolicyInterface` (OPA / Cedar / Casbin) | rule *expression* | **Assist only** | May encode the allowlist/mandate as a contract; the authority gate stays in `risk_gate`. Express rules first, adopt an engine only if justified. |
| `EvidenceInterface` (OpenLineage / MLflow / DVC / Sigstore) | provenance / artifact lineage / signing | **Assist only** | May *store* provenance and signatures; must not replace receipt claim/evidence/non-claim semantics. Do last. |
| Research (vectorbt), Portfolio (Riskfolio) wheels | candidate / weight evidence | **Deepen (bounded)** | May feed the gates as *evidence/inputs* only; must never produce order authority. |
| `execution` paper adapter | paper-parity order shape | **Deepen (bounded)** | Replace the fake adapter in the real graph with Nautilus/official paper; keep fake test-only; live-block unchanged. |

## 2. Must-hold invariants (verify before AND after every boundary-touching step)

Each invariant cites where it lives and the test that guards it. If a step would
weaken any of these, stop — that is a boundary regression, not a refactor.

1. **AI never places orders directly; non-live is the default.**
   `execution_allowed=false` / `live_execution_allowed=False` are defaults, never
   computed to true by a wheel.
   Evidence: [execution.py:85](../../src/finharness/execution.py#L85),
   [risk_gate.py:108](../../src/finharness/risk_gate.py#L108),
   [risk_gate.py:492](../../src/finharness/risk_gate.py#L492).

2. **Live execution is blocked before submit.**
   Evidence: [execution.py:639-640](../../src/finharness/execution.py#L639)
   (`blocked_event("live execution is blocked in Layer 9 MVP")`);
   `allowed_decisions` excludes any live decision
   [execution.py:514](../../src/finharness/execution.py#L514).
   Guard test: `tests/test_execution.py::ExecutionLayerTest::test_live_mode_is_blocked_before_submit`
   (red-team matrix `FH-RT-003`, [hardening.py:196](../../src/finharness/hardening.py#L196)).

3. **Human attestation is fail-closed.**
   No order request is built without `human_review_attested`, and live mode is
   refused regardless.
   Evidence: [execution.py:573](../../src/finharness/execution.py#L573),
   [execution.py:577](../../src/finharness/execution.py#L577);
   `risk_gate` `human_review_check` at
   [risk_gate.py:423](../../src/finharness/risk_gate.py#L423).

4. **risk_gate retains mandate / permission / cap / no-live authority.**
   Failing `paper_or_live_permission_check` or `mandate_check` → `blocked`;
   `no_live_execution_authority` is asserted.
   Evidence: [risk_gate.py:360](../../src/finharness/risk_gate.py#L360),
   `classify_decision` [risk_gate.py:434-461](../../src/finharness/risk_gate.py#L434),
   [risk_gate.py:178](../../src/finharness/risk_gate.py#L178).

5. **Behavior stops still trip.**
   Hard-stop / caution drawdown and consecutive-loss thresholds force
   `trade_allowed=False`.
   Evidence: [trading_guard.py:37-125](../../src/finharness/trading_guard.py#L37).

6. **Lesson→rule changes are refused without lineage.**
   A rule change requires a human attester, a rationale, and receipt refs;
   `is_traceable` is the closure check.
   Evidence: [rule_change_ledger.py:72-129](../../src/finharness/rule_change_ledger.py#L72).

7. **Receipts separate claim / evidence / non-claim.**
   Receipt audits state results are "evidence of use, not proof of correctness".
   Evidence: [receipt_usage_audit.py:279](../../src/finharness/receipt_usage_audit.py#L279),
   post-trade evidence refs [post_trade.py:111](../../src/finharness/post_trade.py#L111).

8. **New wheels emit evidence, never authority.**
   Any research/portfolio/execution adapter output carries
   `execution_allowed=false` and flows into the gates as input, not as a decision.
   Evidence: `VectorbtResearchSummary.execution_allowed=False`,
   `RiskfolioAllocationSummary.execution_allowed=False`,
   data layer has no authority field (`tests/test_data_quality.py`).

## 3. How to use this baseline

- Before a boundary-touching step: run the guard tests for the invariants the
  step could affect (at minimum `tests/test_execution.py`,
  `tests/test_risk_gate*.py`, `tests/test_hardening_gate.py`).
- After the step: the same tests must still pass **unchanged**, and any new
  adapter output must assert `execution_allowed=false` / carry no authority field.
- If a step needs to change one of these invariants, that is a deliberate
  policy change — it goes through a written proposal and human review, not a
  mature-wheel replacement PR.
