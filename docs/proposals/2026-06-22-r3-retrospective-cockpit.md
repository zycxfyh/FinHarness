# R3 Retrospective Cockpit — annual review + lesson/rule closure (mini-RFC, C2)

Architect 设计稿,2026-06-22。**设计 gate 用,不开码、不改既有 API。** 按
[mini-rfc 模板](../templates/mini-rfc.md)。把已有的 headless 复盘资产(年度复盘 receipt、lesson→rule
闭环、未闭环 flags)在 cockpit **只读**露出——让用户每天能看到"过去一年/这条规则从哪来/还有什么没闭环",
而**不**做 rule promotion 写入、不自动改规则、不新增执行面。

### 1. Change Class
**C2**(只读、跨模块、用户可见;无写入/执行/网络)。**注意**:一旦加入 "promote rule" 按钮或任何写规则的动作,
立即升 **C3**,拆到后续 slice——本 slice 明确不做。

### 2. Current behavior(现状事实)
- `annual_review.py`:`compute_annual_review`/`record_annual_review` 把 proposals/revisions/attestations/
  lessons/rule-change ledger 聚合成一条 **dated `annual_review` receipt**(`data/receipts/annual-review/`),
  **已算出** `lessons_closed`、`lessons_open`(tuple)、`untraceable_rule_changes`(tuple);经 `task review:annual`
  触发;**cockpit 不展示**。
- `rule_change_ledger.py`:canonical ledger 在 **state root** `data/state/rule-changes`,经 `load_rule_changes(state_root)`
  读(`RuleChange`:status `active|reverted`、attester、change_kind);**promotion receipt** 写到
  `data/receipts/rule-changes/` 仅作 provenance。cockpit 不展示。
- `lesson_loop.py`:`scan_receipts()` 扫的是**运营 receipt 源 → `ReceiptDigest`**(不是 lesson drafts);
  持久 **lesson draft receipts** 在 `data/receipts/lessons/`(`persist_lesson_draft`)。cockpit 不展示。
- cockpit 当前无任何 `/review/*` 读端点。

### 3. Target behavior
- **主数据源 = 最新 `annual_review` receipt**:闭环状态(`lessons_closed`/`lessons_open`/
  `untraceable_rule_changes`)**直接取自该 receipt**——R3 **不重算** lesson→rule closure(避免 UI 与 annual
  review 算出两套状态)。无该 receipt → empty state,提示"run `task review:annual`"。
- **drill-down / provenance(次要)**:rule-change **state ledger**(`load_rule_changes`,active/reverted)+
  lesson draft receipts(`data/receipts/lessons`)仅供展开查看来源,**不**作为闭环状态的二次计算口径。
- **只读、不写、不计算驱动**:`/review/*` **绝不调用** `compute_annual_review()`、`record_annual_review()`、
  `promote_lesson_to_rule_change()`、`persist_lesson_draft()`;只读取已有 receipt / state ledger。
- cockpit 新增**单个只读 "Retrospective" 面板**消费它(嵌入既有导航的一个 view,**不是**第二个杂乱 dashboard;
  纯只读、零写入/动作按钮)。默认 cockpit 其余视图/端点**逐字节不变**;无数据时优雅 empty state。

### PM 点名的 4 锁
1. **数据源** = **最新 `annual_review` receipt 为主**(闭环状态直接取其字段,不重算);rule-change state ledger +
   lesson draft receipts 仅作 provenance/drill-down。**只读既有**,不新建计算口径、不写。
2. **只读** = 无 rule promotion 写入、无自动改规则、无执行面(加按钮即升 C3,本 slice 不做)。
3. **默认 cockpit 不变** = 新端点/视图附加;现有响应字段级不变;无 receipt → empty state,不报错。
4. **未闭环 lesson 是披露,不是建议/改动** = unclosed flags 仅描述性展示(措辞中性,带 non_claims),
   绝不自动建议规则、绝不触发任何写。

### 4. Surface Inventory
- **输入**:最新 `annual_review` receipt(`data/receipts/annual-review`,主源)+ rule-change **state ledger**
  (`data/state/rule-changes` via `load_rule_changes`)+ lesson draft receipts(`data/receipts/lessons`)作 drill-down。
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
- **最新 receipt 选择规则**:在 annual-review 目录内取 `kind=="annual_review"`、按 `created_at_utc` 最新,
  tie-break by filename;**坏/不可读 receipt → `data_gaps`,不崩**(不静默跳过)。
- **不写不计算**:`/review/*` **不调用** `compute_annual_review`/`record_annual_review`/
  `promote_lesson_to_rule_change`/`persist_lesson_draft`——只读最新 receipt + state ledger。

### 6. Traceability Matrix
| 设计承诺 | 计划代码点 | 测试 | gate 探针 |
| --- | --- | --- | --- |
| 只读、不写不计算 | `/review/*` 仅读最新 receipt + state ledger | 端点不产生任何 receipt/DB 行 | AST/grep:routes 不调用 `compute_annual_review`/`record_annual_review`/`promote_lesson_to_rule_change`/`persist_lesson_draft` |
| 主源=annual_review receipt,不重算闭环 | 闭环字段取自 receipt;routes 不重算 closure | 喂 receipt → 响应闭环字段 == receipt 字段 | 断言字段透传、无二次计算 |
| 默认 cockpit 不变 | 新端点附加 | 既有 `/dashboard`·`/proposals` 响应快照相等 | 快照对比 |
| 无 receipt → empty 不崩 | 缺失/损坏 → empty/gap | 空目录/坏 receipt → 200 + empty/gap | 注入空/坏 receipt |
| 未闭环=披露非建议 | unclosed flags 中性描述 + non_claims | flags/claims 字段无建议式 recommend/promote/apply/change(**只查 flags/claims,不查 non_claims**——后者可合法写 "does not promote") | 针对 flags/claims 的措辞探针 |
| 无执行面 | execution_allowed=False;前端无动作按钮 | jsdom:面板只读无 button/动作链接 | DOM 断言 + AST |
| 数据源可复盘 | 摘要带 source receipt refs | 响应含 receipt_ref/path | 断言 refs 非空(有 receipt 时) |

### 7. Test / Gate Plan
- **进 `task check`**:`/review/*` 端点后端单测(空/有/坏 receipt)、既有响应快照不变、jsdom Retrospective 只读面板。
- **进 `task governance:check`**:Retrospective 面板无动作面;`/review/*` AST 探针不调用
  `compute_annual_review`/`record_annual_review`/`promote_lesson_to_rule_change`/`persist_lesson_draft`;
  flags/claims 措辞探针(无建议式 recommend/promote/apply/change;不误伤 non_claims 的 "does not promote")。
- **Gate**:C2 → design gate(本稿)+ implementation gate;若后续加写规则 → 单独 C3 + independent gate。

### 8. Not claimed / Debt
- **不**主张:rule promotion / 自动改规则 / 任何写(独立 C3 slice);compare UI(R4);real-ledger/观测性。
- **债务**:annual review 目前靠 CLI 写 receipt,cockpit 只读最新一条——"在 cockpit 内触发生成"留作后续(涉及写,C3)。
- 小 follow:R2c 余项(queue 默认 `archive=active` 隐藏 archived)可随本 slice 顺手或单列。

### 任务拆分(设计 gate 过后)
- R3a 后端:`/review/*` 只读端点(主读最新 `annual_review` receipt;rule-change state ledger + lesson draft
  receipts 作 drill-down;空/坏→empty/gap;不调用写/计算入口);单测含上表后端各行 + OpenAPI 契约。
- R3b 前端:cockpit Retrospective 只读面板 + jsdom(空/填充/无动作面/未闭环披露非建议);纳入 `task check`。
