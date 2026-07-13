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

| Part | Core summary | Primary docs | Runtime roots | Mature pattern / tool posture | Check / receipt |
| --- | --- | --- | --- | --- | --- |
| Product North Star | Agent-Native Personal Capital Operating System：Human Principal 拥有资本宪法，Capital Agent 拥有目标闭环，Harness 拥有准入/恢复，deterministic engines 拥有效果正确性。 | `docs/product-north-star.md`, `docs/product/*` | README, cockpit copy | autonomy ladder + product north-star discipline | `task docs:current-check` |
| Evolution Roadmap | 当前系统真相、PR 因果脉络、classical/agentic/human 责任、债务顺序与未来 phase gates。 | `finharness-evolution-roadmap.md`, `docs/proposals/2026-07-11-finharness-evolution-execution-plan.md`, `docs/notes/2026-07-11-external-research-synthesis.md`, `system-catalog.yml`, `docs/governance/debt-register.json` | No runtime root; derives from current code/tests/history. | Contracts closed and user outcomes proven, not PR count, receipt count, or version labels. | `task docs:current-check`, `task agent:work-loop-acceptance-report` |
| State Core | receipt-backed 状态镜像;SQLite 可查,receipt 是证据根。 | `system-map.md`, `module-map.md`, `reference/interfaces.md` | `statecore/`, `api/routes_state.py` | Event/receipt sourcing ideas,但保留本地简洁实现 | `task test`, StateCore tests |
| Capital Map | 把状态变成 exposure、daily brief、dashboard summary。 | `system-map.md`, `tutorials/golden-path.md` | `exposure.py`, `daily_brief.py`, `daily_change_brief.py` | 财务报表/BI read-model 思路;不替代 ledger | `task brief:daily`, `task decisions:scan` |
| IPS / Policy / Authority Credentials | 用户自己的投资政策声明、描述性 compliance check、未来授权前置的 human-attested CapitalMandate,以及 mandate-bound AgentAuthorityGrant credential。 | `capital-os-layering.md`, `system-map.md`, `docs/reference/financial-terminology-map.md`, `docs/adr/2026-07-02-capital-mandate-before-delegated-authority.md`, `docs/adr/2026-07-03-agent-authority-grants-are-mandate-bound-credentials.md` | `ips.py`, `api/routes_ips.py`, `statecore/capital_mandates.py`, `api/routes_capital_mandates.py`, `statecore/agent_authority_grants.py`, `api/routes_agent_authority_grants.py` | IPS / policy-as-code 思路;CapitalMandate 与 AgentAuthorityGrant 先用 receipt-backed local objects + dynamic validator,暂不上 OPA/Cedar;金融术语映射只作 design analogy,不是 compliance claim | `GOV-DOCS-003`, IPS/capital-mandate/agent-authority-grant tests |
| Decision Workflow | exposure + IPS 阈值生成 governed proposal,默认不执行。 | `system-map.md`, `tutorials/golden-path.md` | `allocation.py`, `statecore/decision_scaffold.py`, `risk_classification.py` | RFC/decision record 风格;人类 review 是 authority | `task decisions:scan`, proposal tests |
| Review System | append-only proposal review、scaffold revision、attestation、compare、annual review、lesson-to-rule、deterministic review queue triage、derived risk register v0。 | `system-map.md`, `engineering/system-directory-standard.md` | `statecore/proposals.py`, `review_read.py`, `risk_register.py`, `lesson_loop.py` | GitLab review discipline + risk/issue register;不把 attestation、queue priority 或 risk severity hint 当 execution | `GOV-REVIEW-001`, review/risk tests |
| Capital Action Intent | LEGACY — superseded by Execution Kernel. receipt-backed `ActionIntentCandidate` chain with preflight/simulation/objective-fit/review-gate. Retained for historical readability and migration bridge (`legacy_bridge.py`). New callers use `/execution/*`. | `system-map.md`, `legacy_bridge.py` | `statecore/action_intents.py`, `statecore/action_intent_authority_bindings.py`, `statecore/action_intent_simulations.py`, `statecore/trade_plan_candidates.py`, `statecore/capital_objective_fits.py`, `statecore/trade_plan_review_gates.py`, `api/routes_action_intents.py` | Marked legacy + deprecated in OpenAPI; X-FinHarness-Legacy-Surface header | action-intent + bridge tests |
| Paper Validation Runtime | LEGACY — superseded by Execution Kernel. Paper order ticket / simulated execution / paper account state. Retained for historical readability. New callers use `/execution/*` with SimulatedBrokerAdapter. | `system-map.md` | `statecore/paper_order_tickets.py`, `statecore/paper_executions.py`, `statecore/paper_accounts.py`, `api/routes_paper_validation.py` | Marked legacy + deprecated in OpenAPI; X-FinHarness-Legacy-Surface header | paper validation API tests |
| Execution Kernel | CANONICAL. OrderDraft → PreTradeCheck → ApprovalRecord → ExecutionOrder → SimulatedBrokerAdapter → ExecutionReport → PositionDelta → ReconciliationReport. Full lifecycle on simulated substrate, 9 receipt kinds, 8 API routes. | `system-map.md`, `closure-report.md` | `execution/services.py`, `execution/broker.py`, `execution/commands.py`, `execution/capabilities.py`, `api/routes_execution.py` | Execution-first architecture; simulated-only adapter boundary; service-enforced immutable ExecutionCapabilities | execution services / routes / lifecycle / adapter boundary / capability-enforcement tests |
| Research Evidence | 只读历史/描述性证据,作为 candidate evidence,不生成行动。 | `docs/research/README.md`, `reference/interfaces.md` | `research_evidence.py`, `research_assets.py`, `research_enrichment.py` | vectorbt/Riskfolio/QuantStats 等成熟 wheel 走 adapter | `GOV-RESEARCH-*`, `task hardening:redteam` |
| External Data / Mature Wheels | yfinance/OpenBB/ccxt/TA-Lib/Pandera/Riskfolio 等外部能力只做证据或计算适配。 | `mature-wheel-control-plane.md`, `docs/wheels.md` | `data_entry.py`, `market_data.py`, `providers/`, `portfolio_risk.py`, `data_quality.py` | adopt-not-invent;成熟件负责重活,FinHarness 负责边界和 receipt | adapter tests, `task wheels:check` |
| Agent Operating Surface (current AUT0/AUT1) | Agent 通过 context packs、capability profiles、`AgentToolEntry`、evidence registry、context policy 和 runtime pipeline 选择工具；当前 write profiles 只创建 governed review artifacts。 | `system-map.md`, `reference/interfaces.md` | `agent_context.py`, `agent_context_projection.py`, `agent_capabilities.py`, `agent_evidence.py`, `agent_tools.py`, `agent_runtime.py`, `proposal_queue_checks.py`, `review_read.py` | 当前权限是迁移起点；长期由 mandate + Harness gate 扩张，不靠 prompt 或 profile 自证。 | agent capability/context/evidence/runtime/tool tests |
| Agent Autonomy Control Plane (current AUT2 foundation) | 把 Agent action 按 W0-W4/AUT0-AUT6、Harness runtime ceiling、mandate、scope、expiry 和 kill switch 判为 effective/candidate/escalate/blocked。 | `docs/modules/agent-autonomy-control.md`, `system-map.md`, `finharness-evolution-roadmap.md` | `autonomy_control.py`, `agent_autonomy_adapter.py`, `agent_work_loop.py` | 已接入 work-loop dispatch 并进入 terminal chain；仍只产生 non-executing evidence，不接 effect commands，不推导 AUT3+。 | autonomy control + StateCore adapter + reducer tests |
| Agent Harness / Autonomy | Agent Operating Cycle v0.1：typed arguments、observation-driven decision、独立 budgets、playbook preflight、dispatch admission、terminal receipts/results/search/workspace 与全部 stop reducers 已接通。15-contract gate 是 AUT2 地基，不是 Agent 产品终点。 | `agent-work-loop-plan.md`, `finharness-evolution-roadmap.md` | `agent_work_loop.py` | 下一阶梯是带 W1/W2 前置的 AUT3 delegated review；AUT4+ 不由 AUT2 自动推导。 | `task agent:work-loop-acceptance` (15/15) |
| Cockpit / API | 本地产品表面:读、比较、复核、拒绝、确认、归档。 | `system-map.md`, `reference/interfaces.md` | `api/app.py`, `api/routes_*.py`, `frontend/` | Thin adapter + view contract;暂不引入重前端框架 | `task test:frontend`, route tests |
| EOS Governance / Quality | change control、policy registry、docs-current、security、release、repo intelligence。 | `documentation-fact-governance.md`, `scaffolding-inventory.md`, `docs/engineering/*` | `tests/_policy_registry.py`, `hardening.py`, `repo_intelligence.py`, governance graphs | Python registry now;OPA/Conftest/Backstage/Temporal 只在痛点足够时引入 | `task governance:check`, `task check` |
| Security / Supply Chain | threat model、SSDF map、CODEOWNERS、fuzz、SBOM/provenance baseline。 | `docs/security/*` | `.github/`, `hardening.py`, `data/security/` | OpenSSF Scorecard, CodeQL, Gitleaks, Trivy, SBOM/SLSA posture | `task security:fuzz`, `task security:scan` |
| Archived Live-Trading Legacy | 历史 OKX/Alpaca/trading guard 代码,不属于 current runtime。 | `experiments/archive/live_trading_legacy/README.md`, `capital-os-layering.md` | `experiments/archive/live_trading_legacy/` | 若未来需要,重建为单独 gated capability,不继承主线 | `GOV-DOCS-002`, security docs test |

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
