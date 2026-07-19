# ADR: Keep the Agent Governance Kernel Runtime-Neutral

Date: 2026-07-19  
Status: proposed  
Supersedes: none  
Deciders: FinHarness project operator  
Related Issues: #277, #284, #287, #291, #300, #427, #439, #440

## Context

FinHarness is expected to evolve from one bounded, read-only Agent loop toward
richer orchestration options: stronger or multiple model providers, durable
workflow runtimes, static or dynamic graphs, delegated child Agents, external
MCP tools, A2A-style collaboration, governed memory, and later controlled
self-improvement.

Those mechanisms are intentionally uncertain. Their APIs, persistence models,
message types, tool abstractions, checkpoint semantics, and failure behavior
will continue to change.

The FinHarness domain invariants are less negotiable:

- capital, evidence, policy, decision, mandate, grant, and execution truth remain
  server-owned;
- one logical work request has one canonical responsibility history;
- model output is a proposal for a transition, not proof that the transition
  occurred;
- every tool dispatch is admitted by FinHarness before execution;
- every material result is returned as a typed semantic observation;
- replay and inspection must not repeat side effects;
- runtime authentication, Agent authority, domain truth, and observability remain
  separate concepts.

External runtimes commonly own more than FinHarness can safely delegate. For
example, an Agent SDK runner may own the model loop, handoffs, tool execution,
and terminal-output rule. A graph runtime may persist thread checkpoints and
re-execute model or API nodes when replaying from an earlier checkpoint. A
workflow engine may rebuild local state by replaying an event history and may
require deterministic, versioned orchestration code.

Those runtime behaviors are legitimate implementation strategies. They must not
silently become the canonical FinHarness governance model.

The current product roadmap already separates the relevant implementation
owners:

- #291 owns one canonical `AgentRunTrace` per `WorkRequest`;
- #439 owns typed `AgentWorkObservation` transport;
- #440 owns side-effect-free hydration and replay;
- #287 owns one model/runtime adapter behind `AgentWorkDecisionPort`;
- #284 owns server-resolved `ContextWorld`;
- #427 will later select the minimal supported runtime dependency profile using
  product evidence.

This ADR records the architecture boundary joining those owners. It does not
implement them or choose a provider or orchestration framework.

## Decision

FinHarness will use a **runtime-neutral Agent governance kernel** as the stable
waist between replaceable Agent runtimes and canonical domain systems.

```text
replaceable model / Agent / graph / protocol implementations
                         |
                         v
              FinHarness Agent kernel
 WorkRequest -> ContextWorld -> AgentDecision -> ToolRequest
      -> SemanticObservation -> Evaluation -> Stop -> WorkResult
                         |
                         v
 capital / evidence / decision / authority / receipts / effects
```

### 1. Canonical ownership remains inside FinHarness

FinHarness owns the canonical meaning and lifecycle of:

```text
WorkRequest
ContextWorld
AgentDecision
TypedToolRequest
AgentWorkObservation
AgentRunTrace
RunBudgetState
EvaluationState
StopDecision
WorkResult
OperationReceipt references
DomainRecord references
```

A provider SDK object, graph checkpoint, runtime thread, framework message,
provider transcript, tracing span, MCP session, or external Agent task is never
canonical merely because a library persists it.

Such objects may be retained as referenced artifacts or rebuildable projections
when useful.

### 2. Models propose transitions; they do not apply them

A model-facing `AgentDecision` is a closed, typed proposal such as:

```text
CallTool
DelegateWork
RequestHumanInput
RevisePlan
Finalize
Stop
```

The model or external runtime may select one of these proposals. Only the
FinHarness kernel may:

- validate the exact `ContextWorld`;
- check authority, capability, budget, freshness, and policy;
- admit or reject a tool request;
- dispatch a domain tool;
- append canonical trace events;
- determine canonical terminal state;
- request or apply a governed domain mutation through its existing owner.

Provider output cannot directly mutate StateCore, authority, receipts, trace
state, or execution state.

### 3. Runtime adapters remain thin and replaceable

Every supported runtime integrates through an adapter that maps between its
native mechanics and FinHarness contracts.

```text
Provider / Runtime Adapter
  input:
    - exact ContextWorld reference
    - typed prior observations
    - allowed decision schema
    - allowed tool schemas
    - budget and stop policy
  output:
    - one typed AgentDecision proposal
    - provider metadata and usage
    - typed provider failure when applicable
```

The adapter may manage serialization, streaming, provider retries, local SDK
callbacks, and model-specific input/output translation. It does not own domain
semantics, authority, dispatch, canonical persistence, evaluation admission, or
terminal-state legitimacy.

No public or internal domain contract may expose a provider-specific message or
checkpoint type as a required field.

### 4. Runtime persistence is a projection, not canonical history

A runtime may persist:

- threads;
- checkpoints;
- sessions;
- graph state;
- pending node writes;
- provider conversation state;
- local caches.

These are classified as `ProjectionIndex` or runtime-operational state. They may
accelerate resume, debugging, or runtime-native inspection, but they cannot:

- authorize hydration;
- replace `AgentRunTrace`;
- establish that a tool effect occurred;
- establish that an observation was admitted;
- establish current authority or world state;
- become the only copy of information required for canonical replay.

The canonical trace references durable domain artifacts and operation receipts
rather than copying their contents into a second lifecycle store.

### 5. FinHarness replay is inspection and reconstruction, not re-execution

FinHarness distinguishes:

```text
hydrate / inspect / replay
  = reconstruct the recorded run from canonical events and referenced artifacts

retry / resume / fork
  = create a new governed continuation decision under explicit policy
```

Canonical replay must never re-dispatch a side-effecting tool.

If an external graph runtime defines replay as re-running nodes after a
checkpoint, that capability must use a separate explicit retry, resume, or fork
path. It must not be exposed as FinHarness canonical replay.

### 6. Runs bind every interpretation-affecting version

Each canonical run records or references the exact versions needed to interpret
it:

```text
run_kernel_version
orchestration_strategy_version
model_provider and model_snapshot
provider_adapter_version
prompt/instruction version
AgentDecision schema version
tool schema versions
ContextWorld version
context policy version
budget policy version
evaluation policy version
stop policy version
Skill policy version, when present
```

A later deployment must not silently reinterpret a historical run using a new
orchestration strategy or schema.

Compatibility readers may translate legacy records into an inspection view.
They cannot write new legacy records or authorize current state.

### 7. Observability is exported from canonical events

OpenTelemetry or provider-native traces may be emitted as observability
projections derived from canonical run events and operation receipts.

Observability data may help correlate latency, cost, failures, and distributed
calls. It is not the business responsibility ledger and cannot substitute for:

- `AgentRunTrace` ordering;
- exact world-version binding;
- domain admission;
- authority proof;
- effect receipts;
- reconciliation.

### 8. Protocols do not inherit authority

MCP, A2A-style protocols, HTTP, RPC, subprocesses, and provider tool APIs are
transport and interoperability mechanisms.

Their outputs enter FinHarness as untrusted or candidate inputs until the
relevant FinHarness boundary validates schema, provenance, scope, world version,
and admission.

A transport connection, authenticated peer, advertised capability, or remote
Agent identity cannot mint FinHarness authority.

### 9. Multi-Agent expansion composes WorkRequests

Future delegated Agents will not share a second mutable canonical run root.
Delegation will create a child `WorkRequest` with:

```text
parent WorkRequest reference
delegation event reference
bounded ContextWorld slice
capability lease
budget slice
expected result schema
stop/deadline policy
aggregation policy reference
```

Each child work request retains exactly one canonical trace. Its result returns
to the parent as a typed candidate observation or artifact.

The detailed delegation ontology remains a separate dormant research contract.

## Ownership Matrix

| Concern | FinHarness canonical owner | Replaceable implementation |
| --- | --- | --- |
| Domain truth | Capital/Evidence/Decision domain owners | None |
| Exact run identity and event order | `AgentRunTrace` | Runtime trace exporter |
| Context truth | `ContextWorld` resolver | Prompt/context serializer |
| Next-step proposal | `AgentDecision` schema | Model/provider/runtime |
| Tool permission and dispatch | Tool admission + domain tool owner | MCP/function/RPC adapter |
| Tool result meaning | Domain result + `AgentWorkObservation` | Provider message encoding |
| Budget/evaluation/stop legitimacy | FinHarness run kernel and policy | Runtime callbacks/telemetry |
| Hydration and canonical replay | `AgentRunTrace` + referenced artifacts | Runtime checkpoint cache |
| Observability | Derived projection | OpenTelemetry/provider trace |
| External collaboration | Delegation/admission boundary | A2A or other protocol |

## Architectural Invariants

The following statements are normative:

```text
No provider SDK object is a DomainRecord.
No runtime checkpoint is the canonical Agent history.
No provider transcript owns canonical terminal state.
No framework callback owns FinHarness authority.
No transport authentication implies FinHarness authorization.
No model output proves that a tool or effect occurred.
No replay path repeats a side effect implicitly.
No runtime migration rewrites historical domain truth.
One WorkRequest has one canonical AgentRunTrace.
Every observation identifies the exact world and tool request it came from.
```

## Considered Options

### Option 1: Adopt one Agent framework as the FinHarness runtime and truth store

Examples include making an SDK runner, graph thread/checkpoint store, or durable
workflow history the canonical Agent lifecycle.

Pros:

```text
less integration code initially
framework-native resume, tracing, handoffs, and memory
faster access to framework-specific features
```

Cons:

```text
framework persistence semantics become domain semantics
runtime replay may repeat LLM/API/tool work
provider message and checkpoint types leak into durable contracts
switching runtimes requires historical and authority migration
framework terminal state can diverge from FinHarness admission and receipts
```

Rejected because it couples governance truth to a fast-changing external
runtime.

### Option 2: Build a general-purpose FinHarness workflow or multi-Agent engine

Pros:

```text
complete local control
one implementation for every future topology
```

Cons:

```text
reimplements mature workflow and Agent runtimes
creates a generic platform unrelated to the capital-decision product
large maintenance and correctness burden before product evidence exists
prematurely freezes abstractions for multi-Agent and long-running workflows
```

Rejected. FinHarness will own governance semantics and use thin adapters around
mature execution mechanisms.

### Option 3: Runtime-neutral governance kernel with replaceable adapters (chosen)

Pros:

```text
preserves exact domain and authority ownership
supports one simple Agent now without blocking later graph or multi-Agent work
allows runtime replacement without rewriting canonical records
keeps replay, effects, and terminal-state semantics explicit
lets product evidence drive later dependency selection
```

Cons:

```text
requires explicit adapter and projection boundaries
cannot use every runtime convenience as canonical truth
requires conformance tests for each supported runtime
some provider-native features may remain experimental until mapped safely
```

### Option 4: Delay all boundary decisions until a multi-Agent requirement exists

Pros:

```text
no architecture document now
maximum short-term implementation freedom
```

Cons:

```text
current SDK or graph choices may become accidental canonical contracts
later extraction would require migration of persisted runs and tests
Issue owners could implement incompatible trace, replay, or tool semantics
```

Rejected because the stable boundary is already required by #291, #439, #440,
#287, and #284, even for one Agent.

## Consequences

### Positive

```text
FinHarness may start with one provider and one-shot read-only runs while keeping
an upgrade path to durable graphs, multiple providers, child Agents, MCP, A2A,
and governed self-improvement.

Domain truth and authority remain independent from model intelligence and
orchestration complexity.

Historical runs remain interpretable after runtime replacement.

Framework-native checkpoints, sessions, traces, and memory can be adopted as
operational projections without gaining canonical status.
```

### Negative

```text
A runtime integration cannot simply expose its native Runner, thread, message,
or checkpoint model as the FinHarness public contract.

The project must maintain typed adapter boundaries and conformance fixtures.

Some framework features will require an explicit FinHarness semantic mapping
before they can enter the supported product path.
```

### Neutral

```text
This ADR does not select Responses API, OpenAI Agents SDK, LangGraph, Temporal,
Durable Functions, or another runtime.

#287 owns the first DecisionPort integration. #427 retains ownership of the later
minimal supported dependency-profile decision.

This ADR does not activate multi-Agent, MCP, long-term memory, a scheduler, or
live execution.
```

## Confirmation

This decision is working when all of the following remain true:

```text
A provider/runtime adapter can be replaced without changing CapitalState,
EvidenceSet, DecisionCase, Mandate, Grant, or execution records.

One WorkRequest produces exactly one canonical AgentRunTrace even when a runtime
also stores its own thread or checkpoint.

A provider can propose a tool call but cannot dispatch it without FinHarness
admission.

A tool result reaches the next model turn through a typed Semantic Observation,
not by arbitrary artifact reopening or provider-only transcript state.

Hydration reproduces recorded state without invoking a model, API, or
side-effecting tool.

A runtime-native replay feature cannot be confused with canonical FinHarness
replay.

Every historical run remains bound to the versions that interpreted it.

OpenTelemetry or provider traces can be deleted and rebuilt without losing the
canonical responsibility history.
```

Required destructive fixtures for later implementation Issues:

1. A provider output attempts direct tool dispatch.
2. A runtime checkpoint claims a terminal state not present in the canonical
   trace.
3. A replay request would re-run a side-effecting node.
4. A provider-specific message is substituted for the typed observation schema.
5. A caller supplies a trusted world reference or authority grant.
6. A newer orchestration strategy attempts to reinterpret an older run without
   its recorded version.
7. An observability trace is missing while canonical hydration still succeeds.
8. A runtime is replaced while existing run inspection remains valid.

## Rollout

This ADR authorizes no standalone implementation PR.

Its constraints should be realized through the existing canonical owners:

```text
#291 canonical AgentRunTrace
→ #439 typed Semantic Observation
→ #440 hydration/replay
→ #287 primary DecisionPort adapter
→ #284 server-resolved ContextWorld
```

When those Issues are activated, their review should check conformance to this
ADR. Any new runtime dependency or parallel Agent lifecycle must identify the
specific clause it satisfies or the superseding ADR it requires.

## Deferred Follow-ups

The following remain separate dormant research contracts or later ADRs:

1. Delegation and child-WorkRequest ontology for multi-Agent systems.
2. Orchestration strategy and versioning contract for static/dynamic graphs.
3. Canonical-trace-to-OpenTelemetry projection contract.
4. External MCP read-tool admission contract (#300).
5. A2A/external-Agent delegation and capability-lease contract.
6. Governed self-improvement proposal, evaluation, admission, canary, and
   rollback contract.
7. Minimal supported Agent runtime dependency profile (#427).

## References

FinHarness:

- Program and investment gates: https://github.com/zycxfyh/FinHarness/issues/277
- Canonical AgentRunTrace: https://github.com/zycxfyh/FinHarness/issues/291
- Semantic Observation: https://github.com/zycxfyh/FinHarness/issues/439
- Hydration and replay: https://github.com/zycxfyh/FinHarness/issues/440
- Primary DecisionPort: https://github.com/zycxfyh/FinHarness/issues/287
- Server-resolved ContextWorld: https://github.com/zycxfyh/FinHarness/issues/284
- Deferred MCP boundary: https://github.com/zycxfyh/FinHarness/issues/300
- Runtime dependency ADR owner: https://github.com/zycxfyh/FinHarness/issues/427

External primary documentation:

- OpenAI Agents SDK runner lifecycle and tool loop:
  https://openai.github.io/openai-agents-python/running_agents/
- LangGraph persistence and checkpoint replay:
  https://docs.langchain.com/oss/python/langgraph/persistence
- Model Context Protocol architecture and scope:
  https://modelcontextprotocol.io/docs/learn/architecture
- Azure Durable orchestration replay model:
  https://learn.microsoft.com/en-us/azure/durable-task/common/durable-task-orchestrations
- Azure Durable orchestration versioning:
  https://learn.microsoft.com/en-us/azure/azure-functions/durable/durable-functions-orchestration-versioning
- OpenTelemetry semantic conventions:
  https://opentelemetry.io/docs/specs/semconv/
