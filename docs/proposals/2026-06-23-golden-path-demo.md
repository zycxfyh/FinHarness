# Golden Path — receipt-consumption demo (mini-RFC, C2)

Architect 设计稿,2026-06-23。**设计 gate 用。** 按 [mini-rfc 模板](../templates/mini-rfc.md)。
直击复盘最大盲区:我们到处验证了"写得对",但**从没有一次端到端证明"一条证据链能被读懂、可复盘"**。
Golden Path 在**隔离合成环境**里跑一遍价值回路并**回放 receipt**,产出一份 bounded summary——
不碰真实账本、不联网、不含隐私、无执行。

### 1. Change Class
**C2**(对**隔离 tmp** 的 governed 写 + 只读回放;manual demo + CI 单测;无网络/执行/PII)。
不需 threat model;走 mini-RFC + design gate + implementation gate。

### 1b. Module Placement / System Boundary (G5)
**跨系统 demo harness**(`scripts/` + 一个 task),**不新增任何 domain 逻辑**:只编排既有 system 的
commands 与 read models —— State Core(seed)→ Decision Workflow(`record_allocation_candidates`)→
Review System(`create_governed_attestation`/`create_governed_review_event` + `review_read.*`)→
回放既有 receipt 文件。它是 §3 系统目录标准的"消费者样板",不是新 system。

### 2. Current behavior(现状事实)
- 每个 system 单独验证("写得对");receipt/source_refs/lineage 到处写,**但从未被作为一条链读回**。
- 最接近的 `run_research_smoke` 是单点(provider 接线),非完整价值回路;且本机无网产出 data_gap。

### 3. Target behavior
一个 **manual `task decisions:golden-path`**(背后 `scripts/run_golden_path.py`)+ 一个**CI 单测**,在隔离 tmp:
1. **seed 合成状态(确定性产 ≥2 候选)**:broker account + **高集中度持仓**(public symbol,如 SPY 占绝大多数 + AAPL)
   **+ 低现金 + 月支出 cashflow**,使**两个 detector 都触发**:`concentration_high` 和 `cash_buffer_low`。
   候选 evidence 的 `source_refs` **指向真实 synthetic receipt 文件**(便于 step 5 硬校验)。**无真实账本**。
2. **scan**:`record_allocation_candidates` → ≥2 候选 governed proposals(默认 Noop enrichment,离线)。
3. **复核动作(全走,不条件化)**:对 concentration 候选 `create_governed_attestation(approved)` +
   `create_governed_review_event`(annotation)+ **`compare_mark`(concentration ↔ cash_buffer 两候选)**。
4. **读 read models**:`review_read.read_proposal_timeline`(合并时间线)+ **`read_compare_marks`(必非空)**。
5. **回放 receipt(精确到层级)**:从 receipt 文件读回并校验——
   - **proposal receipt**:`kind == "state_core_proposal"`、**顶层** `content_hash`、`governance.execution_allowed == false`;
   - **review-event receipt**:`kind == "state_core_review_event"`、**`review_event.content_hash`**(嵌套)、
     `governance.execution_allowed == false`、`review_event.source_refs` **含 proposal receipt ref + 自身 receipt ref**;
   - 上述 source_refs 中 **path-/receipt-like 的 ref 对应文件存在**(只对这类 ref 做文件校验)。
   全部成立 → `replayed: true`,证明"链可复盘"。
6. **bounded summary**:打印计数 + receipt refs + `replayed: true` + 每步 receipt 是否可读;**不**回显原始账本/PII/堆栈。
7. **artifact 保留**(`mkdtemp`,不自动删)+ cleanup_hint(同 research smoke 模式),便于人审。

### 4. Surface Inventory
- **输入**:合成 seed(public symbol);无外部输入。
- **输出**:stdout bounded JSON summary;tmp artifact(state + receipts)保留。
- **外部面**:**无**(纯本地、离线;默认 Noop enrichment 不联网)。
- **失败面**:seed/scan 未产候选 → setup 失败、**非零**;回放发现 receipt 缺失/坏 → 标 `replayed:false` + gap。
  **exit code 语义分开**:**manual task** 回放失败 → **exit 0 + `replayed:false`**(向人披露"链读不出来",不是崩);
  **CI happy-path 单测** 必须断言 **`replayed:true`**(链坏掉时单测 fail,不允许带病变绿);另有 **fault-injection 单测**
  故意删一个 receipt,验证 replay 返回 `replayed:false`(且 manual 语义下 exit 0)。
- **排除面**:真实账本、网络、执行面、PII;不改任何既有 system 行为;不进 `task check`/`governance:check` 默认链(它做写 + 是 demo)。

### 5. Default Path Invariant
- **现状事实**:无 golden-path task/脚本;既有 system 行为不变。
- **承诺**:harness **附加**;不改既有 command/read-model/路由/前端;`task decisions:golden-path` **显式不在**
  `check`/`governance:check`/`test:*` 依赖链(写 + demo)。**但** orchestration 逻辑由一个**离线 CI 单测**覆盖
  (隔离 tmp,无网络),所以回路本身仍进 CI——这正是补"真端到端"的点。

### 6. Traceability Matrix
| 设计承诺 | 计划代码点 | 测试 | gate 探针 |
| --- | --- | --- | --- |
| 端到端回路 + **compare 腿真覆盖** | seed 确定性产 `concentration_high`+`cash_buffer_low`;走 attest/annotation/compare_mark | CI 单测:proposals **≥2**、含两 detector kind、compare_mark 写入、`read_compare_marks()` **非空** | 单测断言两 kind + 配对非空 |
| receipt 可复盘(**精确层级**) | proposal:顶层 `content_hash`+`governance.execution_allowed=false`;review-event:`review_event.content_hash`+`source_refs` 含 proposal/自身 ref | 按层级断言;path-/receipt-like source_refs 文件存在 | 断言 `replayed:true` |
| **CI happy-path 不容带病变绿** | CI 单测要求 `replayed:true`;fault-injection 删 receipt → `replayed:false` | happy:replayed=true 否则 fail;fault:replayed=false | 注入缺失 receipt |
| 无执行/无网络 | execution_allowed=False;Noop enrichment | 单测无网络;summary execution_allowed=false | grep 无 provider/网络;AST |
| 不进默认链 | task 不入 check/governance/test | grep 依赖链无 golden-path | 复用 NetworkSmokeExclusion 式探针 |
| 不打印 PII/账本/堆栈 | summary 只计数/refs;异常只 type 名 | 输出审查无原始持仓金额/路径外泄 | 输出 grep 无敏感 token |
| 失败可读不崩 | 回放缺失 → replayed:false + gap,exit 0 | 删一个 receipt → replayed:false、exit 0 | 注入缺失 receipt |

### 7. Test / Gate Plan
- **进 `task check`(CI 锚)**:**离线 CI happy-path 单测**跑完整 orchestration(隔离 tmp),断言
  **proposals ≥2 + 含 `concentration_high` 与 `cash_buffer_low` + compare_mark 写入 + `read_compare_marks()` 非空 +
  `replayed:true`**(链坏即 fail);**fault-injection 单测**删一个 receipt → 断言 `replayed:false`。
- **不进** `task check` 的:`task decisions:golden-path`(manual demo,保留 artifact,回放失败 exit 0+replayed:false);
  加 **exclusion 探针**证明 task 不在 `check`/`governance`/`test:*` 默认链。
- **Gate**:C2 → design gate(本稿)+ implementation gate(重点:确定性 ≥2 候选 + compare 腿、回放精确到层级、
  CI happy-path 必 replayed:true、无网络/执行、不打印敏感)。

### 8. Not claimed / Debt
- **不**主张:真实账本 / 联网 / 执行;不替代真浏览器 E2E(Playwright 仍独立 D8)。
- **债务**:retrospective(annual_review)回放需先跑一次 annual review,本 demo **可选**纳入(否则 retrospective 段标 empty);
  多候选 compare 矩阵留后续。security/dependency/OTel 独立 track。

### 任务拆分(设计 gate 过后)
- GPa:`scripts/run_golden_path.py`(orchestration + 回放 + bounded summary,artifact 保留)+ `task decisions:golden-path`(manual)。
- GPb:离线 CI 单测(跑回路 + 断言可复盘 + 缺失 receipt→replayed:false)+ exclusion 探针(不在默认链);纳入 `task check`(单测)。
