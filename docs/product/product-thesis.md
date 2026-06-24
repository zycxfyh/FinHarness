# FinHarness 产品命题(Product Thesis)

> 状态:草案(2026-06-24)。性质:产品方向论证(C1 纯文档)。
> 它**从属于**已锁定的 [产品北极星](../product-north-star.md);任何与北极星
> 冲突的表述,以北极星为准。本文不保证收益、不提供税务/投资/法律建议、不授权
> 自动执行——这些边界由北极星的硬工程原则继承而来。

## 一句话命题

FinHarness 的机会不是做 AI 投资建议,而是做 **AI 原生的个人财务判断层
(AI-native personal financial judgment layer)**:让普通人看清自己的财务
状态、风险暴露、决策理由、行为偏差和事后教训。

这比"AI 投顾"更安全、更可审计,也更难被重新 prompt 复制——因为它的价值
沉淀在**结构化财务状态 + 决策档案**里,而不是某个一次性回答里。

## FinHarness 不是什么

沿用北极星的 non-goals,并对外明确品类边界:

- 不是 trading bot / 自动交易机器人(执行权永不归 AI)。
- 不是 AI stock picker / 选股器(不做收益预测、不出买卖指令)。
- 不是 robo-advisor / 自动投顾(不替用户自动配置、不承担 fiduciary 判断)。
- 不是记账/预算 App(那只是状态的一个输入,不是产品心智)。
- 不是问一句答一句的 chatbot(它是运行时,会主动巡检、提醒、生成待办)。

## FinHarness 是什么:六个能力,一个闭环

| 能力 | 回答的问题 | 行业锚点 |
| --- | --- | --- |
| 状态理解 | 我现在真实财务状态是什么? | personal balance sheet + cash-flow statement |
| 风险暴露 | 我暴露在哪些风险/因子上?是不是用多个名字押同一个因子? | factor exposure / concentration risk |
| 决策脚手架 | 我为什么想做这个动作?证据、反证、不行动选项、最坏结果是什么? | decision journal / pre-mortem |
| 亏损归因 | 亏了到底是市场 beta、行业、利率、财报、仓位、杠杆还是情绪? | performance / loss attribution |
| 行为复盘 | 这次冲动是否重复了我历史上的坏模式? | behavioral finance review loop |
| 规则沉淀 | 下次该把这次教训变成什么 rule / checklist 改动? | lesson-to-rule(北极星已建机制) |

闭环:`状态读取 → 风险识别 → 方案生成 → 证据解释 → 行为提醒 → 事后归因
→ 经验沉淀`。现有产品大多停在前两环或只做自动配置;FinHarness 的差异化在
后四环——**判断与复盘回路(judgment and review loop)**。

## 市场定位:不是"市面上没有产品",而是"没有这个闭环"

为避免市场判断过度自信,这里明确校准:**已经存在大量相关 AI 财务产品**,
只是覆盖面不同。

| 已有形态 | 代表方向 | 主要在做 |
| --- | --- | --- |
| 预算 / 记账 / cash-flow 工具 | budgeting, expense tracking | 看支出、订阅、预算 |
| portfolio tracker | 净值/资产分布追踪 | 看持仓与净值 |
| robo-advisor | 自动配置、tax-loss harvesting、direct indexing | 替用户自动投资/规划 |
| DIY 财务规划工具 | 退休规划、Monte Carlo、现金流模拟 | 长期规划测算 |
| advisor-facing AI | 顾问用的组合分析/压力测试工具 | 提升顾问效率 |
| AI trading assistant | 交易辅助 | 行情/下单辅助 |

> **校准结论:** 现有产品多覆盖 budgeting / tracking / robo-advice /
> 退休规划 / 顾问效率 / 交易辅助。FinHarness 聚焦的是一个**它们普遍缺失的
> 层**:AI 原生的**个人财务判断与复盘回路**(personal financial judgment
> and review loop)。这是空位,不是"无人区"。

## 为什么这个机会现在才成立

过去普通人做不到完整的个人财务判断:需要财务规划、税务、组合理论、风险
管理、行为金融、复盘能力同时在线,机构有但只服务高净值客户,普通人只拿到
碎片化工具(一个 App 记账、一个看股票、一个报税、一个 Excel 管仓位)。

AI 的变化是:把这些碎片统一成**解释层**——状态读取 → 风险识别 → 方案生成
→ 证据解释 → 行为提醒 → 事后归因 → 经验沉淀。但金融高风险,所以不能做成
"随便给建议的 chatbot"(准确性、监管、隐私、责任边界问题)。FinHarness 的
机会恰好在此:**不是更激进的 AI 投顾,而是更可审计、更有边界、更能训练
用户判断的 AI 财务系统。**

## Wedge(最小切口):每日财务简报 + 决策复盘,而非自动交易

第一版不接更多 broker,不做复杂策略,不做自动交易。第一版只让用户第一次
感受到 aha:

```text
原来我根本不知道自己暴露在哪里;
原来我以为自己在分散,其实全是同一个因子;
原来我每次亏钱不是因为市场坏,而是仓位和行为模式重复出错;
原来我该记录的是决策理由,不只是盈亏。
```

切口落地为两个产品入口(详见 [产品路线](product-roadmap.md)):
**Daily Financial Brief**(每天 5–10 分钟看清状态/风险/可审查选项)+
**Decision Review**(决策前写 thesis,决策后做归因)。

## 护城河

不是代码(Codex/Claude 让代码极易复制,易建的就不是壁垒)。护城河是**会
随时间累积、无法靠重新 prompt 再生成的东西**:用户的结构化财务状态 +
带证据与归因的决策档案 + 行为记忆。把高净值客户才有的"私人财务分析师 +
风控官 + 决策记录员 + 复盘教练",压缩成普通人可用、且**带边界**的 AI 系统。

## Non-claims(对外承诺边界,不可放松)

- 不保证收益、不跑赢任何指数、不预测价格。
- 不提供个性化投资/税务/法律建议,不承担 fiduciary 责任。
- 不自动执行任何交易、转账、报税提交或风险上限修改。
- 一切建议进入 proposal / review,经人工确认 + receipt,READY/PASS 不
  授权 live action。

## 与现有仓库的连接

底座已经在:State Core(Account / Position / Proposal / Attestation /
ReviewEvent / ReceiptIndex)、Decision Workflow、Review System
(proposal / attestation / annotation / archive / annual review /
lesson→rule)、research evidence(带证据等级)、golden path。本命题不要求
重建,只要求把这套底座**变成产品主入口**,而不是继续无限加工程护栏。

## 参考(只作方向锚定,不照搬规格;均为外部公开报道,会过期)

- DIY 财务规划工具综述(Boldin / MaxiFi / Empower / Origin) —
  Kiplinger。
- Vanguard 面向顾问的 AI 组合分析工具 — Barron's。
- Wealthfront(Path 规划 / tax-loss harvesting / direct indexing)—
  WSJ Buyside。
- "AI 能否替代财务顾问"对 AI 金融建议准确性/fiduciary/隐私的提醒 —
  WSJ Buyside。
