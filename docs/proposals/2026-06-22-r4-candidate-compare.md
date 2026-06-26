# R4 Candidate Compare — side-by-side review of compare-marked proposals (mini-RFC, C2)

Architect 设计稿,2026-06-22。**设计 gate 用,不开码、不改既有 API 语义。** 按
[mini-rfc 模板](../templates/mini-rfc.md)。把 S4-R2 已落的 `compare_mark` 治理事件**变成可用的复核能力**:
让用户**只读、并排**比较两个被标记的候选方案,而**不**裁决谁更优、不写、不执行。

### 1. Change Class
**C2**(只读 UI + 一个只读读端点;用户可见;无写/执行/网络)。无需 threat model;走 mini-RFC + design gate
+ implementation gate。

### 1b. Module Placement / System Boundary  (G5)
归属 **Review System**([system-map](../architecture/system-map.md))。这是该 system 的**第 3 个 read model**
(timeline=R2、retrospective=R3、compare-marks=R4)→ 命中 G5 原则 3(第 3 次散点 → 抽共享模块)。
**因此 R4 不只是"再加一个 view/route":先把 Review System 的统一 read model 抽出来,Compare 是它的自然扩展。**
- 新增 **`review_read.py`**:把 timeline / retrospective / compare-marks 的读逻辑统一为该 system 的
  read model(纯函数,输入 engine/roots → 只读 DTO),**不改语义**(timeline/retrospective 行为逐字段不变,有快照锁)。
- `api/routes_review.py` / `routes_proposals.py` 降为**薄 HTTP adapter**,调用 `review_read.*`,不再内联读逻辑。
- 新增 **shared review test fixtures**(`tests/_review_fixtures.py` 或同等):建 proposal/attestation/review_event 的
  共用 setup,timeline/retrospective/compare/R4 测试复用,不各造一套。
- frontend:`app.js` 内**review render 分区**(只读 panel renderer / 只读 selection renderer)+ 既有
  review jsdom 作为 view contract;Compare view 复用该分区。
不新增第二套语义(compare 复用 ReviewEvent.compare_mark);**新增 1 个顶级 cockpit tab(Compare)**——理由:它是独立的
并排比较交互面,无法自然并入 proposal 详情或 retrospective;先抽 read model 控制散点,再加这个面。

### 2. Current behavior(现状事实)
- `compare_mark` 已在 S4-R2 落地:`ReviewEvent(kind="compare_mark", proposal_id=subject, compare_with=target)`,
  构造时已校验 target 非空/存在/非自身([proposals.py](../../src/finharness/statecore/proposals.py))。
- 它只出现在**单个 proposal 的 timeline**(`GET /proposals/{id}/timeline`);**cockpit 不消费**——既没有"哪些对被标记
  待比较"的清单,也没有并排比较视图。候选详情只能逐个看(`GET /proposals/{id}`)。

### 3. Target behavior
- **R4a 只读端点** `GET /review/compare-marks`:列出**规范化配对**(见下),每条带 missing 标记
  (读 ReviewEvent,**不写**)。每条 pair shape:
  `{proposal_id, compare_with, attester, reason, created_at_utc, review_event_id,
  proposal_exists, compare_with_exists, missing_side, data_gaps}`。
- **配对语义(选 B:canonical pair 去重,latest wins)**:把 `compare_mark` 视为对**无序对** `{A,B}` 的标记
  (A→B 与 B→A 同一对);同一对多次标记 → **保留最新一条**(按 `(created_at_utc, review_event_id)`),
  其 attester/reason/方向用于展示。配对清单按各自最新事件 **newest-first** 排序。
- **missing 由后端标**:某侧 proposal 不存在 → 该 pair 的 `proposal_exists`/`compare_with_exists`=false、
  `missing_side` ∈ {left,right,both}、`data_gaps` 记一条;端点仍 200,前端只读呈现"该候选已不存在"。
- **R4b cockpit Compare view**(单个聚焦 view,**非第二杂乱 dashboard**):
  - **只读 selection 控件**(`<select>`/listbox 选 pair)**允许**——它只触发 GET + 重渲染,**不**写、不 POST、不提交表单;
  - 选中后**并排只读**渲染两个候选的事实(claim、dimension、options、key_risks、reversibility、research_evidence、
    attestation 状态),数据来自既有 `GET /proposals/{id}`,**逐项标注来源**;
  - missing 一侧 → 显式 disclosure,不崩。
- **描述性比较,不裁决**:并排只展示双方各自事实;**compare 层不新增** "winner/recommended/better/should pick"
  等裁决措辞(原始 proposal claim/option 文案按其本来内容展示,不在 R4 探针范围——见 Traceability);带 non_claims 披露。
  **写/执行面一律没有**(只读 selection 除外)。
- 默认 cockpit 其余视图/端点**逐字节不变**;无 compare mark → empty state。

### 自我锁定(4 条)
1. **只读** = 无写、无执行;`/review/compare-marks` 与 Compare view 都不产生 ReviewEvent/attestation/任何 receipt。
   **只读 selection 控件允许**(选 pair → GET + 重渲染);**禁止**任何写/执行按钮、POST、表单提交。
2. **复用 `compare_mark`** = 不新增标记机制;配对完全来自既有 compare_mark 事件(标记入口仍是 R2 的 review-events 写端点)。
3. **默认 cockpit 不变** = 端点/视图附加;既有响应字段级不变;无 mark → empty。
4. **比较非建议** = compare 层(端点 summary / view 的 compare chrome 与 flags)**不新增** "更优/推荐/应选" 裁决措辞;
   原始 proposal facts(claim/option 文案)按其本来内容展示并标来源 + non_claims,**不在** R4 措辞探针范围。

### 4. Surface Inventory
- **输入**:读 `ReviewEvent where kind=='compare_mark'`(配对清单);读既有 `GET /proposals/{id}`(两侧详情)。
- **输出**:`GET /review/compare-marks` 只读 JSON(规范化配对 + 每条 `proposal_exists`/`compare_with_exists`/
  `missing_side`/`data_gaps`);Compare view 只读并排渲染(含只读 selection 控件)。
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
| **配对去重 latest-wins(无序对)** | canonical `frozenset{A,B}`;同对保留最新 `(created_at_utc, review_event_id)` | A→B + B→A + 重复 A→B → 端点恰 1 对(最新方向) | 构造正/反/重复事件→断言 1 对 + latest |
| 默认 cockpit 不变 | 端点/视图附加 | 既有 `/proposals`·timeline·retrospective 快照相等 | 快照对比 |
| 比较非建议(**仅 compare 层**) | 端点 summary / view compare chrome 无裁决词 | compare chrome/flags 无 winner/recommended/better/should pick(**不扫 raw proposal facts/non_claims**) | 措辞探针限定 compare-generated 元素 |
| 某侧缺失不崩(定 shape) | 后端标 `proposal_exists`/`compare_with_exists`/`missing_side`/`data_gaps` | 删一侧 → 该对 missing_side 正确、200、data_gaps 非空 | 注入缺失 proposal |
| 只读 selection,无写/执行 | 允许 `<select>`/listbox;无 button-submit/POST/form | jsdom:选 pair 只触发 GET + 重渲染,**无 POST**;无写/执行按钮 | fetch spy 断言无 POST + AST 无 write 调用 |

### 7. Test / Gate Plan
- **进 `task check`**:`/review/compare-marks` 端点后端单测(空/有/缺失一侧)、既有响应快照不变、OpenAPI 契约、
  jsdom Compare view(空/并排;**无写/执行动作面;只读 selection 允许且选 pair 无 POST/无表单提交**;
  裁决措辞探针限 compare 层)。
- **进 `task governance:check`**:`/review/compare-marks` AST 无写入口(无 `create_governed_*`/write);Compare view
  允许只读 selection 但**无写/POST/提交**;裁决措辞探针**限定 compare-generated 元素**(不扫 raw proposal facts/non_claims)。
- **Gate**:C2 → design gate(本稿)+ implementation gate。

### 8. Not claimed / Debt
- **不**主张:自动选优 / 推荐哪个候选 / 任何写或执行;不替代 attestation 决策(选择仍走 attest)。
- **债务**:compare 当前限两两(一对一);多候选矩阵比较留作后续。security/dependabot 债独立 track,不入 R4。

### 任务拆分(设计 gate 过后)
- **R4a-0 抽统一 read model(G5 试点)**:新增 `review_read.py`,把 timeline / retrospective 读逻辑**平移**
  进来(语义不变,快照锁);`routes_review`/`routes_proposals` 改调它。建 shared review test fixtures。**纯重构,
  行为不变**——独立验收(既有 review/timeline/retrospective 测试全绿 + 快照相等)。
- R4a 后端:在 `review_read.py` 加 **compare-marks read model**(canonical 配对去重 latest-wins + missing 标记)+
  薄 adapter `GET /review/compare-marks`;单测含上表后端各行(配对去重、missing shape、只读)+ OpenAPI 契约,复用 shared fixtures。
- R4b 前端:`app.js` review render 分区 + cockpit Compare view(只读 selection 选配对 + 并排只读两候选事实)+
  jsdom(空/并排/只读 selection 无 POST/无裁决措辞限 compare 层);纳入 `task check`。
