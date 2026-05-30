# Idea Lab — 实验模板

每个想法在进入行动前，必须填满以下 7 个字段。
任何一个填不出来，先不行动。

---

## 实验模板

```yaml
id: "EXP-001"
lab: career | trading | agent
status: draft | running | done | killed

idea: |
  一句话描述想法。

hypothesis: |
  我认为 X 会导致 Y。
  例如：AI Trading Risk Agent 项目比通用 AI 项目更能提高简历回复率。

experiment: |
  具体做什么来验证。
  例如：写 README + 架构图 + 3 个核心功能说明，发给 3 个人。

metric: |
  用什么指标衡量。
  例如：认为方向清晰且有展示价值的人数。

threshold: |
  达到什么结果才算有效。
  例如：至少 2/3 人认可方向。

budget: |
  最多投入多少时间/资源。
  例如：2 小时。

results: |
  实验结果（跑完后填）。

decision: continue | modify | kill | scale
  基于结果的决策。

receipt: |
  实验收据链接。
```

## 实验状态流转

```text
draft → running → done → decision
                    ↓
                  killed (放弃)
                  modify (修改假设重做)
                  continue (继续下一轮)
                  scale (扩大投入)
```

## Idea Backlog 规则

1. 所有想法先进 backlog，不直接行动
2. 每周最多跑 3 个实验（防止贪多）
3. 跑完的实验必须写结果 + 决策
4. killed 的实验不删，保留作为"已证伪"证据
