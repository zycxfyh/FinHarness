# FinHarness 产品路线草案(Product Roadmap)

> 状态:草案(2026-06-24)。性质:方向序列,不是排期。它从属于
> [产品北极星](../product-north-star.md) 与 [产品命题](product-thesis.md)。
> 这是**产品交付线**,与北极星的"五阶段能力路线"是**不同的轴**:北极星按
> 能力/治理分阶段,本文按用户能感知的产品入口分阶段。下表给出映射,避免
> 两条线互相打架。

## 轴的区分(重要)

- 北极星五阶段路线 = **能力地基**怎么长(研究证据系统 → 只读驾驶舱 →
  决策工作流 → 人机 cockpit → 有限自动化)。
- 本产品路线 = **用户每天打开看到什么**怎么长。

| 产品阶段 | 北极星能力阶段映射 | 用户感知 |
| --- | --- | --- |
| P1 Product Thesis | 阶段 1(地基,文档先行) | 方向钉进仓库 |
| P2 Daily Financial Brief v1 | 阶段 2(只读驾驶舱) | 每天看清状态/风险 |
| P3 Decision Journal / Proposal Scaffold | 阶段 3(决策工作流) | 决策前写 thesis |
| P4 Post-Loss Attribution v0 | 阶段 3–4(工作流 + 复核) | 亏损后结构化归因 |
| P5 Leverage Warning Gate v0 | 阶段 2/3 的 risk 属性 | 高风险动作前强解释 |

## P1 — Product Thesis(本轮)

C0/C1 纯文档。产物:本路线 + [product-thesis.md](product-thesis.md) + 北极星
新增 `Financial Decision Clarity` 指标块。**不写功能代码。** 目的:在加任何
产品功能前,先把"为什么存在"钉进仓库,挡住"偷偷重建交易产品"的漂移。

## P2 — Daily Financial Brief v1

强化 `task brief:daily`,输出**固定结构**(每一项都是状态核心上的 view,不是
新竖线):

```text
1. Net worth snapshot        净资产快照
2. Cash / liquidity status   现金/流动性安全垫
3. Exposure map              风险暴露地图(因子级,不只是资产名)
4. Concentration risks       集中度风险
5. Leverage / liquidation    杠杆/爆仓预警(见 P5)
6. Market context            与持仓相关的市场变化(历史描述,非预测)
7. Candidate decisions       候选动作(governed proposal)
8. Do-nothing option         不行动选项(永远显式列出)
9. Behavioral warnings       行为风险(追涨/恐慌/加杠杆/过度集中/忽视税务)
10. Review prompts           复盘提示
```

边界:只读;市场上下文必须带证据等级、用历史描述而非预测;候选记录为
governed proposal,不出现买卖按钮。

## P3 — Decision Journal / Proposal Scaffold

每个 proposal 增加结构化字段,把冲动变成**可审查对象**(不是阻止):

```text
decision_intent   thesis           evidence_refs    counter_evidence
alternatives      do_nothing_case  risk_if_wrong    position_impact
tax_consideration review_date      emotion_flag
```

复用现有 Proposal / Attestation / ReviewEvent,不另起对象。

## P4 — Post-Loss Attribution v0

亏损复盘模板,做**结构化归因**而非情绪叙事("庄家割我/运气差"):

```text
market_beta  sector_rotation  rate_change  earnings_event
valuation_compression  position_size_error  leverage_error
timing_error  behavioral_error  unknown
```

输出进入 lesson;够格的 lesson 进入 rule candidate(复用 lesson→rule)。

## P5 — Leverage Warning Gate v0

高风险动作(加杠杆/集中加仓)前**强解释 + 冷静期**,不是硬阻止:

```text
- liquidation estimate         爆仓价与距当前价格的距离
- historical volatility compare 标的历史波动 vs 本次杠杆
- prior similar decision outcome 上次同类决策的最大回撤与复盘结论
- max drawdown memory          行为记忆
- written thesis required      必须有书面 thesis
- cool-down prompt             冷静期(如 30 分钟)确认
```

fail-closed:没人工确认就停;确认动作本身产生 receipt。

## 北极星指标对齐

每个产品阶段都要能映射到 [Financial Decision Clarity](../product-north-star.md)
的七维(有状态/有解释/有风险/有对照/有复盘/有学习/有行为改善)。一个阶段
若无法说清自己推进了哪一维,就先不做。

## 不在本路线内(显式排除)

- 自动交易、自动配置、收益预测、选股器 —— 见 [命题 non-claims](product-thesis.md#non-claims对外承诺边界不可放松)。
- 多租户 / 服务他人 / 机构级合规重量 —— 北极星"先自用、后服务他人"。

## 工程债如何穿插

工程债(安全台账、CVE、change-control 收口)**穿插进行,不抢主线命名**,且
**不和产品文档/功能混进同一个 PR**(除非是同一轮收口后的纯文档整理)。
例:#37/#38 合并后的 C0 台账收口(security register open count、change-control
活页漂移)应是独立 PR。
