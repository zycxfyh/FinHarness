# P3 Daily Financial Brief v1 mini-RFC

> 状态:**设计草案(2026-06-24)。DESIGN ONLY — 本 PR 不含实现代码。** 交 design gate。
> 上游:[产品路线 P2](../product/product-roadmap.md)(注:roadmap 编号 P2 = 本设计的产品阶段;
> 本文沿用工程批次 "P3" 指代该 slice)、[产品命题](../product/product-thesis.md)、
> [北极星](../product-north-star.md)。Change-control:[change-control.md](../engineering/change-control.md)。

## 1. Change Class

**C3。** 命中 change-control 触发器:**改变默认行为**(每日 brief 的 section 结构从 4 段
变 10 段固定槽)、**改变用户可见的解释**(brief 是用户每天看的面)、**触及投资边界**
(新增 market context 与 candidate decisions 的用户可见解释,可能被误读为建议)。按
change-control "命中财务/投资 → 升 C3" 规则,定 C3,**需 independent gate**(沿用 RE3
"投资证据用户可见解释" 的先例)。

> 边界(用户拍板,写死):默认只读、不自动生成交易动作;market context v1 = offline /
> historical / source-graded,**联网能力另列独立 C3,不混进 v1**;candidate decisions 必须
> 进入既有 governed proposal 路径;do-nothing option 必须显式存在;所有输出服务
> **Financial Decision Clarity** 七维,不服务收益率/选股/预测。

## 1b. Module Placement / System Boundary (G5)

- 扩展既有 system:**Exposure + Allocation / Daily Brief 读模型**,不是新 system。
- **复用既有 read model**:`compute_exposure`([exposure.py](../../src/finharness/exposure.py))、
  `compute_daily_brief`([daily_brief.py:114](../../src/finharness/daily_brief.py#L114))、
  allocation 候选([allocation.py](../../src/finharness/allocation.py))、`decisions:scan`→governed
  proposal([scripts/record_decisions.py])。**不新增对象、不新增顶级 cockpit tab**;v1 是把
  既有 brief 面**重排为 10 个固定槽**。
- 同类 renderer 次数:`daily_brief` 已存在 → 本次是**重构既有 renderer**,非第 3 次散点,
  无需先抽新共享模块(G5 通过)。

## 2. Current behavior(现状事实,引用文件:line)

`compute_daily_brief`([daily_brief.py:164-189](../../src/finharness/daily_brief.py#L164))今天产出
**4 个 section** + 顶层字段:

| 现有 section | 内容 | 来源 |
| --- | --- | --- |
| change_section | 组合相对上一快照的变化 | `_change_section` |
| Exposure & concentration | 净值、top holding %、HHI、cash runway、计息负债/年息 | `compute_exposure` |
| Upcoming obligations | 到期事项 | `exposure.upcoming_obligations` |
| Needs review | 待 attestation 的 open proposal(取前 5) | `_open_reviews` |

顶层:`headline / net_worth / total_assets / total_liabilities / holdings_change /
open_review_count / data_gaps / source_refs`。
candidate decisions 当前由**独立** `decisions:scan` 生成为 governed proposal,**不在 brief 内露出**。

## 3. Target behavior(10 固定槽)

默认路径产出 **10 个固定槽**(顺序固定,空槽也显式占位,不静默省略):

| # | 槽 | v1 数据来源 | 现状 |
| --- | --- | --- | --- |
| 1 | Net worth snapshot | `exposure.net_worth/total_assets/total_liabilities` | ✅ 有 |
| 2 | Cash / liquidity status | `exposure.cash_runway_months` | ✅ 有 |
| 3 | Exposure map | `exposure` top holding/权重(v1 持仓级;因子级留债) | 🟡 部分 |
| 4 | Concentration risks | `exposure.concentration_*` | ✅ 有 |
| 5 | Leverage / liquidation warnings | `exposure` 计息负债;v1 仅杠杆/负债提示,**无爆仓价**(P5/未来) | 🟡 部分 |
| 6 | Market context | **offline / historical / source-graded** 描述;无预测、无联网 | 🆕 新增(offline) |
| 7 | Candidate decisions | 引用 `decisions:scan` 产出的 governed proposal(只读露出,不新建) | 🟡 重连 |
| 8 | Do-nothing option | **显式槽**:列出"不行动"作为一个对照选项 | 🆕 新增 |
| 9 | Behavioral warnings | 规则化提示(追涨/恐慌/集中/忽视税务);v1 基于既有 exposure flags + 简单规则 | 🆕 新增 |
| 10 | Review prompts | `_open_reviews` + 复盘提示 | 🟡 部分 |

opt-in 路径:v1 **无新 opt-in**。联网 market context、爆仓价估算 = 各自独立未来 slice。

## 4. Surface Inventory

- **输入**:state core(只读)— exposure read model、portfolio snapshots、open proposals、
  offline market-context 数据(source-graded,随状态打包,无外呼)。
- **输出**:10 槽 `DailyBrief`(扩展现有 dataclass)+ dated receipt(沿用 `record_daily_brief`)。
- **外部调用 / 网络面**:**无。** v1 完全 offline。market context 用本地 source-graded 数据。
- **失败面**:某槽数据缺失 → 显式空槽 + 进 `data_gaps`,**不静默丢槽、不编造**。
- **用户可见面**:既有每日 brief 面(重排),**不新增顶级 tab**。
- **排除面(明确不碰)**:联网/实时行情、爆仓价计算、自动交易动作、收益预测、选股、
  新 proposal 对象、proposal scaffold 字段(那是 P4)。

## 5. Default Path Invariant

默认行为**会变**(4 段 → 10 槽),**这是经产品负责人(用户)批准的有意变更**,非偷改。
锁法:

- **现状事实**:今天默认输出 4 个 `BriefSection` + 上述顶层字段
  ([daily_brief.py:164-189](../../src/finharness/daily_brief.py#L164))。
- **不变量(数据保全)**:现有 4 段承载的数据**全部映射进**槽 1–5、7、10,**字段不丢、数值
  不变**;新增仅是槽 6/8/9 的**加法**。用一个**golden 快照测试**(合成 fixture)锁住:
  (a) 槽顺序与数量恒为 10;(b) 原有字段(net_worth/concentration/obligations/open_review_count
  /source_refs/data_gaps)逐字段相等;(c) 缺数据走显式空槽而非消失。
- 影响谁:每日 brief receipt 的 reader / 下游 cockpit 渲染。批准人:产品负责人(本 RFC)。

## 6. Traceability Matrix

| 设计承诺 | 计划代码点 | 测试 | gate 探针 |
| --- | --- | --- | --- |
| 10 槽固定顺序、空槽显式 | `compute_daily_brief` 重排为 10 槽 | golden 快照(槽数=10、顺序固定) | design gate 审结构;`task check` |
| 原 4 段数据零丢失 | 槽 1–5/7/10 复用 `compute_exposure` 字段 | 逐字段相等测试 | implementation gate |
| 默认 offline、无网络面 | 无新外呼;market context 读本地 source-graded | 无网络的离线测试 + grep 无新 http 客户端 | independent gate 核网络面 |
| candidate 只进 governed proposal | 槽 7 只**引用** `decisions:scan` 产出,不新建 | proposal 路径不变测试 | `task governance:check` |
| do-nothing 显式存在 | 槽 8 恒输出 | 断言槽 8 始终非空占位 | design gate |
| 输出服务 Clarity 七维,不预测 | 槽→七维映射(下表) | vocab:lint(无预测/保证措辞) | independent gate(红线措辞) |

## 7. Test / Gate Plan

- **进 `task check`**:golden 快照测试、字段保全测试、offline 断言。
- **进 `task governance:check`**:proposal 路径不变、红线措辞(无 guaranteed/predict/buy-sell)。
- **design gate**(本 PR):审 10 槽边界、C3 定级、默认变更是否被快照锁住、网络面是否真为零。
- **implementation gate**(后续实现 PR):字段保全、空槽行为、receipt 形态。
- **independent / red-team gate**:核 (a) 是否真无网络面;(b) market context 措辞是否滑向
  预测/建议;(c) candidate 是否绕过 governed proposal。**C3 必须独立复核(author ≠ gate)。**

### Clarity 七维映射(说明输出服务判断而非收益)

有状态→槽1/2/3;有风险→槽4/5;有解释→槽6(source-graded 历史描述);有对照→槽7+槽8
(do-nothing);有复盘→槽10;有学习→喂 P4/lesson(债);有行为改善→槽9。

## 8. Not claimed / Debt

- **不主张**:不预测行情、不出买卖指令、不算爆仓价、不联网、不自动执行、不改 proposal
  字段结构。
- **已知债务(明确接受,非遗漏)**:
  - 因子级 exposure map(v1 仅持仓级)→ 未来 slice。
  - 爆仓价/杠杆量化(槽 5 v1 仅定性提示)→ P5 或专项 C3。
  - 联网 / 实时 market context → **独立 C3**,不混进 v1。
  - behavioral warnings v1 是简单规则(基于现有 flags)→ 行为模型化留后续。
  - proposal scaffold 决策字段(decision_intent/thesis/...)→ **P4**,不在本 slice。
