# FinHarness 产品北极星

> 状态:已锁定(2026-06-17)。这是产品方向的单一事实源。任何产品/工程决策
> 与本文冲突时,先改本文、再改决策——不要让代码悄悄改变方向。
>
> 修订(2026-06-24):新增「北极星指标:Financial Decision Clarity」一节,
> 作为本文一句话北极星的**可度量操作化**。它是**用户价值形态**的指标,与下文
> 「路线与成功指标」里"决策能否仅凭收据重建打分"的**治理形态**指标互补,不
> 替代后者。配套文档:[产品命题](product/product-thesis.md)、
> [产品路线](product/product-roadmap.md)。
>
> 修订(2026-07-02):把"AI 永不拥有执行权"收窄为更精确的产品边界:
> **Agent 不默认拥有高后果身份或执行权**。未来若支持有限代理身份,必须由
> 显式、可撤销、receipt-backed 的授权对象承载,并受 CapitalMandate、limits、
> kill switch、review cadence 和人类 attestation 约束。CapitalMandate 本身
> 仍不是授权、执行、order ticket 或 broker 指令。
>
> 修订(2026-07-03):`AgentAuthorityGrant` 是第一个有限代理 authority credential:
> 它必须引用 active CapitalMandate,验证时动态重查当前 grant 与 mandate 状态,
> 并返回闭集 deny reasons。它只参与 scope validation、evidence binding 和
> downstream preflight 输入。
>
> 修订(2026-07-04):资本动作链不能只发展成 permission firewall。`CapitalObjectiveFit`
> 是 review gate 前的用户利益解释层:它把 TradePlanCandidate 绑定到 objective
> alignment、benefit thesis、risk/liquidity/concentration impact、alternatives、
> uncertainty 和 next safe path,帮助用户理解候选动作是否服务长期资本目标。它
> 位于 review gate 之前;order ticket、broker submission 与 execution
> authorization 必须作为后续高权限能力单独建模。
>
> 修订(2026-07-04):FinHarness 的 agentic development 也遵循同一产品哲学:
> 中型和主线 PR 应先识别 unknowns、产品形态风险、conservative defaults 和
> stop conditions,再实现。这不是流程仪式,而是防止 Agent 在地图缺失处把个人
> capital agency workbench 推向 permission firewall、premature order pipeline、
> 过早收缩成 permission firewall 或 premature order pipeline。工程协议见
> [Agentic Unknowns Protocol](engineering/agentic-unknowns-protocol.md)。
>
> 修订(2026-07-04):FinHarness 不应被一句话定义成"交易型"或"反交易型"。
> 它是 permission-aware、consequence-aware 的个人投资与交易工作台:默认层可
> anti-trading,教育/研究层应 pro-learning / pro-analysis,计划层可
> trade-oriented,审查层 anti-unaudited,执行层只能 controlled execution。金融
> 教育应保留真实金融语言;runtime 层负责防止低权限对象冒充建议、审批、订单或
> 执行。能力地图见 [Financial Judgment Curriculum](product/financial-judgment-curriculum.md)。
>
> 修订(2026-07-11):北极星从“AI 辅助驾驶舱”提升为 **Agent-Native Personal
> Capital Operating System**。人类拥有目标、资本宪法、授权和否决权；Capital
> Agent 逐步拥有 observe → reason → plan → act → verify → learn 的目标闭环；
> FinHarness Harness 负责准入、约束、审计、恢复、回滚和撤销；确定性金融引擎
> 负责计算与效果正确性。当前 Human-in-the-loop 是起点，不是永久上限。
> 控制权决策见 [Agent-Native Control Ownership ADR](adr/2026-07-11-agent-native-control-ownership.md)。

## 一句话定位

FinHarness 是面向个人资本主体的 **Agent-Native Personal Capital Operating
System**：用户声明资本目标、价值偏好、风险边界、禁止事项和可撤销授权，
Capital Agent 持续观察资本世界，自主分解任务、搜集证据、模拟、行动、验证、
复盘和学习；FinHarness 让这个闭环可信、可控、可恢复、可解释、可撤销。

它更接近:
**个人 CFO + 风控台 + 财务操作系统 + AI 运行时 + 决策证据库。**

## 北极星(一句话校验)

> FinHarness 要让 Capital Agent 在人类资本宪法和 mandate 内持续实现目标，
> 同时使每个事实、决定、动作和结果都**可见、可算、可解释、可验证、可恢复、
> 可撤销、可追责**。

这不是让模型拿着凭证任意行动。Agent 拥有目标级控制；Harness 拥有机器级
准入和恢复；确定性引擎拥有效果正确性；Human Principal 拥有最终主权。

## 北极星指标:Financial Decision Clarity(2026-06-24 新增)

北极星指标 = **财务决策清晰度**。它把上面那句北极星拆成七个可观察维度,
并刻意优先衡量用户是否更清楚、更可复盘、更少冲动:

| 维度 | 含义 |
| --- | --- |
| 有状态 | 用户知道自己的资产、负债、现金流、风险资产比例 |
| 有解释 | 每个重要决策都有 written thesis |
| 有风险 | 每个决策前展示最大亏损、仓位影响、杠杆风险 |
| 有对照 | 每个 proposal 有 do-nothing option 和 alternatives |
| 有复盘 | 每次亏损/盈利后都有结构化归因 |
| 有学习 | lesson 能进入 rule candidate |
| 有行为改善 | 无计划交易、冲动加仓、高杠杆次数下降 |

与"治理成功指标"的关系:下文「路线与成功指标」的"决策能否仅凭收据被完整
重建和打分"证明**系统可审计**;本指标证明**用户判断在变强**。两者都满足,才
是"让人变好"的 FinHarness;只满足前者,会退回成一个证据治理系统。

## 产品 B0 与旧 B1-B5 的关系

当前产品 B 是:

```text
B0: Personal Financial Situational Awareness

在每天 5-10 分钟内,我能通过 FinHarness 看清:
- 我拥有什么资产与负债;
- 我暴露在哪些风险上;
- 相对上次发生了什么变化;
- 外部世界哪些变化影响我;
- 当前有哪些值得审查的行动选项;
- 哪些行动被系统明确阻止;
- 过去决策产生了什么结果和教训。
```

2026-06-12 的 B1-B5 不再是产品存在理由;它们被降级为 B0 的安全与质量
predicates:

| 旧 B | 当前定位 | 服务 B0 的方式 |
| --- | --- | --- |
| B1 evidence-on-demand | 基础能力 | 让"外部变化影响我什么"有证据来源 |
| B2 decision discipline | 高风险操作控制 | 让候选行动进入人工复核,而不是冲动执行 |
| B3 bounded loss | 风险约束 | 限制可控路径中的计划风险,并暴露不可控尾部风险 |
| B4 compounding judgment ([glossary](reference/glossary.md)) | 长期学习机制 | 把复盘 lesson 变成可追溯的规则/检查表改动 |
| B5 boundary | 自主性准入 | Agent 不默认拥有高后果身份或执行权；READY/PASS 不授权 live action；未来只能由显式 mandate 和 autonomy gate 扩张。 |

因此:治理、receipt、lesson-to-rule、risk gate 都是驾驶舱的刹车和证据层,
不是用户每天打开 FinHarness 的理由。用户价值必须首先表现为"我现在怎么样、
发生了什么、我该注意什么、有什么可审查选项、什么不能做"。

## 产品边界

FinHarness 的边界用能力层表达,不用防御式品类否定表达:

- 默认体验是 cockpit/runtime:主动巡检、提醒、解释、生成待办和候选项。
- 高后果代理身份必须显式、可撤销、receipt-backed,且不由 READY/PASS 推导。
- 研究、计划、review、paper validation、execution candidate 和 controlled
  execution 是不同层级;低权限对象不能冒充高权限对象。

## 核心三件事(有依赖顺序,不是并列)

这三件不是平行的功能,是一个**地基 → 属性 → 循环**的结构:

1. **状态核心是地基。**
   把账户、资产、负债、现金流、税务事件、风险、目标、文档、收据,变成一个
   **可查询、可计算、可追踪、可版本化**的个人财务状态。没有它,"运行时"无
   东西可看,"治理"无东西可拦。

2. **治理是状态的一个属性,不是独立模块。**
   每一条状态、每一个动作都自带授权级别:`read_only` / `needs_human_confirm`
   / `never_auto`。"安全与授权"不是第六个驾驶舱,是渗透在每条状态里的一列。
   对资本动作链,每一层只授予进入下一层治理步骤的资格,不授予越级执行能力:
   grant 不推 action,action admission 不等于 preflight,preflight 不等于 trade
   approval,trade plan 不等于 order 或 broker execution。

3. **运行时是作用在状态上的循环。**
   它盯住"**相对上次变了什么**",主动浮出:现金流异常、税务节点、风险集中、
   组合漂移、账单遗漏、保险缺口、复盘事项、需要人工确认的动作。

### 推论:驾驶舱 = 状态核心上的视图,不是 6 个产品

投资研究 / 资产配置 / 现金流 / 税务 / 决策复盘 / 安全授权——这些是同一个
状态核心上的**不同视图(view/query)**,不是 6 条独立竖线。判断 FinHarness
是否真的在长成"OS"的硬标准:**加第七个驾驶舱时,它是一个 view,还是又一次
重建?** 必须是 view。

## 路线与成功指标

采用 **路线 A(沿用已建资产)**:第一阶段继续以"可信投资研究与风控证据系统"
为起点,因为仓库已经把交易研究 + 治理那套建好了——在**风险最高的模块**上先
证明治理脊柱成立。

**但成功指标必须是治理形态的,不是收益形态的:**

> 成功 = "一个决策能否**仅凭收据被完整重建和打分**",
> 不是 "我们有没有找到 alpha"。

一旦用收益衡量第一阶段,就会偷偷重建一个交易产品——正是本文要挡的东西。

## 范围纪律

- **先自用,后服务他人。** SEC/FINRA/CFPB 那类监管绝大部分针对"向他人提供
  建议/服务";一个给自己造的工具法律处境轻得多。在它还没改变过你自己一个
  决定之前,不让"服务家庭/他人"的多租户与合规重量上身。
- **先窄后宽。** 价值从窄(交易副驾)到宽(全财务生活)在涨,但数据集成、
  安全/隐私、正确性责任三种成本在指数级涨。先在风险面小的地方把回路跑通。
- **代码不是护城河。** Codex/Claude 让代码极易落地,凡是易建的就不是壁垒。
  护城河是**会随时间累积、无法靠重新 prompt 再生成的东西**:结构化的财务
  状态 + 决策档案。

## 两条校验线(每个产品/工程决策都过一遍)

1. **授权:** 这件事是否位于明确、可撤销的 mandate 内？mandate 内允许 Agent
   作出有效决定；超出范围必须升级，不能靠模型置信度自证权限。
2. **可逆:** 如果这个建议/动作错了,代价是**便宜且可逆**的吗?

两条一起用——授权那条容易自我欺骗,可逆这条更难骗过。几乎所有危险动作都会
在至少一条上亮红灯。

## 硬工程原则(不可放松)

- **默认无高后果授权。** Agent 的自主度必须从 Human-in-the-loop，经
  Human-on-the-loop，逐级到 Human-over-the-loop。每次升级都需要专门授权对象、
  limits、expiry、kill switch、review cadence、receipt、恢复和撤销能力。
- 每个建议必须带 **evidence / assumptions / limitations / claim boundaries**。
- 当前未授权或超出 mandate 的高风险动作必须有**人工确认**。成熟 mandate 内
  的有效 Agent decision 仍须通过 deterministic enforcement，但不永久要求
  每一步点击确认。
- 每个动作必须有 **receipt**(不可变文件证据)。
- 任何"收益 / 合规 / 安全"声明都必须标**证据等级**。
- 前端只能展示和复核边界,**不能放松后端边界**。

## 双轴自主性路线(方向,不是排期)

金融世界可信度：

```text
W0 可信资本事实
→ W1 版本化决策与 mandate
→ W2 Scenario 世界
→ W3 Outcome 与 Reconciliation
→ W4 Learning 与有效政策消费
```

Agent 自主度：

```text
AUT0 Context-aware assistant
→ AUT1 Tool-using reviewer
→ AUT2 Observation-driven durable loop
→ AUT3 Delegated Decision Review
→ AUT4 Autonomous paper capital manager
→ AUT5 Mandate-bound real-world operator
→ AUT6 Continuous personal capital agent
```

Human-in-the-loop 是 AUT0–AUT2 的主要安全模式；AUT3 开始按 mandate 在
in/on-the-loop 之间分级；AUT4 以 human-on-the-loop 监督 paper 管理；AUT5/AUT6
只有在单独授权、安全、法律、恢复和 outcome 证据成立后，才进入
human-over-the-loop 的持续资本管理。

## 三层结构(产品定位,2026-06-21 修正)

个人财务最终一定走到一个真问题:**我的存量资产 + 未来增量现金流,应该如何
分配?** 这天然牵涉投资、再平衡、现金储备、债务、税务、保险、风险暴露。因此
产品结构分成三层:

| 层 | 角色 | 回答 |
| --- | --- | --- |
| **前台 个人财务驾驶舱** | 产品的家 / 心智 | 我有什么、变了什么、风险在哪、现金够不够、今天看什么 |
| **中台 资本分配工作流** | 决策候选(阶段 3+) | 存量怎么调?增量怎么投?现金/债务/保险/税务/投资如何权衡? |
| **后台 研究/交易引擎** | **headless evidence provider** | 为某个候选提供**带证据等级**的证据;执行控制属于单独高权限 surface |

**依赖方向(硬约束):** 候选 →(拉)→ 证据 ←(由)← 研究引擎。研究引擎通过
「挂在某个候选下、带证据等级、历史描述优先」的 evidence 形态服务界面。不能
表达成此形态的复杂度,留在 headless,不上前端。

**模式 = 家 + 工具抽屉。** 资产管理是产品心智的家;交易/研究是从某个候选的
evidence detail 钻进去取证据的工具面,以候选和复盘为入口组织。

行业范式对照(只作方向锚定,不照搬规格):CFP Board 财务规划标准(整合财务
状况 + 替代方案 vs 当前路径分析)对应 stock/flow + options + do-nothing;
BlackRock Aladdin「whole portfolio + common data language」对应前台不暴露引擎
复杂度、后台只做 evidence;FINRA 24-09(AI 仍受既有规则约束,需治理/模型风险/
准确性)与 SEC AI-washing 处罚 → research_evidence 必须带证据等级、历史描述、
非预测,坚持 candidate、少用 recommendation/advice。

## 参考(机构方向,只作方向启发,不照搬规格)

- Morgan Stanley × OpenAI:AI 先增强顾问/人,不替代最终判断。
- BlackRock Aladdin:真正值钱的是"资产全景 + 风险解释 + 决策支持"。
- Intuit Assist:AI 金融产品从聊天走向具体事务处理。
- SEC / FINRA / CFPB / Treasury:核心不是"更聪明",而是"可控、可审计、不过度授权"。

机会是把这些机构级思想**缩小到个人可用**,但**不伪装成机构级合规或自动理财
许可**。
