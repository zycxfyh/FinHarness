# Wave 2: Runtime Integration, not Runtime Expansion

date: 2026-07-09
source: architect plan
status: executing
layer: agentic-cognition-plane

## 总目标

让真实 AgentRuntime 的 context、tool call、tool result、evidence refs、trace refs，
能够进入 AgentCognitionFlow，
并自动生成 receipt-backed evaluation / authority / run trace。

## 一句话

> **Wave 1.3 证明 cognition flow 是可约束的；Wave 2 要证明真实 runtime 可以安全进入这条 flow。**

## 硬边界

- 0 Execution Kernel change
- 0 broker / adapter expansion
- 0 OrderDraft / ExecutionOrder generation
- 0 StateCore table
- 0 AgentSession table
- 0 TaskRuntime table
- 0 autonomous scheduler
- 0 multi-agent manager
- 0 authority grant consumption
- 0 LLM evaluator

## PR DAG

| PR   | Phase | 内容                                              | Space                  |
| ---- | ----- | ------------------------------------------------- | ---------------------- |
| #190 | A     | Runtime dispatch emits AgentRunReceipt skeleton    | Trace / Runtime Int    |
| #191 | B     | Context projection exposes ContextTrust map        | Context / Projection   |
| #192 | B     | Run cognition flow from context projection         | Context+Eval+Trace     |
| #193 | C     | Tool result evidence envelope                      | Trace / Evidence       |
| #194 | C     | Bridge tool envelopes into cognition flow inputs   | Trace+Context+Eval     |
| #195 | D     | Deterministic evaluator registry v0                | Evaluation             |
| #196 | D     | Runtime-integrated cognition smoke                 | Runtime / Trace / Eval |
| #197 | D     | Wave 2 architecture sync                           | Architecture Memory    |

## 执行顺序

#190 → #191 → #192 → #193 → #194 → #195 → #196 → #197

## 验收标准

Wave 2 完成后应能说：
> 真实 AgentRuntime 的上下文、工具结果、证据 refs 和 trace，
> 已经可以进入 AgentCognitionFlow，
> 并产生可审计的 EvaluationReport / AuthorityTransition / AgentRunReceipt。

不应说：
> FinHarness 有 autonomous agent runtime。

正确表述：
> FinHarness has runtime-integrated, receipt-backed, semantically governed agent cognition.
