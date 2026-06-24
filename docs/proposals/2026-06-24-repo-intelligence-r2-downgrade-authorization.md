# repo_intelligence R2 downgrade — authorization RFC

> 状态:**设计草案(2026-06-24)。DESIGN ONLY — 本 PR 不含实现代码,不改 registry /
> Taskfile / graph 模块。** 交 design gate。
> 证据上游:[#44 等价证据 pilot](../../tests/test_repo_intelligence_downgrade_evidence.py)
> (graph path == linear path,语义 contract 等价)。Change-control:
> [change-control.md](../engineering/change-control.md)。Graph 治理:
> [tests/_graph_registry.py](../../tests/_graph_registry.py)。

## 0. 本 RFC 主张什么 / 不主张什么

- **主张**:基于 #44 的 usage evidence,`repo_intelligence` **eligible for downgrade
  authorization review**(具备进入授权评估的资格)。
- **不主张**:本 RFC 合并 **不等于** `authorized to downgrade`。它不拆 graph、不改
  registry status、不加 enum、不改护栏。真正降级是后续被独立 gate 的 implementation
  PR(暂记 #46)。

## 1. Change Class

- **本 RFC 文档**:C1(纯文档)。
- **它所授权评估的 implementation(#46)**:**C2**。命中 change-control 触发器:**跨模块**
  (graph 模块 + Graph Registry schema + 护栏测试)、改**治理面**(registry 状态语义 +
  护栏)。不命中财务/投资/税务/联网/自动化/安全,故不升 C3。implementation 需 **independent
  design + impl gate**(author ≠ gate)。

## 1b. Module Placement / System Boundary (G5)

- 影响 system:**Support / Governance Graphs** + **Graph Registry**。
- **复用既有公共 API 名** `run_repo_intelligence_graph`(见 Q2):内部由 graph 降为 linear
  function,**函数名/签名/返回 shape 不变**,消费者(quality_governance_graph、
  governance_dashboard、project_governance_adapter、scripts、tests)零改动。
- 不新增顶级面;不引入新对象。

## 2. Current behavior(现状事实,引用文件:line)

- `repo_intelligence_graph.py` 是编译后的 LangGraph `StateGraph`,8 节点**纯线性链**
  (source→inventory→import_graph→task_graph→test_map→blast_radius→security_surface→output,
  [repo_intelligence_graph.py:136-155](../../src/finharness/repo_intelligence_graph.py#L136))。
- Graph Registry:`repo_intelligence` status = `downgrade_candidate`,evidence 写明
  "report/receipt flow, not graph semantics; downgrade 要等 usage evidence,当前不授权"
  ([tests/_graph_registry.py:203](../../tests/_graph_registry.py#L203))。
- 护栏:`test_pilot_support_graphs_stay_downgrade_candidates` 硬断言三个 pilot 资产
  **必须保持 `downgrade_candidate`**,文案:registry 不是 promotion/deletion authorization
  ([tests/test_graph_registry.py:81](../../tests/test_graph_registry.py#L81))。
- 公共消费者(name 必须稳定):`quality_governance_graph.py:83`、
  `governance_dashboard.py:151`、`scripts/run_repo_intelligence_graph.py`、
  `project_governance_adapter.py`(public_api 字段)、相关 tests。
- **#44** 已显示:compiled graph path 的输出 == 同样节点线性组合的输出(语义 contract 逐
  字段相等,仅 generated_at + root 前缀归一)。

## 3. Target behavior(#46 实现后的样子)

- 内部:`run_repo_intelligence_graph` 由 `build_repo_intelligence_graph().invoke(...)`
  降为**普通线性函数**(`state.update(node(state))` 顺序串联),移除 `StateGraph` / langgraph
  依赖。
- 外部:**`task repo:intelligence` 任务名不变;CLI 入口不变;输出 contract 不变;
  receipt / markdown / mermaid 输出路径规则不变;`execution_allowed=false` 不变。**
- 治理:Graph Registry 中 `repo_intelligence` status `downgrade_candidate → downgraded`,
  evidence 引用 #44/#45;护栏测试改写(见 Q4),不删除。

## 4. Surface Inventory(#46 改动面,Q2)

- **预期改的文件**:
  - `src/finharness/repo_intelligence_graph.py`(graph → linear,保留公共函数名)
  - `tests/_graph_registry.py`(加 `downgraded` 状态值 + 改 `repo_intelligence` 条目)
  - `tests/test_graph_registry.py`(护栏测试改写,见 Q4)
  - 相关 tests:`test_repo_intelligence.py` / `test_repo_intelligence_downgrade_evidence.py`
    从 "graph equivalence" 转为 "linear-contract regression"(保留或转化,见 Q5.6)
- **保持不变(硬约束)**:`Taskfile.yml` 的 `repo:intelligence` 任务名;
  `scripts/run_repo_intelligence_graph.py` CLI 入口;`quality_governance_graph` /
  `governance_dashboard` / `project_governance_adapter` 调用面。
- **明确不碰**:`quality_governance` / `release_preflight` 两个资产(各自独立后续)。
- **外部网络面**:无(本就 offline)。

## 5. Default Path Invariant(外部 contract 不变)

外部可观察行为**必须完全不变**;内部 graph→linear 是实现细节。锁法:

- **现状事实**:`run_repo_intelligence_graph` 返回 `final`,含 source/inventory_summary/
  import_graph_summary/task_count/test_count/blast_radius/security_surface/mermaid/outputs/
  execution_allowed([repo_intelligence_graph.py:95-133](../../src/finharness/repo_intelligence_graph.py#L95))。
- **不变量**:#44 的等价测试在 #46 中**保留或转为 linear-contract regression**——锁住
  "降级后输出 == 降级前 contract"。`test_repo_intelligence_graph_outputs_final_decision_context`
  继续断言 `final["source"]["graph"] == "repo_intelligence_graph"` 等不变。
- 批准人:独立 design gate(本 RFC)+ 独立 impl gate(#46)。

## 6. Traceability Matrix(给 #46)

| 设计承诺 | 计划代码点 | 测试 | gate 探针 |
| --- | --- | --- | --- |
| 公共 API 名/签名不变 | `run_repo_intelligence_graph` 保留 | 现有消费者 tests 不改仍绿 | impl gate diff 审 |
| graph→linear,移除 StateGraph | `repo_intelligence_graph.py` 重写内部 | linear-contract regression(承自 #44) | impl gate;grep 无 langgraph |
| 输出 contract 不变 | output_node 逻辑保留 | `test_repo_intelligence...final_decision_context` | `task check` |
| task / CLI 入口不变 | Taskfile / script 不改 | 任务名探针 | `task governance:graphs` |
| status → downgraded | registry 条目 + enum | `test_enums_are_closed_sets` | 护栏测试(改写后) |
| 护栏不消失,只允许授权迁移 | 护栏测试改写 | 见 Q4 | design gate 审改写 |

## 7. Test / Gate Plan —— #46 的 implementation gate 条件(写死)

未来实现 PR 必须用测试坐实(非口头):

```text
1. task repo:intelligence 入口不变
2. script CLI 入口不变
3. 输出 contract 不变
4. receipt / markdown / mermaid 输出路径规则不变
5. execution_allowed=false 不变
6. #44 等价测试保留,或改成 linear-contract regression
7. Graph Registry status 改为 downgraded,并引用 #44/#45
8. 不影响 quality_governance / release_preflight
```

- 进 `task check` / `task governance:graphs`:1–7。
- **independent gate**(author≠gate):核 6/7/8 与"无外部 contract 漂移"。

### Q3. 是否新增 `downgraded` 状态?

**需要,但仅在本 RFC 设计;enum/registry 改动留 #46。** 取**轻方案**,避免 registry 变流程引擎:

```text
downgrade_candidate → downgraded
```

**不**引入 `downgrade_authorized`(否则 registry 退化成 workflow 引擎)。授权语义由 evidence
字段承载:`evidence = "#44 proves linear equivalence; #45 authorizes implementation"`。

### Q4. 护栏测试怎么改(不粗暴删)

`test_pilot_support_graphs_stay_downgrade_candidates` 不删除,**升级为更精确的不变量**:

- 改名/改语义为:**pilot support graphs 不得被静默 promote 或 delete**。
- 允许 `repo_intelligence`:`downgrade_candidate → downgraded`(经授权路径)。
- 仍**禁止**它变成:`keep` / `headless_keep` / `delete_candidate` / `archived`。
- `quality_governance` / `release_preflight` 仍冻结在 `downgrade_candidate`(未授权)。

即:护栏从"冻结 candidate"升级为"只允许沿被授权路径移动"。

## 8. Not claimed / Debt

- 本 RFC **不**授权执行降级(合并它 ≠ 拆 graph);它使该降级**具备授权评估资格**,待 design
  gate 通过后才进 #46。
- **不**碰 `quality_governance` / `release_preflight`(各自独立 evidence pilot → RFC →
  implementation,顺序在它们之后)。
- **不**加 `downgrade_authorized` 状态。
- 已知债务:#46 实现前,`repo_intelligence` 输出里的 `WORKFLOW_VERSION =
  "langgraph_repo_intelligence_v1"` 与 `source.graph` 命名仍含 "langgraph"/"graph";是否在
  #46 改名属**输出变更**(会动 contract),需在 #46 单独决策,本 RFC 不预设。

## 排序(本 RFC 锁定)

```text
1. #44 已完成:usage evidence
2. 本 PR #45:downgrade authorization RFC(DESIGN ONLY)
3. #45 过独立 design gate 后:#46 repo_intelligence actual downgrade implementation
4. #46 合并后:再考虑 quality_governance / release_preflight 的 evidence pilot
```
