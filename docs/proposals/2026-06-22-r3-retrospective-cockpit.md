# R3 Retrospective Cockpit — annual review + lesson/rule closure (mini-RFC, C2)

Architect 设计稿,2026-06-22。**设计 gate 用,不开码、不改既有 API。** 按
[mini-rfc 模板](../templates/mini-rfc.md)。把已有的 headless 复盘资产(年度复盘 receipt、lesson→rule
闭环、未闭环 flags)在 cockpit **只读**露出——让用户每天能看到"过去一年/这条规则从哪来/还有什么没闭环",
而**不**做 rule promotion 写入、不自动改规则、不新增执行面。

### 1. Change Class
**C2**(只读、跨模块、用户可见;无写入/执行/网络)。**注意**:一旦加入 "promote rule" 按钮或任何写规则的动作,
立即升 **C3**,拆到后续 slice——本 slice 明确不做。

### 2. Current behavior(现状事实)
- `annual_review.py` 把 proposals/revisions/attestations/lesson drafts/rule-change ledger 聚合成一条**dated
  retrospective receipt**(`data/receipts/annual-review/`),经 `task review:annual` 触发;**cockpit 不展示**。
- `rule_change_ledger.py`:`RuleChange`(status `active|reverted`、attester、change_kind),**receipt-based**
  (`data/receipts/rule-changes/`);cockpit 不展示。
- `lesson_loop.py`:`LessonDraft`/`ReceiptDigest`,`scan_receipts` 读 lesson receipts;cockpit 不展示。
- 三者均 **receipt-based(文件),非 state-core 表**;cockpit 当前无任何 `/review/*` 读端点。

### 3. Target behavior
- 新增**只读** API 读上述既有 receipt,**不计算驱动决策、不写**:
  - 最新 annual-review receipt 摘要(无则 empty state,提示"run task review:annual");
  - rule-change ledger 条目(active/reverted,来自 receipts);
  - lesson 闭环状态 + **未闭环 flags**(来自 lesson receipts/digests)。
- cockpit 新增**单个只读 "Retrospective" 面板**消费它(嵌入既有导航的一个 view,**不是**杂乱的第二 dashboard;
  纯只读、零写入/动作按钮)。
- 默认 cockpit 其余视图/端点**逐字节不变**;无 receipt 时优雅 empty state。

### PM 点名的 4 锁
1. **数据源** = annual_review receipt + rule_change_ledger + lesson_loop,**只读既有 receipt**,不新建计算口径、不写。
2. **只读** = 无 rule promotion 写入、无自动改规则、无执行面(加按钮即升 C3,本 slice 不做)。
3. **默认 cockpit 不变** = 新端点/视图附加;现有响应字段级不变;无 receipt → empty state,不报错。
4. **未闭环 lesson 是披露,不是建议/改动** = unclosed flags 仅描述性展示(措辞中性,带 non_claims),
   绝不自动建议规则、绝不触发任何写。

### 4. Surface Inventory
- **输入**:读 `data/receipts/{annual-review,rule-changes}` + lesson receipts(经 `lesson_loop.scan_receipts`)。
- **输出**:`/review/*` 只读 JSON 摘要;cockpit Retrospective 只读面板。
- **外部面**:无(本地 receipt 读取)。
- **失败面**:无 receipt → empty state;损坏/不可读 receipt → 降级为 disclosed gap,不崩(沿用 revisions 端点的
  anomaly→gap 处理风格)。
- **排除面**:不写任何 receipt/DB、不 promote rule、不改既有 `/proposals`·`/exposure`·`/dashboard` 等响应、
  无执行/网络、无新顶级杂乱 dashboard。

### 5. Default Path Invariant
- **现状事实**:cockpit 今天无 `/review/*` 端点;无 annual-review/rule/lesson 视图。
- **承诺**:R3 端点/视图**附加**;既有端点响应**字段级不变**(快照锁 `/dashboard/summary`·`/proposals` 等);
  无相关 receipt 时 Retrospective 面板渲染 empty state,不影响其它视图。OpenAPI 契约测试加新只读路径。

### 6. Traceability Matrix
| 设计承诺 | 计划代码点 | 测试 | gate 探针 |
| --- | --- | --- | --- |
| 只读、不写不 promote | `/review/*` 仅读 receipt;无 write/ledger-promote 调用 | 端点不产生任何 receipt/DB 行 | AST/grep:无 promote/write 调用 |
| 默认 cockpit 不变 | 新端点附加 | 既有 `/dashboard`·`/proposals` 响应快照相等 | 快照对比 |
| 无 receipt → empty 不崩 | 缺失/损坏 → empty/gap | 空目录/坏 receipt → 200 + empty/gap | 注入空/坏 receipt |
| 未闭环=披露非建议 | unclosed flags 描述性 + non_claims | 响应含中性 flags + non_claims;无 "recommend/promote" | 红线词探针 |
| 无执行面 | execution_allowed=False;前端无动作按钮 | jsdom:面板只读无 button/动作链接 | DOM 断言 + AST |
| 数据源可复盘 | 摘要带 source receipt refs | 响应含 receipt_ref/path | 断言 refs 非空(有 receipt 时) |

### 7. Test / Gate Plan
- **进 `task check`**:`/review/*` 端点后端单测(空/有/坏 receipt)、既有响应快照不变、jsdom Retrospective 只读面板。
- **进 `task governance:check`**:Retrospective 面板无动作面;`/review/*` 无 promote/write/执行 AST 探针;红线(无 recommend/predict)。
- **Gate**:C2 → design gate(本稿)+ implementation gate;若后续加写规则 → 单独 C3 + independent gate。

### 8. Not claimed / Debt
- **不**主张:rule promotion / 自动改规则 / 任何写(独立 C3 slice);compare UI(R4);real-ledger/观测性。
- **债务**:annual review 目前靠 CLI 写 receipt,cockpit 只读最新一条——"在 cockpit 内触发生成"留作后续(涉及写,C3)。
- 小 follow:R2c 余项(queue 默认 `archive=active` 隐藏 archived)可随本 slice 顺手或单列。

### 任务拆分(设计 gate 过后)
- R3a 后端:`/review/*` 只读端点(读 annual-review/rule-change/lesson receipts;空/坏→empty/gap);单测含上表后端各行 + OpenAPI 契约。
- R3b 前端:cockpit Retrospective 只读面板 + jsdom(空/填充/无动作面/未闭环披露非建议);纳入 `task check`。
