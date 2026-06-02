# Goal-Bound Workflow Orchestration Scan

Date: 2026-06-01

Purpose: evaluate whether FinHarness goals should be bound to explicit
workflows so an AI agent completes goals through planned nodes, checkpoints,
reviews, receipts, and human gates instead of only looping until completion.

## Short Answer

Yes.

The useful design is not:

```text
goal -> while not done: ask model what to do next
```

The stronger design is:

```text
goal
-> classify goal type
-> select workflow
-> instantiate workflow state
-> run graph nodes
-> checkpoint after each node
-> require human gates for sensitive actions
-> produce receipts/reviews/lessons
-> mark goal complete only when exit criteria are met
```

The loop is still there, but it becomes subordinate to a workflow.

## Why The Simple Goal Loop Is Not Enough

A simple goal loop is usually:

```text
observe
plan next step
act
check result
repeat
```

This is similar to older ReAct-style loops and Ralph-style execution loops.
It is powerful because it is general.

But for finance and software engineering, generality is also the risk:

```text
the agent can drift
success criteria become vague
state is buried in conversation
long tasks are hard to resume
tool failures become ad hoc
human approval is bolted on late
completion claims become overconfident
```

FinHarness should not rely on "keep going until done" as the main control
structure.

## External Practice Signals

### OpenAI: Agent Loop Plus Workflow, Trace, Handoff, Durable Execution

OpenAI Agents SDK documentation frames `Agent + Runner` as the layer that manages
turns, tools, guardrails, handoffs, and sessions. It also exposes workflow names,
trace IDs, group IDs, hooks, handoffs, tool behavior, max-turn failures, and
durable execution integrations for long-running agents.

Important signals:

```text
agent loop exists
but it is wrapped with:
  guardrails
  handoffs
  sessions
  traces
  workflow names
  max turn limits
  durable execution integrations
  human-in-the-loop patterns
```

OpenAI's practical guide also distinguishes declarative graph workflows from
code-first orchestration, and discusses manager/orchestrator patterns versus
handoff patterns.

FinHarness adaptation:

```text
Goal mode should not be only a loop.
It should create a named workflow run with trace/receipt metadata.
```

### Anthropic / Claude: Subagents And Specialized Context

Claude Agent SDK documentation emphasizes subagents for focused subtasks,
parallel analyses, specialized instructions, and context isolation. Subagents
can be programmatic or filesystem-defined, and the main agent can delegate
based on descriptions.

Important signals:

```text
do not stuff every task into one context
delegate specialized subtasks
isolate noisy work
return compact outputs to the main workflow
```

FinHarness adaptation:

```text
A goal workflow can spawn specialized lanes:
  research
  code implementation
  tests
  review
  documentation
  risk/safety
```

But the main workflow should still own the final receipt and completion claim.

### Google Gemini Managed Agents: Versioned Agent Behavior And Resumable State

Google's Managed Agents direction emphasizes secure cloud sandboxes,
versionable instructions/skills using AGENTS.md and SKILL.md-style files,
tool/code execution, web browsing, and resumable sessions with files and state.

Important signals:

```text
agent behavior should be versioned
execution should happen in bounded environments
state should survive follow-up calls
skills/instructions become first-class artifacts
```

FinHarness adaptation:

```text
Goal workflows should be repo-defined, versioned, and resumable.
AGENTS.md should describe when to use each workflow.
```

### LangGraph: Workflow State, Persistence, Human-In-The-Loop

LangGraph's core value is representing agent/workflow execution as a state graph.
Its persistence and durable execution docs emphasize checkpointing graph state,
resuming runs, fault tolerance, human-in-the-loop inspection, interrupts, and
approval before continuing.

Important signals:

```text
graph state is the source of truth
checkpoints make long tasks resumable
human gates should inspect state, not only approve a vague final answer
```

FinHarness adaptation:

```text
Goal mode should instantiate a LangGraph workflow with:
  GoalSpec
  WorkflowSpec
  Checkpoint
  Gate
  Receipt
  Review
```

## Proposed FinHarness Model

### 1. GoalSpec

```text
goal_id
created_at
user_intent
goal_type
success_criteria
non_goals
permissions
risk_level
workflow_id
status
```

### 2. WorkflowSpec

```text
workflow_id
version
nodes
edges
required_artifacts
human_gates
exit_criteria
failure_modes
```

### 3. GoalRun

```text
goal_id
run_id
workflow_id
current_node
node_outputs
checkpoints
receipts
open_questions
blocked_reason
completion_evidence
```

### 4. Completion Rule

A goal is complete only when:

```text
exit criteria are satisfied
required artifacts exist
tests/checks pass or failure is explicitly accepted
receipts link to evidence
review/lesson decision is made when needed
```

The agent should not mark completion just because it ran out of turns or wrote a
convincing answer.

## Workflow Selection

FinHarness can route goals by type:

```text
research goal:
  idea -> note -> synthesis -> proposal/recommendation -> receipt

implementation goal:
  proposal -> code -> tests -> docs -> review -> receipt

finance data goal:
  source -> ingest -> normalize -> quality -> snapshot -> receipt

strategy research goal:
  hypothesis -> data -> backtest -> risk -> proposal -> review

paper execution goal:
  proposal -> risk gate -> broker adapter -> execution receipt -> review

architecture goal:
  context -> alternatives -> ADR -> module doc -> tests/checks
```

## Key Design Principle

```text
Goal mode owns persistence and completion.
Workflow mode owns sequence and gates.
Agent loop owns local reasoning inside each node.
```

This separation matters:

```text
goal without workflow:
  persistent but vague

workflow without goal:
  structured but not purposeful

loop without both:
  flexible but hard to audit
```

## MVP For FinHarness

Add a thin goal orchestration layer:

```text
src/finharness/goal_runner.py
docs/modules/00-goal-orchestration.md
data/receipts/goals/
```

Minimum objects:

```text
GoalSpec
GoalRunReceipt
WorkflowBinding
```

First supported workflows:

```text
cognitive_graph:
  for idea -> proposal -> review -> lesson

finance_graph:
  for data-entry research workflows

trade_graph:
  for paper execution workflows only after risk gates
```

Do not build a general autonomous engine yet.

Start with:

```text
goal -> workflow selection -> run existing LangGraph -> receipt -> completion check
```

## Sources

- OpenAI Agents SDK, running agents:
  https://openai.github.io/openai-agents-python/running_agents/
- OpenAI Agents SDK, agent definition and orchestration:
  https://openai.github.io/openai-agents-python/agents/
- OpenAI practical guide to building agents:
  https://openai.com/business/guides-and-resources/a-practical-guide-to-building-ai-agents/
- Claude Agent SDK subagents:
  https://code.claude.com/docs/en/agent-sdk/subagents
- Google Managed Agents in the Gemini API:
  https://blog.google/innovation-and-ai/technology/developers-tools/managed-agents-gemini-api/
- LangGraph durable execution:
  https://docs.langchain.com/oss/python/langgraph/durable-execution
- LangGraph persistence:
  https://docs.langchain.com/oss/python/langgraph/persistence
- LangGraph workflows and agents:
  https://docs.langchain.com/oss/python/langgraph/workflows-agents
