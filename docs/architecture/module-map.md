# FinHarness 模块表(基础设施分层 × 实际模块)

> 用途:把"后端 12 层 + 前端 15 层"两套通用工程分层,映射到 FinHarness **当前
> 真实存在的模块/文件**,作为一张需要长期维护的活地图。
> 单一事实源,方向以 [docs/product-north-star.md](../product-north-star.md) 为准
> (产品 B0;治理/receipt/lesson 是刹车与证据层,不是产品本身)。

校对基准:`feat/four-loops-llm-integration` @ 2026-06-18(每次大改后更新本行)。

## 状态标记与缺口约定

```text
✅ 成熟      已建且被测试/治理覆盖
🟡 半截      已建一部分,或形状对但很薄
⬜ 未建      还没有实现
⛔ 有意不做   设计上明确不做(标注原因)
```

缺口列引用 [gap register](industry-benchmark/03-gap-register-codex.md) 的编号与
band(Now / Next / Later)。**新增能力前先查 band 与 doctrine:不为语言纯度重构、
不扩张治理面(G15),产品价值优先于治理成熟度。**

> 注意:本表的"层"是**横向基础设施栈**。仓库里另有一套**纵向 domain 十层**
> (market-data → … → post-trade,见 [docs/modules/](../modules/) 与
> [ten-layer-langgraph-map](ten-layer-langgraph-map.md))。两者并存:domain 十层
> 大多落在本表的 L2/L3。

---

## 后端 12 层

| 层 | 名称 | 状态 | 当前模块 / 文件 | 缺口与计划锚点 |
| --- | --- | --- | --- | --- |
| 1 | API / Transport | 🟡 | `api/app.py` `api/routes_state.py`(只读 GET state/positions/snapshots/diff/receipts)`api/routes_proposals.py`(POST proposals/attest)、`okx_cli.py`、Taskfile CLI、各 `*_graph` 脚本 | 薄但形状对(只读优先 + propose 需人工背书)。G10 读-only OpenAPI 契约 `Next`,扩面**需 operator 批准**;无 WebSocket |
| 2 | Application Service | ✅ | `*_graph.py`(market_data/indicator/events/interpretation/hypotheses/proposal/risk_gate/execution/post_trade/daily_evidence…)、`ten_layer_graph.py`、`statecore/proposals.py` | 编排成熟(LangGraph) |
| 3 | Domain Core | ✅ | `risk_gate/` `validation/` `authorization.py` `market_access_ledger.py` `effective_rules.py` `effective_ceilings.py` `restricted_symbols.py` `control_owner.py` `okx_live_gate.py` `post_trade/` | 当前最强;大文件已按职责包化并经 `__init__` 再导出 |
| 4 | Persistence | 🟡 | `statecore/store.py`(SQLite + SQLAlchemy,WAL/外键/完整性检查)、`statecore/models.py`(带 `schema_version`)、`data/receipts/**` 文件回执、`data/state/**` | 迁移:`schema_version` 守 + Alembic 缓办、多用户再上 Postgres(见 state-core 提案);备份 root 已在 config |
| 5 | Integration | 🟡 | `providers/`、`alpaca_client.py`、`okx_*.py`、`hermes_bridge.py`(LLM 生成位)、`market_data.py`(yfinance/ccxt) | paper / read-mostly;execution 默认 paper 适配器 |
| 6 | Background Job / Runtime | 🟡 | `market_cockpit.py` `daily_change_brief.py`(确定性 daily change-brief 循环)、`daily_evidence_graph` 递归、`trading_state_store.py`(Loop 3 反馈边) | 调度部分在**仓库外**(hermes cron `30 7 * * 2-6`);缺仓库内 scheduler/daemon。见 daily-change-brief-runtime-loop 提案 |
| 7 | Event / Messaging | ⛔ | 黑板模式:循环间经 `data/` 下 receipt/snapshot 通信(非 agent 互聊)。`events.py` 是 **domain 事件**(SEC-EDGAR),非消息总线 | 有意不做消息总线(loop topology doc);单用户本地用黑板足够 |
| 8 | Auth / Permission | 🟡 | `authorization.py`(typed `AuthorizedOperator/Account/Registry/Decision`,fail-closed,**无凭证落地**)、`control_owner.py` | 运行时授权模型有(G07);**无** web 登录/session/oauth(单用户本地,暂不需要) |
| 9 | Security / Governance | ✅ | `hardening.py`(pip-audit/gitleaks/trivy 门)、`rule_change_ledger.py`(B4 血缘)、`market_access_ledger.py`、`effective_ceilings.py`、受控词表 + `vocab_lint`、redteam、SBOM、threat model | 最成熟;G15 封顶:不再扩张治理面 |
| 10 | Observability | 🟡 | `runtime_log.py`(JSON 日志,`log_json` 配置)、receipt 作为不可变证据、`governance_dashboard.py` | **缺** `/health`、OTel trace/metrics、DORA 趋势。G12 OTel trace ID `Later` |
| 11 | Config / Secrets | ✅ | `config.py`(pydantic-settings,`FINHARNESS_` 前缀;broker 密钥走 **OS keyring**,不落文件) | 无 feature-flag 系统(影响小) |
| 12 | Testing / Tooling / DevOps | ✅ | 66 个 unittest、`Taskfile.yml`(lint/test/typecheck/check/security…)、CI `.github/workflows/`(security 跑 `task check`=ruff 广规则集 + mypy + 测试 + rules audit + eval smoke)、ruff、mypy、hardening gate、`task rules:audit` 已接入 `check` | CI **已跑**全套测试 + ruff;本地 `task check` 现在也覆盖渐进类型检查 |

---

## 前端 15 层

> 现状:**几乎全部未建**。无 React/Vue/Svelte 应用、无 vite/next 配置;根
> `package.json` 仅为 promptfoo 工具链。但 API(L1)与 view-model 雏形已就位,
> 是未来前端的数据来源。北极星硬约束:**驾驶舱 = 状态核心上的视图,不是 6 个独立
> 产品;前端只能展示与复核边界,不能放松后端边界。**

| 层 | 名称 | 状态 | 现有支撑 / 说明 | 下一步锚点 |
| --- | --- | --- | --- | --- |
| 1 | Product / UX | 🟡 | [product-north-star.md](../product-north-star.md) 已定义首屏:我现在怎么样 / 发生了什么 / 该注意什么 / 有哪些可审查选项 / 什么不能做 | 方向已定,无实现 |
| 2 | Routing | ⬜ | — | 路线图阶段 2-4 |
| 3 | Page | ⬜ | 最接近的是 `data/operations/market-cockpit-latest.md`(文本简报,非网页) | Dashboard / Receipts / Proposals |
| 4 | Component | ⬜ | — | Card / Table / Chart / Modal |
| 5 | State | ⬜ | — | 选中/筛选/复核状态 |
| 6 | Data Fetching | 🟡 | 后端只读 API 可供拉取(`api/routes_state`);无前端 fetcher | 接 G10 read-only API |
| 7 | View Model | 🟡 | `daily_change_brief.py` / `market_cockpit.py` / `statecore/diff.py` 已在**服务端**把状态整理成简报/差异(view-model 雏形) | 前端复用其形状 |
| 8 | Design System / Styling | ⬜ | — | — |
| 9 | Interaction | ⬜ | — | 复核/确认/拒绝/归档(非"一键执行") |
| 10 | Validation / Form | 🟡 | 后端 `routes_proposals.py` + pydantic 已校验;无前端表单 | 高风险动作需人工确认 |
| 11 | Auth / Permission UI | 🟡 | 后端授权模型在(`authorization.py`);授权级别 `read_only / needs_human_confirm / never_auto` 可驱动按钮可见性 | 无 UI |
| 12 | Error / Empty / Loading | ⬜ | — | — |
| 13 | Observability / Analytics(前端) | ⬜ | — | — |
| 14 | Testing(前端) | ⬜ | 仅后端测试 | 组件/E2E |
| 15 | Build / Deployment | ⬜ | 根 `package.json`+pnpm 仅 promptfoo;无前端打包 | 选型(阶段 4)|

---

---

## 代码模块明细(逐文件,源自 AST + docstring,校对 2026-06-18)

> 行数=物理行;测试 ✓=有直测、~=被包级/横切测试覆盖、—=未找到测试。
> 职责取自模块 docstring(代码自述)。前端无代码模块,故本节只覆盖后端层。

### L1 API / Transport(接请求的表面)

| 文件 | 行 | 测试 | 职责 |
| --- | --: | :-: | --- |
| `api/app.py` | 65 | ~ | FastAPI 应用,只读 state 表面 |
| `api/routes_state.py` | 111 | ~ | 只读 state 路由(accounts/positions/snapshots/diff/receipts) |
| `api/routes_proposals.py` | 130 | ~ | 治理化 proposal + 人工背书路由 |
| `api/dependencies.py` | 37 | — | 共享 FastAPI 依赖 |
| `okx_cli.py` | 212 | ✓ | OKX CLI 适配器,显式 read/write 安全门 |
| `workflow.py` | 160 | — | 给 CLI/agent 复用的金融工作流入口 |
| `agent_tools.py` | 138 | ✓ | OpenAI Agents SDK 工具表面 |

### L2 Application Service(编排一次动作 / 图)

| 文件 | 行 | 测试 | 职责 |
| --- | --: | :-: | --- |
| `ten_layer_graph.py` | 633 | ✓ | 顶层 LangGraph,串十个 domain 层 |
| `cognitive_graph.py` | 480 | ✓ | 认知工程工作流 |
| `market_data_graph.py` | 271 | ✓ | 第一层 market data 图 |
| `indicator_graph.py` | 246 | ✓ | 第二层 indicator 图 |
| `events_graph.py` | 239 | ✓ | 第三层 SEC EDGAR 事件图 |
| `interpretation_graph.py` | 262 | ✓ | 第四层 来源支撑的解读图 |
| `hypotheses_graph.py` | 303 | ✓ | 第五层 可证伪假说图 |
| `validation_graph.py` | 347 | ✓ | 第六层 validation 图 |
| `proposal_graph.py` | 330 | ✓ | 第七层 结构化 proposal 图 |
| `risk_gate_graph.py` | 533 | ✓ | 第八层 独立风控门图(含人工 interrupt) |
| `execution_graph.py` | 405 | ✓ | 第九层 paper 执行生命周期图 |
| `post_trade_graph.py` | 358 | ✓ | 第十层 后交易对账图 |
| `daily_evidence_graph.py` | 424 | ✓ | 打包前四层证据(Loop 1 递归种子) |
| `daily_evidence.py` | 245 | — | 每日证据 bundle 治理 |
| `engineering_delivery_graph.py` | 624 | ✓ | 工程交付治理图 |
| `quality_governance_graph.py` | 288 | ✓ | 质量治理图 |
| `repo_intelligence_graph.py` | 169 | ✓ | 仓库情报图 |
| `release_preflight_graph.py` | 157 | ✓ | 发布预检图 |
| `governance_dashboard_graph.py` | 63 | ✓ | 治理仪表盘图包装 |
| `statecore/proposals.py` | 256 | ~ | API 与运行时共用的治理化 proposal 写入 |

### L3 Domain Core(真正的业务规则)

**domain 十层管线(纵向):**

| 文件 | 行 | 测试 | 职责 |
| --- | --: | :-: | --- |
| `market_data.py` | 615 | ✓ | 一层:围绕成熟金融轮子的薄 market-data 治理 |
| `indicator_layer.py` | 449 | ✓ | 二层:指标治理 |
| `events.py` | 593 | ✓ | 三层:官方市场敏感信息事件治理 |
| `interpretation.py` | 593 | ✓ | 四层:来源支撑的解读治理 |
| `hypotheses/` | 1033 | ✓ | 五层:可证伪假说治理包(models/providers/formulation/quality/bundle;公开 API 由 `__init__` 再导出) |
| `validation/` | 1894 | ✓ | 六层:validation 治理包(models/providers/backtest/checks/bundle;公开 API 由 `__init__` 再导出) |
| `validation_metrics.py` | 86 | ✓ | 六层:确定性 disconfirming 检查(只能削弱假说) |
| `proposal/` | 935 | ✓ | 七层:结构化 proposal 治理包(models/providers/formulation/quality/bundle;公开 API 由 `__init__` 再导出) |
| `risk_gate/` | 1180 | ✓ | 八层:独立风控门治理包(models/context/controls/decisions/bundle;公开 API 由 `__init__` 再导出) |
| `execution/` | 1346 | ✓ | 九层:paper 执行生命周期治理包(models/planning/controls/adapters/bundle;公开 API 由 `__init__` 再导出) |
| `post_trade/` | 1107 | ✓ | 十层:后交易对账与复盘治理包(models/reconciliation/costs/exceptions/bundle;公开 API 由 `__init__` 再导出) |

**domain 控制(风控/限额/授权/状态):**

| 文件 | 行 | 测试 | 职责 |
| --- | --: | :-: | --- |
| `okx_live_gate.py` | 502 | ✓ | 每个 OKX live mutation 必过的 fail-closed 门 |
| `market_access_ledger.py` | 337 | ✓ | 共享聚合市场准入限额账本(G06) |
| `effective_ceilings.py` | 329 | ✓ | 人类拥有的风险上限解析(G09) |
| `effective_rules.py` | 76 | ✓ | B4 执行:从规则账本解析有效 guard 阈值 |
| `restricted_symbols.py` | 296 | ✓ | 带版本的受限标的检查(G08) |
| `authorization.py` | 300 | ✓ | typed operator/account 授权注册表(G07,无凭证) |
| `trading_guard.py` | 126 | ✓ | 交易行为护栏 |
| `okx_policy.py` | 163 | — | OKX CLI venue 适配器白名单策略 |

**domain 数学/研究:**

| 文件 | 行 | 测试 | 职责 |
| --- | --: | :-: | --- |
| `research_assets.py` | 296 | ✓ | 研究资产库契约 |
| `research_rigor.py` | 221 | ✓ | rung 受限 validation 证据原语 |
| `metrics.py` | 89 | ✓ | 风险-收益指标稳定接口 |
| `data_quality.py` | 97 | ✓ | Pandera 支撑的 OHLCV 数据质量契约 |
| `indicators/smc.py` | 116 | ~ | SMC 指标 |
| `indicators/squeeze.py` | 78 | ~ | squeeze 指标 |
| `indicators/macd.py` | 60 | ~ | MACD 指标 |
| `indicators/shared.py` | 48 | ~ | 指标共用工具 |

### L4 Persistence(持久化)

| 文件 | 行 | 测试 | 职责 |
| --- | --: | :-: | --- |
| `statecore/snapshot_ingest.py` | 275 | ✓ | broker-read 证据的组合快照摄入 |
| `statecore/observations.py` | 273 | ~ | 确定性组合变化观测 |
| `statecore/diff.py` | 191 | ✓ | 只读组合快照差异 |
| `statecore/receipt_index.py` | 177 | ~ | 只读 receipt 文件索引 |
| `statecore/store.py` | 175 | ✓ | SQLite store(WAL/外键/完整性检查) |
| `statecore/models.py` | 138 | ~ | SQLModel 表(带 schema_version) |
| `statecore/receipt_io.py` | 79 | ~ | 持久化本地 receipt 文件助手 |
| `statecore/snapshots.py` | 38 | ~ | 只读组合快照查询 |
| `trading_state_store.py` | 256 | ✓ | 跨风控运行共享的持久化交易状态(Loop 3 反馈边) |

### L5 Integration(外部适配器)

| 文件 | 行 | 测试 | 职责 |
| --- | --: | :-: | --- |
| `vectorbt_runner.py` | 280 | ✓ | vectorbt 研究适配器(快速策略筛选) |
| `data_entry.py` | 187 | ✓ | 建在社区轮子之上的数据录入层 |
| `alpaca_client.py` | 131 | ✓ | Alpaca paper API 小客户端 |
| `portfolio_risk.py` | 129 | ✓ | Riskfolio-Lib 组合风险研究适配器 |
| `hermes_bridge.py` | 80 | ✓ | 通往本地 hermes-agent CLI 的窄子进程桥(LLM 生成位) |
| `backtrader_runner.py` | 48 | — | Backtrader 集成 |
| `okx_redaction.py` | 47 | — | OKX CLI 输出/错误脱敏 |
| `providers/ccxt_provider.py` | 43 | ✓ | 可选 CCXT 源适配器 |
| `okx_symbols.py` | 23 | — | OKX 符号规范化 |

### L6 Background / Runtime(运行时循环)

| 文件 | 行 | 测试 | 职责 |
| --- | --: | :-: | --- |
| `market_cockpit.py` | 458 | ✓ | 市场驾驶舱:watchlist 证据一屏可见 |
| `daily_change_brief.py` | 323 | ✓ | 确定性每日组合变化简报运行时循环 |

> 递归调度在仓库外(hermes cron);`daily_evidence_graph`(L2)是 Loop 1 的递归种子。

### L9 Security / Governance(安全与治理)

| 文件 | 行 | 测试 | 职责 |
| --- | --: | :-: | --- |
| `repo_intelligence.py` | 438 | ✓ | 本地仓库情报助手 |
| `hardening.py` | 420 | ✓ | 发布验证 hardening 门(pip-audit/gitleaks/trivy) |
| `lesson_loop.py` | 392 | ✓ | Loop 4 v0:从 receipt 起草 lesson 候选 |
| `receipt_usage_audit.py` | 303 | ✓ | receipt 使用审计 |
| `governance_dashboard.py` | 250 | ✓ | 治理仪表盘聚合(亦含 L10 性质) |
| `project_governance_adapter.py` | 229 | ✓ | 工作站项目治理回路 receipt 兼容适配器 |
| `rule_change_ledger.py` | 205 | ✓ | B4:lesson→规则变更血缘 |
| `control_owner.py` | 192 | ✓ | 安全刹车的 control-owner 认证 receipt(G05) |

### L10 Observability / L11 Config / L12 Tooling

| 文件 | 行 | 测试 | 职责 / 说明 |
| --- | --: | :-: | --- |
| `runtime_log.py` | 38 | — | L10:structlog 设置(缺 /health、OTel) |
| `config.py` | 46 | — | L11:pydantic-settings + OS keyring(密钥不落文件) |
| `tests/`(66 文件)+`Taskfile.yml`+`.github/workflows/` | — | ✓ | L12:`task check`(ruff 广规则集 + mypy 渐进类型检查 + 测试 + rules:audit + experiments + eval smoke)、security/fuzz/scorecard CI |

### 横切测试(不绑单一模块)

```text
test_property_baseline / test_security_fuzz / test_security_sbom /
test_security_maturity_docs / test_hardening_gate / test_vocab_lint /
test_trading_validation_report / test_research_asset_handoff /
test_risk_gate_interrupt / test_statecore_{support,vertical_reconstruction}
```

---

## 维护协议(这张表怎么活下去)

```text
何时更新:
- 新增/删除/重命名 src/finharness 下模块,或新增 API 路由 → 改对应行的"模块/文件"。
- 某层状态变化(⬜→🟡→✅,或确定⛔)→ 改"状态"并在 commit 里说明依据。
- 新增/改动 .github/workflows 或 Taskfile 的门 → 改 L12。
- gap register 的 band/编号变化 → 同步"缺口"列。

怎么改:
- 状态升级必须有证据(测试/CI 输出/receipt),不凭印象——见
  docs/lessons/2026-06-18-stale-doc-as-current-guide.md。
- 加能力前过两条校验线(授权 / 可逆)与 doctrine(产品价值优先、不扩张治理面)。
- 本表只记"是什么、在哪、缺什么",不记排期;排期看路线图与 gap register band。
```

## 链接

```text
docs/product-north-star.md                          产品方向单一事实源
docs/architecture/industry-benchmark/03-gap-register-codex.md   缺口与 band
docs/architecture/ten-layer-langgraph-map.md        纵向 domain 十层
docs/modules/                                        各 domain 模块 spec
docs/proposals/2026-06-17-state-core-and-api.md      L1/L4 设计
docs/proposals/2026-06-17-daily-change-brief-runtime-loop.md   L6 设计
```
