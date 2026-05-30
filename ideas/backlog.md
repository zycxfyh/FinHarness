# Idea Backlog

最后更新: 2026-05-30

## 活跃实验

| ID | Lab | 状态 | Idea | Decision |
|----|-----|------|------|----------|
| EXP-001 | career | running | AI Trading Risk Agent 是比通用 AI 项目更适合的作品方向 | — |
| EXP-002 | trading | running | 强趋势回踩多比逆势做空更适合我 | — |
| EXP-003 | agent | running | 开仓前强制填写 R 和失效条件可以减少冲动交易 | — |

## 实验详情

### EXP-001 · Career Lab

```yaml
id: "EXP-001"
lab: career
status: running
started: 2026-05-30

idea: |
  AI Trading Risk Agent 是比通用 AI 项目更适合我的作品方向。

hypothesis: |
  一个聚焦金融风控的 AI Agent 项目，比一个泛用 AI 项目，
  更能让 AI 应用工程 / 金融科技 / 数据分析方向的面试官觉得"这个人有东西"。

experiment: |
  1. 写 README 草稿
  2. 画系统架构图
  3. 列出 3 个核心功能（实时风控、交易复盘、策略回测）
  4. 发给 3 个 AI/金融相关的人看，收集反馈

metric: |
  反馈中认为"方向清晰"且有"展示价值"的人数。

threshold: |
  至少 2/3 人认可方向。

budget: |
  2 小时。

results: |

decision: |

receipt: |
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
  用虚拟账户记录 10 笔强趋势回踩多 setup。
  每笔记录：入场理由、止损位、仓位、结果、是否违规。

metric: |
  纪律执行率（有无违反止损/仓位规则）
  平均 R-multiple
  胜率

threshold: |
  10 笔中 0 次纪律违规。
  EV 不明显为负（不做严格显著性要求，样本太小）。

budget: |
  每笔交易不超过账户 2% 风险。
  总计 10 笔，时间不限。

results: |

decision: |

receipt: |
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
  在每笔交易前，强制填写：
  1. 入场价
  2. 止损价（= 1R 距离）
  3. 账户权益
  4. 最大仓位比例（2%）
  输出：最大允许仓位 和 是否允许交易。
  这样做能阻止无止损/过大仓位的冲动交易。

experiment: |
  做一个最简单的 Rust CLI 命令：
  `cargo run -q -p finharness-cli -- guard --interactive`
  输入入场、止损、权益 → 输出仓位上限 + 通过/拦截。

metric: |
  连续用 10 个交易想法测试。
  记录每次输入和输出。
  统计：正确拦截的次数 vs 漏过违规的次数。

threshold: |
  10 个想法全部被规则正确处理（该拦的拦，该放的放）。

budget: |
  2 小时开发。

results: |

decision: |

receipt: |
```

## Idea Pool (draft)

尚未激活的想法池。

| ID | Lab | Idea |
|----|-----|------|
| EXP-004 | career | 公开技术写作能提高信任度和面试机会 |
| EXP-005 | career | 冷邮件/私信比海投更有效 |
| EXP-006 | trading | RSI 极低时反抽有正期望 |
| EXP-007 | trading | 相对价值组合比单边交易更稳定 |
| EXP-008 | agent | Agent 复盘能提高交易纪律执行率 |
| EXP-009 | agent | 风控 Agent 自动拦截能减少情绪化交易 |
| EXP-010 | career | 每周自动抓取岗位要求 → 生成技能差距报告 |

## Killed Experiments

| ID | Lab | Idea | 死因 |
|----|-----|------|------|
| — | — | — | — |
