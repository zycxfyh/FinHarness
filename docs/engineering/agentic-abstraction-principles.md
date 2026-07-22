# Agentic Abstraction Principles — FinHarness Stabilization Program

状态: v1 (2026-07-08)
目标: 把 FinHarness 从 object-heavy agentic codebase 改造成 abstraction-classified agentic codebase。

配套 inventory: [abstraction-inventory.yml](./abstraction-inventory.yml) — 当前
artifact 分类以该 machine-readable inventory 及其 current-fact tests 为准，
不再手写固定数量。

## 0. 核心诊断

FinHarness 把 agentic execution complexity 过多压进了 Object / State / Receipt / API / Docs / Registry 层。
结果: 每出现一个新的 agentic concern（权限判断、步骤编排、成败检查、过程记录），
默认做法都是新增一个 StateCore model，而不是分配到正确的抽象层。

改进方向不是继续补对象，而是 **把复杂度重新分配到正确的抽象层**。

## 1. 抽象分类表 — 每个概念先分类，再决定是否写代码

以后任何改动先问:

| 问题 | 如果是 | 应放哪里 |
| --- | --- | --- |
| 它是长期业务事实吗？ | 是 | **Object** / DB / Receipt |
| 它是 Agent 可调用能力吗？ | 是 | **Tool** |
| 它是 Agent 可读材料吗？ | 是 | **Resource** / **Context** |
| 它是做事方法吗？ | 是 | **Skill** |
| 它是步骤编排吗？ | 是 | **Workflow** |
| 它是重复执行机制吗？ | 是 | **Loop** |
| 它是成败判断吗？ | 是 | **Evaluator** |
| 它是禁止事项吗？ | 是 | **Guardrail** |
| 它是授权机制吗？ | 是 | **Permission** |
| 它是过程记录吗？ | 是 | **Trace** |

### 1.1 各层定义

#### Object
长期业务事实。持久化存储，有 schema，有 receipt 支撑，不可随意删除。
例: Account, Position, Proposal, IPS, CapitalMandate, AgentAuthorityGrant。
反例: ActionIntentAuthorityBinding（它其实是 evaluator finding，不是业务事实）。

#### Tool
Agent 可调用的能力。单一、明确、可测试、有 typed input/output。
例: read_market_data, create_proposal, compute_risk_metrics。
注意: Tool 不包含编排逻辑；编排属于 Workflow。

#### Resource / Context
Agent 可读但不可直接调用的材料。可能是 docs、policy、catalog、register。
例: DataCatalog（read model）、RiskRegister（read model）、InvestmentPolicyStatement（read + policy binding）。
Context 是 Resource 的运行时版本 —— 注入 prompt 的材料。

#### Skill
做事方法。可复用的检查清单、验证步骤、工作流片段。
例: verify-no-live-submit, verify-route-semantics, verify-statecore-split。
Skill 是给你的（人或 agent），不是给系统的。Skill 输出判断，不输出 Object。

#### Workflow
步骤编排。定义顺序、分支、gates、checkpoints。
例: engineering_delivery_graph, cognitive_graph, ten-layer domain chain。
Workflow 调用 Tool，读取 Resource，触发 Evaluator，写入 Trace。

#### Loop
重复执行机制。定期或事件驱动的检查/维护循环。
例: CI repair loop, docs-current drift loop, route semantics audit loop, debt cleanup loop。
Loop 不是 cron job wrapper —— 它是一个 feedback loop: 发现问题 → 记录 → 修复 → 验证。

#### Evaluator
成败判断。输入是 Object / Trace / Resource，输出是 pass/warn/block + findings。
例: route_semantics_match_openapi, receipt_write_registry_matches_routes, no_live_submit_surface。
Evaluator 可以 fail a PR, block a release, 或生成 debt entry。不修改 runtime state。

#### Guardrail
禁止事项。硬约束，违反即 block。
例: 不得新增 live broker route、不得删除 receipt 不记 removal ledger、不得新增 Agent capability 不带 authority bound。
Guardrail 是静态规则，Evaluator 是检查 Guardrail 是否被遵守的机制。

#### Permission
授权机制。谁在什么条件下可以做什么。
例: LocalOperatorContext（local write enablement）、CapitalMandate（autonomy level）、AgentAuthorityGrant（tool permission config）。
Permission 控制 Tool / Workflow 的可用性，不控制业务逻辑。

#### Trace
过程记录。observability span、receipt、audit log、execution timeline。
Trace 是审计与证据材料；它不直接授予权限，但可以作为 Evaluator / Guardrail / Preflight 的输入。
例: 每个 StateCore write 的 receipt、API request tracing、workflow checkpoint evidence。

## 2. 最关键的约束

```text
不能再把 Skill / Loop / Evaluator / Guardrail / Permission 的问题，
默认做成 StateCore Object。
```

具体:
- 需要 "验证某条件是否满足" → 写 Evaluator，不加 model
- 需要 "记录检查步骤" → 写 Skill，不加 registry
- 需要 "定期检查" → 写 Loop，不加 cron-backed object
- 需要 "禁止某操作" → 写 Guardrail，不加 permission model
- 需要 "授权" → 用已有 Permission 机制，不加新 capability profile

## 3. Stabilization Freeze Rule

停顿期内默认禁止:

- 新增 StateCore model
- 新增 receipt kind
- 新增 API write route
- 新增 registry
- 新增 Agent capability profile
- 新增 Action / Authority / TradePlan / Paper object
- 新增 docs-current 强绑定事实

允许的改动只有:

- classification（归类现有 artifacts）
- bridge read model（read-only aggregate view over existing objects）
- compatibility wrapper（旧路径保留）
- migration helper（数据迁移辅助）
- deletion（在 removal ledger 记录下删除）
- test/evaluator（新增检查/测试）
- skill/checklist（新增技能/清单）
- security fix（安全修复）
- documentation deprecation（文档标记废弃）

## 4. 迁移原则

不直接重构。迁移顺序:

1. **先建 read model** — 新语义从 aggregate read model 开始
2. **bridge, 不 break** — 旧对象不删、旧 receipt 不改、旧 API 不炸
3. **先拆代码边界** — 文件级拆分先于 store/repository 拆分
4. **最后才考虑 schema migration** — 数据库改动是最高风险操作

四不原则:

```text
旧对象不删；
旧 receipt 不改；
旧 API 不炸；
新语义从 aggregate read model 开始。
```

## 5. 与现有治理的关系

本分类体系不取代现有治理机制，而是给它们分配正确的抽象层:

| 现有机制 | 在分类体系中的位置 |
| --- | --- |
| change-control.md (C0-C3) | Guardrail + Evaluator |
| gate-checklists.md | Skill (checklist form) |

## 6. 对新 PR 的要求

每个 PR 必须在 description 中声明:

```markdown
## Abstraction Classification

| Artifact | Current Form | Correct Layer | Migration Path |
| --- | --- | --- | --- |
| [name] | Object / Route / Registry / ... | Object / Tool / Resource / ... | bridge / reclassify / delete / none |

## Freeze Rule Compliance

- [ ] 不新增 StateCore model
- [ ] 不新增 receipt kind
- [ ] 不新增 write route
- [ ] 不新增 Agent capability profile

或声明例外理由。
```
