# Solution Research Packs

Author: Codex
Parallel agent: Claude
Status: historical reference (downgraded 2026-07-02)
Date: 2026-06-15
Evidence policy: primary-source-first

This document turns the highest-priority gaps into design packs. It does not
implement code, add dependencies, create services, or approve product work.

Parallel input read: [Gap Solutions](../gap-solutions.md).

## Pack 1: Research Rigor Ladder

Problem: Validation can produce evidence, but it does not yet climb a mature
research robustness ladder.

Why it matters: Without OOS, walk-forward, trial accounting, and selection-bias
discounts, the system can govern a lucky curve while still failing the value
question.

Mature method/projects:

- vectorbt for portfolio/backtest computation.
- Deflated Sharpe style discount for selection bias.
- CPCV as a later candidate if the project accepts a dependency or implements a
  small scoped method.

FinHarness fit:

- Keep vectorbt behind `ResearchInterface`.
- Add a local `ResearchRung` concept to validation evidence: `in_sample`,
  `out_of_sample`, `walk_forward`, `trial_discounted`, `cpcv_candidate`.
- Validation may weaken or describe evidence at lower rungs, but it must not
  label a hypothesis supported above the rung actually climbed.

Risks:

- More metrics can make bad research look more scientific if data validity stays
  weak.
- CPCV dependency decisions should not happen before OOS and walk-forward are
  useful.

Recommended path:

1. Add OOS split output to validation evidence.
2. Add walk-forward result summary.
3. Record trial count and selection method.
4. Add discounted-performance field with limitations.
5. Evaluate CPCV only after the first three rungs are real.

Acceptance criteria:

- Every validation receipt states research rung and data limitations.
- Any "supported" status is capped by rung rules.
- Trial count is present or explicitly `unknown` with a warning.

## Pack 2: Data Validity And Reconciliation

Problem: The data plane is good enough for local experiments but not for serious
research claims.

Why it matters: Bad or biased data can make any robustness method meaningless.

Mature method/projects:

- Provider disclosure and adjusted data semantics.
- Multi-source reconciliation.
- Point-in-time/survivorship-bias-aware datasets when available.
- Pandera for structural contracts, already adopted.

FinHarness fit:

- Keep Pandera as `DataQualityInterface`.
- Add provider/adjustment/bias fields to market-data lineage.
- Add a second-provider reconciliation note where provider access exists.
- Stamp research receipts with data-bias limitations until point-in-time and
  survivorship questions are solved.

Risks:

- Free/public providers may not offer institutional-grade point-in-time data.
- Reconciliation can flag noise without enough context.

Recommended path:

1. Disclose adjusted/unadjusted settings in lineage.
2. Add divergence checks for overlapping OHLCV fields when two providers exist.
3. Record `data_bias_uncontrolled` until a stronger data source is chosen.
4. Treat point-in-time data as A4 until a vendor/project decision exists.

Acceptance criteria:

- Market-data receipts identify provider, adjustment mode, and reconciliation
  status.
- Validation receipts do not hide data bias.
- No research doc claims institutional data quality from yfinance/OpenBB alone.

## Pack 3: Market-Access Control Model

Problem: FinHarness has strong local brakes, but no single market-access control
model for owner, authorized operators/accounts, aggregate limits, restricted
symbols, and erroneous-order checks.

Why it matters: The current safety shape is good, but scattered controls can
drift as new paper/live-adjacent scripts are added.

Mature method/projects:

- SEC Rule 15c3-5 as engineering benchmark, not legal compliance claim.
- Existing FinHarness `risk_gate`, `trading_guard`, lesson-to-rule, and receipts.

FinHarness fit:

- Keep control ownership in FinHarness, not in mature libraries.
- Use a shared control model before any mutating broker/venue adapter.
- Let mature tools produce evidence and order shapes only after local checks.

Risks:

- Overbuilding a broker-style system before the project needs it.
- Confusing a local control register with compliance certification.

Recommended path:

1. Add a control-owner register and draft certification receipt.
2. Add authorized operator/account models without secrets.
3. Add aggregate limit ledger.
4. Add restricted-symbol and provider-tradability evidence.
5. Add erroneous-order checks: max notional, max quantity, price collar,
   duplicate client id, rate/window cap, open-order cap.

Acceptance criteria:

- All mutation-capable paths consume the same control decision.
- Raising configured limits requires rule-change or owner attestation lineage.
- Receipts state "not legal compliance certification" and "not live authority."

## Pack 4: Post-Trade And TCA

Problem: Post-trade receipts exist, but execution quality is not yet measured in
a product-useful way.

Why it matters: Without TCA and deeper reconciliation, the system cannot learn
whether execution decisions improved or degraded outcomes.

Mature method/projects:

- Implementation shortfall as first TCA metric.
- VWAP/arrival-price comparisons as later secondary metrics when data supports
  them.
- NautilusTrader paper/backtest concepts for lifecycle semantics, not live
  authority.

FinHarness fit:

- Keep first TCA on paper fills only.
- Preserve intended -> submitted -> filled/canceled/rejected chain.
- Feed Loop 4 lessons from post-trade evidence, never automatic rule changes.

Risks:

- Paper fills are not real market microstructure.
- TCA numbers can overclaim if data frequency is too coarse.

Recommended path:

1. Record arrival/reference price at decision time.
2. Record submitted order, fill/cancel/reject events, and quantities.
3. Compute implementation-shortfall-style paper metric with limitations.
4. Feed observations to lesson drafts.

Acceptance criteria:

- Post-trade receipt shows lifecycle state and first TCA fields.
- Receipt explicitly says paper TCA is practice evidence, not live execution
  quality proof.

## Pack 5: Read-Only Backend Interface

Problem: CLI tasks and files are workable for operators but insufficient for a
safe frontend or product surface.

Why it matters: A frontend should query evidence through a stable interface
without gaining any order-entry capability.

Mature method/projects:

- OpenAPI for HTTP surface description.
- JSON Schema for response payloads.
- Idempotency for any future review-attestation writes.
- ASVS for future web-security verification.

FinHarness fit:

- Start with a specification only.
- Initial interface is read-only: snapshots, receipts, cockpit state, review
  queue, module metadata.
- No execution, sizing, live authorization, or broker mutation endpoint.

Risks:

- Adding FastAPI/uvicorn would be a new dependency and needs approval.
- A product surface can make weak evidence look more authoritative.

Recommended path:

1. Draft OpenAPI/JSON Schema without adding dependency.
2. Expose only read-only resources in the spec.
3. Add a security review checklist before implementation.
4. Require explicit user approval before adding web dependencies.

Acceptance criteria:

- OpenAPI draft has no mutation endpoint.
- Every evidence response includes non-claims and receipt refs.
- UI clients cannot relax backend gates.

## Pack 6: Frontend Evidence Workstation

Problem: FinHarness has no interactive frontend, only CLI tasks and generated
Markdown/JSON cockpit output.

Why it matters: The value moment is a human making a better, documented
decision. A frontend should support review and learning without becoming an
order-entry console.

Mature method/projects:

- Read-only operational dashboards.
- Review queues with explicit attestations.
- WCAG 2.2 for accessible review surfaces.

FinHarness fit:

- Build after the read-only backend spec is stable.
- Display evidence, assumptions, rejected alternatives, risks, non-claims,
  rung, trial count, and receipt refs.
- Support review annotations and lesson seeds only after write contracts are
  explicitly designed.

Risks:

- UI polish can create false confidence.
- Any "action" control can be misread as trading authority.

Recommended path:

1. Read-only evidence dashboard.
2. Receipt and lineage drill-down.
3. Human review queue with slow attestation language.
4. Later annotation-to-receipt flow, still no order entry.

Acceptance criteria:

- No buy/sell/order/sizing/live controls exist in UI.
- Every recommendation view includes evidence and non-claims.
- Accessibility checklist is part of UI acceptance.

## Pack 7: Observability And Lineage Compatibility

Problem: FinHarness has rich receipts, but future backend/frontend operation
will need runtime traces and external lineage compatibility.

Why it matters: Product surfaces need debuggable request/run paths, but generic
tracing must not replace receipt semantics.

Mature method/projects:

- OpenTelemetry for traces, metrics, and logs.
- OpenLineage for job/dataset lineage.

FinHarness fit:

- Keep receipts as the durable evidence root.
- Add trace IDs and lineage-export compatibility only as indexes into receipts.

Risks:

- Tool adoption can become new governance breadth.
- Traces are lossy and should not be treated as closure receipts.

Recommended path:

1. Standardize local run IDs and trace IDs in docs first.
2. Map snapshots/receipts to OpenLineage-like job/dataset concepts.
3. Defer tool adoption until backend/product surface exists.

Acceptance criteria:

- Trace IDs point to receipts.
- External lineage export preserves non-claims.
- No OpenTelemetry/OpenLineage dependency is added without approval.

## Non-Claims

- These packs do not approve dependencies.
- These packs do not close any gap.
- These packs do not authorize live trading, autonomous trading, or UI order
  entry.
