# Gap Register

Author: Codex
Parallel agent: Claude
Status: historical reference (downgraded 2026-07-02)
Date: 2026-06-15
Evidence policy: primary-source-first

This register records gaps between the 2026-06-15 FinHarness snapshot and mature
methods. It is a historical planning artifact, not a current gap source and not
a claim that any gap is closed. Current architecture facts live in
[Framework Index](../framework-index.md), [Capital OS Layering](../capital-os-layering.md),
[System Map](../system-map.md), [Module Map](../module-map.md), and
[System Catalog](../system-catalog.yml).

Parallel input read: [Gap Analysis](../gap-analysis.md).

Severity scale: `critical`, `high`, `medium`, `low`.
Debt scale: A1 direct fix, A2 logic refinement, A3 system redesign, A4 formalize.

## Register

| ID | Plane | Current evidence | Industry reference | Gap | Severity | Debt class | Recommended method | Close criteria | Non-claims | Owner agent |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| G01 | Research / validation | [Validation module](../../modules/06-validation.md), [Research spec](../research-interface-vectorbt-spec.md), `task validation:graph` | OOS, walk-forward, trial accounting, Deflated Sharpe, CPCV | Validation is still near bottom rung: single in-sample style evidence, no full robustness ladder. | critical | A3 | Add research-rung model and enforce "no support above rung climbed." G01 is an edge-CLAIM validation / overclaim-prevention ladder, not an edge-discovery engine (see 2026-06-17 ADR). | Receipts expose rung, trial count, OOS metrics, walk-forward metrics when present, and limitations. | Does not prove alpha or future returns; "supported" never equals "edge proven". | Codex draft; Claude review candidate |
| G02 | Data validity | [Market Data module](../../modules/01-market-data.md), [Data quality spec](../data-quality-interface-pandera-spec.md) | Point-in-time data, corporate actions, survivorship-bias control, multi-vendor reconciliation | Data validity limitations can silently invalidate research rigor. | high | A3 | Add adjustment disclosure, second-source reconciliation, and explicit bias limitation until solved. | MarketDataQuality/receipts disclose adjustment, provider, reconciliation result, and unresolved bias. | Does not certify vendor accuracy. | Codex draft; Claude review candidate |
| G03 | Trial accounting | [Research spec](../research-interface-vectorbt-spec.md), [Validation module](../../modules/06-validation.md) | Multiple-testing correction and Deflated Sharpe style discount | No durable record of how many variants were tried before a result. | high | A3 | Record trial count, selection process, and discounted metric in validation evidence. | Receipt has `trial_count`, selection note, and discounted performance field or explicit unknown. | Does not transform a backtest into proof. | Codex |
| G04 | Post-trade / TCA | [Post Trade module](../../modules/10-post-trade.md), [Execution module](../../modules/09-execution.md) | TCA, implementation shortfall, intended/submitted/filled/canceled/rejected reconciliation | Post-trade exists but does not yet measure execution quality deeply. | medium | A3 | Add paper-fill implementation shortfall and deeper lifecycle reconciliation. | Post-trade receipt shows arrival price, execution price, filled/canceled/rejected state, and TCA limitations. | Does not claim live execution quality. | Codex |
| G05 | Market-access control owner | [Policy Contract](../policy-contract.md), [SEC review](../../reviews/2026-06-15-sec-15c3-5-market-access-rule-review.md) | 15c3-5 named review/certification analogue | Per-action attestation exists; no named owner of the whole control system. | high | A4 | Add control-owner register and periodic draft certification receipt. | A named human, review cadence, in-force controls, next review, and non-certification statement exist. | Not legal compliance certification. | Codex; human decision required |
| G06 | Aggregate limits | [Risk Gate module](../../modules/08-risk-gate.md), [SEC review](../../reviews/2026-06-15-sec-15c3-5-market-access-rule-review.md) | Pre-set aggregate credit/capital limits | Per-run/per-order caps exist, but no shared account/operator/symbol daily ledger. | high | A3 | Shared market-access limit ledger for all mutating broker/venue paths. | Every mutation-capable path consumes the same ledger and receipt records remaining limit. | Does not authorize mutations. | Codex |
| G07 | Authorized operator/account model | [README](../../../README.md), [SEC review](../../reviews/2026-06-15-sec-15c3-5-market-access-rule-review.md) | Authorized persons/accounts | Attester strings and CODEOWNERS exist, but runtime authorization is not typed. | medium | A3 | AuthorizedOperator and AuthorizedAccount config/receipt models with no secrets. | Risk/execution attestations include operator, account, environment, scope, and reason. | Does not store credentials or prove legal permission. | Codex |
| G08 | Restricted-symbol control | [Risk Gate module](../../modules/08-risk-gate.md), [SEC review](../../reviews/2026-06-15-sec-15c3-5-market-access-rule-review.md) | Restricted securities/persons | Allowlists are not the same as a restricted-list source and provider tradability evidence. | medium | A3 | Local restricted-symbol reference plus provider tradability evidence for securities-like brokers. | Receipts cite restricted-list version and provider tradability result. | Not regulatory compliance. | Codex |
| G09 | Threshold-change governance | [Lesson-to-rule how-to](../../how-to/promote-lesson-to-rule.md), [SEC review](../../reviews/2026-06-15-sec-15c3-5-market-access-rule-review.md) | Supervisory control over limit changes | Lesson-to-rule exists for guard thresholds; CLI/request caps can still be confusing as overrides. | medium | A2/A3 | Split configured ceiling from request limit; raising ceilings requires rule-change or owner receipt. | Cap-raising path is impossible without lineage and human attestation. | Does not approve higher risk. | Codex |
| G10 | Backend HTTP interface | [Command Reference](../../reference/commands.md), [Docs map](../../README.md) | OpenAPI/JSON Schema contract for product backend | CLI and files are the interface; no read-only product backend. | high | A4 | Design read-only backend interface first; require user approval before dependencies. | OpenAPI/JSON Schema draft exists for snapshot/receipt/cockpit query only, no mutation. | No execution or authorization endpoint. | Codex; user approval needed |
| G11 | Frontend evidence workstation | [README](../../../README.md), [Market cockpit task](../../reference/commands.md) | Read-only cockpit, evidence drill-down, review queue, WCAG 2.2 | No interactive frontend; generated Markdown/JSON only. | high | A4 | Design read-only review UI after backend interface. | UI spec shows evidence, assumptions, non-claims, receipts, and no order-entry controls. | UI does not trade. | Codex; future design |
| G12 | Observability | [Ten Layer LangGraph Map](../ten-layer-langgraph-map.md), [Receipt Reference](../../reference/receipts.md) | OpenTelemetry traces/metrics/logs | Receipts exist, but runtime observability is not standardized for product/API use. | medium | A3 | OpenTelemetry-compatible trace IDs in workflows and future backend requests. | Trace IDs connect task run, snapshot, receipt, and UI request without replacing receipt semantics. | Trace is not a receipt. | Codex |
| G13 | Lineage export | [Evidence Inventory](../evidence-inventory.md), [Receipt Reference](../../reference/receipts.md) | OpenLineage job/dataset lineage | Local lineage exists in receipts, but no export shape for external lineage tools. | low/medium | A4 | Evaluate OpenLineage-compatible export after receipt schema stabilizes. | Export maps job, inputs, outputs, receipt refs, and non-claims. | External lineage does not replace receipts. | Codex |
| G14 | Records integrity | [Receipt Reference](../../reference/receipts.md), [SEC review](../../reviews/2026-06-15-sec-15c3-5-market-access-rule-review.md) | Books/records retention, immutable audit trails | Receipts are mutable local JSON/Markdown files. | medium | A4 | Add checksum manifest and optional signing/append-only policy for live-adjacent receipts. | Manifest proves file set observed at a point in time and is itself reviewed. | Not legal records compliance. | Codex |
| G15 | Governance over-investment | [Target State B](../../think/2026-06-12-target-state-b-and-loop-topology.md), [Graph Rationalization Audit](../graph-rationalization-audit.md), `task governance:graphs` | Governance should support work, not replace it | Governance/evidence plane is more mature than research/execution substance. | low but strategic | A4 | Freeze new governance graph breadth unless it directly closes G01-G14. | Roadmap says "do not add governance breadth" and reviewers enforce it. | Does not delete existing governance. | Codex |

## Priority Bands

| Band | Gaps | Reason |
| --- | --- | --- |
| Now | G01, G02, G05, G06 | These affect value, safety, or accountable control shape. |
| Next | G03, G04, G07, G08, G09, G10 | These deepen research/control loops and create the product hinge. |
| Later | G11, G12, G13, G14 | These matter for frontend/product maturity and external auditability. |
| Hold | G15 | Avoid adding governance breadth before substance deepens. |

## Non-Claims

- This register does not close the listed gaps.
- This register does not authorize dependencies, frontend work, or live trading.
- This register does not certify compliance with SEC, FINRA, broker, exchange,
  ASVS, SSDF, WCAG, or any other external standard.
