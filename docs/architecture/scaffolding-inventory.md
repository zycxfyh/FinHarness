# Scaffolding Inventory

状态:v0(2026-06-23)。目的:把自建脚手架从"一堆聪明补丁"理成几个稳定系统——给每项标
**keep / standardize / replace / delete**,并对照成熟件。配合 [system-map](./system-map.md) +
[architecture-principles](../engineering/architecture-principles.md)(G5)。

判断三档(承 Program Lead):
- **领域治理核心**(Proposal/Receipt/ReviewEvent/Evidence/source_refs/execution_allowed)= 护城河 → **keep**。
- **工程流程**(EOS / mini-RFC / gates)= 不直接替代,但**standardize** 成 repo-native 平台。
- **通用平台**(policy / data-quality / workflow / observability / catalog)= **逐步借成熟件**,不长期手搓。
- 原则:**最危险的不是手搓,是每次搓一个新形状**。

## 1. 领域治理核心 — keep(护城河)
| 资产 | 文件 | 判断 |
| --- | --- | --- |
| Proposal / Attestation / ReviewEvent / Receipt 链 | `statecore/{models,proposals,proposal_revisions,receipt_io,store}.py` | **keep** |
| Research evidence 契约 + redline | `research_evidence.py`、`redlines.py`、`research_*` | **keep** |
| Review System read model | `review_read.py` | **keep**(已是 G5 标准雏形) |
| Decision/exposure 候选 | `allocation.py`、`exposure.py` | **keep** |

## 2. 工程流程(EOS)— standardize(repo-native 平台)
| 资产 | 现状 | 判断 |
| --- | --- | --- |
| Change Class / mini-RFC / gate-checklists / postmortem / G5 | `docs/engineering/*`、`docs/templates/mini-rfc.md` | **keep + standardize**(已是平台;借 Backstage 的 metadata 思想,给每 system 加 `catalog-info`-style 元数据,**暂不上 Backstage**) |
| `governance:check` 探针(6 类) | `tests/test_governance_invariants.py`(ImportBoundary / ReviewReadOnly / RedlinePolicyCoverage / AttachmentRedline / NetworkSmokeExclusion / NoPydanticLeak) | **standardize → policy registry**:每条规则给 id/owner/scope/source/test;**先用 Python,不急 OPA/Conftest** |
| 测试脚手架(临时库 + init_state_core + helper) | `tests/_review_fixtures.py` + 各 `TemporaryDirectory` 重复 | **standardize**:优先把 State Core / Review System 的 fixture 收进 shared 层;**中期渐进迁 pytest fixtures**,不一次搬完 |

## 3. 系统目录标准(新代码按此长,不强制一次搬)
每个 system 固定形状:`domain` / `commands` / `read_model` / `adapters` / `fixtures` / `governance`。
Review System 已接近(`proposals.py`=domain+commands、`review_read.py`=read_model、`routes_*`=adapters、
`_review_fixtures.py`=fixtures、governance probe=governance)。**作为模板,其它 system 渐进对齐。**

## 4. scripts/run_*(~40)— 分组判断
不逐条搬;按归属 system 分组,**delete 仅限确证死代码**(需 receipt-usage-audit 佐证)。
| 组 | 脚本 | 判断 |
| --- | --- | --- |
| Review/Decision 产品流 | `record_decisions`、`record_annual_review`、`record_daily_brief`、`run_daily_change_brief`、`run_research_smoke` | **keep**(产品/治理入口) |
| State/数据导入 | `import_beancount_ledger`、`import_personal_finance_export`、`backup` | **keep** |
| 十层/图工作流(headless) | `run_*_graph`(market_data/post_trade/execution/risk_gate/ten_layer/proposal/indicator/...) | **keep headless**;**standardize**:这些图胶水是"每个一套形状"的重灾区,长期评估统一 orchestration(**若出现定时/异步/长流程/重试再看 Temporal,现在不上**) |
| 指标 snapshots | `run_{macd,smc,squeeze,indicator,event}_snapshot` | **keep**(headless 指标),但**candidate for standardize**(同形状重复) |
| 治理/质量 | `run_governance_dashboard`、`run_quality_governance_graph`、`run_control_certification`、`run_hardening_gate`、`run_receipt_usage_audit`、`run_repo_intelligence_graph` | **keep**(EOS/质量),归 EOS 平台 |
| OKX/trading headless | `run_okx_read`、`run_trading_guard`、`run_execution_graph` | **keep headless**(C3 边界) |

> 待办:用 `run_receipt_usage_audit` 输出标出**真死代码**再 `delete`;本表先不删任何脚本。

## 5. 通用平台 — 逐步借成熟件(方向,非现在做)
| 能力 | 现状(手搓) | 成熟件 | 时机 |
| --- | --- | --- | --- |
| policy-as-code | governance:check Python 探针 | OPA / Conftest | 中期(规则多到 Python 难管时) |
| catalog / ownership | `system-map.md` | Backstage(借结构,不上) | 多 repo/多人协作时 |
| durable workflow | receipt/event 链(审计,非 runtime) | Temporal | 出现定时/异步/长审批/重试补偿时 |
| observability | receipts + structlog + task output | OpenTelemetry(D7) | 近中期:**只接 traces → receipt/task/request**,不做大而全 |
| supply-chain | Scorecard/Trivy/Gitleaks/CodeQL(已用) | + SBOM / SLSA provenance / 依赖升级治理 | 接 security-debt track |
| test fixtures | unittest + helper | pytest fixtures | 中期渐进 |

## 6. 建议下一步(Program Lead 的 6 步映射)
1. 本 inventory(✅ 本文件)。
2. 系统目录标准(§3)——**新代码按此长**,Review System 作模板。
3. governance:check → policy registry(§2)——给规则加 id/owner/scope。
4. 测试 fixture 标准化(§2)——先 State Core / Review System。
5. D7 OpenTelemetry——只接 traces→receipt/task/request。
6. **暂不上** Backstage/Temporal——先借结构思想。

> 与在飞工作的关系:R4(Candidate Compare)正在 Review System 内收尾(R4a 已交 impl gate),**正好是 §3 系统标准的活样板**;inventory 落地不打断 R4,二者互证。
