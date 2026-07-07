# FinHarness 分层架构(Capital OS Layering)

> 状态:current(2026-07-02)。这是 FinHarness **架构分层的单一事实源**,
> 取代已归档的 [ten-layer-langgraph-map](../archive/ten-layer-trading-chain/architecture/ten-layer-langgraph-map.md)。
> 产品方向仍以 [产品北极星](../product-north-star.md) 为准;本文是北极星
> "状态 → 解释 → 方案 → 决策 → 行动 → 复盘 → 学习" 闭环的**工程落层**。
> 金融行业词与 FinHarness 原语的对应关系见
> [Financial Terminology Map](../reference/financial-terminology-map.md);
> 该映射是 design analogy,不是 regulatory status claim。
>
> modular monolith,不是微服务。新功能**先选归属层**(见 [system-map](system-map.md) 的 deep modules),再实现。

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
| **L5** | Agent / 个人资本 Agent | 这些状态和提案是什么意思? | `agent_context.py`、`agent_context_projection.py`、`agent_capabilities.py`、`agent_evidence.py`、`agent_tools.py`、`agent_runtime.py`、`proposal_queue_checks.py`、proposal review surface | ✅ v0:context packs + context projection/budget + default read/explain profile + ToolEntry metadata + evidence provider registry + runtime pipeline + review-draft proposal drafts + review-note artifacts + scaffold apply candidates + review provenance + queue checks + review-task lifecycle |
| **L6** | Execution Kernel 执行内核 | 这个动作可以执行吗?执行后发生了什么? | `statecore/execution_models.py` (OrderDraft, PreTradeCheck, ApprovalRecord, ExecutionOrder, ExecutionReport, PositionDelta, ReconciliationReport, BrokerConnection, ExecutionAccount)、`execution/services.py`、`execution/receipts.py`、`execution/broker.py`、`execution/commands.py`、`execution/adapters/simulated_broker.py`、`api/routes_execution.py` | ✅ v0: full canonical execution lifecycle on simulated substrate; live-shaped model, live environment is legal, only SimulatedBrokerAdapter registered, no real external connectivity |
| **L6-legacy** | ~~Action Intent Chain (legacy)~~ | _(superseded by L6 Execution Kernel)_ | ~~`action_intents.py`、`trade_plan_candidates.py`、`capital_objective_fits.py`、`paper_order_tickets.py` 等~~ | ↳ See `execution/legacy_bridge.py` for migration |

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
3. **L6**:Execution Kernel v0 已建成:canonical execution lifecycle 从 OrderDraft → PreTradeCheck → ApprovalRecord → ExecutionOrder → SimulatedBrokerAdapter.submit_order() → ExecutionReport → PositionDelta → ReconciliationReport。执行环境是 live-shaped:ExecutionEnvironment.LIVE 是合法值,ExecutionOrder 和 submit_order 是合法概念,但只注册 SimulatedBrokerAdapter,无真实 broker SDK/credential/funding/venue connectivity。旧 ActionIntent/TradePlan/PaperValidation 链由 `execution/legacy_bridge.py` 桥接分离;执行相关事实投影到 Execution Spine,agentic artifacts 留在 agentic layers,旧影子和不执行标记等待后续清理。
4. **Authority path**:任何未来 AgentAuthorityGrant、ActionIntentAuthorityBinding、
   SuitabilityCheck、AuthorityContract 或 order-ticket path 必须先引用 active
   `CapitalMandate` 或显式说明豁免;CapitalMandate 是政策域,
   AgentAuthorityGrant 是受限 authority credential,ActionIntentAuthorityBinding
   只授予进入下一层治理检查的资格,三者都不是 execution authorization。

P5 follow-up 已有实现路径:高风险 proposal 若缺 `counter_evidence`,可以记录和拒绝;
若之后要批准,先通过 proposal scaffold revision 补 `counter_evidence`,再走 human
attestation。该 revision 是 review evidence,不是 execution authorization。

## 不变量(跨层)

- Execution Kernel (L6) 使用 live-shaped model, simulated substrate; `network_enabled=false`。
- StateCore 是 queryable state; receipt files 才是 source of truth。
- 金额用 `DecimalText`(TEXT),不用 float。
- Agent 经 tool + 最小上下文包读数据,不裸读全库、不写核心状态。
- Old ActionIntent/PaperValidation chains are legacy; execution facts projected to Execution Spine via `execution/legacy_bridge.py`;
  agentic artifacts retained in agentic layers; negative protection docs tagged for future cleanup.

## 已退役(2026-06-26)

旧十层交易信号链整体退役:`ten_layer_graph.py` 及 10 个 `*_graph.py` 编排器、
`daily_evidence_graph.py`、`market_cockpit.py`、子系统目录
`indicators/ hypotheses/ validation/ risk_gate/ execution/ post_trade/ proposal/`、
`events.py / interpretation.py / indicator_layer.py / validation_metrics.py /
vectorbt_runner.py / workflow.py / backtrader_runner.py`,以及对应 `scripts/`、
`task` 任务与测试。共享底座 `market_data.py`(MarketDataSnapshot 等类型)、`metrics.py`
保留,作为 L0B 的数据子件复用。文档归档在
[docs/archive/ten-layer-trading-chain/](../archive/ten-layer-trading-chain/)。

live-trading 相关的 OKX / Alpaca / trading guard / market-access ledger 代码已于
2026-06-27 从 mainline runtime 归档到
`experiments/archive/live_trading_legacy/`。当前 Taskfile 不暴露 live execution 或
paper broker 执行入口;若未来需要只读 market-data 能力,应按 L0B 重新建外部数据
adapter,不要继承归档执行代码。
