# FinHarness Framework Index

状态:current(2026-06-30)。这是 FinHarness 的“不要每次重新理解一遍”索引。

本页只回答四件事:

1. FinHarness 到底是什么框架;
2. 每个部分的核心职责是什么;
3. 当前入口和机器检查在哪里;
4. 我们借鉴哪些成熟方案,哪些暂时不上。

更细的文件事实看 [Module Map](module-map.md);系统边界看
[System Map](system-map.md);分层演进看 [Capital OS Layering](capital-os-layering.md)。
机器可读目录看 [System Catalog](system-catalog.yml);工程推进风险看
[Engineering Leverage Map](engineering-leverage-map.md)。Agent L5 参考模式看
[Agent Runtime Reference](agent-runtime-reference/README.md)。

## One Sentence

FinHarness 是一个 local-first **personal capital governance framework**:
把个人资本状态、IPS、证据、proposal/review、Agent explanation、receipt、governance
checks 组织成可审计闭环。它不是 trading bot、stock picker、robo-advisor 或执行授权系统。

## Framework Shape

```text
personal data -> state core -> capital map -> IPS/policy
-> governed proposal -> human review -> receipt/lesson
-> Agent explanation + cockpit

EOS governance cuts across the whole loop.
External/mature wheels are adapters, not authority.
Archived live-trading code has no edge back into mainline.
```

## System Summary

| Part | Core summary | Primary docs | Runtime roots | Mature pattern / tool posture | Check / receipt |
| --- | --- | --- | --- | --- | --- |
| Product North Star | 产品类别和 non-claims:个人资本判断层,不是交易系统。 | `docs/product-north-star.md`, `docs/product/*` | README, cockpit copy | Diataxis + product north-star discipline | `task docs:current-check` |
| State Core | receipt-backed 状态镜像;SQLite 可查,receipt 是证据根。 | `system-map.md`, `module-map.md`, `reference/interfaces.md` | `statecore/`, `api/routes_state.py` | Event/receipt sourcing ideas,但保留本地简洁实现 | `task test`, StateCore tests |
| Capital Map | 把状态变成 exposure、daily brief、dashboard summary。 | `system-map.md`, `tutorials/golden-path.md` | `exposure.py`, `daily_brief.py`, `daily_change_brief.py` | 财务报表/BI read-model 思路;不替代 ledger | `task brief:daily`, `task decisions:scan` |
| IPS / Policy | 用户自己的投资政策声明和描述性 compliance check。 | `capital-os-layering.md`, `system-map.md` | `ips.py`, `api/routes_ips.py` | IPS / policy-as-code 思路;暂不上 OPA/Cedar | `GOV-DOCS-003`, IPS tests |
| Decision Workflow | exposure + IPS 阈值生成 governed proposal,默认不执行。 | `system-map.md`, `tutorials/golden-path.md` | `allocation.py`, `statecore/decision_scaffold.py`, `risk_classification.py` | RFC/decision record 风格;人类 review 是 authority | `task decisions:scan`, proposal tests |
| Review System | append-only proposal review、scaffold revision、attestation、compare、annual review、lesson-to-rule、deterministic review queue triage、derived risk register v0。 | `system-map.md`, `engineering/system-directory-standard.md` | `statecore/proposals.py`, `review_read.py`, `risk_register.py`, `lesson_loop.py` | GitLab review discipline + risk/issue register;不把 attestation、queue priority 或 risk severity hint 当 execution | `GOV-REVIEW-001`, review/risk tests |
| Research Evidence | 只读历史/描述性证据,作为 candidate evidence,不生成行动。 | `docs/research/README.md`, `reference/interfaces.md` | `research_evidence.py`, `research_assets.py`, `research_enrichment.py` | vectorbt/Riskfolio/QuantStats 等成熟 wheel 走 adapter | `GOV-RESEARCH-*`, `task hardening:redteam` |
| External Data / Mature Wheels | yfinance/OpenBB/ccxt/TA-Lib/Pandera/Riskfolio 等外部能力只做证据或计算适配。 | `mature-wheel-control-plane.md`, `docs/wheels.md` | `data_entry.py`, `market_data.py`, `providers/`, `portfolio_risk.py`, `data_quality.py` | adopt-not-invent;成熟件负责重活,FinHarness 负责边界和 receipt | adapter tests, `task wheels:check` |
| Agent Explanation | Agent 通过 context packs、capability profiles、`AgentToolEntry`、evidence provider registry、context projection policy 和 runtime pipeline 选择 actual tools;runtime 暴露 visible/hidden/unavailable tools、structured result/error/evidence envelope、profile-aware context budget、result budget;default profile 是 read/explain baseline,review-draft 可创建 append-only governed proposal draft,review-note 可创建 append-only `AgentReviewNoteDraft`,这些 artifacts 进入 deterministic review queue triage,不靠 prompt 承诺升级权限。 | `system-map.md`, `reference/interfaces.md` | `agent_context.py`, `agent_context_projection.py`, `agent_capabilities.py`, `agent_evidence.py`, `agent_tools.py`, `agent_runtime.py`, `proposal_queue_checks.py`, `review_read.py`, `hermes_bridge.py` | Hermes-style spec/availability/dispatch/context budget/profile/toolset/provider registry 思路;每个 Agent 能力必须带 typed governance artifact / review carrier;draft proposal 和 review note 都是 review objects,不是 approval | agent proposal/review-note/capability/context/projection/evidence/runtime/tool tests, future evals |
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
