# Slice Plan: 阶段 3 — 资本分配工作流(Capital Allocation Candidates)

Status: draft
Date: 2026-06-21 (revised same day: first-principles discussion + code verification)
North star phase: 3「决策工作流」(see [product-north-star.md](../product-north-star.md)
§五阶段路线 + §三层结构)
Builds on: 阶段 2 暴露图 + 每日简报(see
[2026-06-20-exposure-map-and-daily-brief.md](2026-06-20-exposure-map-and-daily-brief.md))

这是规划 + 执行制品。它**不**授权 live trading、券商写入、上调风险上限或任何
执行;它**不**声称投资、税务、会计正确性。它做的唯一一件新事:把暴露图发现的
风险,变成**带 evidence/assumptions/limitations/收据的只读资本分配候选**。

## 0. 产品定位:三层(已上提至 north star §三层结构)

前台个人财务驾驶舱(家)/ 中台资本分配工作流(本 slice)/ 后台研究引擎
(headless evidence provider)。依赖方向硬约束:**候选拉证据,引擎不驱动界面**;
研究证据只能以「带证据等级、历史描述而非预测」形态挂在候选下。模式 = 家 + 工具
抽屉,不是双主页。详见 north star。

## 0.1 代码核实结论(2026-06-21,决定本 slice 范围)

核实后,治理复核回路**后端 + 前端已端到端建好**,本 slice 因此大幅缩小:

- `GET /proposals`([routes_proposals.py](../../src/finharness/api/routes_proposals.py))
  直接 `select(Proposal)` 读 statecore `Proposal` 表,返回 proposal + attestations
  + open_for_review,自带 `status=all|open|attested` 过滤。
- `POST /proposals/{id}/attest` 已存在(human attest,approved ≠ execution)。
- 前端 Proposals tab([app.js](../../frontend/app.js))已 fetch `/proposals`、渲染
  列表 + 详情 + non-claims + attestations,**并已有 attest 表单**(确认/拒绝)。

因此:用 `create_governed_proposal` 写入的候选会**自动**进入 `/proposals` → 现有
Proposals tab → 现有 attest 表单 → 收据。**不**新建 `/decisions` 端点;**不**新建
Decisions 视图;确认/拒绝 UI **已存在**。本 slice 实质 = 候选引擎 + 记录器 + 一点
前端渲染润色。

## 1. 目标发现 (Goal)

北极星阶段 3:AI 生成候选方案(再平衡、税损收割、现金储备、风险集中、年度
复盘),每个带 evidence/assumptions/limitations/receipt,进入人工复核。成功指标
是治理形态的:**一个决策能否仅凭收据被完整重建和打分**,不是「找到 alpha」。

今天暴露图能算出「现金跑道 2.5 个月」「SPY 集中度 53% 越过 40%」,但到此为止
——没把「那我可以怎么分配资本、代价是什么、不做会怎样」组织成可复核候选。本
slice 跨这一步,永远停在**候选**:do-nothing 始终是显式选项,AI 不替你决定。

Done when:暴露图里每个被 flag 的风险,都能生成一个 governed `Proposal`
(`execution_allowed=false`、带 evidence/assumptions/limitations/non-claims/收据、
含 do-nothing 选项),在现有 Proposals tab 里可读其完整理由、证据来源与选项,
并可经现有 attest 表单人工复核。

## 2. 需求定义 (Requirements)

候选覆盖**存量 + 增量**两维度(可逆性不同,见 §3):
- **存量(stock):** 现有资产是否需再平衡、降集中度、降风险、补现金、还债。
- **增量(flow):** 未来工资/现金流优先去 现金 / 投资 / 还债 / 保险 / 税务准备
  / 目标账户。
- **约束:** 现金跑道、税务窗口、负债利率、保险缺口、风险阈值。

P0 — 候选生成引擎(地基,纯函数):
- 输入 `ExposureReport`(+ 阈值),输出 0..n 个结构化 `AllocationCandidate`。
- 每个候选必带:`detector_kind`(写入 `Proposal.kind`,如 `cash_buffer_low`)、
  `dimension`(`stock`|`flow`)、一句话 `claim`、`evidence`、`assumptions`、
  `limitations`、`options`(含**显式 do-nothing 及其代价**)、`key_risks`、
  `reversibility`、授权行。
- **`research_evidence` 为可选插槽(默认空)**:预留后台研究引擎接入点,
  **本 slice 不接引擎**(见 §3 / §4 backlog)。
- 首批两探测器(取数最短、可逆性最清楚,均偏 flow 侧):
  - `cash_buffer_low`:`cash_runway_months < 阈值` → 选项含「暂停新增投资先补
    现金(flow)」「降低某高集中持仓补现金(stock,标注更高代价/不可逆)」。
  - `concentration_high`:`top_holding_weight ≥ 阈值`(复用
    `ObservationThresholds.concentration_pct`)→ 选项含「新增现金流优先投向其他
    资产(flow)」「分批减仓进入人工复核(stock)」。**不下单、不给目标价。**
- 纯函数,不写库。

P1 — 治理化持久与收据:
- 经**已有** `statecore/proposals.py::create_governed_proposal` 写成通用 `Proposal`
  行 + 收据。`Proposal.kind` = `detector_kind`;**receipt kind 仍是
  `state_core_proposal`**(由 `create_governed_proposal` 硬编码,不改)。
- **幂等 + append-only 收据(见 Progress Log d)**:同 as-of + 同 detector_kind →
  同 proposal_id;`Proposal` 行是**当前态**(upsert)。收据文件**append-only**:每次
  内容变化写一份新修订(`receipt_<id>_<stamp>_<hash8>.json`),receipt index 保留所有
  修订,Proposal 指向 latest,新修订 `supersedes` 指回上一版,形成可复盘链。内容
  未变的重扫是 **no-op**(不产生冗余修订),所以审计链只记录"何时变了什么",无噪声。

P2 — 前端渲染润色(小):
- 现有 proposal 详情视图把 `evidence` / `options` / `dimension` / `assumptions`
  / `limitations` 渲染清楚(目前主要渲染 rows + non-claims + attestations)。
- **不**新建 Decisions 视图、**不**新建 `/decisions` 端点;后续复盘只在现有
  Proposal 详情里读 proposal 自身的只读 revision 子资源。

Non-goals(本 slice):新建 `/decisions` 端点或 Decisions 视图(复用 `/proposals`
+ Proposals tab);真正接入研究/交易引擎(留窄契约 + backlog);任何执行、下单、
转账、报税提交、改上限(B5);收益序列风险(vol/drawdown/VaR,等序列再上
QuantStats/Riskfolio);FX 自动换算(混币种仍标 data gap);mode 切换界面;
实时未落库候选预览(若做须标 `draft_unrecorded`,本 slice 不做)。

## 3. 架构设计 (Architecture)

```
ExposureReport (阶段 2,纯只读;边界为 float)
        │
        ▼
allocation.py: compute_allocation_candidates(report, thresholds)  ← FOUNDATION (P1)
        │   纯函数 → tuple[AllocationCandidate, ...],不写库
        │   .research_evidence: tuple[...] = ()   (插槽,本 slice 留空)
        │
        └── record_allocation_candidates(engine, receipt_root, as_of)  ← P1
                复用 create_governed_proposal(idempotent=True)
                CLI: scripts/record_decisions.py / task decisions:scan
                        │
                        ▼  (持久化后自动可见,无需新端点)
        现有 GET /proposals → 现有 Proposals tab → 现有 attest 表单 → 收据

[后台 研究/交易引擎] --(窄契约,backlog)--> research_evidence 插槽
```

Decisions(已据实核对代码):
- **复用通用 `Proposal`,不碰交易域 `ProposalCandidate`。** `Proposal` 在 DB 层有
  `CheckConstraint(execution_allowed=0)` + field validator 双锁执行权,
  `authority_level` 默认 `needs_human_confirm`。
- `compute_allocation_candidates` 是**纯函数**(无写入)→ 易测、可复用;持久化与
  收据是 `record_*` 的职责。
- 候选**消费 `ExposureReport`,不重算**:暴露图是唯一事实源。
- **证据数字的精度纪律(规格点):** `ExposureReport` 边界是 **float**。候选 `evidence`
  里的触发指标(跑道月数、集中度%)作为**描述性 float** 存,**不声称 exact**,并带
  `source_refs`(snapshot_id + exposure as_of)保证**可重建**(= 北极星「仅凭收据
  重建」)。任何**作为金额**呈现的值用 **Decimal string** 从精确路径取,不从 float
  报告取。头两探测器为比率触发,float 描述性 + source_refs 即足。
- **可逆性排序(第一性):** 增量(flow)比存量(stock,卖现有持仓触发税/不可逆)
  更便宜可逆 → 候选**优先给 flow 选项**,stock 选项标注更高代价并强制人工复核。

Rejected / 本 slice 明确不做:
- 新建 `/decisions` 端点 / Decisions 视图(已有 `/proposals` + Proposals tab)。
- 新建持久化 `Decision` 状态表(候选是派生视图;只在写 governed `Proposal` 时
  落库 + 收据)。
- **真正接入研究/交易引擎。** 只定义 `research_evidence` 插槽 + 窄契约(候选问具体
  问题 → 引擎回带证据等级的证据束);接线是后续单独 task。理由:头两候选纯用
  暴露图即可算,过早拖入 8,700 行引擎违反务实/渐进原则。
- 实时未落库候选冒充已记录(若做须标 `draft_unrecorded` 且无 receipt_ref)。
- 任何「目标价 / 下单数量 / 一键执行」字段(B5);两个对等产品脸 / mode 切换。

## 4. 任务拆分 (Tasks,一条条做,每条过 `task check` + 回归测试)

- **P1 — 候选引擎 + 记录器(地基)。** `src/finharness/allocation.py`:
  `AllocationCandidate` 模型(含 `detector_kind`/`dimension`/`options`/
  `research_evidence` 空插槽)+ 纯函数 `compute_allocation_candidates(report,
  thresholds)`(`cash_buffer_low` + `concentration_high`)+
  `record_allocation_candidates(engine, receipt_root, as_of)`(复用
  `create_governed_proposal(idempotent=True)`)。`scripts/record_decisions.py` +
  `task decisions:scan`。
  测试:触发/不触发/空状态;do-nothing 永在;flow 选项先于 stock;
  `execution_allowed=false` 端到端;`Proposal.kind` = detector_kind 且 receipt kind
  = `state_core_proposal`;evidence 带 source_refs;同 as-of 重扫幂等(不重复)。
- **P2 — 前端渲染润色(小)。** 现有 proposal 详情渲染 evidence/options/dimension/
  assumptions/limitations。served-shell 测试断言新字段出现。
- 计划落地后:**live uvicorn + curl 冒烟**验「scan → /proposals 出现候选 → attest」
  整条(阶段 2 教训:冒烟能抓单测漏掉的真 bug)。

后续(本 slice 之后,各自一条 task + 回归测试):
- DONE `rate_exposure_high`(见 Progress Log b)。
- DONE `cash_overweight` 探测器(现金占比过高 = 现金拖累,见 Progress Log f),
  与 concentration 互补(concentration 现已排除现金,见 Progress Log c)。
- 待做:`tax_window`、`insurance_gap`、`annual_review`(接 `lesson_loop` → B4)。
- DONE append-only / content-hash 收据(见 Progress Log d)。
- DONE proposal revision 复盘端点/视图(见 Progress Log e)。
- **研究证据窄契约:** 定义「证据请求 → 带等级证据束」接口,把 vol/回撤/流动性/
  税务窗口作为**历史描述性证据**(非预测、自带 limitations)填入 `research_evidence`。

## 5–7. 实现 / 评审 / 测试 (gates)

每条 task 的评审闸门:
- **授权线**:增强人的判断,还是诱导 AI 越权替人决定?(必须前者)
- **可逆线**:候选错了代价便宜可逆吗?是否显式给出 do-nothing 代价?flow 先于 stock?
- 是否保持只读 + `execution_allowed=false`?(本 slice 不引入任何写端点)
- evidence 是否遵守精度纪律(float 描述性 + source_refs 可重建,金额用 Decimal
  string,不冒称 exact)?
- 是否复用现成治理路径(`create_governed_proposal`/`Proposal`/`/proposals`/attest
  表单)而非另造?
- **研究证据(若有)是否标注证据等级、为历史描述而非预测?**(防 alpha 后门 /
  SEC AI-washing)
- 是否服务 B0 觉察,而非只加仪式?候选是否真带 evidence + 收据可复重建?

Adopt / 复用映射:
- 候选写入 → `statecore/proposals.py`(governed Proposal + 收据 + non-claims)。
- 集中度阈值 → `ObservationThresholds.concentration_pct`。
- 暴露数字 → 阶段 2 `compute_exposure`,不重算。
- 列表/详情/确认/拒绝 → 现有 `GET /proposals` + `POST /proposals/{id}/attest` +
  前端 Proposals tab(attest 表单已存在)。
- 研究证据 → 后台引擎经**窄契约**降维为证据,backlog。

Testing:每条 task 后 `task check` green;每条 ship 回归测试;落地后 live 冒烟。

## Non-Claims

- 资本分配候选是对镜像状态的**描述性提示 + 证据组织**,不是投资/税务/会计建议,
  不保证正确性,不保证收益。
- **do-nothing 永远是有效选项**,每个候选显式给出「不做」的代价。
- 候选**不含**目标价、下单数量、执行步骤;approval 只记录人工复核,**不是执行
  授权**。
- **研究/交易引擎仅作证据来源**,不主导决策、不暴露执行;其证据为历史描述,非预测。
- 数据缺口(未定价持仓 / 混币种 / 缺现金流)继续如阶段 2 披露,不静默估值。

## Progress Log

- DONE P1 — `src/finharness/allocation.py`:`AllocationCandidate`/`CandidateOption`
  模型 + 纯函数 `compute_allocation_candidates` + `record_allocation_candidates`
  (复用 `create_governed_proposal(idempotent=True)`),探测器
  `cash_buffer_low`(flow)与 `concentration_high`(stock);新增阈值
  `ObservationThresholds.cash_runway_target_months=6.0`;CLI
  `scripts/record_decisions.py` + `task decisions:scan`;回归测试
  `tests/test_allocation.py`(触发/静默/幂等)。
  - 验证:`task check` exit 0(**448 tests OK**,445 基线 +3);
  - Live 冒烟(uvicorn + curl,隔离临时库):`record_decisions.py` 写出 2 候选 +
    收据落盘;`GET /proposals?status=open` 返回两候选(dimension=flow/stock、
    options=[do_nothing, flow, stock]、execution_allowed=false);
    `POST /proposals/{id}/attest` 拒绝其一 → 转入 attested(open 2→1),
    `approved_is_not_execution_authorization=true`。**无新增端点/视图**,候选经现有
    `/proposals` + attest 回路端到端贯通。
- DONE P2 — 前端 `renderCandidateDetail`(frontend/app.js):现有 proposal 详情视图
  在 trading 域 proposal 之外,额外渲染资本分配候选的 Dimension / Trigger evidence
  (描述性标量 + source_refs)/ Options(do_nothing·flow·stock,各带 cost +
  reversibility)/ Key risks / Reversibility / Assumptions / Limitations;无 dimension/
  options 的 proposal 安全跳过。served-shell 测试
  `test_cockpit_renders_allocation_candidate_detail` 断言接线。
  - 验证:`task check` exit 0(**449 tests OK**)。**不新建视图/端点**:候选经现有
    Proposals tab 即可读全部理由与选项。

## 阶段 3 收尾

P1 + P2 完成 = 北极星阶段 3「决策工作流」首条 slice 落地:暴露图 → 资本分配候选
(cash_buffer_low / concentration_high)→ governed Proposal + 收据 → 现有
`/proposals` + Proposals tab(含 evidence/options/dimension 渲染)→ 现有 attest
回路。全程只读、`execution_allowed=false`、do-nothing 永在、flow 先于 stock。
后续探测器(tax/insurance/annual_review)与研究证据窄契约见 §4 backlog,
按「渐进更新」按需推进;`cash_overweight` 已作为后续增量在 Progress Log f 落地。

## 真实数据接入与后续增量(2026-06-21)

- 接入官方 `bean-example`(seed 42)生成的多年真实账本 → `task beancount:import` →
  全管线在真实数据上验证(net worth $109,326、RGAGX 48.4% 集中度、cash_buffer)。
- DONE (a) 现金流派生 — beancount 适配器从账本 Income/Expenses 派生**经常性月
  收入/月支出**(单一操作币种、尾窗 6 月均值、剔除部分月),写为 source 化
  `CashflowEvent`(再导入即替换);并把 `exposure._cash_runway` 由「净烧钱率」修正为
  **CFP 应急金标准「现金 ÷ 月支出 = 可覆盖月数」**(代码原文档/计划本就如此声称,
  实现此前与之背离)。效果:示例账本此人净储蓄 +$3,341/月,但应急现金仅 1.0 月 →
  `cash_buffer_low` 如实触发(旧口径会漏报)。回归测试:
  `test_recurring_cashflows_are_derived_and_replaced_on_reimport`、更新
  `test_exposure` 跑道断言。`task check` exit 0(450 tests)。
- DONE (b) `rate_exposure_high` 探测器 — 键于暴露图既有
  `interest_bearing_debt_total / weighted_avg_interest_rate / annual_interest_estimate`
  + 新阈值 `ObservationThresholds.high_interest_rate_pct=0.10`;dimension=stock,
  options=do_nothing·flow(额外本金)·stock(再融资,人工复核)。**注意**:beancount
  账本不编码利率,故在示例账本上**休眠**(无利率数据);经 personal-finance CSV
  导入或账本账户 metadata(future)提供利率后即触发。回归测试:
  `test_rate_exposure_candidate_fires_on_high_rate_debt`、
  `test_low_rate_debt_does_not_trigger_rate_candidate`。`task check` exit 0(452 tests)。
- DONE (c) 代码评审三处修正:
  1. **集中度排除现金** — `exposure._holdings` 此前把 USD/CASH 算进 long book,
     现金多的人会被建议「Trim USD / single-name risk」(语义 bug)。改为集中度只算
     **非现金证券**(现金走 `cash_total`);holdings 列表不再含现金,
     `concentration_high` 永不会拿现金当持仓。`holding_count` / `top_holding_weight` /
     `concentration_hhi` 语义随之变为「证券口径」。更新 `test_exposure` 断言。
  2. **精度纪律措辞收紧** — allocation.py docstring 原称「金额必须来自 Decimal path」
     与实际(evidence 内 cash_total/monthly_net 来自 ExposureReport float)不符;改述为
     这些是**display rollup**(描述性 float、经 source_refs 可重建),不冒充可对账金额。
  3. **「不可变收据」改口** — 实为每 as-of 一份的**幂等当前态收据**(再扫描覆盖当日
     同名,非 append-only);文档(§2 P1)已改口,append-only/content-hash 收据入 backlog。
- DONE (d) append-only / content-hash 收据(把"复盘链"做实)— `create_governed_proposal`:
  `Proposal` 行保持当前态(idempotent upsert);**receipt 文件改为 append-only 修订**
  `receipt_<id>_<stamp>_<hash8>.json`,receipt index 保留每个修订(历史),Proposal 指向
  latest,修订 payload 带 `content_hash` + `supersedes`(指回上一版)形成可复盘链。
  **内容去重**:内容未变的幂等重扫是 no-op(不产生冗余修订),因此既不破坏现有
  `/proposals`,也守住 `test_daily_change_brief` 的"同数据重跑收据数不变"约束。不破坏
  非幂等路径(API POST 仍每次一份)。回归测试 `test_governed_proposal_receipts`
  (no-op 不增修订;内容变则 +1 修订、supersedes 链、两份文件并存、content_hash 不同)。
  真实 DB 复跑确认幂等 no-op(2/2 不变)。`task check` exit 0(456 tests,含
  A→B→A 回归:回到旧内容仍追加新修订,不覆盖旧收据)。
- DONE (e) proposal revision 复盘端点/视图 — 新增只读
  `GET /proposals/{proposal_id}/revisions`:从当前 `Proposal.receipt_ref` 沿
  `supersedes` 链 latest-first 回放每个 proposal receipt 的 content_hash / receipt_ref /
  proposal snapshot,返回 `execution_allowed=false`;前端仍在现有 Proposals tab 详情里
  渲染 Revisions,不新建 Decisions 视图/端点。
- DONE (f) `cash_overweight` 探测器 — 键于暴露图既有 `cash_total / total_assets`
  和 `cash_runway_months`;新增阈值
  `ObservationThresholds.cash_overweight_pct=0.50`。只有当现金跑道已达到
  `cash_runway_target_months` 后才触发,避免与 `cash_buffer_low` 同时给出互相拉扯的
  现金信号。dimension=stock,options=do_nothing·flow(未来盈余先按目标分配)·stock
  (分批移动现有现金至目标/还债/投资,人工复核)。回归测试:
  `test_cash_overweight_candidate_fires_only_after_buffer_target`、
  `test_low_cash_runway_blocks_cash_overweight_candidate`。验证:
  targeted `tests.test_allocation` 7 tests OK;最终全量见本轮执行收据。
