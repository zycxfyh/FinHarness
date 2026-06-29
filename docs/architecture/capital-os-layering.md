# FinHarness 分层架构(Capital OS Layering)

> 状态:current(2026-06-29)。这是 FinHarness **架构分层的单一事实源**,
> 取代已归档的 [ten-layer-langgraph-map](../archive/ten-layer-trading-chain/architecture/ten-layer-langgraph-map.md)。
> 产品方向仍以 [产品北极星](../product-north-star.md) 为准;本文是北极星
> "状态 → 解释 → 方案 → 决策 → 行动 → 复盘 → 学习" 闭环的**工程落层**。
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
| **L3** | IPS / 投资政策声明 | 这个状态适合我吗? | `ips.py`、`api/routes_ips.py`、`InvestmentPolicyStatement` | ✅ 有(v0;已接 L4 detector 阈值) |
| **L4** | Proposal & Review 决策提案与审查 | 哪些事值得审查?如何留痕? | `allocation.py`、`statecore/proposals.py`、`decision_scaffold.py`、`risk_classification.py`、`routes_proposals.py`、`routes_review.py` | ✅ 有(candidate+proposal 合并为一层) |
| **L5** | Agent / 个人资本 Agent | 这些状态和提案是什么意思? | `agent_context.py`、`agent_capabilities.py`、`agent_tools.py`、`proposal_queue_checks.py`、proposal review surface | ✅ v0:context packs + default read/explain profile + review-draft proposal drafts + review provenance + queue checks + review-task lifecycle |
| **L6** | Pre-/Post-trade 行动模拟与复盘 | 做这个动作会怎样?做完如何? | (无 ActionIntent / PreTradeImpactReport) | ❌ gap |
| **L7** | Learning 长期记忆与学习 | 我从过去学到什么? | `annual_review.py`、`lesson_loop.py`、`rule_change_ledger.py` | 🟡 有闭环;Journal/Pattern 待建 |
| **L8** | Cockpit / API 产品表面 | 用户怎么用这一切? | FastAPI(`api/app.py` + routers)、vanilla JS cockpit | ✅ 有 |

> L1 与 L2 在 system-map 里同属 **State Core** deep module(状态 + 资本地图),
> 故合并标注。

## 新版相对现状的增量

现状文档(north-star 06-17/06-24、system-map 06-22)已覆盖 L0A/L1/L2/L4/L8。
PR #51 已补上 L3 IPS v0。下一版增量按优先级:

1. **L0B**:外部标的数据从"仅价格"扩成 Instrument / 财报 / 宏观分类。
2. **L5**:把 context packs 用在更好的 Agent 解释/eval 中;review-draft profile
   可写 append-only governed proposal draft,并在 proposal review surface 暴露
   Agent provenance、带 blocked transition scope 的 queue checks 和 read-only
   review-task lifecycle,但不是 approval、recommendation 或 execution authorization。
3. **L6**:`ActionIntent` → `PreTradeImpactReport`(复用 `exposure.compute_exposure`,
   需先把它重构成可接受 hypothetical 持仓集的形态)。

P5 follow-up 已有实现路径:高风险 proposal 若缺 `counter_evidence`,可以记录和拒绝;
若之后要批准,先通过 proposal scaffold revision 补 `counter_evidence`,再走 human
attestation。该 revision 是 review evidence,不是 execution authorization。

## 不变量(跨层)

- `execution_allowed=false` 默认贯穿;approval ≠ execution authorization。
- StateCore 是 queryable state;receipt files 才是 source of truth。
- 金额用 `DecimalText`(TEXT),不用 float。
- Agent 经 tool + 最小上下文包读数据,不裸读全库、不写核心状态。

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
