# 人体系统 — Health Layer

## 数据流水线

```
华为手表 → 手机(App) → 导出ZIP → 电脑(health/data/)
  → 解析脚本 → 标准化JSON → 日报/周报/趋势
```

## 七个子系统对应指标

| 子系统 | 手表数据 | 目标 |
|--------|---------|------|
| 睡眠 | 深睡/浅睡/REM/清醒 时长 | 深睡 > 1.5h, 总时长 > 7h |
| 心率 | 静息心率, 全天心率 | 静息 < 65bpm, 趋势稳定 |
| 活动 | 步数, 卡路里 | 日均 > 8000 步 |
| 运动 | 运动记录(类型/时长/心率) | 每周 > 3 次, 每次 > 30min |
| 血氧 | SpO2 | > 95% |
| 压力 | 压力等级 | 日均 < 中等 |
| 体成分 | 体重/BMI/体脂率 | BMI < 24, 体脂 < 20% |

## 目录

```
health/
  README.md        本文件
  data/            原始导出数据
  reports/         生成的日报/周报
  plans/           运动计划/饮食计划
  import_health.py 数据导入脚本
  summary.py       日报/周报生成
  plan.py          基于数据的计划生成
```

## 命令

```bash
task health:import     # 导入华为健康导出数据
task health:summary    # 生成今日/本周摘要
task health:plan       # 基于数据生成运动计划
task health:report     # 生成完整健康周报
```
