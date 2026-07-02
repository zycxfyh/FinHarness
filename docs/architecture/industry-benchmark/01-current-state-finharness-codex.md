# Current State Of FinHarness (Historical 2026-06-15 Snapshot)

Author: Codex
Parallel agent: Claude
Status: historical reference (downgraded 2026-07-02)
Date: 2026-06-15
Evidence policy: primary-source-first

This document describes what FinHarness looked like on 2026-06-15. It is
intentionally descriptive historical evidence, not the current fact source.
Current facts live in [Framework Index](../framework-index.md),
[Capital OS Layering](../capital-os-layering.md), [System Map](../system-map.md),
[Module Map](../module-map.md), and [System Catalog](../system-catalog.yml).
Historical task names in this document must not be treated as current command
guidance; use [Command Reference](../../reference/commands.md).

The industry comparison starts in
[02-industry-benchmark-map-codex.md](02-industry-benchmark-map-codex.md), and
gap judgment starts in [03-gap-register-codex.md](03-gap-register-codex.md).

Parallel input read: [State of FinHarness](../state-of-finharness.md).

## A. Data Plane

| Area | Current state | Repo evidence | Descriptive maturity |
| --- | --- | --- | --- |
| Market data ingestion | Pulls OHLCV/quotes, normalizes payloads, writes hashes, lineage, and receipts. | [Market Data module](../../modules/01-market-data.md), [Interface Reference](../../reference/interfaces.md), `task market-data:graph` in [Command Reference](../../reference/commands.md) | Primitive but real. |
| Data quality | Uses Pandera-backed OHLCV schema checks plus local soft verdict semantics. | [Data quality spec](../data-quality-interface-pandera-spec.md), [Receipt Reference](../../reference/receipts.md) | Production-shaped for the current OHLCV contract. |
| Provider surface | Uses OpenBB/yfinance and paper-broker data surfaces. | [Interface Reference](../../reference/interfaces.md), [README](../../../README.md) | Shallow provider diversity. |

Current limits: daily-bar focus, no explicit point-in-time guarantee, no
survivorship-bias-free universe, no multi-vendor reconciliation, and no
corporate-action audit beyond what providers expose.

## B. Feature And Indicator Plane

| Area | Current state | Repo evidence | Descriptive maturity |
| --- | --- | --- | --- |
| Indicators | MACD, squeeze, SMC/state labels, RSI/ATR and feature snapshots use mature indicator libraries where available. | [Indicators module](../../modules/02-indicators.md), `task feature:macd`, `task feature:squeeze` | Mixed: library-backed core, shallow around custom state labels. |
| Risk/return metrics | Risk-return summaries use QuantStats-backed metrics where wired. | [Interface Reference](../../reference/interfaces.md), `task experiments` | Production-shaped for summary metrics, not a full feature store. |
| Feature receipts | Feature outputs carry lineage and `execution_allowed=false`. | [Receipt Reference](../../reference/receipts.md) | Good evidence posture. |

Current limits: no formal feature store, no full look-ahead audit, and some
descriptive statistics remain local implementation rather than mature-wheel
owned.

## C. Research And Validation Plane

| Area | Current state | Repo evidence | Descriptive maturity |
| --- | --- | --- | --- |
| Hypothesis generation | LLM/deterministic generators draft falsifiable hypotheses; LLM stays in generator seat. | [Hypotheses module](../../modules/05-hypotheses.md), [Target State B](../../think/2026-06-12-target-state-b-and-loop-topology.md) | Shallow but correctly bounded. |
| Backtest evidence | vectorbt is wired as the mature research owner for validation evidence. | [Research spec](../research-interface-vectorbt-spec.md), [Interface Reference](../../reference/interfaces.md), `task validation:graph` | Primitive. |
| Validation output | Validation creates evidence snapshots and proposal handoff but does not authorize execution. | [Validation module](../../modules/06-validation.md), [Receipt Reference](../../reference/receipts.md) | Primitive evidence layer. |

Current limits: one basic in-sample MA-crossover style evidence path, no
out-of-sample ladder, no walk-forward, no explicit multiple-testing discount,
no cost-realism standard, and no claim that validation proves profitable alpha.

## D. Portfolio And Risk Plane

| Area | Current state | Repo evidence | Descriptive maturity |
| --- | --- | --- | --- |
| Portfolio risk | Riskfolio-Lib can produce allocation/weight evidence, but output feeds the requested side only. | [Portfolio risk spec](../portfolio-risk-interface-riskfolio-spec.md), [Interface Reference](../../reference/interfaces.md) | Toy-to-primitive. |
| Risk Gate | Applies mandate, symbol/action, cap, concentration, liquidity, drawdown/loss state, behavior reset, order-language, and human-review checks. | [Risk Gate module](../../modules/08-risk-gate.md), [Policy Contract](../policy-contract.md), `task risk-gate:graph` | Production-shaped for the current safety model. |
| Trading guard | Behavioral circuit breaker protects against drawdown/loss/cooldown/thesis failures. | [README](../../../README.md), [Evidence Inventory](../evidence-inventory.md) | Production-shaped discipline layer. |
| Lesson-to-rule | Lessons can be human-promoted into rule changes with receipt lineage. | [Promote Lesson To Rule](../../how-to/promote-lesson-to-rule.md), [Receipt Reference](../../reference/receipts.md) | Production-shaped for local governance. |

Current limits: no aggregate account-level limit ledger, no formal authorized
operator/account model, no restricted-symbol model, and no named control-owner
certification receipt.

## E. Proposal, Execution, And Post-Trade Plane

| Area | Current state | Repo evidence | Descriptive maturity |
| --- | --- | --- | --- |
| Proposal | Converts validation evidence into structured candidates with non-authority review questions. | [Proposal module](../../modules/07-proposal.md), `task proposal:graph` | Primitive. |
| Execution | Uses NautilusTrader-shaped paper/dry-run execution semantics; live mode is blocked in MVP layer execution. | [Execution module](../../modules/09-execution.md), [Execution spec](../execution-interface-nautilus-spec.md), `task execution:graph` | Primitive and safety-first. |
| Venue adapters | OKX read/write path and Alpaca paper scripts exist as venue-adjacent adapters with local gates. | [README](../../../README.md), [SEC 15c3-5 review](../../reviews/2026-06-15-sec-15c3-5-market-access-rule-review.md) | Mixed: OKX gate strongest, Alpaca paper scripts shallower. |
| Post-trade | Reconciles execution evidence and writes post-trade receipts. | [Post Trade module](../../modules/10-post-trade.md), `task post-trade:graph` | Shallow. |

Current limits: no smart order routing, no allocation/settlement/back-office
loop, no surveillance-grade post-trade report queue, and no first-class TCA
surface across paper fills.

## F. Evidence, Governance, And Security Plane

| Area | Current state | Repo evidence | Descriptive maturity |
| --- | --- | --- | --- |
| Receipts | Field-level receipt reference exists across layer and direct JSON shapes. | [Receipt Reference](../../reference/receipts.md) | Production-shaped evidence discipline. |
| Receipt usage | Receipt usage audit distinguishes durable consumed receipts, candidates, runtime output, and missing references. | [Receipt Usage Audit](../receipt-usage-audit.md) | Strong local governance. |
| Hardening | Security scan and hardening tasks aggregate pip-audit, gitleaks, Trivy, and local boundary tests. | [Security docs](../../security/mvp-hardening-gate.md), `task security:scan`, `task hardening:gate` | Production-shaped for local project governance. |
| Release/governance graphs | Quality, release, dashboard, and repo-intelligence graph lifecycle is tracked. | [Graph Rationalization Audit](../graph-rationalization-audit.md), `task governance:graphs` | Useful but already heavier than the trading substance. |

Current limit: governance is ahead of the finance substance. Adding more
governance graphs would not by itself improve research value or execution
quality.

## G. Orchestration, Backend Surface, And Frontend Surface

| Area | Current state | Repo evidence | Descriptive maturity |
| --- | --- | --- | --- |
| Orchestration | Ten-layer LangGraph chain and supporting graphs orchestrate snapshots and receipts. | [Ten Layer LangGraph Map](../ten-layer-langgraph-map.md), [Golden Path](../../tutorials/golden-path.md) | Primitive but coherent. |
| Backend surface | Primary interface is CLI tasks plus JSON/Markdown artifacts. No stable HTTP interface is documented. | [Command Reference](../../reference/commands.md), [Docs Map](../../README.md) | CLI-first, no product backend. |
| Frontend surface | No interactive frontend. Market cockpit writes Markdown/JSON review artifacts. | [README](../../../README.md), `task cockpit:market` | None beyond generated read-only artifacts. |
| Agent tools | OpenAI Agents SDK tools are registered for research tooling, not order entry. | [Interface Reference](../../reference/interfaces.md), `task agent:describe` | Shallow, correctly bounded. |

Current limits: no read-only evidence HTTP interface, no WebSocket/event stream,
no frontend review queue, no receipt drill-down UI, and no UI-level accessibility
or interaction standard.

## Non-Claims

- This inventory does not prove that FinHarness has profitable alpha.
- This inventory does not authorize live trading or autonomous order entry.
- This inventory does not certify legal, broker, exchange, tax, accounting,
  cybersecurity, or production readiness.
- This inventory does not close any gap; it only records the present state used
  by the benchmark series.
