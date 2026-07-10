# FinHarness Module Map

状态:current(2026-07-10)。本页只描述**当前 mainline** 的模块事实。历史
ten-layer trading chain 与 live-trading code 保留在 archive,不列为当前模块。

方向以 [Product North Star](../product-north-star.md) 与
[Capital OS Layering](capital-os-layering.md) 为准。系统归属看
[System Map](system-map.md)。如果只需要每个部分的一屏摘要,先看
[Framework Index](framework-index.md)。

## Status Legend

```text
current   已在 mainline,有直接或横切测试
thin      已在 mainline,但仍是薄适配/解释层
canonical 当前唯一主线;新调用方必须使用
scaffolded 结构存在,但生命周期验收尚未闭合
legacy    仅兼容历史读取/迁移;不得新增调用方或能力
planned   明确下一步,尚未实现
archived  只作历史参考,不属于 mainline runtime
```

## Mainline Modules

| System | Status | Main files | Notes |
| --- | --- | --- | --- |
| State Core | current | `statecore/models.py`, `store.py`, `receipt_io.py`, `receipt_index.py`, `snapshot_ingest.py`, `observations.py`, `diff.py`, `snapshots.py` | SQLite query mirror + receipt source-of-truth. Decimal money is TEXT-backed. |
| Capital Map | current | `exposure.py`, `daily_brief.py`, `daily_change_brief.py` | Read-only state views, ten-slot daily brief, data gaps explicit. |
| IPS / Policy / Authority Credentials | current | `ips.py`, `api/routes_ips.py`, `statecore/capital_mandates.py`, `api/routes_capital_mandates.py`, `statecore/agent_authority_grants.py`, `api/routes_agent_authority_grants.py`, `InvestmentPolicyStatement`, `CapitalMandate`, `AgentAuthorityGrant` | L3 v0. Active IPS personalizes L4 `ObservationThresholds`; compliance check is descriptive. CapitalMandate records the human-attested policy domain future authority objects may cite. AgentAuthorityGrant is a receipt-backed mandate-bound authority credential with dynamic validation and closed deny reasons. Neither object authorizes execution, approves trade plans, submits orders, or bypasses preflight. |
| Decision Workflow | current | `allocation.py`, `statecore/decision_scaffold.py`, `statecore/risk_classification.py` | Capital allocation candidates become governed proposals. High-risk approval needs counter-evidence. |
| Review System | current | `statecore/proposals.py`, `proposal_revisions.py`, `review_read.py`, `risk_register.py`, `annual_review.py`, `lesson_loop.py`, `rule_change_ledger.py` | Append-only review, scaffold revision, attestation, compare marks, annual review, lesson-to-rule, deterministic review queue triage, and derived risk register v0. |
| Capital Action Intent | legacy | `statecore/action_intents.py`, `statecore/action_intent_authority_bindings.py`, `statecore/action_intent_simulations.py`, `statecore/trade_plan_candidates.py`, `statecore/capital_objective_fits.py`, `statecore/trade_plan_review_gates.py`, `action_intent_preflight.py`, `api/routes_action_intents.py` | Superseded by Execution Kernel. Retained only for historical receipt readability and bounded migration; no new callers or capability expansion. |
| Paper Validation Runtime | legacy | `statecore/paper_order_tickets.py`, `statecore/paper_executions.py`, `statecore/paper_accounts.py`, `api/routes_paper_validation.py` | Superseded by the Execution Kernel simulated substrate. Retained only for historical reads and migration. |
| Execution Kernel | canonical | `statecore/execution_models.py`, `execution/services.py`, `execution/broker.py`, `execution/commands.py`, `execution/capabilities.py`, `execution/adapters/simulated_broker.py`, `api/routes_execution.py` | Canonical deterministic execution lifecycle. Only simulated adapter registration is allowed; future external execution requires a separate C3 boundary program. |
| Research Evidence | current | `research_evidence.py`, `research_history_provider.py`, `research_enrichment.py`, `research_rigor.py`, `research_assets.py`, `redlines.py` | Historical/descriptive evidence only. Default path stays offline. |
| External Data Adapters | thin | `data_entry.py`, `market_data.py`, `providers/ccxt_provider.py`, `portfolio_risk.py`, `metrics.py`, `data_quality.py` | Mature-wheel adapters; not source-of-truth for personal state. |
| Personal Finance Imports | current | `beancount_adapter.py`, `personal_finance.py`, import scripts | Read-only mirror into State Core; FinHarness is not the ledger. |
| Agent Explanation | current v0 | `agent_context.py`, `agent_context_projection.py`, `agent_capabilities.py`, `agent_evidence.py`, `agent_tools.py`, `agent_runtime.py`, `scaffold_candidate_preflight.py`, `proposal_queue_checks.py`, `review_read.py`, `hermes_bridge.py` | Capital OS context packs plus explicit capability profiles, profile-aware context projection/budget, `AgentToolEntry` metadata/availability, evidence provider registry, runtime resolver/dispatch result/error/evidence envelope/budget, proposal draft provenance, AgentReviewNoteDraft timeline artifacts, AgentScaffoldRevisionApplyCandidate timeline artifacts, system-recomputed scaffold candidate preflight, preflight-bound human-confirmed scaffold candidate apply, read-only queue checks with blocked transition scope, review-task lifecycle projections, deterministic review queue triage, and derived risk register; default remains read/explain baseline, review-draft can create append-only proposal drafts, review-note can create append-only review-note artifacts, scaffold-candidate can create append-only scaffold apply candidates from risk register items, system preflight can return pass/warn/block readiness, and human confirmation can apply them through the proposal revision chain after hash binding. |
| Agent Cognition Runtime / Work Orchestrator | scaffolded | `agent_cognition_flow.py`, `agent_run_receipts.py`, `agent_runtime_receipts.py`, `agent_tool_registry.py`, `agent_tool_availability.py`, `agent_tool_result_envelope.py`, `agent_context_trust_map.py`, `agent_receipt_search.py`, `domain_memory.py`, `playbook_loader.py`, `evaluator_registry.py`, `agent_operating_flow.py`, `review_workspace.py`, `agent_work_loop.py` | Cognition primitives and operating surfaces are consumable. The current work entry point remains a deterministic pre-requested pipeline; observation-driven control, step reduction, complete artifact linkage, persistence/search, and workspace hydration are pending. |
| Cockpit/API | current | `api/app.py`, `routes_cockpit.py`, `routes_state.py`, `routes_proposals.py`, `routes_review.py`, `routes_action_intents.py`, `routes_paper_validation.py`, `routes_ips.py`, `routes_capital_mandates.py`, `routes_agent_authority_grants.py`, `frontend/` | Read/review/action-intent/paper-validation/authority-binding/capital-mandate/agent-authority-grant validation surface. No transfer, live execution, broker submit, or ceiling-raise endpoint. |
| Governance/Quality | current | `hardening.py`, `governance_dashboard.py`, `quality_governance_graph.py`, `release_preflight_graph.py`, `repo_intelligence_graph.py`, `project_governance_adapter.py`, `receipt_usage_audit.py`, `runtime_log.py`, `observability.py` | Checks, receipts, dashboards, trace-index support, repo intelligence. |
| Config/Auth | current | `config.py`, `authorization.py`, `restricted_symbols.py` | Runtime settings, optional authorization registry, research-symbol restrictions. |
| Workflows | current | `cognitive_graph.py`, `engineering_delivery_graph.py` | Goal-bound cognitive and engineering delivery workflows. |

## Capital Workbench Roadmap Modules

This table is intentionally split from current mainline modules. It names the
next work without pretending it has shipped.

| Layer | Status | Planned objects / surfaces | Notes |
| --- | --- | --- | --- |
| L0 Data Ingestion & Connectors | next | `DataConnector`, `RawDataArtifact`, `NormalizedDataFrame`, `DataReceipt`, `DataSourceRegistry` | First target after PR 103. |
| L1 Data Lake / Catalog / Quality | next | `DataCatalog`, `DataQualityReport`, `FieldSchema`, `FreshnessPolicy`, `LineageGraph`, `ProviderFallback` | Must expose source, provider, freshness, coverage, missing fields, and point-in-time safety. |
| L2 State Core / Capital Graph | current + planned | `statecore/model_base.py`, bounded-context model modules, `PersonalCapitalGraph`, richer capital-state read models | Shared model primitives and personal-finance models are split; higher-coupling contexts and graph queries remain planned. |
| L3 Research Workspace | planned | `InstrumentProfile`, `EvidencePack`, `ResearchMemo`, watchlist, instrument page, filing reader | Research evidence exists, but workspace artifacts/pages are planned. |
| L4 Scenario / What-if Engine | planned | `Scenario`, `WhatIfRun`, `PortfolioDelta`, `RiskImpactReport`, `DoNothingBaseline`, `ScenarioComparison` | Current action simulation is qualitative; scenario comparison is planned. |
| L5 Simulated Execution / Paper Review | current + planned | `PaperPerformanceReview`, `ScenarioVsExecutionComparison`, `PaperPnLSeries`, `PaperLessonCandidate` | Canonical Execution Kernel provides the simulated lifecycle; the old PaperValidation runtime is legacy. Performance/review closure is planned. |
| L6 Agent Task Runtime | scaffolded + planned | `AgentTask`, `AgentPlan`, `AgentStep`, `AgentToolRun`, `AgentArtifact`, `AgentCheckpoint`, `HumanHandoff` | Cognition surfaces and a deterministic work orchestrator exist; a semantically closed, resumable task runtime does not. |
| L7 Cockpit / Frontend Workbench | planned | Home, Portfolio, Research, Scenarios, Decisions, Paper, Agent Tasks, Data Catalog, Settings | Build page-by-page as APIs stabilize. |
| L8 Review / Learning / Governance | current | receipt, attestation, review, lesson, rule candidate, policy update, risk register, audit trail | Cross-cutting system property, not the product headline. |

## Product Surface

| Surface | Status | Files | Notes |
| --- | --- | --- | --- |
| Local API | current | `api/app.py` + routers | FastAPI, trace header, static cockpit mount. |
| Cockpit frontend | current | `frontend/index.html`, `api.js`, `state.js`, `actions.js`, `app.js`, `styles.css` | Vanilla JS product surface; governed review writes use one fail-closed action shell. |
| CLI tasks | current | `Taskfile.yml`, `scripts/*.py` | Use `task --list` for live list; `docs:current-check` guards current docs. |

## Tests And Checks

| Layer | Entry point |
| --- | --- |
| Standard suite | `task check` |
| Fast local suite | `task check:fast` |
| CI merge suite | `task check:ci` |
| Research-complete suite | `task check:research` |
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
