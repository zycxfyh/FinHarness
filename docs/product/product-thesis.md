# FinHarness 产品命题(Product Thesis)

> 状态:当前方向草案(2026-07-11)。性质:产品方向论证(C1 纯文档)。
> 它**从属于**已锁定的 [产品北极星](../product-north-star.md);任何与北极星
> 冲突的表述,以北极星为准。本文不保证收益;任何高后果资本动作都必须沿着
> evidence、review、receipt、paper validation 和受控执行能力逐步推进。

## 一句话命题

FinHarness 的北极星是 **Agent-Native Personal Capital Operating System**：
用户提出资本目标、价值偏好、风险边界和授权，Capital Agent 负责持续实现，
FinHarness Harness 负责让实现过程可信、可控、可恢复、可解释和可撤销。
当前产品更准确的定位仍是
**local-owned Personal Capital Review and Decision Ledger**：先服务愿意自主
管理多账户或复杂资本状态、重视隐私与决策纪律的用户，再验证是否能够降低
普通用户的输入和维护门槛。

这条路线更可审计,也更难被重新 prompt 复制——因为它的价值沉淀在
**结构化财务状态 + 决策档案**里。

## FinHarness 的品类边界

FinHarness 的产品心智靠一条可推进的能力链定义:

- 状态与风险先清楚;
- 候选方案要有证据、反证、成本、风险和替代路径;
- review gate 决定能否进入下一层;
- paper validation 用来验证计划质量和行为质量;
- 受控执行能力只能在明确授权、限制、kill switch、receipt 和复盘条件下逐步进入产品。

记账、预算、研究、规划、复盘、paper validation 和执行候选都可以成为能力层,
但它们必须服务同一个目标:让用户的财务判断越来越可见、可算、可解释、可复核。

## FinHarness 是什么:六个能力,一个闭环

| 能力 | 回答的问题 | 行业锚点 |
| --- | --- | --- |
| 状态理解 | 我现在真实财务状态是什么? | personal balance sheet + cash-flow statement |
| 风险暴露 | 我暴露在哪些风险/因子上?是不是用多个名字押同一个因子? | factor exposure / concentration risk |
| 决策脚手架 | 我为什么想做这个动作?证据、反证、不行动选项、最坏结果是什么? | decision journal / pre-mortem |
| 亏损归因 | 亏了到底是市场 beta、行业、利率、财报、仓位、杠杆还是情绪? | performance / loss attribution |
| 行为复盘 | 这次冲动是否重复了我历史上的坏模式? | behavioral finance review loop |
| 规则沉淀 | 下次该把这次教训变成什么 rule / checklist 改动? | lesson-to-rule(北极星已建机制) |

目标闭环:`状态读取 → 风险识别 → 方案生成 → 证据解释 → 行为提醒 → 事后归因
→ 经验沉淀`。现有产品大多停在前两环或只做自动配置;FinHarness 的差异化在
后四环——**判断与复盘回路(judgment and review loop)**。

当前仓库已经可靠交付的是状态、候选、人工复核与决策记录；Scenario、
Paper Performance、规则真实消费和 Agent 完整任务仍是待交付能力，不能用
北极星名称替代当前成熟度判断。

近期 Human-in-the-loop 并非永久产品定义。长期责任关系是：Human Principal
拥有资本宪法和最终主权；Capital Agent 拥有目标分解、行动策略和持续闭环；
Harness 拥有准入、约束、恢复和撤销；确定性引擎拥有计算、事务和效果正确性。

## 市场定位:不是空白市场，而是跨域闭环相对稀缺

为避免市场判断过度自信,这里明确校准:**已经存在大量相关 AI 财务产品**,
只是覆盖面不同。

| 已有形态 | 代表方向 | 主要在做 |
| --- | --- | --- |
| 预算 / 记账 / cash-flow 工具 | budgeting, expense tracking | 看支出、订阅、预算 |
| portfolio tracker | 净值/资产分布追踪 | 看持仓与净值 |
| 自动配置平台 | 自动配置、tax-loss harvesting、direct indexing | 长期配置与再平衡 |
| DIY 财务规划工具 | 退休规划、Monte Carlo、现金流模拟 | 长期规划测算 |
| advisor-facing AI | 顾问用的组合分析/压力测试工具 | 提升顾问效率 |
| AI trading assistant | 交易辅助 | 行情/下单辅助 |

> **校准结论:** ProjectionLab、TraderSync、Origin、robo-advisor 等产品已经
> 分别覆盖情景比较、计划与实际复盘、AI 财务解释或自动配置。FinHarness 的
> 假设不是“别人没有闭环”，而是：把现金流、负债、长期规划和自主投资放在
> 同一资本状态上，并统一证据、反证、人工决策、结果归因和规则历史，可能为
> 自主决策者形成有价值的长期档案。这个假设仍需留存、复盘回访和付费实验验证。

## 为什么这个机会现在才成立

过去普通人做不到完整的个人财务判断:需要财务规划、税务、组合理论、风险
管理、行为金融、复盘能力同时在线,机构有但只服务高净值客户,普通人只拿到
碎片化工具(一个 App 记账、一个看股票、一个报税、一个 Excel 管仓位)。

AI 的变化是:把这些碎片统一成**解释层**——状态读取 → 风险识别 → 方案生成
→ 证据解释 → 行为提醒 → 事后归因 → 经验沉淀。金融高风险,所以产品必须把
建议、候选、review、paper validation、执行候选和真实执行分层建模。FinHarness
的机会恰好在此:**做一个可审计、有推进路径、能训练用户判断的 AI 财务系统。**

## Wedge(最小切口):重大决策复核 + 定期事后复盘

第一版先让用户第一次感受到 aha:

```text
原来我根本不知道自己暴露在哪里;
原来我以为自己在分散,其实全是同一个因子;
原来我每次亏钱不是因为市场坏,而是仓位和行为模式重复出错;
原来我该记录的是决策理由,不只是盈亏。
```

主任务是 **Material Decision Review + Scheduled Retrospective**：决策前记录
thesis、反证、不行动选项、最大可接受损失与复核日期，决策后在 30/90/180 天
比较预期与实际。**Home/Today** 是把状态、数据缺口和到期复核导向该任务的
入口；Daily Brief 不是制造日活或市场噪声的产品目标。

第一条验证闭环聚焦集中度决策：保持不动、用未来现金流稀释、或按用户给定
规模减持。Scenario 只做透明、可重放的确定性差异计算，不先引入 optimizer
或 Monte Carlo。

这只是自主性阶梯的入口：近期产品是 Material Decision Review，中期产品是
Autonomous Paper Capital Manager，长期产品是 Mandate-Bound Personal Capital
Agent。首个 counter-evidence/review-packet 任务用于证明 Harness，不把 Agent
永久限定成研究助理。

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
