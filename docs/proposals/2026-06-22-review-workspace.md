# Review Workspace — ReviewEvent / Annotation / Archive (S4-R2 mini-RFC, C3)

Architect 设计稿,2026-06-22。**设计 gate 用,不开码、不新增 API 实现**(本稿只锁边界)。
按 [mini-rfc 模板](../templates/mini-rfc.md)。把阶段 4 从"能复盘"推进到"能协作复核":人类对 governed
proposal 的**批注 / 归档 / 重开**成为一等、受治理、可审计的行为,而不反向驱动证据或决策。

### 1. Change Class
**C3**(PM 指定取强 gate)。命中触发器:**新增人类写入 state 的治理面**(annotation/archive)、**用户可见解释**
(复核时间线)、**审计边界**(每个人工动作要可复盘)。不联网、不碰执行。走 mini-RFC + surface inventory +
independent gate + governance:check 硬化。

### 2. Current behavior(现状事实,可引用)
- **Proposal 不可变**([models.py](../../src/finharness/statecore/models.py)):无 `status` 字段;evidence/claim/refs 定死,`execution_allowed=False`。
- **Attestation** 是独立表 + receipt:`decision ∈ {approved, rejected}`、`attester`、`reason`(均必填),append。
- **状态是派生的**:[routes_proposals.py](../../src/finharness/api/routes_proposals.py) `open`=无 attestation / `attested`=有;无 archive、无 annotation、无统一事件账本。
- cockpit:proposal 详情 + revision diff(只读);确认/拒绝走 attest 表单。

### 3. Target behavior
- 新增**附加的 append-only `ReviewEvent` 账本**:`kind ∈ {annotation, archive, reopen, compare_mark}`,每条
  receipt-backed、`execution_allowed=False`、带 `attester`+`reason`(沿用 attestation 的"具名人 + 书面理由"约束)。
- **Attestation 不变、仍是决策 of record**(approve/reject);ReviewEvent **不**替代它,可经 `attestation_ref` 引用它。
- **Archive 是事件,不是 Proposal 上的可变状态**:`is_archived` 像 `attested` 一样**派生**自最新的 archive/reopen 事件;
  Proposal 保持不可变、append-only 历史(archive→reopen→archive 全留痕)。
- **Review Workspace = 既有 proposal 复核面的增强**,不是新顶级 dashboard:每个 proposal 一条**合并时间线**
  (attestations + review events 按时间只读渲染)+ 最小人工写入(加批注 / 归档 / 重开,均显式确认)。复用既有
  cockpit 渲染原语 + revision-history 模式。
- **旧 `/proposals` 默认语义不变**:现有端点**默认仍返回 all**,archive 事件**绝不**悄悄改变它。"默认隐藏 archived"
  只在 **显式 opt-in** 下成立——新增 `archive=active|all|archived` 查询参数(缺省=`all`,= 今天),或一个独立的
  workspace 读端点;前端 Review Workspace 显式传 `archive=active`。避免把协作面做成隐性 breaking change。
- **ReviewEvent 失败语义**(沿用 attestation 模式):生成唯一 `review_event_id` → 写 receipt → DB 写入失败则
  **清理刚写的 receipt** 再抛错;`content_hash` 只做**完整性/复盘**,**不做幂等去重**——人工重复批注是**新事件**,不是 no-op
  (archive/reopen 同理:每次都是新留痕事件)。
- **合并时间线排序(钉死)**:按 `(created_at_utc, source_type, id)` 三键 **全部降序**(`reverse=True`)——
  确定性、无抖动。同秒时该规则下 `review_event` 排在 `attestation` 之前(`'review_event' > 'attestation'` 字典序),
  此即预期顺序(R2b 实现与 jsdom/接口测试以此为准)。

### PM 点名的 5 个边界(锁定)
1. **ReviewEvent 是统一事件账本吗** → 是**复核交互**的统一账本(annotation/archive/reopen/compare_mark);
   **attestation 仍是独立的决策记录**(语义更强、已被 cockpit/annual_review 消费)。二者**视图层合并成一条时间线**
   (统一 UX),**存储层不合并**(避免迁移/反向驱动风险)。这是"统一账本"的低风险落法。
2. **Annotation 必须 receipt 化吗** → **必须**。人工书面输入 = 治理证据,append-only + content-hash + receipt,
   与项目 receipt/provenance 护城河一致。
3. **Archive 是状态还是事件** → **事件**。`is_archived` 派生自最新 archive/reopen;不在 Proposal 上加可变列
   (保持不可变 + 可复盘的开/关历史)。
4. **Archive 等于 reject 吗** → **不等于**。reject 是 *attestation 决策*(判断:否决);archive 是 *生命周期/可见性*
   动作(从活跃队列移走),可作用于 accepted/rejected/stale 任意 proposal。两条正交轴,不语义重载。
5. **ReviewEvent 与 attestation 关系** → attestation = 决策 of record(不变);ReviewEvent = 附加交互账本,
   `attestation_ref` 可引用(如 archive 引用否决它的 attestation)。视图合并、存储分离。

### 4. Surface Inventory
- **输入(人工写入)**:加批注(proposal_id, attester, reason/text)、archive(proposal_id, attester, reason)、
  reopen(同)、compare_mark(**仅落事件标记**,R2 不做比较 UI)。
- **输出**:`ReviewEvent` 记录(唯一 `review_event_id`)+ 各自 receipt(经 `resolve_under` 写 receipt root);派生 `is_archived`。
- **只读视图**:proposal 合并时间线;queue 的 archived 过滤**仅经显式 `archive=` 参数 / workspace 端点**(旧默认不变)。
- **外部面**:无(纯本地 state + receipt,不联网)。
- **失败面**:空 attester/reason 拒;未知 proposal_id → 404;非法 kind 拒;DB 写失败 → 清理新 receipt 后抛错。
- **排除面(明确不碰)**:不改 Proposal/Attestation schema 语义、不加执行面、不新增网络、不动 `decisions:scan`/
  **既有 `/proposals` 默认列表语义(默认仍 all)**及 attest 端点现有响应、archive 不触发任何自动动作、
  `compare_mark` 不改变当前 queue 行为(纯 future marker,比较 UI 是 R4)。

### 5. Default Path Invariant
**无 review 事件时,现有行为逐字节不变**:
- **现状事实**:proposal 详情/queue/attest 响应今天不含任何 review-event/archive 字段;`open/attested` 派生不变。
- **承诺**:ReviewEvent 表与端点**附加**;**旧 `/proposals` 默认仍返回 all**,archive 事件不改其默认语义;隐藏
  archived 只在显式 `archive=active` / workspace 端点下发生。proposal 无 review 事件 → 时间线只含既有 attestations、
  现有端点响应**字段级不变**(新字段可选/独立端点)。**用快照测试锁**既有 proposal/queue(默认 all)响应在 R2 前后相等。

### 6. Traceability Matrix
| 设计承诺 | 计划代码点 | 测试 | gate 探针 |
| --- | --- | --- | --- |
| 默认无事件 → 现有响应不变 | ReviewEvent 附加、不改既有端点 | 既有 proposal/queue 响应快照逐字段相等 | 快照对比 R2 前后 |
| 旧 `/proposals` 默认=all 不变 | 隐藏 archived 仅经显式 `archive=active`/workspace 端点 | 默认 list 仍含 archived 的 proposal;`archive=active` 才隐藏 | 断言默认响应不因 archive 事件变化 |
| ReviewEvent 失败语义 | 唯一 id→写 receipt→DB 失败清理 receipt;`content_hash` 非幂等 | DB 失败 → 无残留 receipt;重复批注 = 两条事件 | 注入 DB 失败 + 重复写断言 |
| 合并时间线稳定排序 | `created_at_utc desc` + tie-breaker(`source_type`,`id`) | 同秒事件顺序确定 | 同秒构造断言 |
| annotation/archive receipt 化 | 复用 governed receipt 写(`resolve_under`) | 写事件→receipt 落盘可复盘、content-hash | 断言 receipt 存在 + 可读 |
| archive 是事件非状态 | 无 Proposal 列;`is_archived` 派生 | archive→reopen→archive 历史全留、派生正确 | 序列断言 |
| archive ≠ reject | archive 与 attestation 解耦 | reject 不产生 archive;archive 不改 decision | 交叉断言 |
| attestation 仍权威 | ReviewEvent 只 `attestation_ref` 引用 | attest 流不回归 | 既有 attestation 测试 |
| 无执行/无网络 | execution_allowed=False;无外部调用 | 构造校验;AST 无 route→执行/网络 | governance:check 探针 |
| 人工输入需具名+理由 | 沿用 attester/reason 必填校验 | 空值被拒 | 反例构造 |
| 前端只读时间线 + 显式写入 | 合并渲染、写入按钮显式确认 | jsdom:时间线渲染、无误导、写入需确认 | DOM 断言 |
| 不变第二个 dashboard | 嵌入既有复核面,非新顶级 nav | 前端结构评审 | 设计 gate 人评 |

### 7. Test / Gate Plan
- **进 `task check`**:ReviewEvent 模型/派生/receipt 后端单测、既有响应快照不变测试、jsdom 时间线只读 + 写入需确认。
- **进 `task governance:check`**:ReviewEvent receipt 路径走 `resolve_under`;无执行/网络 AST 探针;前端复核面无未确认即写入。
- **Gate**:C3 → design gate(本稿)+ implementation gate(独立)+ Risk(人工写入边界、archive≠reject 不被误用)。

### 8. Not claimed / Debt
- **不**主张:compare 的实际并排比较实现(R2 仅落 `compare_mark` 事件;比较 UI 是 R4);annual_review /
  lesson-rule 在 cockpit 的露出(单独 slice);执行/网络任何面。
- **债务**:ReviewEvent 与 attestation 是否长期合并成单账本(本稿选视图合并/存储分离,合并留作未来评估);
  archived 的保留/清理策略;Review Workspace 的可观测性(trace→receipt)。

### 任务拆分(设计 gate 过后)
- R2a 后端:`ReviewEvent` 模型 + receipt 写(`resolve_under`)+ 派生 `is_archived` + 校验;单测含上表后端各行。
- R2b API:附加只读(合并时间线、archived 过滤)+ 人工写入端点(annotation/archive/reopen),既有端点响应不变(快照锁)。
- R2c 前端:proposal 复核面嵌入只读时间线 + 显式确认的写入;jsdom(渲染/无误导/写入需确认);纳入 `task check`。
