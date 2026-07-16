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

The OpenAI Agents SDK already supplies a complete Runner loop, tool execution,
streaming, handoffs, sessions, usage accounting, serializable human-in-the-loop
run state, and observability tracing. Those are mature capabilities, but a
complete Runner cannot be nested behind FinHarness's single-next-action port.
Its run state and trace also remain runtime mechanics; they do not define
FinHarness capital truth or evidence policy.

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
provider selection point. It is a **single-next-action decision port**: each
invocation returns exactly one `AgentWorkToolRequest` dispatch or `complete`.
`run_bounded_tool_dispatch_loop()` remains the outer Harness reducer and owns
work budgets, autonomy admission, tool/capability admission, dispatch,
canonical Observation reduction, stop reasons, and terminal reduction.

Issue #287 owns the separate adoption decision between a direct Responses API
adapter and the OpenAI Agents SDK. Until that decision is accepted, neither
candidate is frozen as a product dependency. A complete SDK Runner loop,
runtime-internal tool execution, or runtime-internal handoff/terminal chain is
forbidden on this primary path: nesting one behind the DecisionPort would create
a second loop and could bypass the Harness boundary.

Every candidate tool call must return as `AgentWorkToolRequest` and cross all
four local boundaries: autonomy admission, tool/capability admission, work
budgets, and canonical Observation reduction.

### Mature capabilities versus delegated mechanics

Provider runtimes may maturely implement model turn loops, tool execution,
handoffs, sessions, streaming, and tracing. The current DecisionPort delegates
only one model inference/decision turn, typed candidate tool-call decoding,
provider transport retry, token/request usage accounting, and non-authoritative
observability export. Mature capability does not imply delegation through the
current abstraction.

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

Provider sessions, suspended runs, and checkpoints are non-authoritative
runtime state. They may be ephemeral when no resume obligation exists, but must
remain durable while an active pause, resume, recovery, or human-approval
obligation exists. They may be pruned only after the terminal outcome is
persisted, canonical trace reconciliation completes, and pending approval is
resolved or expires. They must bind their provider/agent definition and
ContextWorld version, and cannot replace ContextWorld, CapitalStateVersion,
DecisionCaseVersion, EvidenceSetVersion, PolicyVersion, AgentRunTrace, or
another DomainRecord.

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
boundary. MCP may own protocol capability negotiation, tools/resources/prompts
discovery, lifecycle and transport errors, transport authentication, OAuth
token/scope mechanics, and the resource-server access decision.

FinHarness still owns the approved-server allowlist, accepted-scope policy,
Principal binding, context trust, tool visibility/admission, evidence admission,
CapitalMandate, AgentAuthorityGrant, domain truth, decision validity, execution
permission, and canonical receipts. MCP transport authorization cannot
substitute for principal identity, mandate, grant, tool admission, evidence
admission, or execution authority. This distinction permits standard MCP OAuth
without translating transport access into capital-domain authority.

### Optional workflow-engine boundary

A mature workflow runtime may later own checkpoint, resume, scheduling,
interrupt, and compensation mechanics only after a measured need and a separate
adoption decision. It cannot own CapitalState or DecisionCase meaning, evidence
admission, authority policy, stale-world policy, domain evaluation, or execution
permission. A workflow engine is not a default core dependency.

## First evaluation task

The first real contribution benchmark is a **concentration decision
contribution**, not a recommendation or execution task.

Its input root is one server-resolved ContextWorld owned by #284; callers cannot
supply or override independent world references. One exact DecisionCaseVersion
must match its bound CapitalStateVersion, EvidenceSetVersion, PolicyVersion, and
ProposalVersion. Selecting independently latest/current versions is forbidden:
freshness without Case-basis equality is insufficient.

Principal, CapitalMandateVersion, and AgentAuthorityGrantVersion also come from
that exact ContextWorld. Its output is limited to the five candidate types
above. Evaluation must cover:

1. exact world and domain-version freshness;
2. evidence lineage and admission status;
3. deterministic concentration facts separated from model interpretation;
4. uncertainty, counter-evidence, and data gaps;
5. a Scenario request when the current basis is insufficient;
6. policy and mandate constraints treated as deterministic inputs;
7. bounded stop, escalation, and human handoff;
8. a candidate-only result with no execution authority.

The task has `execution_allowed=false` and cannot directly mutate a domain. The
current implementation is explicitly `not_yet_conforming`; Issue #279 owns the
later real-task benchmark implementation, with #284 and #291 as prerequisites.

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
- a full SDK Runner, internal tool execution/handoff, multi-action decision, or
  tool call that bypasses Harness admission, budgets, or Observation reduction;
- treating a mature runtime capability as delegated through the current port;
- provider ownership of domain semantics;
- provider-state authority, premature pruning, or substitution for ContextWorld,
  domain versions, or canonical trace;
- mixed Case-basis inputs, caller-supplied world refs, missing ProposalVersion,
  or mandate/grant bindings outside the exact ContextWorld;
- MCP transport OAuth being removed or being treated as Principal, mandate,
  grant, admission, or execution authority;
- workflow-engine ownership of domain policy or default activation;
- authoritative, mutating, or execution-capable model/task outputs;
- incomplete concentration-task evaluation criteria.

This is an architecture contract only. It adds no SDK, provider, MCP server,
workflow engine, session/checkpoint store, registry, evaluator platform,
runtime behavior, persistence, API, frontend, or execution path.
