# 执行手册:每日"变了什么"运行时回路(第一个驾驶舱)

> 类型:执行手册(给 Codex)。建在已提交的状态核心(commit 0c6dcf2)之上。
> 角色分工:Claude 设计/审查,Codex 执行。每个任务独立验收。
> 北极星依据:这是"驾驶舱 = 状态核心上的视图"的第一个真实例子(投资/观测舱)。

## 0. 这个回路是什么

每天:**ingest(落当日持仓快照)→ diff(相对上一份变了什么)→ 确定性观测 →
生成一条 governed proposal(`daily_change_brief`)+ 人读 markdown**,等你 attest。
它是你 6·18 设想里"第一个会主动说'变了什么'的副驾",但**只说事实,不预测、不下单**。

## 1. 锁定的设计原则(与状态核心一脉相承)

```text
- v1 不接 LLM。观测由确定性规则 + 明确阈值产出, 100% 可复现、可审计。
  LLM 叙述留作以后单独 ADR, 且只允许复述确定性观测, 绝不新增判断/预测。
- 只描述、不预测、不建议交易。proposal 的 non_claims 必须显式声明:
  "descriptive state change only / not a market prediction / not trading advice"。
- 防狼来了: 只报越过阈值的观测; 没有越阈 → 出"无重大变化"安静简报。
- 阈值显式、可配置、写进 receipt(观测可复现: "concentration 0.55 > threshold 0.40")。
- loop 内不做实盘调用: 消费一份已有的 broker-read receipt, 不碰活的 broker。
- execution_allowed 全程 False(Proposal 已结构性钉死)。
- 复用而非另造: 提案写入走状态核心同一条 governed-write 路径。
```

## 2. 任务序列

### L1 — 当日快照接入 + 定位上一份快照
交付:在 statecore 加 `latest_portfolio_snapshot(before=as_of)` 查询;一个 loop 入口
从给定的 broker-read receipt 落当日 `portfolio` snapshot(复用
`ingest_portfolio_snapshot_from_receipt`)并解析出**上一份** portfolio 快照用于 diff。
验收:两天的样例 receipt → 落两份快照、正确认出前一份;**首次运行无前序快照时走
"baseline,无 diff"路径而非报错**。
护栏:无实盘调用;只读消费已有 receipt;幂等(同日重复跑不产生重复快照)。

### L2 — 确定性观测引擎(描述性 + 阈值)
交付:`statecore/observations.py`——纯函数,输入 `SnapshotDiff` + 当前持仓,输出
`Observation(kind, detail, numbers, threshold, crossed)` 列表,覆盖:
```text
new_position / closed_position
material_move        (单仓 qty 或 mv 变动超阈值)
total_exposure_delta (总市值变动超阈值)
concentration        (单一 symbol 占总市值 > 阈值)
data_gap             (持仓缺 cost_basis)
```
验收:每类观测各有单测 + 一个"无越阈→空列表"用例。
护栏:**零预测/建议措辞**;观测是事实 + 阈值,仅凭输入可复现;不读市场、不读未来。

### L3 — governed proposal 写入核心(复用)+ 人读 markdown
交付:
- **重构**:把 `routes_proposals.py` 里的提案写入逻辑(receipt payload + 原子写 +
  write_records + 孤儿清理)抽到 statecore 的一个共享函数;API 路由变薄壳调用它。
  loop 与 API 从此共用**同一条** governed-write 路径(不得有第二份提案逻辑)。
- loop 用该核心写 `Proposal(kind="daily_change_brief")`:claim = 确定性事实摘要,
  evidence = {before/after snapshot_id, diff, 观测 + 阈值},non_claims 见第 1 节。
- 渲染人读 `docs/operations/daily-change-brief-latest.md` + 落一份带日期 receipt。
验收:API 路由回归仍通过;loop 不经 HTTP 也能写出同样的 governed proposal;markdown
渲染正确;execution_allowed 处处 False。
护栏:一条共享写入路径;markdown 只是状态核心的视图,不放松任何后端边界。

### L4 — `task cockpit:daily` 编排 + run-log + 安静路径 + 测试
交付:`task cockpit:daily -- --portfolio-receipt <path>`,串起 ingest→diff→observe→
brief;structlog 运行日志;无越阈观测时出"无重大变化"安静简报;幂等。
验收:端到端测试:两份 receipt → 简报含预期观测;同日重跑幂等;无变化跑 → 安静简报。
护栏:无 broker/order/transfer;execution_allowed False;**整次运行可仅凭 receipt 重建**。

## 3. 完成定义(对齐北极星)
```text
- 跑一条命令, 拿到一份"相对上一份快照变了什么"的描述性简报(markdown + receipt),
  零预测性主张、零执行路径。
- 该简报可仅凭 DB + receipt 重建。
- 加这个回路没有重写状态核心(纯增量: 新观测模块 + 新 proposal kind + 新 task)。
```

## 4. 待 operator 拍板
```text
1. v1 用确定性观测、不接 LLM —— 是否同意?(我的强烈建议; 这是本回路最关键的治理决定)
2. 当日组合来源 = 消费一份已有的 broker-read receipt(复用现有 alpaca/okx 读),
   loop 内不做实盘调用 —— 是否同意?
3. 触发 = 先做成可手动跑的 task, cron 以后再挂(沿用 hermes) —— 是否同意?
```

## Links
```text
docs/product-north-star.md
docs/proposals/2026-06-17-state-core-and-api.md
docs/proposals/2026-06-17-state-core-and-api-execution-brief.md
src/finharness/statecore/(diff / snapshot_ingest / models / store)
src/finharness/api/routes_proposals.py(L3 抽取来源)
```
