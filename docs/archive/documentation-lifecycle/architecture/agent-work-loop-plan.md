# Agent Work Loop v0 — Planning Framework

> Wave 2.2: establish a bounded, auditable, stoppable, learnable agent work cycle.

> **Current status (2026-07-11): semantic acceptance met.** Agent Operating
> Cycle v0.1 closes all 15 AUT2 foundation contracts. Session, scheduling,
> checkpoint/resume, subagents, AUT3 delegated decisions, and effect authority
> remain later programs.

## What Wave 2.1 completed

Wave 2.1 hardened the Agent Operating Surface from "surface objects exist"
to "surface semantics are consumed by runtime, flow, memory, playbooks,
evaluator discovery, and workspace." Specifically:

| Surface | Status after 2.1 |
|---|---|
| Tool Registry | Strict, authoritative, findings-visible |
| Tool Availability | Global universe + cached checks |
| Tool Result Envelope | Clean ref taxonomy (provider ≠ evidence) |
| Runtime Trace | sink.dispatch() lifecycle |
| Context Trust | Typed extraction findings |
| Domain Memory | Propose → attest → promote to context pack |
| Receipt Search | JSONL index for recall |
| Playbook | Real YAML parser + frontmatter validation |
| Evaluator Registry | Both evaluators registered, discoverable |
| Operating Flow | Playbook requirements enforced |
| Review Workspace | Receipt-hydrated with findings/data_gaps |
| Smoke | 24 semantic lifecycle checks |

## Current primary contradiction

```
有工具、记忆、搜索、playbook、evaluator、workspace、trace sink，
但还没有一个统一的 bounded work loop 把它们组织成完整工作周期。
```

The surfaces exist and are semantically consumable, but they are still
orchestrated ad-hoc by individual test cases and smoke scripts. There is
no single entry point that:

1. Accepts a work request with explicit budget
2. Freezes a context snapshot before work begins
3. Dispatches tools within budget constraints
4. Traces every dispatch into a receipt
5. Validates playbook requirements
6. Runs the cognition flow (evaluation → authority)
7. Updates the search index
8. Hydrates the review workspace
9. Optionally proposes domain memory
10. Produces a single work result with explicit stop reason

## Wave 2.2 Goal

```
建立 Agent Work Loop v0：
让 agent 能从一个明确 work request 出发，
在有限预算内完成 context acquisition、tool dispatch、
playbook requirement check、evaluation、trace、
memory/search update、workspace hydration。
```

The result is NOT execution, NOT autonomous action. It is:

```
一个完整、可审计、可复盘、可搜索、可继续推进的人机协作工作包。
```

## What work loop is NOT

- **Not session.** A work loop is one bounded unit. A session may span
  multiple work loops, but session is Wave 3 territory.
- **Not scheduler.** A work loop runs once when triggered. Recurring
  scheduled work loops are Wave 4 territory.
- **Not execution.** A work loop never creates orders, contacts brokers,
  or transitions authority to execution. It produces review artifacts.
- **Not multi-agent.** A work loop runs in a single profile context.

## Non-goals (this wave)

- No Execution Kernel integration
- No OrderDraft / ApprovalRecord creation
- No broker adapter interaction
- No autonomous scheduler / cron
- No AgentSession table / persistence
- No multi-agent manager
- No MCP/plugin ecosystem
- No LLM evaluator marketplace

## Design principles

### Bounded budget
Every work loop has `max_tool_calls` (default 5) and `max_steps` (default 8).
The loop stops when budget is exhausted, regardless of remaining work.

### Frozen context snapshot
Before any work is done, the context projection payload is frozen into an
`AgentWorkContextSnapshot`. The work loop consumes only the snapshot — no
dynamic context reads during the loop.

### Trace-by-default
Every tool dispatch in the work loop passes through `AgentRuntimeTraceSink`.
At loop completion, an `AgentRunReceipt` is always written, even for failed
or partial loops.

### Explicit stop reason
Every work loop terminates with a specific `AgentWorkStopReason`, not a
generic "failed" or "partial". See PR #228 for the full taxonomy.

### Playbook-bound
When a playbook is specified, its `required_context_packs` and
`recommended_evaluators` are validated before the loop executes.

### Searchable output
After the loop completes, the receipt search index is updated so the work
result is discoverable by work_id, goal, status, and refs.

### Execution-allowed never crosses False
The work loop operates entirely in review/cognition space. No tool has
`execution_allowed=True`. No authority transition grants execution
eligibility.

## PR DAG

```
#218 Plan (this doc)
  │
  ▼
#219 AgentWorkRequest / AgentWorkResult (models)
  │
  ▼
#220 AgentWorkContextSnapshot (context freeze)
  │
  ▼
#221 Bounded tool dispatch loop (core loop)
  ├──► #222 Trace sink integration
  ├──► #223 Playbook-bound planning
  │
  ▼
#224 Cognition flow from work result
  ├──► #225 Search index update
  ├──► #226 Hydrated workspace from work loop
  ├──► #227 Domain memory from completed work
  │
  ▼
#228 Stop reason taxonomy
  │
  ▼
#229 Agent Work Loop semantic smoke
  │
  ▼
#230 Architecture sync
```

## Wave 2.2 acceptance criteria

Executable closure gate:

```bash
task agent:work-loop-acceptance
```

As of 2026-07-11 the gate is green: **15/15 contracts pass and 0 remain open**.
`task agent:work-loop-acceptance-report`
prints the same repository evidence with a zero diagnostic exit. A future
implementation may change this baseline only by closing a real contract and
updating the architecture status in the same slice.

给定一个 AgentWorkRequest，FinHarness 可以在有限预算内完成一项 agent
work cycle，并输出：

- AgentWorkResult
- AgentRunReceipt
- EvaluationReport
- SearchIndex entry
- HydratedReviewWorkspace

同时：

- every stop path visible
- every tool call traced
- every context snapshot frozen
- every playbook requirement checked
- every generated workspace hydrated
- every result searchable
- no execution boundary crossed

## Target state naming after semantic closure

```
Agent Operating Cycle v0.1
Agent Cognition Runtime overall v0.93
```

The current state is named:

```text
Agent Operating Surface: semantically consumable
Agent Operating Cycle v0.1: current AUT2 foundation
Agent Cognition Runtime: v0.93, without session/resume/scheduling
```

## Future waves

| Wave | Trigger | Deliverable |
|---|---|---|
| Wave 3 | Wave 2.2 semantic closure plus real retry/resume/interrupt needs | AgentSession, WorkCheckpoint, ResumePolicy |
| Wave 4 | Periodic tasks / external tools | ScheduledCognitionJob, SubagentWorkEnvelope, MCPEvidenceAdapter |
| Wave 5 | Stable proposal lifecycle | ExecutionCandidateReview, PreExecutionSimulation, ApprovalHandoff |
