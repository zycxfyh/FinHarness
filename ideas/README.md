# Idea Lab

基于 **BES (Backward Evolution Search)** 框架的实验管理系统。

## 快速入口

```bash
task ideas:list     # 查看所有实验
task ideas:evolve   # 运行想法重组
```

## 文件

| 文件 | 内容 |
|------|------|
| [BES.md](BES.md) | BES 引擎设计 — Forward Evolution / Backward Decomposition / Dense Feedback |
| [backlog.md](backlog.md) | 实验 Backlog — 活跃实验 + Idea Pool + Killed Log |

## 核心原则

1. **每个想法必须填满 7 个字段才能行动** (idea/hypothesis/experiment/metric/threshold/budget/decision)
2. **每个实验必须拆成 3-7 个一眼能判断对错的子步骤** (Backward Decomposition)
3. **每个子步骤完成后立即反馈，不等最后** (Dense Feedback)
4. **每周最多 3 个并行实验**
5. **Killed 实验不删，保留作为"已证伪"证据**
6. **定期从 Pool 中交叉重组想法** (Forward Evolution)
