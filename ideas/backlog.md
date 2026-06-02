# Idea Backlog

最后更新: 2026-05-30

BES 引擎: 见 [BES.md](BES.md) — Forward Evolution / Backward Decomposition / Dense Feedback

## 活跃实验

| ID | Lab | 状态 | Idea | Decision |
|----|-----|------|------|----------|
| EXP-002 | trading | running | 强趋势回踩多比逆势做空更适合我 | — |
| EXP-003 | agent | running | 开仓前强制填写 R 和失效条件可以减少冲动交易 | — |
| EXP-001 | career | draft | AI Trading Risk Agent 是比通用 AI 项目更适合的作品方向 | — |

## 实验详情 (BES 增强版)

### EXP-001 · Career Lab

```yaml
id: "EXP-001"
lab: career
status: draft

idea: |
  AI Trading Risk Agent 是比通用 AI 项目更适合我的作品方向。

hypothesis: |
  一个聚焦金融风控的 AI Agent 项目，比泛用 AI 项目更能让
  AI 应用工程 / 金融科技 / 数据分析方向的面试官觉得"有东西"。

experiment: |
  1. 写 README 草稿
  2. 画系统架构图
  3. 列出 3 个核心功能
  4. 发给 3 个人收集反馈

metric: |
  反馈中认为"方向清晰"且有"展示价值"的人数。

threshold: |
  至少 2/3 人认可。

budget: |
  2 小时。

decomposition:
  - step: 1
    gate: "README 草稿完成"
    metric: "一句话能说清楚项目做什么 → 能/不能"
  - step: 2
    gate: "架构图完成"
    metric: "图里至少有数据层/策略层/风控层三层 → 有/没有"
  - step: 3
    gate: "3 个核心功能清晰"
    metric: "每个功能能用一句话描述 → 3/3"
  - step: 4
    gate: "外部反馈收集"
    metric: "至少 2 人认为方向清晰且有展示价值 → ≥2/3"

feedback_log: []

results: |
decision: |
```

### EXP-002 · Trading Lab

```yaml
id: "EXP-002"
lab: trading
status: running
started: 2026-05-30

idea: |
  强趋势回踩多比逆势做空更适合我的性格和风险偏好。

hypothesis: |
  在明确上升趋势中，回踩支撑位做多，
  比在上升趋势中猜顶做空的胜率和盈亏比更高。

experiment: |
  虚拟账户记录 10 笔强趋势回踩多 setup。
  每笔记录：趋势确认、回踩结构、入场执行、止损执行、复盘。

metric: |
  纪律执行率 (4/5 gates 全部通过的比例)
  平均 R-multiple
  胜率

threshold: |
  纪律执行率 ≥ 80% (10 笔中至少 8 笔 gates 全过)。
  EV 不明显为负。

budget: |
  每笔 ≤ 账户 2% 风险。总计 10 笔。

decomposition:
  - step: 1
    gate: "趋势确认"
    metric: "日线 EMA20 > EMA50 且价格在 EMA20 上方 → ✓/✗"
  - step: 2
    gate: "回踩结构"
    metric: "价格触及支撑位 (前低/EMA20/需求区) → ✓/✗"
  - step: 3
    gate: "入场执行"
    metric: "实际入场价在计划入场价 ± 0.2% 内 → ✓/✗"
  - step: 4
    gate: "止损执行"
    metric: "止损按计划执行，未手动移动止损 → ✓/✗"
  - step: 5
    gate: "24h 内复盘"
    metric: "交易后 24h 内写了复盘笔记 → ✓/✗"

feedback_log: []

results: |
decision: |
```

### EXP-003 · Agent Lab

```yaml
id: "EXP-003"
lab: agent
status: running
started: 2026-05-30

idea: |
  开仓前强制填写 R 和失效条件可以减少冲动交易。

hypothesis: |
  在每笔交易前强制使用 `guard --interactive` 输入入场/止损/权益，
  系统输出最大仓位 + 是否允许交易。
  这样做能阻止无止损/过大仓位的冲动交易。

experiment: |
  task guard:interactive
  用 10 个交易想法测试（不一定是真实交易）。
  记录每次输入和输出。

metric: |
  正确拦截率：该拦的拦了 / 总该拦数
  误拦率：不该拦的拦了 / 总不该拦数

threshold: |
  正确拦截率 = 100% (0 漏网)。
  误拦率 ≤ 1/10。

budget: |
  已开发完成 (2h)。测试用 10 个想法。

decomposition:
  - step: 1
    gate: "输入验证"
    metric: "entry ≠ stop → ✓/✗"
  - step: 2
    gate: "仓位计算"
    metric: "max_position = equity × 2% / 1R → ✓/✗"
  - step: 3
    gate: "风险拦截"
    metric: "仓位 > 50% equity → WARN / 否则 → OK"
  - step: 4
    gate: "论文检查"
    metric: "thesis 非空 → ✓/✗"
  - step: 5
    gate: "最终裁决"
    metric: "全部 ✓ → ALLOW / 任一 ✗ → BLOCK"

feedback_log: []

results: |
decision: |
```

## Idea Pool

| ID | Lab | Idea | Parents |
|----|-----|------|---------|
| EXP-004 | career | 公开技术写作能提高信任度和面试机会 | — |
| EXP-005 | career | 冷邮件/私信比海投更有效 | — |
| EXP-006 | trading | RSI 极低时反抽有正期望 | — |
| EXP-007 | trading | 相对价值组合比单边交易更稳定 | — |
| EXP-008 | agent | Agent 复盘能提高交易纪律执行率 | — |
| EXP-009 | agent | 风控 Agent 自动拦截能减少情绪化交易 | — |
| EXP-010 | career | 每周自动抓取岗位要求 → 生成差距报告 | — |
| EXP-011 | trading | RSI 反抽 × 强势板块过滤 | EXP-006 × EXP-007 |
| EXP-012 | agent | API-native trading harness：read → proposal → risk gate → receipt | — |
| EXP-013 | research | Bottleneck Rent Alpha Model：给复杂系统中的绑定约束定价 | — |
| EXP-014 | agent | 多 Agent 投委会只生成 proposal，不拥有 live execution 权限 | — |
| EXP-015 | trading | 交易所 API 必须拆成 read / preview / demo / live-write 四层权限 | — |
| EXP-016 | research | 每个金融判断必须拆成事实、推断、假设、猜测和反证条件 | — |

## Killed

| ID | Lab | Idea | 死因 |
|----|-----|------|------|
| — | — | — | — |
