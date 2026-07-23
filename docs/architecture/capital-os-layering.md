# FinHarness 分层架构(Capital OS Layering)

> 状态:current(2026-07-10)。这是 FinHarness **产品分层的事实源**;
> system lifecycle/status 的 machine-readable 事实源是
> [System Catalog](system-catalog.yml)。本文
> 取代早期十层交易链设计；历史版本由 Git history 保存，不留在当前工作树。
> 产品方向仍以 [产品北极星](../product-north-star.md) 为准;本文是北极星
> "状态 → 解释 → 方案 → 决策 → 行动 → 复盘 → 学习" 闭环的**工程落层**。
> 金融行业词与 FinHarness 原语的对应关系见
> [Financial Terminology Map](../reference/financial-terminology-map.md);
> 该映射是 design analogy,不是 regulatory status claim。
>
> modular monolith,不是微服务。新功能**先选归属层**(见 [system-map](system-map.md) 的 deep modules),再实现。

## Canonical plane model

L0-L8 是产品与实现展示，不再承担规范性 ownership。规范词表由
[Plane Model ADR](../adr/2026-07-16-finharness-plane-model-and-dependency-direction.md)
和现有 `config/architecture-layers.yml` 共同定义：**Truth、Knowledge、
Control、Judgment、Agent、Action/Learning、Product**，以及横向
**Assurance**。当前模块可以跨多个关注点，但每个对象和 backlog 变更只有一个
primary plane；Python import layers 仍独立描述当前代码事实。

依赖只消费较低层的 admitted output。Action/Learning 产生的 observation、
reconciliation 或 LessonCandidate 若要回到 Knowledge、Truth 或 Control，必须重新
通过对应 admission，而不是形成反向写入。Assurance 提供事务、恢复、索引、CI 和
proof，不是第八个产品步骤。

## 为什么换图

旧的 "十层 LangGraph 链"(market data → indicators → events → interpretation →
hypotheses → validation → proposal → risk-gate → execution → post-trade)把**交易信号管线**
当成系统主干。这与北极星明确冲突:北极星说"交易、投顾、行情、治理的能力都可以
**收编**,但谁都不是产品中心"。那套链的代码与文档已于 2026-06-26 整体归档/退役
(见本文末「已退役」),避免旧版与新版在未来错乱。

## 八层(L0–L8)

闭环:`导入 → 状态 → 政策 → 提案与审查 → Agent 解释 → 行动模拟 → 复盘学习 → 产品表面`。

| 层 | 名称 | 回答 | 当前代码 | 状态 |
| --- | --- | --- | --- | --- |
| **L0A** | 个人资本数据 Personal Capital Data | 我有什么? | `beancount_adapter.py`、`personal_finance.py`、`snapshot_ingest`、`data_entry.py` | ✅ 有 |
| **L0B** | 外部标的数据 External Instrument Data | 外部价格/财报/宏观是多少? | `data_entry.py`(yfinance)、`research_evidence.py` | 🟡 仅价格+证据;Instrument/财报/宏观分类待建 |
| **L1/L2** | StateCore / 资本地图 Capital Map | 我现在是什么状态? | `statecore/`、`exposure.py`、`/exposure`、`/dashboard/summary` | ✅ 有 |
| **L3** | IPS / Policy / Authority Credentials | 这个状态适合我吗?未来授权必须站在哪个政策域内?Agent 是否有受限 authority credential? | `ips.py`、`api/routes_ips.py`、`statecore/capital_mandates.py`、`api/routes_capital_mandates.py`、`statecore/agent_authority_grants.py`、`api/routes_agent_authority_grants.py`、`InvestmentPolicyStatement`、`CapitalMandate`、`AgentAuthorityGrant` | ✅ 有(IPS v0 + CapitalMandate v0 + AgentAuthorityGrant v0;CapitalMandate 是政策域,AgentAuthorityGrant 是 mandate-bound credential,两者都不授权执行) |
| **L4** | Proposal & Review 决策提案与审查 | 哪些事值得审查?如何留痕? | `allocation.py`、`statecore/proposals.py`、`decision_scaffold.py`、`risk_classification.py`、`routes_proposals.py`、`routes_review.py` | ✅ 有(candidate+proposal 合并为一层) |
| **L5** | Agent / 个人资本 Agent | 这些状态和提案是什么意思?下一步应观察什么? | `capital_agent.py`、`agent_context.py`、`agent_tools.py`、`agent_runtime.py`、`agent_work_loop.py` | ✅ bounded read/explain loop + explicit durable personal Mission/checkpoint/resume + simulated delegated Effect;无 scheduler/daemon/live effect |
| **L6** | Execution Kernel 执行内核 | 这个动作可以执行吗?执行后发生了什么? | `statecore/execution_models.py` (OrderDraft, PreTradeCheck, ApprovalRecord, ExecutionOrder, ExecutionReport, PositionDelta, ReconciliationReport, BrokerConnection, ExecutionAccount)、`execution/services.py`、`execution/receipts.py`、`execution/broker.py`、`execution/commands.py`、`execution/adapters/simulated_broker.py`、`api/routes_execution.py` | ✅ v0: full canonical execution lifecycle on simulated substrate; live-shaped model, live environment is legal, only SimulatedBrokerAdapter registered, no real external connectivity |

| **L7** | Learning 长期记忆与学习 | 我从过去学到什么? | `annual_review.py`、`lesson_loop.py`、`rule_change_ledger.py` | 🟡 有闭环;Journal/Pattern 待建 |
| **L8** | Cockpit / API 产品表面 | 用户怎么用这一切? | FastAPI(`api/app.py` + routers)、vanilla JS cockpit | ✅ 有 |

> L1 与 L2 在 system-map 里同属 **State Core** deep module(状态 + 资本地图),
> 故合并标注。

## 新版相对现状的增量

现状文档(north-star 06-17/06-24、system-map 06-22)已覆盖 L0A/L1/L2/L4/L8。
PR #51 已补上 L3 IPS v0;#91 补上 receipt-backed `CapitalMandate` v0,作为
未来 authority objects 之前的 human-attested policy domain,但它本身不授权执行、
不授予 Agent identity。#94 补上 receipt-backed `AgentAuthorityGrant` v0:它是
mandate-bound authority credential,创建时要求 active CapitalMandate,验证时动态
重查当前 grant 与 mandate 状态并返回闭集 deny reasons,但仍不批准 trade plan、
不绕过 preflight、不提交 broker、不授权 execution。下一版增量按优先级:

1. **L0B**:外部标的数据从"仅价格"扩成 Instrument / 财报 / 宏观分类。
2. **L5**:把 context packs 用在更好的 Agent 解释/eval 中;review-draft profile
   可写 append-only governed proposal draft,review-note profile 可写 append-only
   `AgentReviewNoteDraft` typed artifact,并在 proposal review surface/timeline 暴露
   Agent provenance;scaffold-candidate profile 可基于 active risk register item 创建
   append-only `AgentScaffoldRevisionApplyCandidate`,包含 patch/proposed scaffold/
   changed fields/preflight/rollback/human confirmation requirements,但不直接修改
   proposal;system preflight 会重算 readiness,preflight-bound human-confirmed
   apply path 可将 candidate patch 通过 proposal revision chain 写成真实 scaffold
   revision;带 blocked transition scope 的 queue checks 和 read-only
   review-task lifecycle;Agent tools 通过 ToolEntry metadata 暴露 capability、
   toolset、side-effect、availability 和 evidence provider ids;`agent_context_projection.py`
   为不同 profile 提供 office brief 和上下文预算,并通过 runtime pipeline 暴露
   resolved visibility、structured result/error/evidence envelope、context budget
   和 result budget。更强权限应通过 profile/tool/evidence/context/review contract
   毕业,不是靠 prompt 承诺。
3. **L6**:Execution Kernel v0 已建成；`capital_agent.py` 以 World digest、Delegation 和幂等 EffectIntent 绑定现有 simulated lifecycle，不提供 live broker 或 funded effect。
4. **Authority path**:当前最小 Delegation 只覆盖单 principal、单 Agent、串行 simulated order；未来扩展只由真实 dogfood 需求触发。

P5 follow-up 已有实现路径:高风险 proposal 若缺 `counter_evidence`,可以记录和拒绝;
若之后要批准,先通过 proposal scaffold revision 补 `counter_evidence`,再走 human
attestation。该 revision 是 review evidence,不是 execution authorization。

## 不变量(跨层)

- Execution Kernel (L6) 使用 live-shaped model, simulated substrate; `network_enabled=false`。
- StateCore 是 queryable state; receipt files 才是 source of truth。
- 金额用 `DecimalText`(TEXT),不用 float。
- Agent 经 tool + 最小上下文包读数据,不裸读全库、不写核心状态。

## 已退役(2026-06-26)

旧十层交易信号链整体退役:`ten_layer_graph.py` 及 10 个 `*_graph.py` 编排器、
`daily_evidence_graph.py`、`market_cockpit.py`、子系统目录
`indicators/ hypotheses/ validation/ risk_gate/ execution/ post_trade/ proposal/`、
`events.py / interpretation.py / indicator_layer.py / validation_metrics.py /
vectorbt_runner.py / workflow.py / backtrader_runner.py`,以及对应 `scripts/`、
`task` 任务与测试。共享底座 `market_data.py`(MarketDataSnapshot 等类型)、`metrics.py`
保留,作为 L0B 的数据子件复用。历史实现由 Git history 保留，不继续放在当前工作树中。

live-trading 相关的 OKX / Alpaca / trading guard / market-access ledger 代码已从
当前工作树删除，历史版本由 Git history 保留。当前 mainline 只有 canonical
Execution Kernel (L6) 的 simulated substrate，无真实 broker SDK、credential、
funding 或 venue connectivity。
