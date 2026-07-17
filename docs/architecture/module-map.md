# FinHarness Module Map

状态:current(2026-07-10)。本页只描述**当前 mainline** 的模块事实。历史
ten-layer trading chain 与 live-trading code 保留在 archive,不列为当前模块。

方向以 [Product North Star](../product-north-star.md) 与
[Capital OS Layering](capital-os-layering.md) 为准。系统归属看
[System Map](system-map.md)。如果只需要每个部分的一屏摘要,先看
[Framework Index](framework-index.md)。

## Canonical plane model

模块清单描述当前文件事实；规范性 ownership 与依赖方向见
[Plane Model ADR](../adr/2026-07-16-finharness-plane-model-and-dependency-direction.md)
和 `config/architecture-layers.yml`。统一词表是 **Truth、Knowledge、Control、
Judgment、Agent、Action/Learning、Product** 与横向 **Assurance**。

这里的 system/module 不要求与 plane 一一对应。一个模块可以实现多个关注点，但
canonical object 只有一个 owning plane；跨 plane 输入只沿矩阵的低 rank → 高 rank
方向消费。Python `statecore`、`decisioning`、`research` 等 import layers 继续用于
检查当前代码依赖，不能被误读为第二套领域 plane。

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

<!-- BEGIN GENERATED: system-catalog -->
> Generated from `docs/architecture/system-catalog.yml`. Do not edit this section; run `task docs:generate-current-views`.

| System | Lifecycle | Runtime roots | Ownership note |
| --- | --- | --- | --- |
| Shared Artifact and Receipt Store | `current` | `src/finharness/artifact_store.py`<br>`src/finharness/import_provenance.py`<br>`src/finharness/statecore/receipt_io.py` | Domain services own semantics and authority; the store owns durability and integrity. Descriptors and bytes are truth, while indexes are reconstructable. |
| Product North Star | `current` | `README.md`<br>`docs/product/` | Diataxis and product-principle discipline; keep category language explicit. |
| Evolution Roadmap | `current` | `docs/architecture/finharness-evolution-roadmap.md`<br>`docs/governance/debt-register.json` | Sequence by closed contracts, native issue dependencies, and user-outcome proof; PR counts and version labels are not completion evidence. |
| State Core | `current` | `src/finharness/statecore/`<br>`src/finharness/capital_import_contract.py`<br>`src/finharness/statecore/identities.py`<br>`src/finharness/position_valuation.py`<br>`src/finharness/personal_finance.py`<br>`src/finharness/beancount_adapter.py`<br>`src/finharness/api/routes_state.py` | Borrow event/receipt-sourcing ideas without adopting a heavy event platform. |
| Capital Map | `current` | `src/finharness/exposure.py`<br>`src/finharness/daily_brief.py`<br>`src/finharness/daily_change_brief.py` | BI/read-model pattern; FinHarness mirrors state and does not replace the ledger. |
| IPS / Policy / Authority Credentials | `current` | `src/finharness/ips.py`<br>`src/finharness/api/routes_ips.py`<br>`src/finharness/authority_administration.py`<br>`src/finharness/statecore/capital_mandates.py`<br>`src/finharness/api/routes_capital_mandates.py`<br>`src/finharness/statecore/agent_authority_grants.py`<br>`src/finharness/api/routes_agent_authority_grants.py` | IdentityProvider assertions feed one closed domain-owned human-administration guard; they do not become capital authority by authentication alone. CapitalMandate versions and lifecycle events remain immutable principal-bound inputs. AgentAuthorityGrant stays exact-version/currency/scope bound, while Agent-runtime consumption remains separate from human administration and never grants execution authority. |
| Decision Workflow | `current` | `src/finharness/allocation.py`<br>`src/finharness/statecore/decision_scaffold.py`<br>`src/finharness/statecore/risk_classification.py` | RFC and decision-record style; human review remains authority. |
| Review System | `current` | `src/finharness/statecore/proposals.py`<br>`src/finharness/review_read.py`<br>`src/finharness/risk_register.py`<br>`src/finharness/lesson_loop.py`<br>`src/finharness/rule_change_ledger.py` | Decision log plus risk/issue register discipline; attestation and risk severity hints are review evidence, not execution. |
| Capital Action Intent | `legacy` | `src/finharness/statecore/action_intents.py`<br>`src/finharness/statecore/action_intent_authority_bindings.py`<br>`src/finharness/statecore/action_intent_simulations.py`<br>`src/finharness/statecore/trade_plan_candidates.py`<br>`src/finharness/statecore/capital_objective_fits.py`<br>`src/finharness/statecore/trade_plan_review_gates.py`<br>`src/finharness/action_intent_preflight.py`<br>`src/finharness/api/routes_action_intents.py` | Compatibility-only. Preserve historical reads and migration evidence; do not add new objects, callers, or product capability to this chain. |
| Paper Validation Runtime | `legacy` | `src/finharness/statecore/paper_order_tickets.py`<br>`src/finharness/statecore/paper_executions.py`<br>`src/finharness/statecore/paper_accounts.py`<br>`src/finharness/api/routes_paper_validation.py` | Compatibility-only. Preserve historical receipts and bridge projections while new callers use the Execution Kernel simulated substrate. |
| Execution Kernel | `canonical` | `src/finharness/statecore/execution_models.py`<br>`src/finharness/execution/`<br>`src/finharness/api/routes_execution.py` | Classical execution kernel with receipt-backed services, service-enforced immutable capabilities, and an adapter protocol; only simulated submission is enabled and real external execution remains absent. |
| Research Evidence | `current` | `src/finharness/research_evidence.py`<br>`src/finharness/research_assets.py`<br>`src/finharness/research_enrichment.py` | Mature finance wheels provide calculations; FinHarness owns claims, redlines, and receipts. |
| External Data / Mature Wheels | `thin` | `src/finharness/data_entry.py`<br>`src/finharness/market_data.py`<br>`src/finharness/providers/`<br>`src/finharness/portfolio_risk.py`<br>`src/finharness/data_quality.py` | Adopt-not-invent; use mature wheels for heavy calculation and scanning. |
| Agent Explanation | `current` | `src/finharness/agent_capabilities.py`<br>`src/finharness/agent_context.py`<br>`src/finharness/agent_context_projection.py`<br>`src/finharness/agent_evidence.py`<br>`src/finharness/agent_runtime.py`<br>`src/finharness/agent_tool_entries.py`<br>`src/finharness/agent_tools.py`<br>`src/finharness/scaffold_candidate_preflight.py`<br>`src/finharness/review_read.py`<br>`src/finharness/proposal_queue_checks.py`<br>`src/finharness/hermes_bridge.py` | Hermes-style spec, availability, dispatch wrapper, output-budget, toolset registry, and capability-profile ideas; ToolEntry availability and profiles are diagnostics/visibility, not permission bypasses. |
| Agent Cognition Runtime / Work Orchestrator | `current` | `src/finharness/agent_cognition_flow.py`<br>`src/finharness/agent_run_receipts.py`<br>`src/finharness/agent_runtime_receipts.py`<br>`src/finharness/agent_tool_registry.py`<br>`src/finharness/agent_tool_availability.py`<br>`src/finharness/agent_tool_result_envelope.py`<br>`src/finharness/agent_context_trust_map.py`<br>`src/finharness/agent_receipt_search.py`<br>`src/finharness/domain_memory.py`<br>`src/finharness/playbook_loader.py`<br>`src/finharness/evaluator_registry.py`<br>`src/finharness/agent_operating_flow.py`<br>`src/finharness/review_workspace.py`<br>`src/finharness/agent_work_loop.py` | Keep domain cognition contracts provider-neutral. Reuse mature runner/checkpoint infrastructure only after the local action-observation-decision reducer and artifact chain are semantically proven. |
| Agent Autonomy Control Plane | `current` | `src/finharness/autonomy_control.py`<br>`src/finharness/agent_autonomy_adapter.py`<br>`src/finharness/agent_work_loop.py` | Keep admission local, typed, deterministic, and provider-neutral. Consider an external policy engine only after rule volume or multi-runtime consistency creates measured pressure. |
| Cockpit / API | `current` | `src/finharness/api/`<br>`frontend/` | Thin adapter and view-contract discipline; avoid heavy frontend framework until needed. |
| EOS Governance / Quality | `current` | `tests/_policy_registry.py`<br>`tests/_graph_registry.py`<br>`src/finharness/hardening.py`<br>`src/finharness/repo_intelligence.py`<br>`src/finharness/quality_governance_graph.py`<br>`src/finharness/release_preflight_graph.py`<br>`scripts/verify_debt_register.py` | Python registry now; defer OPA, Conftest, Backstage, Temporal until repeated pain. |
| Security / Supply Chain | `current` | `.github/`<br>`src/finharness/hardening.py`<br>`data/security/` | OpenSSF Scorecard, CodeQL, Gitleaks, Trivy, SBOM/SLSA posture. |
| Archived Live-Trading Legacy | `archived` | `experiments/archive/live_trading_legacy/` | If revived, redesign as a separately gated capability rather than inheriting mainline authority. |
<!-- END GENERATED: system-catalog -->

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
| L6 Agent Task Runtime | current AUT2 + planned | `AgentWorkRequest`, `AgentWorkToolRequest`, `AgentWorkObservation`, `AgentWorkDecision`, `AgentWorkResult`; later `AgentCheckpoint`, `HumanHandoff` | One bounded Agent Operating Cycle is semantically closed and durable/searchable. Cross-cycle session, checkpoint/resume, scheduling, and delegation remain planned. |
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
