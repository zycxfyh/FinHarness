# FinHarness Module Map

状态:current(2026-06-28)。本页只描述**当前 mainline** 的模块事实。历史
ten-layer trading chain 与 live-trading code 保留在 archive,不列为当前模块。

方向以 [Product North Star](../product-north-star.md) 与
[Capital OS Layering](capital-os-layering.md) 为准。系统归属看
[System Map](system-map.md)。如果只需要每个部分的一屏摘要,先看
[Framework Index](framework-index.md)。

## Status Legend

```text
current   已在 mainline,有直接或横切测试
thin      已在 mainline,但仍是薄适配/解释层
planned   明确下一步,尚未实现
archived  只作历史参考,不属于 mainline runtime
```

## Mainline Modules

| System | Status | Main files | Notes |
| --- | --- | --- | --- |
| State Core | current | `statecore/models.py`, `store.py`, `receipt_io.py`, `receipt_index.py`, `snapshot_ingest.py`, `observations.py`, `diff.py`, `snapshots.py` | SQLite query mirror + receipt source-of-truth. Decimal money is TEXT-backed. |
| Capital Map | current | `exposure.py`, `daily_brief.py`, `daily_change_brief.py` | Read-only state views, ten-slot daily brief, data gaps explicit. |
| IPS / Policy | current | `ips.py`, `api/routes_ips.py`, `InvestmentPolicyStatement` | L3 v0. Active IPS personalizes L4 `ObservationThresholds`; compliance check is descriptive. |
| Decision Workflow | current | `allocation.py`, `statecore/decision_scaffold.py`, `statecore/risk_classification.py` | Capital allocation candidates become governed proposals. High-risk approval needs counter-evidence. |
| Review System | current | `statecore/proposals.py`, `proposal_revisions.py`, `review_read.py`, `annual_review.py`, `lesson_loop.py`, `rule_change_ledger.py` | Append-only review, scaffold revision, attestation, compare marks, annual review, lesson-to-rule. |
| Research Evidence | current | `research_evidence.py`, `research_history_provider.py`, `research_enrichment.py`, `research_rigor.py`, `research_assets.py`, `redlines.py` | Historical/descriptive evidence only. Default path stays offline. |
| External Data Adapters | thin | `data_entry.py`, `market_data.py`, `providers/ccxt_provider.py`, `portfolio_risk.py`, `metrics.py`, `data_quality.py` | Mature-wheel adapters; not source-of-truth for personal state. |
| Personal Finance Imports | current | `beancount_adapter.py`, `personal_finance.py`, import scripts | Read-only mirror into State Core; FinHarness is not the ledger. |
| Agent Explanation | current v0 | `agent_context.py`, `agent_capabilities.py`, `agent_tools.py`, `hermes_bridge.py` | Read-only Capital OS context packs plus explicit capability profiles; default profile remains read/explain and no source-of-truth writes. |
| Cockpit/API | current | `api/app.py`, `routes_cockpit.py`, `routes_state.py`, `routes_proposals.py`, `routes_review.py`, `routes_ips.py`, `frontend/` | Read/review surface only. No order, transfer, live execution, or ceiling-raise endpoint. |
| Governance/Quality | current | `hardening.py`, `governance_dashboard.py`, `quality_governance_graph.py`, `release_preflight_graph.py`, `repo_intelligence_graph.py`, `project_governance_adapter.py`, `receipt_usage_audit.py`, `runtime_log.py`, `observability.py` | Checks, receipts, dashboards, trace-index support, repo intelligence. |
| Config/Auth | current | `config.py`, `authorization.py`, `restricted_symbols.py` | Runtime settings, optional authorization registry, research-symbol restrictions. |
| Workflows | current | `cognitive_graph.py`, `engineering_delivery_graph.py` | Goal-bound cognitive and engineering delivery workflows. |

## Product Surface

| Surface | Status | Files | Notes |
| --- | --- | --- | --- |
| Local API | current | `api/app.py` + routers | FastAPI, trace header, static cockpit mount. |
| Cockpit frontend | current | `frontend/index.html`, `frontend/app.js`, `frontend/styles.css` | Vanilla JS product surface; review-only affordances. |
| CLI tasks | current | `Taskfile.yml`, `scripts/*.py` | Use `task --list` for live list; `docs:current-check` guards current docs. |

## Tests And Checks

| Layer | Entry point |
| --- | --- |
| Standard suite | `task check` |
| Fast Python checks | `task test` |
| Frontend DOM checks | `task test:frontend` |
| Optional browser smoke | `task test:browser` |
| Governance boundary probes | `task governance:check` |
| Current-doc drift probe | `task docs:current-check` |
| Security hardening | `task hardening:gate`, `task security:*` |

## Archived Modules

| Archive | Location | Boundary |
| --- | --- | --- |
| Ten-layer trading signal chain | `docs/archive/ten-layer-trading-chain/` | Historical docs and retired code references. Not current architecture. |
| Legacy live-trading experiments | `experiments/archive/live_trading_legacy/` | OKX/Alpaca/trading guard code moved out of mainline; no Taskfile/API/Agent entry. |
| Legacy Rust crate | `docs/archive/legacy-rust-crate/` | Historical implementation only. Active control plane is Python. |

## Maintenance Contract

Update this page when any of these change:

- `src/finharness` module added/deleted/renamed;
- API router added/deleted/renamed;
- Taskfile entry added/deleted/renamed;
- a planned layer becomes current;
- an active module is archived.

Run:

```bash
task docs:current-check
```

This page is a current-fact map, not a changelog. Put why/why-not reasoning in
ADRs, proposals, or reviews.
