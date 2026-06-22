# R4 Candidate Compare — side-by-side review of compare-marked proposals (mini-RFC, C2)

Architect 设计稿,2026-06-22。**设计 gate 用,不开码、不改既有 API 语义。** 按
[mini-rfc 模板](../templates/mini-rfc.md)。把 S4-R2 已落的 `compare_mark` 治理事件**变成可用的复核能力**:
让用户**只读、并排**比较两个被标记的候选方案,而**不**裁决谁更优、不写、不执行。

### 1. Change Class
**C2**(只读 UI + 一个只读读端点;用户可见;无写/执行/网络)。无需 threat model;走 mini-RFC + design gate
+ implementation gate。

### 2. Current behavior(现状事实)
- `compare_mark` 已在 S4-R2 落地:`ReviewEvent(kind="compare_mark", proposal_id=subject, compare_with=target)`,
  构造时已校验 target 非空/存在/非自身([proposals.py](../../src/finharness/statecore/proposals.py))。
- 它只出现在**单个 proposal 的 timeline**(`GET /proposals/{id}/timeline`);**cockpit 不消费**——既没有"哪些对被标记
  待比较"的清单,也没有并排比较视图。候选详情只能逐个看(`GET /proposals/{id}`)。

### 3. Target behavior
- **R4a 只读端点** `GET /review/compare-marks`:列出所有 `compare_mark` 事件配对
  `{proposal_id, compare_with, attester, reason, created_at_utc}`(读 ReviewEvent,**不写**)。
- **R4b cockpit Compare view**(单个聚焦 view,**非第二杂乱 dashboard**):列出 marked 配对;选中一对后
  **并排只读**渲染两个候选的事实(claim、dimension、options、key_risks、reversibility、research_evidence、
  attestation 状态),数据来自既有 `GET /proposals/{id}`。
- **描述性比较,不裁决**:两侧都只展示各自事实,**不**输出 "winner/recommended/better/should pick" 等裁决性结论;
  带 non_claims 披露。无写入、无动作按钮、无执行面。
- 默认 cockpit 其余视图/端点**逐字节不变**;无 compare mark → empty state。

### 自我锁定(4 条)
1. **只读** = 无写、无执行;`/review/compare-marks` 与 Compare view 都不产生 ReviewEvent/attestation/任何 receipt。
2. **复用 `compare_mark`** = 不新增标记机制;配对完全来自既有 compare_mark 事件(标记入口仍是 R2 的 review-events 写端点)。
3. **默认 cockpit 不变** = 端点/视图附加;既有响应字段级不变;无 mark → empty。
4. **比较非建议** = 并排是描述性的;无 "更优/推荐/应选" 裁决措辞;非闭环驱动、非投资建议。

### 4. Surface Inventory
- **输入**:读 `ReviewEvent where kind=='compare_mark'`(配对清单);读既有 `GET /proposals/{id}`(两侧详情)。
- **输出**:`GET /review/compare-marks` 只读 JSON;Compare view 只读并排渲染。
- **外部面**:无(本地 state 读)。
- **失败面**:无 mark → empty;某侧 proposal 已不存在 → 该对标 "missing"/降级 disclosure,不崩。
- **排除面**:不写 ReviewEvent/attestation/receipt、不改既有 `/proposals`·`/review/retrospective` 响应、
  不新增标记入口(仍走 R2 写端点)、无裁决性结论、无执行/网络、无新顶级杂乱 dashboard。

### 5. Default Path Invariant
- **现状事实**:cockpit 无 `/review/compare-marks` 端点、无 Compare view;`compare_mark` 仅在 per-proposal timeline。
- **承诺**:端点/视图**附加**;既有端点响应**字段级不变**(快照锁 `/proposals`·`/proposals/{id}/timeline`·
  `/review/retrospective`);无 compare mark → Compare view empty state,不影响其它视图。OpenAPI 契约测试加新只读路径。

### 6. Traceability Matrix
| 设计承诺 | 计划代码点 | 测试 | gate 探针 |
| --- | --- | --- | --- |
| 只读、不写 | `/review/compare-marks` 仅 select ReviewEvent | 端点不产生任何 ReviewEvent/receipt/DB 行 | AST/grep:无 create_governed_*/write 调用 |
| 复用 compare_mark | 配对来自 `kind=='compare_mark'` 事件 | 标一个 compare_mark → 端点列出该对 | 构造事件→断言配对 |
| 默认 cockpit 不变 | 端点/视图附加 | 既有 `/proposals`·timeline·retrospective 快照相等 | 快照对比 |
| 比较非建议 | 并排只展示双方事实,无裁决词 | 响应/DOM 无 winner/recommended/better/should pick | 措辞探针(flags/claims,不误伤 non_claims) |
| 某侧缺失不崩 | 缺失 proposal → disclosure 降级 | 删一侧 → 该对标 missing、200 | 注入缺失 proposal |
| 无执行/动作面 | execution_allowed=False;前端无 button/动作链接 | jsdom:Compare view 只读无 button/动作 a | DOM 断言 + AST |

### 7. Test / Gate Plan
- **进 `task check`**:`/review/compare-marks` 端点后端单测(空/有/缺失一侧)、既有响应快照不变、OpenAPI 契约、
  jsdom Compare view(空/并排/无动作面/无裁决措辞)。
- **进 `task governance:check`**:`/review/*` AST 无写入口;Compare view 无动作面;裁决措辞探针。
- **Gate**:C2 → design gate(本稿)+ implementation gate。

### 8. Not claimed / Debt
- **不**主张:自动选优 / 推荐哪个候选 / 任何写或执行;不替代 attestation 决策(选择仍走 attest)。
- **债务**:compare 当前限两两(一对一);多候选矩阵比较留作后续。security/dependabot 债独立 track,不入 R4。

### 任务拆分(设计 gate 过后)
- R4a 后端:`GET /review/compare-marks` 只读端点(列 compare_mark 配对;缺失一侧 disclosure;不写);单测含上表后端各行 + OpenAPI 契约。
- R4b 前端:cockpit Compare view(列配对 + 选中并排只读两候选事实)+ jsdom(空/并排/无动作面/无裁决);纳入 `task check`。
