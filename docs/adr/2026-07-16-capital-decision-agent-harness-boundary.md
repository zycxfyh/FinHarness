# ADR: Capital Decision Agent Harness Ownership Boundary

- Status: Accepted
- Date: 2026-07-16
- Issue: #405
- Baseline: `main@d00cd968d504f6655d993a6aa40f08a8f0d5eab7`
- Plane: Agent
- Reference-First classification: B — Adapt

## Context

FinHarness already has a provider-neutral `AgentWorkDecisionPort`, a bounded
observation-driven reducer, deterministic tool and autonomy admission,
independent budgets, terminal work results, and durable trace/receipt paths.
It also exposes tools through the OpenAI Agents SDK. What it lacked was one
accepted boundary between mature runtime mechanics and capital-domain meaning.

Without that boundary, a provider adapter could accidentally become a second
work lifecycle, provider session state could be treated as current capital
truth, an MCP server could appear to grant tool authority, or a workflow engine
could acquire domain-policy ownership merely because it stores checkpoints.

## Reference-First basis

The OpenAI Agents SDK already owns a model turn loop, tool-call execution,
streaming, handoffs, sessions, usage accounting, human-in-the-loop run state,
and observability tracing. Its run state and trace remain runtime mechanics;
they do not define FinHarness capital truth or evidence policy.

MCP defines a client-host-server protocol for negotiated tools, resources,
prompts, lifecycle, and transport. Its own architecture explicitly does not
dictate how an AI application uses the supplied context. Therefore MCP cannot
be the owner of ContextTrust, evidence admission, tool admission, or authority.

LangGraph supplies low-level durable execution, checkpoint persistence,
interrupts, and human-in-the-loop resume. Those mechanics are eligible only
after a measured long-running, restart, scheduling, or compensation need. They
do not justify making a graph runtime the default core path today.

Primary references:

- [OpenAI Agents SDK — running agents](https://openai.github.io/openai-agents-python/running_agents/)
- [OpenAI Agents SDK — human in the loop](https://openai.github.io/openai-agents-python/human_in_the_loop/)
- [OpenAI Agents SDK — tracing](https://openai.github.io/openai-agents-python/tracing/)
- [MCP architecture](https://modelcontextprotocol.io/docs/learn/architecture)
- [MCP authorization](https://modelcontextprotocol.io/specification/2025-11-25/basic/authorization)
- [LangGraph overview](https://docs.langchain.com/oss/python/langgraph/overview)
- [LangGraph persistence](https://docs.langchain.com/oss/python/langgraph/persistence)
- [LangGraph interrupts](https://docs.langchain.com/oss/python/langgraph/interrupts)

## Decision

### One runtime selection point

`finharness.agent_work_loop.AgentWorkDecisionPort` remains the single future
provider selection point. Issue #287 owns the separate adoption decision
between a direct Responses API adapter and the OpenAI Agents SDK. Until that
decision is accepted, neither candidate is frozen as a product dependency.

A selected runtime must enter behind this port and translate its tool calls,
interruptions, failures, and results into the existing Harness lifecycle. It
must not create a parallel core loop, terminal chain, admission path, or trace
authority.

### Runtime-owned mechanics

Mature provider/runtime implementations may own:

- model turns and typed tool-call transport;
- streaming events and runtime handoffs;
- session and conversation mechanics;
- bounded transport retry behavior;
- token/request usage accounting;
- observability trace export.

These are adopted mechanics, not capital authority.

### FinHarness-owned semantics

FinHarness remains the only owner of:

- server-resolved ContextWorld and exact domain-version binding;
- CapitalState and DecisionCase meaning;
- evidence admissibility and claim/source policy;
- tool visibility, admission, and dispatch policy;
- authority and autonomy admission;
- stale-world replan policy;
- independent budgets and stop/escalation policy;
- domain evaluation and readiness;
- canonical durable AgentRunTrace and operation receipts;
- human review, correction, and handoff.

Provider sessions and checkpoints are runtime state or disposable cache. They
must bind their provider/agent definition and ContextWorld version, and cannot
replace CapitalStateVersion, DecisionCaseVersion, EvidenceSetVersion,
PolicyVersion, AgentRunTrace, or another DomainRecord.

### Candidate-only output

Model output remains candidate-only until the owning deterministic domain
boundary admits it. The allowed contribution outputs are:

- candidate evidence;
- data gaps;
- Scenario request;
- proposal draft;
- human handoff.

No model output may self-admit evidence, mutate domain truth, grant authority,
write a decision of record, authorize execution, or cause an external effect.

### MCP boundary

Issue #300 remains the deferred owner of a vetted external MCP read-tool
boundary. MCP may own capability negotiation, discovery, prompts transport,
protocol lifecycle, and transport errors. It may not own context trust,
evidence/tool admission, domain truth, decision validity, authority, canonical
receipts, or execution permission.

### Optional workflow-engine boundary

A mature workflow runtime may later own checkpoint, resume, scheduling,
interrupt, and compensation mechanics only after a measured need and a separate
adoption decision. It cannot own CapitalState or DecisionCase meaning, evidence
admission, authority policy, stale-world policy, domain evaluation, or execution
permission. A workflow engine is not a default core dependency.

## First evaluation task

The first real contribution benchmark is a **concentration decision
contribution**, not a recommendation or execution task.

It consumes exact CapitalStateVersion and DecisionCaseVersion identities,
admitted EvidenceSetVersion, and effective PolicyVersion. Its output is limited
to the five candidate types above. Evaluation must cover:

1. exact world and domain-version freshness;
2. evidence lineage and admission status;
3. deterministic concentration facts separated from model interpretation;
4. uncertainty, counter-evidence, and data gaps;
5. a Scenario request when the current basis is insufficient;
6. policy and mandate constraints treated as deterministic inputs;
7. bounded stop, escalation, and human handoff;
8. a candidate-only result with no execution authority.

The task has `execution_allowed=false` and cannot directly mutate a domain.
Issue #279 owns the later real-task benchmark implementation.

## Migration and ownership

This ADR moves no runtime or persisted state. Existing implementation owners
remain separate:

| Concern | Owner |
| --- | --- |
| Provider selection behind DecisionPort | #287 |
| Semantic observations and canonical run trace | #291 |
| Server-resolved world versions | #284 |
| Replan, retry, fallback, and no-progress | #278 |
| Real-task evaluation | #279 |
| Provider capability routing | #280 |
| Skills/playbooks as runtime policy | #290 |
| Governed memory lifecycle | #288 |
| External MCP boundary | #300 |
| Product handoff | #310 |

## Rejected alternatives

- Keeping the handwritten loop as a permanent model runtime duplicates mature
  turn, streaming, session, handoff, and trace mechanics.
- Freezing the OpenAI Agents SDK now preempts #287 without real-task evidence.
- Making LangGraph the default core path adds durability machinery before a
  measured checkpoint/resume or compensation need.
- Letting MCP own admission or authority confuses protocol transport with
  FinHarness policy.
- Treating provider session/checkpoint state as domain state bypasses exact
  version and admission boundaries.
- Adding a generic runtime/workflow registry creates a second lifecycle before
  any concrete adoption decision.

## Executable contract

`config/architecture-layers.yml` contains the exact
`finharness.agent_harness_boundary.v1` contract. The existing architecture
checker rejects:

- unknown top-level fields or parallel loops;
- a selection point or owner other than `AgentWorkDecisionPort` / #287;
- provider ownership of domain semantics;
- provider-state substitution for domain versions or canonical trace;
- MCP ownership of admission, authority, or domain state;
- workflow-engine ownership of domain policy or default activation;
- authoritative, mutating, or execution-capable model/task outputs;
- incomplete concentration-task evaluation criteria.

This is an architecture contract only. It adds no SDK, provider, MCP server,
workflow engine, session/checkpoint store, registry, evaluator platform,
runtime behavior, persistence, API, frontend, or execution path.
