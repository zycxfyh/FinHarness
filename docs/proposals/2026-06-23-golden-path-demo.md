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
1. **seed 合成状态**:broker account + 高集中度持仓(public symbol,如 SPY/AAPL)+ cashflows。**无真实账本**。
2. **scan**:`record_allocation_candidates` → 候选 governed proposals(默认 Noop enrichment,离线)。
3. **复核动作**:对 concentration 候选 `create_governed_attestation(approved)` + `create_governed_review_event`
   (annotation;若有第二候选则 compare_mark)。
4. **读 read models**:`review_read.read_proposal_timeline`(合并时间线)+ `read_compare_marks`(如有配对)。
5. **回放 receipt**:从 receipt 文件读回 **proposal receipt** + **review-event receipt** 的 JSON,校验
   `source_refs` 指向的文件存在、content_hash 在、`execution_allowed=false`——证明"链可复盘"。
6. **bounded summary**:打印计数 + receipt refs + `replayed: true` + 每步 receipt 是否可读;**不**回显原始账本/PII/堆栈。
7. **artifact 保留**(`mkdtemp`,不自动删)+ cleanup_hint(同 research smoke 模式),便于人审。

### 4. Surface Inventory
- **输入**:合成 seed(public symbol);无外部输入。
- **输出**:stdout bounded JSON summary;tmp artifact(state + receipts)保留。
- **外部面**:**无**(纯本地、离线;默认 Noop enrichment 不联网)。
- **失败面**:seed/scan 未产候选 → summary 标 setup 问题、非零;回放发现 receipt 缺失/坏 → 标 `replayed:false` + gap(但 exit 0,因为这是"读不出"的真实发现,不是 harness 崩)。
- **排除面**:真实账本、网络、执行面、PII;不改任何既有 system 行为;不进 `task check`/`governance:check` 默认链(它做写 + 是 demo)。

### 5. Default Path Invariant
- **现状事实**:无 golden-path task/脚本;既有 system 行为不变。
- **承诺**:harness **附加**;不改既有 command/read-model/路由/前端;`task decisions:golden-path` **显式不在**
  `check`/`governance:check`/`test:*` 依赖链(写 + demo)。**但** orchestration 逻辑由一个**离线 CI 单测**覆盖
  (隔离 tmp,无网络),所以回路本身仍进 CI——这正是补"真端到端"的点。

### 6. Traceability Matrix
| 设计承诺 | 计划代码点 | 测试 | gate 探针 |
| --- | --- | --- | --- |
| 端到端回路真跑通 | harness 串 seed→scan→review→read | CI 单测:跑完产出 ≥1 proposal + ≥1 review event | 单测断言链非空 |
| receipt 可复盘 | 回放读 proposal/review receipt + source_refs | 断言 receipt 文件可读、content_hash 在、source_refs 文件存在 | 断言 `replayed:true` |
| 无执行/无网络 | execution_allowed=False;Noop enrichment | 单测无网络;summary execution_allowed=false | grep 无 provider/网络;AST |
| 不进默认链 | task 不入 check/governance/test | grep 依赖链无 golden-path | 复用 NetworkSmokeExclusion 式探针 |
| 不打印 PII/账本/堆栈 | summary 只计数/refs;异常只 type 名 | 输出审查无原始持仓金额/路径外泄 | 输出 grep 无敏感 token |
| 失败可读不崩 | 回放缺失 → replayed:false + gap,exit 0 | 删一个 receipt → replayed:false、exit 0 | 注入缺失 receipt |

### 7. Test / Gate Plan
- **进 `task check`**:**离线 CI 单测**跑完整 orchestration(隔离 tmp)+ 断言链可复盘(这是"真端到端"的 CI 锚)。
- **不进** `task check` 的:`task decisions:golden-path`(manual demo,保留 artifact);加 **exclusion 探针**证明它不在默认链。
- **Gate**:C2 → design gate(本稿)+ implementation gate(重点:真跑通、回放成立、无网络/执行、不打印敏感)。

### 8. Not claimed / Debt
- **不**主张:真实账本 / 联网 / 执行;不替代真浏览器 E2E(Playwright 仍独立 D8)。
- **债务**:retrospective(annual_review)回放需先跑一次 annual review,本 demo **可选**纳入(否则 retrospective 段标 empty);
  多候选 compare 矩阵留后续。security/dependency/OTel 独立 track。

### 任务拆分(设计 gate 过后)
- GPa:`scripts/run_golden_path.py`(orchestration + 回放 + bounded summary,artifact 保留)+ `task decisions:golden-path`(manual)。
- GPb:离线 CI 单测(跑回路 + 断言可复盘 + 缺失 receipt→replayed:false)+ exclusion 探针(不在默认链);纳入 `task check`(单测)。
