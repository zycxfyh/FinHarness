# Wave 2: Agent Operating Surface

date: 2026-07-09 (revised)
source: architect plan v2
status: executing
layer: agentic-operating-surface

## 总目标

让 FinHarness 从"可审计 agent cognition flow"升级为"有真实 operating surface 的 domain agent environment"。

## 核心原则

1. **强 agent 假设**：未来 agent 能理解 draft/evidence/plan/execution 区别；系统不围绕"防蠢"设计
2. **Hermes 启发 — narrow waist, edge expansion**：agent core 不膨胀，operating surfaces 扩张
3. **Governance 是承重结构，不是产品本体**：叙事中心是 agent 能力面，不是安全笼子

## Wave 2 PR DAG (revised)

| PR   | Track        | 标题                                         | 状态 |
|------|-------------|----------------------------------------------|------|
| #190 | Architecture | Agent Operating Surface RFC                  | 待做 |
| #191 | Tool         | AgentToolRegistry v0                         | 待做 |
| #192 | Tool         | Tool availability snapshot                   | 待做 |
| #193 | Runtime      | Tool result evidence envelope                | 待做 |
| #194 | Runtime      | AgentRuntime → AgentRunReceipt bridge        | 已合并 |
| #195 | Context      | Context projection → trust map               | 待做 |
| #196 | Search       | Receipt / run search v0                      | 待做 |
| #197 | Memory       | Domain memory draft + promotion path         | 待做 |
| #198 | Playbook     | CognitionPlaybook spec                       | 待做 |
| #199 | Playbook     | Progressive disclosure loader                | 待做 |
| #200 | Evaluation   | Evaluator registry v0                        | 待做 |
| #201 | Evaluation   | Research evidence quality evaluator          | 待做 |
| #202 | Flow         | Run flow from operating inputs               | 待做 |
| #203 | Work         | Human review workspace projection            | 待做 |
| #204 | Smoke        | Agent operating surface smoke                | 待做 |
| #205 | Docs         | Wave 2 architecture sync                     | 待做 |

## 执行顺序

#190 → #191 → #192 → #193 → #195 → #196 → #197 → #198 → #199 → #200 → #201 → #202 → #203 → #204 → #205

## 硬边界（继续冻结）

- No StateCore table
- No Execution Kernel change
- No broker connection
- No order/execution object creation
- No autonomous scheduler
- No AgentSession table
- No LLM evaluator marketplace
- No agent freely mutating domain memory
