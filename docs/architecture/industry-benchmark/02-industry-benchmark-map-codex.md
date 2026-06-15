# Industry Benchmark Map

Author: Codex
Parallel agent: Claude
Status: draft
Date: 2026-06-15
Evidence policy: primary-source-first

This map lists the mature methods FinHarness should compare against. It does
not say FinHarness must become an institutional broker, OEMS vendor, enterprise
SaaS backend, or trading UI. It identifies which methods are worth adopting,
which belong behind mature wheels, and which are explicit non-targets.

Parallel input read: [Industry Reference and Roadmap](../industry-reference-and-roadmap.md).

## Benchmark Lanes

| Lane | Mature reference | FinHarness use | Not a target |
| --- | --- | --- | --- |
| Trading lifecycle | OMS/EMS/OEMS split: order lifecycle, execution, allocation, reconciliation, settlement, reporting. | Use as a lifecycle checklist for proposal -> risk -> paper execution -> post-trade evidence. | Full broker OMS, clearing, settlement, SOR, FIX, custody. |
| Market-access controls | SEC Rule 15c3-5 control shape: pre-set limits, erroneous-order checks, authorized users/accounts, immediate post-trade reports, direct control, periodic review. | Benchmark safety design even though FinHarness is not a broker-dealer. | Claiming legal compliance or market-access certification. |
| Quant research rigor | In-sample -> out-of-sample -> walk-forward -> multiple-testing correction/Deflated Sharpe -> CPCV. | Define research evidence rungs and forbid claims above the rung climbed. | Treating one backtest as proof of edge. |
| Mature quant libraries | vectorbt, Riskfolio-Lib, QuantStats, TA-Lib/pandas-ta, NautilusTrader, broker/venue tooling. | Heavy math/engine behavior lives behind adapters; local code records evidence and keeps authority limits. | Rebuilding engines, optimizers, order semantics, or portfolio accounting locally. |
| Backend interface discipline | OpenAPI, JSON Schema, idempotency, typed contracts, audit logs. | Future read-only backend interface over snapshots/receipts/cockpit. | Mutation endpoint, order entry, live authorization. |
| Observability and lineage | OpenTelemetry for traces/metrics/logs; OpenLineage-style job/dataset lineage. | Future compatibility target for workflow/evidence traces. | Replacing FinHarness receipts with a generic tracing product. |
| Software security | NIST SSDF, OWASP ASVS, dependency/secret/container scanning. | Keep security gates and review maps grounded in mature standards. | Certifying SSDF/ASVS compliance from local checks alone. |
| Frontend safety and accessibility | Read-only review UX, evidence drill-down, deliberate confirmation, WCAG 2.2. | Future cockpit/review frontend must make brakes visible and slow down authority-changing actions. | One-click trade UI, autonomous execution UI, gamified signal dashboard. |

## Financial Trading References

### OMS / EMS / OEMS

Mature trading platforms separate the order lifecycle from execution mechanics:

- OMS-like concerns: portfolio state, mandates, compliance, pre-trade risk,
  allocations, reconciliation, reporting.
- EMS-like concerns: routing, execution venues, fills, execution quality, TCA.
- OEMS trend: unify lifecycle and execution data so analytics and controls share
  one model.

FinHarness implication: the ten-layer chain is closer to a research and
control-plane harness than an OEMS. It should borrow the lifecycle vocabulary
without pretending to own allocation, settlement, routing, or custody.

Primary repo anchors:

- [Ten Layer LangGraph Map](../ten-layer-langgraph-map.md)
- [Execution module](../../modules/09-execution.md)
- [Post Trade module](../../modules/10-post-trade.md)

### SEC Rule 15c3-5 Control Shape

Rule 15c3-5 applies to broker-dealers with market access. FinHarness is not in
that legal role, but the rule names a serious control shape:

- reject orders above pre-set credit/capital thresholds;
- reject erroneous orders by price, size, duplicate-order, or rapid-order
  parameters;
- restrict access to authorized people/accounts;
- block restricted securities/persons;
- send immediate post-trade reports to surveillance;
- keep controls under direct and exclusive control of the responsible party;
- document reviews and named-person certification.

FinHarness implication: local brakes stay local. Riskfolio, vectorbt,
NautilusTrader, and broker tools may produce evidence or order-shaped objects;
they must not widen caps, bypass human confirmation, or authorize live orders.

Sources:

- SEC FAQ:
  https://www.sec.gov/rules-regulations/staff-guidance/trading-markets-frequently-asked-questions/divisionsmarketregfaq-0
- eCFR 17 CFR 240.15c3-5:
  https://www.ecfr.gov/current/title-17/chapter-II/part-240/subject-group-ECFRc8401dcba174f73/section-240.15c3-5
- Parallel input:
  [SEC 15c3-5 Market Access Review](../../reviews/2026-06-15-sec-15c3-5-market-access-rule-review.md)

## Quant Research References

| Rung | Mature method | FinHarness rule |
| --- | --- | --- |
| R0 | In-sample backtest | May only show initial evidence; not enough for support. |
| R1 | Out-of-sample split | First honest holdout evidence. |
| R2 | Walk-forward | Tests robustness under rolling reoptimization. |
| R3 | Trial accounting + Deflated Sharpe style discount | Discounts selection bias from trying many variants. |
| R4 | CPCV candidate | Later false-discovery control candidate; likely dependency decision. |

FinHarness implication: a receipt must say the rung climbed, trial count when
known, data limitations, cost assumptions, and non-claims. Validation must not
label a hypothesis "supported" above the rung actually climbed.

Sources:

- vectorbt portfolio documentation:
  https://vectorbt.dev/api/portfolio/base/
- Deflated Sharpe / backtest overfitting paper:
  https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2460551
- Research interface spec:
  [Research Interface vectorbt spec](../research-interface-vectorbt-spec.md)

## Mature Wheel References

| Capability | Mature owner | Local FinHarness role |
| --- | --- | --- |
| Indicator math | TA-Lib, pandas-ta, vectorbt indicators | Feature naming, state labels, lineage, `execution_allowed=false`. |
| Backtesting/research | vectorbt | Evidence provider and validation handoff. |
| Portfolio optimization | Riskfolio-Lib | Suggested weights as reviewed requests only. |
| Performance summaries | QuantStats/vectorbt stats | Summary fields and non-claims. |
| Execution modeling | NautilusTrader paper/backtest concepts, official broker/venue tools | Dry-run/paper adapter, no-live block, receipts. |
| Data contracts | Pandera, provider schemas | OHLCV contract and soft quality semantics. |

Sources:

- Riskfolio-Lib docs: https://riskfolio-lib.readthedocs.io/
- NautilusTrader docs: https://nautilustrader.io/docs/latest/
- Interface reference: [Interface Reference](../../reference/interfaces.md)

## Backend References

| Mature method | Use in future FinHarness backend | Safety note |
| --- | --- | --- |
| OpenAPI | Describe a read-only HTTP interface for snapshots, receipts, cockpit state, and review queues. | OpenAPI describes the surface; it must not create authority. |
| JSON Schema | Version external payload shapes and receipt query responses. | Schema validation is not policy authorization. |
| Idempotency | Required for any future receipt-writing or review-attestation command. | Idempotency keys prevent duplicate action; they do not make the action safe. |
| OpenTelemetry | Future trace/metric/log compatibility for workflows and UI requests. | Trace is not a receipt. |
| OpenLineage | Future job/dataset lineage export target. | External lineage must index, not replace, FinHarness receipts. |
| NIST SSDF | Secure software practice reference for local development. | Local check pass is not SSDF certification. |
| OWASP ASVS | Security verification checklist for future web surface. | ASVS must be scoped; no blanket compliance claim. |

Sources:

- OpenAPI 3.2: https://spec.openapis.org/oas/v3.2.0.html
- JSON Schema 2020-12: https://json-schema.org/draft/2020-12
- OpenTelemetry: https://opentelemetry.io/
- OpenLineage: https://openlineage.io/docs/
- NIST SSDF SP 800-218: https://csrc.nist.gov/pubs/sp/800/218/final
- OWASP ASVS: https://owasp.org/www-project-application-security-verification-standard/

## Frontend References

The future frontend should be a review workstation, not a trading terminal:

- read-only evidence dashboard first;
- receipt and lineage drill-down;
- human review queue with slow, explicit attestations;
- every recommendation shows evidence, assumptions, rejected alternatives,
  risks, non-claims, receipt refs, and authority state;
- no order-entry control, no "go live" control, no hidden mutation path;
- WCAG 2.2 accessibility as baseline for readable, keyboard-navigable review.

Source:

- WCAG 2.2: https://www.w3.org/TR/WCAG22/

## Non-Claims

- This map does not prove FinHarness conforms to any listed standard.
- This map does not authorize live trading.
- This map does not require adopting every listed tool or standard immediately.
- This map does not make mature library output equivalent to a human decision.
