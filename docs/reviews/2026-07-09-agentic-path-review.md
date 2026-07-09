# Agentic Path Review: Waves 0–1.3 复盘与 Wave 2 方向

date: 2026-07-09
source: architect review
status: direction-confirmed
layer: agentic-cognition-plane

## 核心判断

> **FinHarness 这条路径是成立的，而且比单纯"接 agent runtime / 接 MCP / 接 LangGraph"更适合这种古典软件 + agentic 认知层混合项目。**
> 它的真正价值不是"我们也做了 agent"，而是：**我们先把 agent 的责任、证据、评价、权限、上下文可信度和执行边界做成了可验证结构。**

这比直接上 runtime 更慢，但更稳。对 FinHarness 这种涉及资本判断、review、policy、authority、execution boundary 的系统，这是正确路径。

---

## 1. 外部参照：工业界现在主要在做什么

当前工业界 agent 工程大体分成四类。

### 1.1 Runtime / loop 框架

OpenAI Agents SDK 明确提供 agent loop、tools、handoffs、guardrails、sessions、human-in-the-loop、tracing 等 primitives。它的核心是帮助开发者管理 tool invocation、turn loop、guardrails、sessions 和 traces。

LangGraph 则定位为 long-running、stateful agent orchestration runtime，强调 durable execution、streaming、human-in-the-loop、persistence、debugging/observability。

AutoGen 主要面向 single / multi-agent applications，并有 AgentChat、Core、Extensions，其中 Core 是事件驱动的多 agent 系统框架，支持 business workflows、multi-agent collaboration、distributed agents 等场景。

这些框架解决的是：

```text
agent 怎么跑
agent 怎么调 tool
agent 怎么跨 agent 协作
agent 怎么保留状态
agent 怎么被观察
```

但它们不天然解决：

```text
某个 domain 里的 agent 判断是否有权进入下一状态
某个 context 是否能作为 evidence
某个 plan 是否只是 deliberation 还是 action
某个 evaluation 是否能驱动 authority
某条 trace 是否足以作为审计证据
```

这正是 FinHarness 这轮做的事情。

---

### 1.2 Tool / context protocol

MCP 的定位是把 AI applications 连接到 external systems，例如 local files、databases、tools、workflows。官方文档直接把它类比成 AI applications 的 "USB-C port"。

这类协议解决的是：

```text
agent 如何获得工具和上下文
```

但不自动解决：

```text
这个上下文是否可信
这个上下文是否可作为 evidence
这个工具输出能不能进入 authority chain
这个 action 是否越过 execution boundary
```

所以我们做 `ContextTrust` / `ContextUsePolicy` 是必要的。MCP 负责连接，FinHarness 负责解释连接后的责任语义。

---

### 1.3 Observability / tracing / eval

OpenAI Agents SDK 和 LangGraph 都强调 tracing、debugging、evaluation、monitoring。OpenAI Agents SDK 文档把 tracing 列为核心能力之一，用于可视化、debug、monitor workflows；LangGraph 也强调 LangSmith tracing、evaluation、observability。

这和我们的 `AgentRunReceipt` / `EvaluationReport` 方向一致，但我们做得更 domain-specific：

```text
通用框架 trace:
  记录 agent/tool/runtime 行为

FinHarness receipt:
  记录资本判断链中的证据、评价、权限资格、上下文使用边界
```

我们不是替代 tracing，而是在 tracing 上面建立 domain accountability layer。

---

### 1.4 研究界开始意识到 loop / state / plan-execute 问题

近期研究已经开始关注 agentic loop 的失败模式。比如 2026 年关于 infinite agentic loops 的论文把问题定义为：agent 在 planning、tool use、state updates、handoffs 中可能重复触发 costly/state-growing operations，导致成本、上下文增长和外部副作用放大。

另一个方向是 Plan-then-Execute 架构：它强调把 strategic planning 和 tactical execution 分离，并通过 least privilege、tool scoping、sandboxing、human-in-the-loop 等降低风险。

这两点都支持我们的路径：

```text
先 plan / evaluate / authority / trace
后 runtime / execution
```

而不是直接让 agent 进入可循环执行层。

---

## 2. 我们的路径与主流 agent 工程的差异

主流 agent 框架通常从这里开始：

```text
model
→ tools
→ loop
→ memory/session
→ observability
→ guardrails
```

FinHarness 这轮实际走的是：

```text
responsibility boundary
→ receipt primitive
→ context trust
→ evaluation projection
→ authority eligibility
→ deliberation artifact
→ feedback policy
→ deterministic cognition flow
→ semantic hardening
```

这不是同一层级。

更准确说：

| 方向   | 主流框架                            | FinHarness                                                       |
| ---- | ------------------------------- | ---------------------------------------------------------------- |
| 起点   | runtime/tool loop               | domain responsibility model                                      |
| 中心对象 | agent / tool / session / graph  | receipt / evaluation / authority / context trust                 |
| 核心风险 | loop、tool misuse、state drift    | 责任迁移、authority 混淆、execution 边界污染                                 |
| 主要控制 | guardrails、sandbox、HITL、tracing | receipt-only、projection-only、semantic evaluator、ContextUsePolicy |
| 目标   | 让 agent 能跑                      | 让 agent 的判断可被审计、约束、回放                                            |

这说明 FinHarness 不是在"晚一点接 runtime"。它是在补很多 runtime 框架默认不替你建的 domain semantics。

---

## 3. 为什么这条路径特别适合 FinHarness

FinHarness 不是普通任务 agent，也不是客服 agent，更不是 coding agent。它是一个资本判断系统，天然有这些高摩擦边界：

```text
state vs receipt
proposal vs approval
review vs attestation
plan vs execution
evaluation vs authority
evidence vs draft
agent suggestion vs human decision
```

如果直接接 agent runtime，很容易出现一种危险结构：

```text
agent sees context
→ agent drafts plan
→ agent calls tool
→ tool writes state
→ trace says it happened
```

但这还不能回答：

```text
这个 plan 凭什么成立？
这些 source_refs 能不能作为 evidence？
Evaluation 是 real evaluator 还是 symbolic placeholder？
Authority 是 eligibility 还是 approval？
Human confirmation 是 gate 还是 override？
有没有越过 Execution Kernel？
```

我们这轮做的 Wave 0–1.3，恰好是在回答这些问题。

---

## 4. Wave 0–1.3 路径复盘

### 4.1 Wave 0：开空间，而不是堆对象

Wave 0 的正确性在于先定义 agent-native target space，然后每个原语都有明确 space：

```text
Trace → AgentRunReceipt
Context → ContextTrust
Evaluation → EvaluationReport
Authority → AuthorityTransitionRecord
Feedback → PlanningPolicyView
Deliberation → OptionSetReceipt / PlanDraftReceipt
```

而且全部 receipt-only / projection-only，没有新 StateCore 表，没有 Execution Kernel 改动。这个选择非常关键。

它避免了最常见的 agentic 早期错误：

```text
一看到 agent，就立刻加 AgentSession / Task / Loop / Runtime / Scheduler。
```

我们先问的是：

```text
agent 产生的东西在系统里算什么？
```

而不是：

```text
agent 怎么跑得更久？
```

这是正确的。

---

### 4.2 Wave 1：从 primitive plane 到 flow proof

`AgentCognitionFlow` 把目标、option set、plan draft、evaluation、authority transition、agent run receipt 串起来。代码头部仍然声明 No LLM、No broker、No StateCore table、No Execution Kernel。

这一步证明：

```text
这些原语不是孤立 schema；
它们能形成 deterministic cognition chain。
```

这对 FinHarness 特别重要。因为在资本判断系统里，单个 artifact 没有意义，chain 才有意义：

```text
context → reasoning → evaluation → authority → trace
```

---

### 4.3 Wave 1.2：让 flow 有语义

`plan_draft_evaluator.py` 现在是 deterministic evaluator，会检查 plan completeness、stop conditions、option set linkage，并拒绝 action/execution language。

它不是"聪明 evaluator"，但它是第一层 semantic evaluator：

```text
PlanDraft 不是任意文本；
PlanDraft 必须满足结构条件；
PlanDraft 不能偷偷携带 execution language。
```

这正是古典软件与 agentic 软件的交界点：

```text
LLM 可以生成文字；
系统必须把文字降解/提升成可验证结构。
```

---

### 4.4 Wave 1.3：关闭语义逃逸口

Wave 1.3 的关键不是新增能力，而是消除绕过路径。

#### eval override 关闭

旧 `eval_status` 参数已删除，传旧参数会 TypeError。测试明确覆盖。

现在只有 `evaluator_override + allow_evaluation_override=True` 双因素路径，而且默认走真实 evaluator。

#### ContextUsePolicy 接入 flow

`run_agent_cognition_flow()` 现在接收 `context_trust_by_ref` 与 `required_context_use`，并调用 `validate_context_refs_for_use()`。如果 source refs 没有 trust metadata，会生成 warn finding；如果 trust 不允许 required use，则生成 block finding。

#### Evaluation status 重新计算

context findings 会 merge 到 evaluator findings，然后 recompute：

```text
any block → block
any warn → warn
else keep evaluator status
```

#### Authority 消费最终 evaluation status

authority transition 使用 recomputed `eval_report.status` 派生 eligibility。

所以现在真正成立的是：

```text
source_refs
→ context validation
→ plan evaluator
→ merged findings
→ recomputed EvaluationReport.status
→ authority eligibility
```

这已经是 semantically governed flow，不只是 artifact flow。

---

## 5. 我们这条路径的实际作用

### 5.1 对 agent 的作用：把"能力"变成"责任结构"

普通 agent 工程常说：

```text
agent can use tools
agent can plan
agent can reason
agent can call APIs
```

但 FinHarness 现在能说：

```text
agent 的 context 有 trust profile
agent 的 plan 是 deliberation artifact
agent 的 evaluation 是 receipt-backed projection
agent 的 authority transition 是 eligibility-only
agent 的 run 有 trace receipt
agent 不能把 draft context 当 evidence
agent 不能把 warn/block evaluation 覆盖成 eligible
```

这比"agent 会做事"更重要。

---

### 5.2 对古典软件的作用：保护 Execution Kernel

FinHarness 的古典层本来已经有 canonical Execution Kernel。最危险的事情就是 agentic layer 快速污染 Execution Kernel。

我们没有这么做。

到 Wave 1.3 为止，新增的是 cognition plane，不是 execution plane：

```text
没有新 StateCore 表
没有 Execution Kernel 改动
没有新 API route
没有 broker 接入
没有 OrderDraft 生成
```

这使古典软件层保持稳定，同时 agentic 层逐步获得表达能力。

---

### 5.3 对未来智能提升的作用：给更强 agent 一个可承载结构

这点最关键。

如果未来模型更强，它不会只需要更多 tools。它需要更清晰的"世界结构"：

```text
什么能读
什么能引用
什么能作为证据
什么只是草稿
什么是计划
什么是评价
什么是权限资格
什么是执行授权
什么必须 human gate
什么可以进入反馈闭环
```

FinHarness 这轮做的就是给更强 agent 建立这些坐标系。

所以它不是过早抽象。它是在提前建设 agent-native operating semantics。

---

## 6. 与业界相比，我们领先在哪里，不领先在哪里

### 领先点

#### 6.1 责任迁移建模比较早

主流框架更多关注 tools、sessions、graphs、handoffs、observability。FinHarness 更早把 attention 放在：

```text
Evaluation → Authority
ContextTrust → Evaluation
Trace → Accountability
Deliberation ≠ Execution
Human confirmation ≠ override
```

这在 domain-agent 系统里是更核心的问题。

#### 6.2 domain semantics 比通用 guardrails 更具体

通用 guardrail 通常是 input/output validation。FinHarness 的 guardrail 是：

```text
source_refs allowed_uses
plan action-language detection
evaluation status recompute
authority eligibility mapping
execution boundary freeze
```

这是更 domain-native 的 guardrail。

#### 6.3 receipt-first 比 state-first 更适合早期 agentic migration

如果过早把 agent artifact 放进 StateCore，会导致对象膨胀和语义固化。receipt-only / projection-only 给了我们试错空间，同时保留审计性。

---

### 不领先点 / 仍落后点

#### 6.4 还没有 runtime loop

OpenAI Agents SDK、LangGraph、AutoGen 都已经有成熟 runtime / orchestration / session / multi-agent pattern。FinHarness 还没有把 cognition flow 接入真实 agent loop。

这不是缺陷，是阶段选择。但不能误判为已经拥有完整 Agent Runtime。

#### 6.5 还没有 durable agent session

LangGraph 明确区分 checkpointer / store：checkpointer 负责 thread-scoped graph state，store 负责 cross-thread durable memory。

FinHarness 现在有 receipts，但还没有 AgentSession / checkpointer / resumable task state。

#### 6.6 evaluator 仍是 deterministic lexical evaluator

当前 plan evaluator 很有用，但它不是财务合理性 evaluator。它检查：

```text
结构完整性
action language
source refs
stop conditions
option set linkage
required evaluations
```

不是检查：

```text
这个 plan 在资本配置上是否正确
这个 risk assumption 是否成立
这个 scenario 是否完整
```

这需要下一层 domain evaluator。

---

## 7. 路径是否需要调整？

我的判断：**大方向不需要调整。节奏需要保持克制。**

现在最容易犯的错误是：看到 Wave 1.3 成功，就立刻进入大 runtime：

```text
AgentSession
TaskRuntime
Scheduler
Autonomous loop
Multi-agent manager
CapitalActionKernel
```

我不建议马上这么做。

更好的路线是：

```text
先 runtime integration，不先 runtime expansion。
```

也就是说，Wave 2 不应该是"新建很多运行时对象"，而应该是：

```text
把现有 Agent Tool Runtime 的真实 dispatch / context projection / tool call envelope
接入 AgentCognitionFlow 的 trace/eval/context/authority 结构。
```

---

## 8. Wave 2 应该是什么

我建议 Wave 2 定义为：

```text
Wave 2: Runtime Integration, not Runtime Expansion
```

核心目标：

```text
真实 agent runtime 运行时，
能够自动产生 AgentRunReceipt，
自动带入 ContextTrust，
自动把 selected source_refs 做 ContextUsePolicy validation，
自动把 deliberation/evaluation/authority artifacts 写入 receipt trail。
```

### Wave 2 最小 PR DAG

| PR   | 内容                                                              |
| ---- | --------------------------------------------------------------- |
| W2-1 | Agent runtime dispatch 自动写 `AgentRunReceipt` skeleton           |
| W2-2 | context projection 输出 `context_trust_by_ref` map                |
| W2-3 | `run_agent_cognition_flow_from_context_projection()`            |
| W2-4 | tool result envelope → evidence/source refs bridge              |
| W2-5 | evaluator registry v0：只注册 deterministic evaluators              |
| W2-6 | runtime smoke：真实 context projection → cognition flow → receipts |
| W2-7 | architecture sync                                               |

暂时不要做：

```text
AgentSession table
autonomous scheduler
execution connection
multi-agent manager
CapitalActionKernel
```

---

## 9. 判断标准：什么时候才进入更高 runtime？

只有当下面几个条件满足，才进入 AgentSession / TaskRuntime：

```text
1. 至少 2–3 条 cognition flows 需要 resume / retry / cancellation
2. AgentRunReceipt 不足以表达 run lifecycle
3. context projection 与 evaluation 需要跨多轮保存 working state
4. 人类 review 需要在中间 interrupt / resume
5. 多 agent handoff 开始产生真实 trace complexity
```

否则 AgentSession 现在就是 premature abstraction。

---

## 10. 最终复盘判断

> **FinHarness 的路径是正确的：不是先让 agent 多行动，而是先定义 agent 的认知对象、证据边界、评价语义、权限转换和 trace 结构。**

它的实际作用是：

```text
把 agentic layer 从"会调用工具的 LLM"
提升成"有责任结构的认知运行层"。
```

这对 FinHarness 这种新兴 agentic + 古典混合项目尤其重要，因为它既需要 agent 的探索性，又必须保护古典 Execution Kernel 的确定性。

当前状态：

```text
FinHarness is not yet an autonomous agent runtime.
But it now has a domain-native, receipt-backed, semantically governed cognition plane.
```

中文更直接：

> **它还不是"自动代理系统"，但已经是"可审计代理认知层"。**

---

## References

- [OpenAI Agents SDK](https://openai.github.io/openai-agents-python/)
- [LangGraph Overview](https://docs.langchain.com/oss/python/langgraph/overview)
- [AutoGen](https://microsoft.github.io/autogen/stable/)
- [MCP Introduction](https://modelcontextprotocol.io/introduction)
- [When Agents Do Not Stop: Uncovering Infinite Agentic Loops](https://arxiv.org/abs/2607.01641)
- [Secure Plan-then-Execute Implementations](https://arxiv.org/abs/2509.08646)
- [LangGraph Durable Execution / Persistence](https://docs.langchain.com/oss/python/langgraph/durable-execution)
