# Idea Lab — BES 引擎

基于 Guowei Xu 的 Backward Evolution Search 框架改造 Idea Lab。

## 三个核心机制

### 1. Forward Evolution — 想法重组

周期性从想法池中取两个想法，强制交叉产生新假设。

**操作：**
```bash
task ideas:evolve
```

**算法：**
1. 从 active 池随机取一个
2. 从 pool/killed 池随机取一个
3. 生成交叉假设：A 的方法 × B 的领域，或 A 的指标 × B 的实验对象

**输出：** 新 EXP-NNN 写入 backlog，状态 draft。

### 2. Backward Decomposition — 实验拆子目标

每个实验拆分 3-7 个一眼能判断对错的子步骤。不是"做完看总结果"，而是"每步都有 gate"。

**模板：**
```yaml
steps:
  - id: 1
    gate: "趋势是否明确向上？"
    check: 日线 EMA20 > EMA50 且价格在 EMA20 上方
    pass: ✓
  - id: 2
    gate: "回踩是否到支撑？"
    check: 价格触及前低/EMA20/需求区 任意一个
    pass: ✗ (追高了)
  - id: 3
    gate: "止损是否按计划执行？"
    check: 实际止损 = 计划止损 ± 0.1%
    pass: ✓
```

**规则：** 任一 gate fail → 实验直接标记该步骤失败，不等到最后。

### 3. Dense Feedback — 每步验证

每完成一个步骤立即记录，不攒到最后。反馈频率 = 实验步数，不是实验数量。

**对比：**

| | Sparse (旧) | Dense (BES) |
|---|---|---|
| 反馈频率 | 30 笔后看 EV | 每笔每个 gate 后 |
| 发现问题速度 | 30 笔后才知道 | 第 1 笔第 2 步就能发现 |
| 纠偏能力 | 方向错了跑到底 | 立刻停止/修正 |

## 实验模板 v2 (BES 增强版)

```yaml
id: "EXP-NNN"
lab: career | trading | agent
status: draft | running | done | killed

# --- 原 7 字段 ---
idea: |
  一句话描述。
hypothesis: |
  我认为 X 会导致 Y。
experiment: |
  具体做什么。
metric: |
  用什么指标衡量。
threshold: |
  什么结果算有效。
budget: |
  最多投入多少。

# --- BES 新增 ---
decomposition:
  - step: 1
    gate: "可独立验证的子目标"
    metric: "怎么判断这一步过没过"
    result:
  - step: 2
    gate: "..."
    metric: "..."
    result:

feedback_log:
  - at: "2026-05-30T19:00"
    step: 1
    passed: true
    note: "趋势确认通过，日线 EMA20 > EMA50"
  - at: "2026-05-30T19:30"
    step: 2
    passed: false
    note: "回踩不清晰，入场过早"

evolution_parents:  # 如果是 evolve 产生的
  - EXP-006
  - EXP-007

results: |
  最终汇总。

decision: continue | modify | kill | scale
```

## 命令

```bash
task ideas:list          # 查看所有实验状态
task ideas:evolve        # 运行一次想法重组
task ideas:run EXP-NNN   # 开始一个实验 (draft → running)
task ideas:close EXP-NNN # 关闭实验并记录决策
```
