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
- DONE `insurance_gap` 探测器(coverage review gap,非精算,见 Progress Log g;第三轮 gate PASS)。
- DONE `tax_window` 探测器(deadline/预缴/文档复核,非税务建议,见 Progress Log h;第二轮 gate PASS)。
- `annual_review`(接 `lesson_loop` → B4):**设计 gate PASS**(见 §annual_review 设计),
  待 author 实现 N1/N2。
- DONE 把候选 `source_refs` 从 **report 级聚合**收窄为 **detector 级最小 provenance**
  (见 Progress Log i;第三轮 gate PASS)。
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

## annual_review 设计(Architect 设计 gate PASS,2026-06-21)

阶段 3 最后一条 slice。**它是复盘报告,不是 allocation 候选**:复用 `daily_brief` 的
`compute_+record_` 模式(纯函数 + dated receipt),**不进 `_DETECTORS`、不写 `Proposal`**。
它综合既有只读状态,回答 B0 第 7 问"过去决策的结果与教训"。

**4 个 fork(已定)**
1. 报告 vs 候选 → **报告**(`compute_annual_review` + `record_annual_review`)。
2. lesson→rule → **只报告闭环,不自动改规则**(改规则是人工/governed 动作)。
3. 端点 → **本 slice 不新增**;经 `/receipts?kind=annual_review` + `/timeline` 浮现;
   `/brief/annual` 留到 cockpit 复盘视图再加。
4. period → **默认滚动 12 个月,显式支持自然年**;模型必含
   `period_start` / `period_end` / `period_label`;CLI `--year 2026`,默认 = as_of 往前 12 月。

**数据源(全部已存在,只读综合)**
- `Proposal` 表 + revision 链(supersedes)→ 期间候选 + 演变。
- `Attestation` 表 → approved / rejected(approved≠execution)。
- 持久化 lesson 收据(`lesson_loop.LESSON_RECEIPT_ROOT` = `data/receipts/lessons`)+
  `lesson_loop.scan_receipts` / `build_observations` / `build_proposed_rule_changes`。
- `rule_change_ledger.load_rule_changes()` / `audit_untraceable()` / `is_traceable()` /
  `RuleChange.lesson_draft_id`。

**输出 `AnnualReview`(+ sections)**
- period(start/end/label)。
- 决策面板:期间候选数、按 kind 分布、open vs attested、approved vs rejected。
- 演变:有 revision 的候选(证据变过的)。
- B4 闭环:已持久化 lesson 中,被 human-promoted RuleChange 闭环的 vs **未闭环的(flag)**;
  外加 `audit_untraceable()` 的反向缺口(无 lesson 溯源的规则改动)。
- data gaps;`record` 成 dated receipt(`kind="annual_review"`)。

**Codex 设计 gate 的 3 条必入修订(实现时遵守)**
1. `compute_annual_review` **不得调用 `draft_lessons()`**(它生成 UUID/当前时间,破坏纯计算);
   改用 `scan_receipts` / `build_observations` / `build_proposed_rule_changes`,再**按 period 过滤**。
2. B4 闭环用 `load_rule_changes()` / `audit_untraceable()`,以 `lesson_draft_id` 判断**已持久化
   lesson** 是否被 human-promoted rule change 闭环(不是用临时 draft)。
3. revision 链读取要把 **receipt 缺失 / 损坏 / cycle 写进 `data_gaps`**,不得让年度报告崩溃。

**边界(红线)**:只读、`execution_allowed=false`、描述性非建议;B4 不自动改规则;复用 receipt 模式。

**任务拆分(gate 后 author 侧)**
- N1 `src/finharness/annual_review.py`:`AnnualReview` model + `compute_annual_review(engine, *,
  as_of_date, period)`(纯)+ `record_annual_review(...)`(dated receipt)。单测:决策面板计数、
  revision 演变、B4 闭环(闭环 vs 未闭环)、period(滚动 12 月 vs `--year`)、data gap(缺失/损坏/
  cycle 不崩)。
- N2 CLI `scripts/record_annual_review.py` + `task review:annual`(`--year` 可选)。

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
- DONE (g) `insurance_gap` 探测器(**coverage review gap,不是精算**)— 角色路由:
  Claude 作者侧实现,Codex 总领 + 独立验收。`exposure.py` 新增保险复核摘要
  (`ExposureReport.insurance_active_count` + `insurance_review_gaps`,经
  `_insurance_review`);`allocation.py` 新增 `_insurance_gap_candidate`(dimension=flow:
  首动作是收集保单/补数据/安排复核,不是立刻买保险)。触发(保守):有保单在册但
  无 active;active 保单 coverage_amount<=0;缺/不可解析/已过期(renewal_date <
  as_of 仍 active)的续保日期。**设计决定(已对齐 quiet-on-no-data 不变量并提交独立
  验收)**:零保单视为**暴露图 data gap**(`no insurance policy on record`),**不**当
  governed 候选,以免空 state 唠叨;有保单后才进入候选流。框定为"覆盖证据缺失/过期/
  不可复核,建议人工 review",limitations 显式声明非精算/未建模家庭结构/收入替代/
  风险画像。`execution_allowed=false`,复用 `/proposals`,不新增端点/视图。回归测试:
  missing-renewal / expired-renewal / none-active 触发,healthy 不触发,零保单=data gap
  非候选(`tests.test_allocation`)。
  - **第一轮 gate BLOCKED → 已修(证据链 blocker)**:Codex 独立验收发现
    `compute_exposure` 的 `source_refs` 只取 portfolio snapshot,导致 insurance-only
    场景候选 `source_refs=[]`,违反"evidence 带 source_refs 可重建"。修复:`source_refs`
    现**聚合所有参与状态来源**(snapshot + positions + liabilities + cashflows + tax +
    insurance),一并修掉 `rate_exposure`/`cash_buffer` 同源漏洞。回归测试
    `test_insurance_gap_candidate_carries_policy_source_refs`(保单 source_refs 必现于
    候选 evidence)。
  - **第二轮 gate BLOCKED(类型门禁)→ 已修**:source_refs 功能 live-smoke 通过,但
    混合 tuple loop 被 mypy 收敛到 `StateCoreBase`(无 `source_refs`)→ task check 在
    mypy 失败。修复:改为**一类一类显式 loop**(per-type)保持类型窄化,不引 Protocol/
    cast。措辞红队顺带软化:`Adjust/add/replace a policy` → `Review potential policy
    changes`。验证:`task typecheck` 137 文件 0 issue;`task check` exit 0;**464 tests OK**。
  - **第三轮 gate PASS(Codex 独立验收)**:per-type loop 已落地、source_refs 探针证实
    cash/rate/insurance 三类候选均带非 snapshot 来源 refs、live smoke 通过、`task check`
    exit 0。`insurance_gap` 验收通过。非阻断债务(Codex 记录):①未来可把 source_refs
    从 **report 级聚合**收窄为 **detector 级最小 provenance**(当前够重建但偏宽);
    ②本 slice 尚未 commit(作者侧 4 文件变更)。
  - insurance_gap 已于 `b5ea83e` 结构化提交(4 文件,Release Manager 收口)。
- DONE (h) `tax_window` 探测器(**deadline / 预缴 / 文档复核,不是税务建议**)— 角色路由:
  Claude 作者侧,Codex 总领 + 独立验收(待 gate)。`exposure.py` 新增
  `_tax_review` + `ExposureReport.tax_review_gaps`;`allocation.py` 新增
  `_tax_window_candidate`(dimension=flow:首动作确认状态/记录金额/设提醒/预留资金)。
  触发(保守,复用 `TaxEvent.status` 区分已处理):未处理且在 horizon 内的 deadline、
  未处理且已过期的 deadline(confirm status)、缺/不可解析 due_date、estimated_payment
  无/零金额。**已 paid/filed 等状态不触发**(不对已缴税唠叨)。零税务事件=暴露图
  data gap 不出候选(同 insurance,守 quiet-on-no-data)。边界严守:limitations 显式
  声明**非税务建议、不计算应纳税、不优化税、不建议申报/缴款时点、不套用辖区规则**;
  `execution_allowed=false`,复用 `/proposals`,无新端点/视图。回归测试(`tests.test_allocation`):
  upcoming-deadline / past-due-unhandled / missing-estimated-amount / missing-due-date /
  unverifiable-due-date 触发,已 paid 不触发,零事件=data gap,source_refs 携带回归。
  - **第一轮 gate BLOCKED(ruff E501)→ 已修**:`test_allocation.py:417` 内联表达式超 100 列;
    改用局部变量。同时**修正作者侧验证方法缺陷**:此前 `task check 2>&1 | tail` 读到的是
    `tail` 的退出码而非 `task check` 的,误报过 exit 0;改为不经管道、`echo REAL_EXIT=$?`
    捕获真实退出码。另按 Codex 建议补 missing/unverifiable due_date 两条持久回归测试。
    验证:`ruff check .` 全树 All checks passed;`task check` **REAL_EXIT=0**;**472 tests OK**
    (464→+8);工作树仅本 slice 4 文件。
  - **第二轮 gate PASS(Codex 独立验收)**:targeted 47 tests OK、source_refs 探针(tax 候选带
    TaxEvent 来源 refs)、live uvicorn smoke(/health、/proposals、/proposals/{id}/revisions 全通、
    execution_allowed=false、revision 可回放)、`task check` exit 0(ruff/mypy 137 文件/472 tests/
    properties/rules/experiments/promptfoo)。税务措辞红队:可接受(框在 deadline/records review,
    不计算税额/不优化/不建议申报缴款时点)。非阻断债务:source_refs 仍 report 级聚合(与 insurance
    一致,适合后续统一收窄)。Release Manager 结构化提交 `ef0fee2`。
- DONE (i) **source_refs 最小 provenance 清债**(横切治理,Codex 两轮 gate 重复记录的债)—
  角色路由:Claude 作者侧,Codex independent gate(打 source_refs 泄漏/mypy/live scan)。
  `exposure.py` 新增 `ExposureProvenance`(按域:portfolio/cash/cashflow/liability/tax/
  insurance),`compute_exposure` 按域聚合;`ExposureReport.source_refs` **保留为全局 union
  不破 API**。`allocation.py` 各 detector 改取自己域(`_refs(...)`):cash_buffer=cash+cashflow、
  concentration=portfolio+cash、rate=liability、insurance=insurance、tax=tax。
  回归测试:`test_candidate_provenance_is_domain_scoped`(各域只带自己 refs + 跨域泄漏断言 +
  report union 不变)。无新端点、无前端改动。
  - **第一轮 gate BLOCKED(证据治理)→ 已修**:Codex red-team 发现 `cash_overweight` 的
    claim/evidence 含 `cash_runway_months`(来自 cashflows),但只给了 portfolio+cash →
    **无法用自己的 source_refs 重建自己的声明**(违反 metric_precision 承诺)。修复原则确立:
    **detector 的 source_refs 必须覆盖它 evidence/claim 引用的一切域**。具体:`cash_overweight`
    → **portfolio+cash+cashflow**;并把 **snapshot ref 纳入 cash 域**(它是 `cash_total` 乃至
    `cash_total==0` 的来源)。测试相应改为 `test_cash_overweight_provenance_includes_cashflow`
    (必含 cashflow ref);`cash_buffer_low` 期望同步含 snapshot ref。
  - **第二轮 gate BLOCKED(同类边角)→ 已修**:有 cashflow 但**无 portfolio snapshot** 时,
    `cash_total=0` 是**未经证实的 0**,cash_buffer 却据此声称"covers 0.0 months"且只带 r_flow。
    修复:`ExposureReport` 新增 `cash_total_verified`(= snapshot 是否存在);无 snapshot 时加
    data gap `no portfolio snapshot on record; cash total not verified`,且 `cash_buffer_low`
    在 `cash_total_verified=False` 时**不触发**。**比 gate 字面建议更稳**:gate 建议"provenance.cash
    为空时不触发",但合成场景下 snapshot 可能 `source_refs=[]` 使 provenance.cash 也空(却有
    snapshot)——真正可靠信号是 snapshot 存在性,故用 `cash_total_verified`。有 snapshot 但无现金
    持仓仍触发(snapshot 已证现金缺席)。回归测试 `test_cash_buffer_does_not_fire_without_a_portfolio_snapshot`。
  验证:`task check` **REAL_EXIT=0**(写入独立 exit 文件);`ruff` All checks passed、`mypy`
  137 文件 0 issue、**475 tests OK**(472→+3)、property/promptfoo 过;工作树仅本 slice 4 文件。
  - **第三轮 gate PASS(Codex 独立验收)**:三场景 provenance 探针(no-snapshot+cashflow → 不出
    候选 + data gap;有 snapshot 低现金 → cash_buffer 带 r_cash/r_flow/r_snap;无 snapshot 但
    tax/insurance/rate → 各自独立触发带对应 refs)、`task check` exit 0、真实 uvicorn smoke
    (/health、/exposure、/proposals;no-snapshot 不写 proposal、有 snapshot 正常写)。
    残留:更宽的"上游数据源 provenance 完整性"作为后续质量闸门单列,非本 slice 引入。
    Release Manager 结构化提交 `3a188c1`。
- DONE (j) `annual_review`(阶段 3 最后一条 slice;**复盘报告,非候选**)— 角色路由:
  Architect 设计 gate PASS → Claude 作者侧 N1/N2 → Codex independent gate 第一轮 BLOCKED
  → Codex 作者侧修 3 处设计门问题 → independent gate(待)。
  N1 `src/finharness/annual_review.py`:`AnnualReview` model + `compute_annual_review`(纯)+
  `record_annual_review`(dated receipt,kind=`annual_review`),复用 daily_brief 模式,**不进
  `_DETECTORS`、不写 Proposal、不新增端点**。综合 5 源:Proposal/Attestation(决策面板:计数/
  按 kind/open/attested/approved/rejected)、revision 收据(演变计数)、持久 lesson 收据 +
  `rule_change_ledger`(B4 闭环:已闭环 vs 未闭环 flag + `audit_untraceable` 反向缺口)。
  period 默认滚动 12 月、`year=` 选自然年(`period_start/end/label`)。**遵守 3 条设计修订**:
  不调用 `draft_lessons()`(用 `scan_receipts` / `build_observations` /
  `build_proposed_rule_changes` + `load_rule_changes`/持久 lesson 收据);B4 以 `lesson_draft_id`
  判闭环且只认 period 内已发生、`is_traceable()` 的 rule change;revision 链从
  `Proposal.receipt_ref` 沿 `supersedes` 读真实收据,缺失/损坏/cycle → 写 `data_gaps` 不崩。
  N2 CLI `scripts/record_annual_review.py`
  (`--year` 可选)+ `task review:annual`;`.gitignore` 加 `data/receipts/annual-review/`。
  回归测试 `tests/test_annual_review.py`(决策面板/滚动 vs --year/B4 闭环/损坏收据 data gap/
  演变+record + 未来 rule change 不关过去 lesson + revision 缺失/损坏/cycle data gap +
  lesson_loop signals 接入)8 项。验证:作者侧 CLI 自检(默认 + --year)、`task check` REAL_EXIT(见本轮收据)。
  第三轮独立 gate PASS(Codex 作者侧修 3 blocker;Claude gate 复验:revision 链读真实收据、
  B4 point-in-time 闭环、lesson_loop 接入)。Release Manager 结构化提交 `cf7dc22`。
- DONE (k) **阶段 4 S4-R1:Proposal Revision Review View**(把复盘链接到 cockpit)。
  - step 1 **shared revision walker**:`statecore/proposal_revisions.py`(`walk_proposal_revisions`:
    receipt_ref→supersedes 读真实收据、anomaly codes 全、可选 path guard、cycle/depth/kind/
    proposal_id 校验、latest-first、halt-at-first-anomaly),routes 与 annual_review 都 delegate
    给它(anomaly→HTTP / anomaly→data_gaps),消除两处重复。Codex 作者侧,**Claude gate PASS**
    (10 项测试 + 独立反例探针)。Release Manager 提交 `1e03839`。
  - step 2 **版本间 diff**:cockpit Proposal 详情每版下展示「Changes from previous」
    (`describeRevisionChanges` 客户端比较相邻版本 claim/evidence/assumptions/limitations,
    标量老→新、复杂值压缩),最旧版标 Initial version。纯前端、无新端点、只读。
    **Codex gate PASS**(node 算法探针 + DOM-stub 探针)。Release Manager 提交 `9f1e525`。
  - step 3 **jsdom DOM 测试**:`frontend/tests/revision_history.test.cjs` 加载真实
    index.html + app.js,断言 `renderRevisionHistory` 真渲染出 diff/Initial/empty;
    `task test:frontend` 并纳入 `task check`。**纠错记录**:作者先误判"环境装不了 npm"(从一次
    npm 内部 bug 跳结论),经用户提示改用 **pnpm 一次装上 jsdom**(registry 实测可达)——
    见记忆 [[dont-declare-blocked-from-one-failure]]。真·浏览器 Playwright E2E 仍作独立 D8
    基建 slice。验证:`task check` **REAL_EXIT=0**、jsdom 阶段在 check 内通过。**待 Codex gate**。
