# FinHarness Framework Index

状态:current(2026-07-11)。这是 FinHarness 的“不要每次重新理解一遍”索引。

本页只回答四件事:

1. FinHarness 到底是什么框架;
2. 每个部分的核心职责是什么;
3. 当前入口和机器检查在哪里;
4. 我们借鉴哪些成熟方案,哪些暂时不上。

更细的文件事实看 [Module Map](module-map.md);系统边界看
[System Map](system-map.md);分层演进看 [Capital OS Layering](capital-os-layering.md)。
产品能力路线看 [Capital Workbench Roadmap](../product/capital-workbench-roadmap.md)。
2026-07-11 外部调研与代码校准看
[External Research Synthesis](../notes/2026-07-11-external-research-synthesis.md)，
分阶段实施门槛看
[Evidence-First Evolution Execution Plan](../proposals/2026-07-11-finharness-evolution-execution-plan.md)。
机器可读目录看 [System Catalog](system-catalog.yml);工程推进风险看
[Engineering Leverage Map](engineering-leverage-map.md)。Agent L5 参考模式看
[Agent Runtime Reference](agent-runtime-reference/README.md)。金融行业词与
FinHarness 原语的对应关系看
[Financial Terminology Map](../reference/financial-terminology-map.md)。

## One Sentence

FinHarness 当前是一个 local-owned **Personal Capital Review and Decision
Ledger**：把个人资本状态、证据、proposal/review、human DecisionRecord 方向、
receipt、governance checks 和 simulated Execution substrate 组织成可审计的
复核工作台。**Agent-Native Personal Capital Operating System** 是北极星，
不是当前产品完成度声明。

## Framework Shape

```text
Human Principal
  goals + capital constitution + mandate + veto/revocation
        ↓
Capital Agent
  observe -> reason -> plan -> act -> verify -> learn
        ↓
FinHarness Harness
  world model + tools/skills + policy + receipts + recovery + escalation
        ↓
Deterministic Engines
  accounting/FX/risk/Scenario + persistence + execution + reconciliation
```

当前 Agent Operating Cycle v0.1 已达到 AUT2 foundation（15/15），仍处于
Human-in-the-loop；这不是 AUT3 delegated decision authority。
目标不是让确定性引擎永久拥有工作流，而是让 Agent 在 Harness 的机器边界内
逐步获得目标级自治。External/mature wheels 负责 mechanics，不拥有目标或权限。

Current executable truth: **Agent Operating Cycle v0.1 is the current AUT2
foundation**. Structural evidence: `run_agent_operating_surface_smoke.py` (23 checks);
`run_agent_work_loop_smoke.py` (18 structural checks). The dedicated behavioral
gate is 15/15.
This closure does not imply session/resume, scheduling, subagents, or AUT3 authority.

## System Summary

<!-- BEGIN GENERATED: system-catalog -->
> Generated from `docs/architecture/system-catalog.yml`. Do not edit this section; run `task docs:generate-current-views`.

| System | Lifecycle | Current responsibility | Primary roots | Verification |
| --- | --- | --- | --- | --- |
| Shared Artifact and Receipt Store | `current` | Domain-neutral immutable-byte, descriptor, integrity-audit, index, and recovery ports. STORE-00 is live for new artifact forms; existing domain receipts migrate separately with replay and rollback proof. | `src/finharness/artifact_store.py`<br>`src/finharness/import_provenance.py`<br>`src/finharness/statecore/receipt_io.py` | `uv run python -m unittest tests.test_artifact_store` |
| Product North Star | `current` | Product category and staged capability path; FinHarness is a personal capital governance framework moving from awareness and review toward paper validation and controlled capital-action workflows. | `README.md`<br>`docs/product/` | `task docs:current-check` |
| Evolution Roadmap | `current` | Canonical implementation sequence, phase gates, dependency order, and current active-debt projection for the verified capital decision loop. | `docs/architecture/finharness-evolution-roadmap.md`<br>`docs/governance/debt-register.json` | `uv run python -m unittest tests.test_evolution_roadmap`<br>`uv run python scripts/verify_debt_register.py` |
| State Core | `current` | Receipt-backed query mirror for personal capital state; receipts remain the evidence root. | `src/finharness/statecore/`<br>`src/finharness/personal_finance.py`<br>`src/finharness/beancount_adapter.py`<br>`src/finharness/api/routes_state.py` | `task test:all`<br>`task governance:check` |
| Capital Map | `current` | Read-only exposure, daily brief, dashboard summary, and capital-state observations. | `src/finharness/exposure.py`<br>`src/finharness/daily_brief.py`<br>`src/finharness/daily_change_brief.py` | `task brief:daily`<br>`task decisions:scan` |
| IPS / Policy / Authority Credentials | `current` | User-owned Investment Policy Statement, descriptive compliance checks, immutable principal-bound CapitalMandate versions with append-only lifecycle resolution, and mandate-bound AgentAuthorityGrant credentials with dynamic validation and closed deny reasons. | `src/finharness/ips.py`<br>`src/finharness/api/routes_ips.py`<br>`src/finharness/statecore/capital_mandates.py`<br>`src/finharness/api/routes_capital_mandates.py`<br>`src/finharness/statecore/agent_authority_grants.py`<br>`src/finharness/api/routes_agent_authority_grants.py` | `task governance:check`<br>`uv run python -m unittest tests.test_ips`<br>`uv run python -m unittest tests.test_capital_mandates`<br>`uv run python -m unittest tests.test_versioned_capital_mandates`<br>`uv run python -m unittest tests.test_agent_authority_grants`<br>`uv run python -m unittest tests.test_statecore_store` |
| Decision Workflow | `current` | Turns exposure and IPS thresholds into governed proposal review objects. | `src/finharness/allocation.py`<br>`src/finharness/statecore/decision_scaffold.py`<br>`src/finharness/statecore/risk_classification.py` | `task decisions:scan`<br>`task test:all` |
| Review System | `current` | Append-only proposal review, attestation, compare marks, annual review, lesson-to-rule, deterministic review queue triage, and derived risk register v0. | `src/finharness/statecore/proposals.py`<br>`src/finharness/review_read.py`<br>`src/finharness/risk_register.py`<br>`src/finharness/lesson_loop.py`<br>`src/finharness/rule_change_ledger.py` | `task governance:check`<br>`task test:all`<br>`uv run python -m unittest tests.test_review_read tests.test_review_workspace_api`<br>`uv run python -m unittest tests.test_risk_register` |
| Capital Action Intent | `legacy` | Superseded ActionIntent/TradePlan compatibility chain retained for historical receipt readability and migration through the Execution Kernel legacy bridge; no new callers. | `src/finharness/statecore/action_intents.py`<br>`src/finharness/statecore/action_intent_authority_bindings.py`<br>`src/finharness/statecore/action_intent_simulations.py`<br>`src/finharness/statecore/trade_plan_candidates.py`<br>`src/finharness/statecore/capital_objective_fits.py`<br>`src/finharness/statecore/trade_plan_review_gates.py`<br>`src/finharness/action_intent_preflight.py`<br>`src/finharness/api/routes_action_intents.py` | `uv run python -m unittest tests.test_action_intents`<br>`uv run python -m unittest tests.test_action_intent_authority_bindings`<br>`uv run python -m unittest tests.test_statecore_api` |
| Paper Validation Runtime | `legacy` | Superseded paper-order/account compatibility runtime retained for historical reads; new simulated execution uses the canonical Execution Kernel. | `src/finharness/statecore/paper_order_tickets.py`<br>`src/finharness/statecore/paper_executions.py`<br>`src/finharness/statecore/paper_accounts.py`<br>`src/finharness/api/routes_paper_validation.py` | `uv run python -m unittest tests.test_action_intents`<br>`uv run python -m unittest tests.test_statecore_api` |
| Execution Kernel | `canonical` | Canonical deterministic execution lifecycle from OrderDraft through pre-trade, approval, staging, simulated submission, execution report, position delta, and reconciliation. | `src/finharness/statecore/execution_models.py`<br>`src/finharness/execution/`<br>`src/finharness/api/routes_execution.py` | `uv run python -m unittest tests.test_execution_schema`<br>`uv run python -m unittest tests.test_execution_services`<br>`uv run python -m unittest tests.test_routes_execution`<br>`uv run python -m unittest tests.test_execution_adapter_boundary`<br>`uv run python -m unittest tests.test_execution_lifecycle_hardening`<br>`uv run python -m unittest tests.test_execution_capability_enforcement` |
| Research Evidence | `current` | Cite-only historical/descriptive evidence attached to candidates and proposals. | `src/finharness/research_evidence.py`<br>`src/finharness/research_assets.py`<br>`src/finharness/research_enrichment.py` | `task governance:check`<br>`task hardening:redteam` |
| External Data / Mature Wheels | `thin` | Read-only data and mature-tool adapters; external outputs are evidence, not authority. | `src/finharness/data_entry.py`<br>`src/finharness/market_data.py`<br>`src/finharness/providers/`<br>`src/finharness/portfolio_risk.py`<br>`src/finharness/data_quality.py` | `task wheels:check`<br>`task test:all` |
| Agent Explanation | `current` | Profile-selected Agent tools over Capital OS context packs; AgentToolEntry metadata, agent_evidence.py, agent_context_projection.py, and agent_runtime.py map profiles to actual SDK tools with capability, toolset, side-effect, availability, evidence provider ids, profile-aware context budgets, visible/hidden/unavailable runtime facts, structured dispatch results/errors/evidence envelopes, and result budgets; default posture is read/explain, review-draft can create append-only governed proposal drafts, review-note can create append-only AgentReviewNoteDraft artifacts, scaffold-candidate can create append-only AgentScaffoldRevisionApplyCandidate artifacts from active risk register items without mutating proposals, system preflight recomputes candidate apply readiness, and preflight-bound human-confirmed apply can move those candidates through the proposal revision chain. | `src/finharness/agent_capabilities.py`<br>`src/finharness/agent_context.py`<br>`src/finharness/agent_context_projection.py`<br>`src/finharness/agent_evidence.py`<br>`src/finharness/agent_runtime.py`<br>`src/finharness/agent_tool_entries.py`<br>`src/finharness/agent_tools.py`<br>`src/finharness/scaffold_candidate_preflight.py`<br>`src/finharness/review_read.py`<br>`src/finharness/proposal_queue_checks.py`<br>`src/finharness/hermes_bridge.py` | `uv run python -m unittest tests.test_agent_proposal_drafts`<br>`uv run python -m unittest tests.test_agent_review_note_drafts`<br>`uv run python -m unittest tests.test_agent_scaffold_revision_candidates`<br>`uv run python -m unittest tests.test_scaffold_candidate_preflight`<br>`uv run python -m unittest tests.test_scaffold_candidate_apply`<br>`uv run python -m unittest tests.test_agent_context_projection`<br>`uv run python -m unittest tests.test_agent_evidence`<br>`uv run python -m unittest tests.test_agent_runtime`<br>`uv run python -m unittest tests.test_agent_capabilities`<br>`uv run python -m unittest tests.test_agent_context`<br>`uv run python -m unittest tests.test_agent_tools` |
| Agent Cognition Runtime / Work Orchestrator | `current` | Agent Operating Cycle v0.1 passes the 15-contract AUT2 foundation gate with typed arguments, observation-driven decisions, independent budgets, playbook preflight, autonomy admission, terminal receipts/results/search/workspace, and all declared stop reducers. Session, resume, scheduling, and AUT3 authority are absent. | `src/finharness/agent_cognition_flow.py`<br>`src/finharness/agent_run_receipts.py`<br>`src/finharness/agent_runtime_receipts.py`<br>`src/finharness/agent_tool_registry.py`<br>`src/finharness/agent_tool_availability.py`<br>`src/finharness/agent_tool_result_envelope.py`<br>`src/finharness/agent_context_trust_map.py`<br>`src/finharness/agent_receipt_search.py`<br>`src/finharness/domain_memory.py`<br>`src/finharness/playbook_loader.py`<br>`src/finharness/evaluator_registry.py`<br>`src/finharness/agent_operating_flow.py`<br>`src/finharness/review_workspace.py`<br>`src/finharness/agent_work_loop.py` | `task test:all`<br>`task test:pytest`<br>`uv run python scripts/run_agent_operating_surface_smoke.py`<br>`uv run python scripts/run_agent_work_loop_smoke.py` |
| Agent Autonomy Control Plane | `current` | Deterministic Harness admission vocabulary and evaluator across W0-W4 world fidelity and AUT0-AUT6 autonomy, with a compatibility adapter for CapitalMandate and AgentAuthorityGrant. Every Agent work-loop dispatch crosses admission and persists non-executing evidence in the AUT2 terminal chain; effect commands remain outside this integration. | `src/finharness/autonomy_control.py`<br>`src/finharness/agent_autonomy_adapter.py`<br>`src/finharness/agent_work_loop.py` | `uv run python -m unittest tests.test_autonomy_control`<br>`uv run python -m unittest tests.test_autonomy_statecore_adapter`<br>`task agent:work-loop-acceptance-report` |
| Cockpit / API | `current` | Local read/review product surface for state, proposals, review, IPS, capital mandates, agent authority grant validation, and cockpit views. | `src/finharness/api/`<br>`frontend/` | `task test:frontend`<br>`task test:all` |
| EOS Governance / Quality | `current` | Change control, evidence-strength proof registry, docs-current guard, repo intelligence, hardening, and release checks. | `tests/_policy_registry.py`<br>`tests/_graph_registry.py`<br>`src/finharness/hardening.py`<br>`src/finharness/repo_intelligence.py`<br>`src/finharness/quality_governance_graph.py`<br>`src/finharness/release_preflight_graph.py`<br>`scripts/verify_debt_register.py` | `task docs:current-check`<br>`task governance:check`<br>`uv run python scripts/verify_debt_register.py`<br>`task check` |
| Security / Supply Chain | `current` | Threat model, SSDF map, CODEOWNERS, fuzz baseline, scanner aggregation, SBOM/provenance baseline. | `.github/`<br>`src/finharness/hardening.py`<br>`data/security/` | `task security:fuzz`<br>`task security:scan` |
| Archived Live-Trading Legacy | `archived` | Historical OKX, Alpaca, trading guard, and market-access code; no mainline runtime edge. | `experiments/archive/live_trading_legacy/` | `task docs:current-check`<br>`task governance:check` |
<!-- END GENERATED: system-catalog -->

## What Lives Where

| Need | Start here | Why |
| --- | --- | --- |
| “我们是什么?” | README + this page | 产品类别 + 框架一屏总结 |
| “有哪些系统?” | [System Map](system-map.md) | 每个 system 的职责、读写、adapter、不变量 |
| “有哪些文件?” | [Module Map](module-map.md) | 当前 mainline 文件事实 |
| “现在能跑什么?” | [Command Reference](../reference/commands.md), `task --list` | Taskfile 是命令事实源 |
| “哪些文档必须保持 current?” | [Documentation Fact Governance](documentation-fact-governance.md) | current lane 与 history lane 分开 |
| “哪些成熟方案可借?” | [Engineering Leverage Map](engineering-leverage-map.md), [Scaffolding Inventory](scaffolding-inventory.md), [Mature Wheel Control Plane](mature-wheel-control-plane.md) | 工程层次、keep / standardize / replace / defer 判断 |
| “Agent L5 参考哪些成熟运行时模式?” | [Agent Runtime Reference](agent-runtime-reference/README.md) | Hermes-style tool runtime、prompt/context、guardrail、review lifecycle、delegation、memory/skills 的参考边界 |
| “机器可读系统目录在哪?” | [System Catalog](system-catalog.yml) | 给 repo intelligence / checks / future generated docs 使用 |
| “哪些边界是机器守的?” | `task governance:policies` | policy registry 是当前 guardrail 入口 |
| “安全边界在哪?” | [Threat Model](../security/finharness-threat-model.md), [SSDF Control Map](../security/ssdf-control-map.md) | current security facts |

## Mature Solution Posture

FinHarness 的管理方式不是“所有成熟工具都上”,而是三档:

| Problem | Current solution | Mature reference | Decision rule |
| --- | --- | --- | --- |
| Architecture ownership | `system-map.md` + `module-map.md` + this index | Backstage catalog metadata | 先借 catalog 思想;多人/多 repo 后再考虑工具 |
| Change proposals | mini-RFC / ADR / proposal docs | Kubernetes KEPs, Rust RFCs | 大变更先写动机、边界、替代方案、receipt |
| Documentation types | tutorials / how-to / reference / explanation 分流 | Diataxis | 防止 README 变成百科全书 |
| Docs freshness | `GOV-DOCS-*` policy + `task docs:current-check` | docs-as-code / GitLab docs discipline | 可枚举漂移进机器检查 |
| Policy checks | Python `PolicyRule` registry | OPA / Conftest / Cedar | 规则多到 Python 难管时再升级 |
| Workflow durability | Taskfile + receipts + LangGraph where useful | Temporal | 出现定时、重试、长审批、补偿事务后再评估 |
| Observability | trace id -> receipt/task/request index | OpenTelemetry | trace 索引 receipt,不替代 receipt |
| Evidence lineage | local receipts | OpenLineage / MLflow / DVC / Sigstore | 外部 lineage 只能镜像/索引,不能成为 source-of-truth |
| Supply chain | CodeQL / Gitleaks / Trivy / Scorecard / local SBOM | SLSA, CycloneDX/SPDX, Syft | 有发布 artifact 后再做正式 attestation |

## Maintenance Rule

This index must change when any of these change:

- a current system is added, removed, archived, or renamed;
- `system-catalog.yml` changes a system id, doc path, runtime root, check, or
  upgrade trigger;
- a mature tool graduates from “reference posture” to active dependency;
- a current entry doc changes the product category or mainline loop;
- `system-map.md` or `module-map.md` changes system ownership.

Run:

```bash
task docs:current-check
task governance:check
```

This page is an index, not a design proof. Detailed reasoning belongs in ADRs,
mini-RFCs, reviews, or architecture specs.
