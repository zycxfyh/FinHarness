# Dormant Research Contract: Orchestration Strategy and Versioning

Date: 2026-07-19  
Status: dormant research contract  
Implementation authorization: none  
Canonical implementation owner: none until activation  
Program owner: #277  
Related ADR: `docs/adr/2026-07-19-runtime-neutral-agent-governance-kernel.md`  
Related research contract:
`docs/architecture/agent-runtime-reference/research-contracts/2026-07-19-delegation-child-workrequest-ontology-research-contract.md`  
Related Issues: #278, #279, #284, #287, #291, #439, #440, #427

## 1. Purpose

This contract defines the research and compatibility boundary for evolving the
FinHarness Agent work loop from its current bounded reducer into possible future
orchestration forms:

```text
fixed single loop
→ richer reducer
→ explicit static graph
→ hierarchical graph
→ bounded parallel graph
→ dynamically proposed RunPlan
→ externally hosted durable orchestration
```

The central question is:

> How can FinHarness change the strategy that decides the next permissible
> transition without changing the meaning of historical runs, repeating effects,
> allowing a runtime checkpoint to become domain truth, or binding the product to
> one workflow framework?

This document is deliberately **dormant**.

It does not authorize:

- LangGraph, Temporal, Durable Functions, Step Functions, or another workflow
  engine as a core dependency;
- a new graph runtime;
- asynchronous background Agents;
- dynamic topology;
- multi-Agent implementation;
- scheduler or daemon ownership;
- workflow migration of current Agent receipts;
- replacement of `AgentRunTrace`;
- replacement of `ContextWorld`;
- automatic replay of model or tool calls;
- a second event store;
- a second stop, evaluation, authority, or effect lifecycle;
- a runtime dependency decision before #427's activation gates.

Its purpose is to ensure that current implementation choices do not make those
future options unsafe or prohibitively expensive.

## 2. Existing Binding Constraints

### 2.1 Canonical run truth remains FinHarness-owned

The runtime-neutral governance ADR establishes:

```text
provider/runtime mechanics
≠ canonical FinHarness run truth
```

The canonical record of one Agent work request is the FinHarness-owned ordered
`AgentRunTrace` and its referenced durable artifacts.

The following may be useful runtime projections but cannot silently become
canonical:

- OpenAI Agents SDK `RunState`, `RunResult`, or runner events;
- LangGraph thread state, checkpoint, pending writes, or node tasks;
- Temporal Workflow History;
- Durable Functions orchestration history;
- Step Functions execution history;
- provider conversation or response IDs;
- scheduler state;
- retry queue state;
- observability spans.

### 2.2 One WorkRequest has one terminal authority

A framework may expose its own success, failure, cancellation, interrupt, or
handoff state.

FinHarness must still decide the canonical terminal classification through its
own run kernel, evaluation, stop, and human-boundary rules.

Runtime completion is evidence consumed by FinHarness. It is not automatically
FinHarness completion.

### 2.3 Exact world versions remain immutable run inputs

A strategy may select the next action but cannot invent or replace:

- `PrincipalIdentity`;
- `AgentRuntimeIdentity`;
- `CapitalStateVersion`;
- `VerifiedProjectionVersion`;
- `EvidenceSetVersion`;
- `DecisionCaseVersion`;
- policy, mandate, grant, or authority versions;
- freshness/currentness classifications.

Material world change requires explicit re-resolution and a recorded replan,
fork, cancellation, or new WorkRequest.

### 2.4 Tool admission and effects remain outside strategy authority

An orchestration strategy may propose:

```text
dispatch tool
wait
retry
replan
evaluate
escalate
complete
cancel
delegate, if later authorized
```

It cannot itself:

- execute an admitted tool;
- mutate StateCore;
- create authority;
- approve an action;
- write a canonical receipt;
- classify an effect as successfully applied;
- reconcile an external effect;
- rewrite prior events;
- declare a capital decision valid.

### 2.5 Hydration is not effect replay

Issue #440 owns side-effect-free hydration and replay of the canonical Agent
run.

This contract uses precise vocabulary:

```text
hydrate
= reconstruct canonical state from existing trace and artifacts

inspect
= read historical state without changing it

resume
= continue a nonterminal run from an admitted canonical boundary

retry
= schedule a new attempt under an explicit retry policy

recompute
= execute a pure deterministic derivation again

re-execute
= invoke a model, tool, API, external Agent, or effect again

fork
= create a new descendant run or branch with an explicit lineage relationship
```

These verbs must never be treated as interchangeable.

## 3. Current FinHarness Baseline

The current work loop is a bounded, provider-neutral orchestrator scaffold.

Its present shape is approximately:

```text
AgentWorkRequest
→ freeze context
→ build decision state
→ DecisionPort chooses dispatch or complete
→ autonomy admission
→ tool dispatch
→ observation
→ repeat under budgets
→ terminal receipt/result/search/workspace chain
```

Current constraints explicitly exclude:

```text
session
scheduler
cross-cycle resume
execution
multi-Agent
```

This is a useful baseline because it is small enough to evaluate and replace.

The next authorized Agent Issues already have narrow owners:

- #291: one canonical `AgentRunTrace`;
- #439: typed Semantic Observation;
- #440: hydration and replay without re-executing effects;
- #287: one real model DecisionPort;
- #284: one server-resolved `ContextWorld`;
- #278: bounded retry, replan, fallback, and no-progress reduction;
- #279: evaluation-controlled stop;
- #427: eventual minimal supported runtime dependency decision.

This contract must not become a second owner for any of those capabilities.

## 4. Research Question

The primary research question is:

```text
Can FinHarness replace or evolve the next-transition strategy while preserving
the exact same domain truth, authority checks, canonical event semantics,
world-version bindings, stop legitimacy, effect boundaries, and historical
interpretability?
```

The research is successful only when:

1. a run declares the exact orchestration strategy version used;
2. historical runs remain interpretable after code changes;
3. in-flight runs cannot be silently switched to incompatible logic;
4. a runtime projection can be deleted and rebuilt from canonical records;
5. hydration never repeats an external call or effect;
6. resume, retry, fork, and replay have distinct contracts;
7. strategy change cannot expand tools, context, authority, or effect scope;
8. the selected framework can be removed without migrating domain truth.

## 5. Why Orchestration Versioning Is a Separate Problem

Model versioning is not orchestration versioning.

Prompt versioning is not orchestration versioning.

Tool schema versioning is not orchestration versioning.

A run may use the same model and tools but change behavior materially because
the strategy changes:

```text
v1:
tool A
→ tool B
→ evaluate
→ complete

v2:
tool A
→ parallel B and C
→ reconcile disagreement
→ evaluate
→ complete
```

The following changes may be orchestration-breaking:

- adding, deleting, or reordering transitions;
- changing which observation triggers which action;
- changing retry or timeout placement;
- changing parallelism;
- changing aggregation rules;
- changing interrupt or human-review boundaries;
- changing the point where evaluation controls stop;
- changing cancellation propagation;
- changing child-run creation;
- changing the interpretation of a persisted strategy state;
- changing the schema of an intermediate decision or observation.

A code deployment that preserves type checking may still be incompatible with
an existing run history.

## 6. Three Distinct Histories

A future implementation must distinguish three kinds of history.

### 6.1 Domain and governance history

Examples:

```text
CapitalState versions
EvidenceSet versions
DecisionCase versions
Mandate and Grant versions
Approval records
Execution records
Reconciliation records
```

This history is authoritative for the product domain.

An orchestration engine cannot rewrite it.

### 6.2 Canonical Agent run history

Examples:

```text
WorkRequest identity
ContextWorld binding
Agent decisions
tool requests
admission results
Semantic Observations
evaluation decisions
budget consumption
stop and terminal state
artifact and receipt refs
```

This history is authoritative for Agent responsibility and replay.

### 6.3 Runtime-operational history

Examples:

```text
graph checkpoint
workflow-engine event history
queue lease
worker build ID
runtime retry metadata
scheduler heartbeat
provider streaming event
transport session
```

This history may be required by a runtime to recover its mechanics.

It remains an operational projection or external artifact unless a later ADR
explicitly adopts a subset into the canonical run contract.

The safe relationship is:

```text
domain/governance history
        ↑ referenced by
canonical AgentRunTrace
        ↑ projected into / supplemented by
runtime-operational history
```

The unsafe relationship is:

```text
runtime checkpoint
= Agent truth
= domain truth
= authority
```

## 7. Candidate Stable Interface

The following is a research vocabulary, not an authorized Python API.

### 7.1 OrchestrationStrategy

A pure or bounded policy interface that proposes the next transition from
canonical state.

Candidate shape:

```text
OrchestrationStrategy.propose(
    canonical_run_state,
    exact_context_world,
    strategy_policy,
) -> ProposedTransitionSet
```

The strategy must not receive direct mutation handles, database sessions,
unbounded provider clients, or effect adapters.

### 7.2 ProposedTransition

A closed union of strategy outputs.

Candidate forms:

```text
DispatchTool
WaitForExternalInput
RequestContextRefresh
RetryPriorOperation
Replan
RunEvaluation
EscalateToHuman
CompleteCandidate
FailCandidate
CancelCandidate
DelegateChildWork, only if separately authorized
```

A proposed transition is not yet admitted.

### 7.3 TransitionAdmission

The FinHarness run kernel validates:

```text
run status
event sequence
ContextWorld validity
authority
tool capability
budget
strategy version
schema version
retry policy
stop policy
human boundary
effect class
```

Only an admitted transition may be dispatched or committed.

### 7.4 OrchestrationStrategyVersion

An immutable identity for the logic that proposes transitions.

Candidate fields:

```text
strategy_id
strategy_version
strategy_kind
definition_hash
input_state_schema_version
proposed_transition_schema_version
compatibility_class
activation_status
created_at_utc
supersedes_ref
implementation_artifact_ref
evaluation_corpus_ref
```

`strategy_kind` may include:

```text
fixed_reducer
single_loop
static_graph
hierarchical_graph
bounded_parallel_graph
dynamic_run_plan
external_durable_runtime_adapter
```

A kind describes shape. It does not grant authority.

### 7.5 RunKernelVersion

The kernel version identifies FinHarness code that owns:

```text
transition admission
event append
budget accounting
world invalidation
evaluation reduction
stop
terminal classification
effect boundary
```

The strategy and kernel must be independently versioned.

A new strategy should not require a new kernel unless the stable transition
contract itself changes.

### 7.6 RuntimeAdapterVersion

A runtime adapter translates between a framework's mechanics and the stable
FinHarness contracts.

Candidate fields:

```text
runtime_family
adapter_version
runtime_library_version
checkpoint_schema_version
supported_strategy_kinds
supported_kernel_range
resume_semantics
cancellation_semantics
retry_semantics
projection_rebuild_support
```

This object records compatibility. It does not become the runtime dependency
decision owned by #427.

### 7.7 RunVersionVector

Every run should eventually bind the versions that can change its behavior.

Candidate vector:

```text
run_kernel_version
orchestration_strategy_version
runtime_adapter_version
DecisionPort_version
provider_adapter_version
model_snapshot
prompt_or_instruction_version
tool_contract_versions
SemanticObservation_schema_version
ContextWorld_policy_version
capability_policy_version
retry_policy_version
evaluation_policy_version
stop_policy_version
aggregation_policy_version, if later needed
```

Not every version must be persisted as a new domain record.

The final design must avoid duplicating canonical owners while preserving enough
identity to interpret the run.

## 8. Compatibility Classes

A future versioning mechanism should classify changes explicitly.

### 8.1 Representation-compatible

The implementation changes internally but produces the same canonical
transition semantics.

Examples:

- performance improvement;
- local refactor;
- logging change;
- runtime checkpoint storage change;
- adapter implementation change with identical conformance output.

Expected behavior:

```text
old and new runs may use the new implementation
provided replay/conformance proves semantic equivalence
```

### 8.2 Forward-compatible additive

A new optional field or transition capability is added, but older strategies and
runs remain valid.

Requirements:

- old readers ignore only fields explicitly declared optional;
- unknown transitions still fail closed;
- new writers do not emit new transition types to old kernels;
- old historical records remain interpretable.

### 8.3 Strategy-breaking

The transition graph or decision semantics change.

Examples:

- adding parallel branches;
- changing retry ordering;
- moving evaluation earlier or later;
- adding a human interrupt;
- changing the aggregation of observations;
- changing terminal reduction.

Expected behavior:

```text
new WorkRequests bind a new strategy version
existing runs remain pinned to the old strategy version
```

### 8.4 Kernel-breaking

The admission or canonical event contract changes.

Examples:

- new authority rule;
- new canonical event sequencing;
- new terminal-state semantics;
- changed effect boundary;
- incompatible ContextWorld invalidation semantics.

Expected behavior:

```text
new kernel version
explicit compatibility range
migration or coexistence decision
no silent reinterpretation of historical runs
```

### 8.5 Runtime-only breaking

A framework changes checkpoint schema or worker protocol without changing
FinHarness semantics.

Expected behavior:

```text
upgrade or replace RuntimeAdapter
rebuild runtime projections where possible
preserve AgentRunTrace
```

If a runtime-only change requires rewriting canonical Agent history, the
boundary has failed.

## 9. Run Pinning

Every started WorkRequest should be permanently associated with its admitted
version vector or an immutable reference to it.

Minimum principle:

```text
a run does not silently change orchestration strategy while in flight
```

Allowed future policies may include:

### 9.1 Strict pinning

A run uses exactly the strategy and kernel versions admitted at start.

Best for:

- initial implementation;
- short and bounded FinHarness runs;
- high-integrity replay;
- clear rollback.

### 9.2 Compatible worker execution

A newer worker may process older runs only when its declared compatibility range
includes their pinned versions.

This must be proved by replay/conformance tests, not assumed from semantic
version numbers.

### 9.3 Explicit upgrade transition

A nonterminal run may request migration to a new strategy only through a
canonical event.

Candidate requirements:

```text
old and new state schemas validated
migration function versioned
no unresolved tool or effect attempts
ContextWorld revalidated
human review when consequence class requires it
old strategy state retained
new lineage recorded
rollback policy explicit
```

No first implementation should require live in-flight strategy migration.

## 10. Five Operations That Must Remain Distinct

### 10.1 Historical hydration

```text
input:
canonical trace + referenced artifacts

output:
same historical run state

external execution:
none
```

### 10.2 Operational resume

```text
input:
nonterminal canonical state + valid pinned versions

output:
continued run

external execution:
only newly admitted transitions after the resume boundary
```

### 10.3 Retry

```text
input:
one classified failed or incomplete operation

output:
new attempt identity under bounded retry policy

external execution:
yes, but only as a new attempt
```

Retry must never overwrite or pretend the prior attempt did not occur.

### 10.4 Fork

```text
input:
historical boundary + explicit changed premise

output:
new descendant WorkRequest or run branch

external execution:
allowed only in the descendant under its own admission
```

A fork is not a mutation of the original run.

### 10.5 Framework replay or time travel

An external framework may use "replay" to mean re-running nodes after a
checkpoint.

FinHarness must translate this precisely.

If framework replay may invoke an LLM, API, interrupt, Agent, tool, or effect
again, it cannot be used as canonical historical hydration.

It may be used only as an explicitly classified retry, experiment, or fork.

## 11. Event Sourcing and Determinism

Durable workflow engines commonly reconstruct workflow state by replaying an
event history.

This yields important lessons but does not require FinHarness to adopt a
workflow engine.

### 11.1 Deterministic orchestration code

A replay-based runtime generally requires orchestration logic to emit the same
commands for the same recorded history.

Potentially nondeterministic work includes:

- model calls;
- network calls;
- current time;
- random values;
- unversioned configuration;
- mutable external state;
- non-stable iteration order;
- provider routing;
- dynamic tool discovery.

These must not be re-derived during historical hydration.

### 11.2 Recorded results versus repeated effects

A durable runtime may record the result of an external activity and return that
result during replay instead of repeating the activity.

FinHarness already requires a stronger domain distinction:

```text
recorded operation result
≠ proof that domain admission succeeded
≠ proof that an external effect reconciled
```

Runtime durability cannot substitute for operation receipts or reconciliation.

### 11.3 Determinism is not correctness

A workflow can replay deterministically while:

- using stale capital data;
- violating authority;
- repeating a logically invalid plan;
- accepting unsupported evidence;
- stopping too early;
- producing a deterministic but false result.

FinHarness evaluation and domain admission remain independent.

## 12. External Runtime Patterns Under Study

### 12.1 OpenAI Agents SDK Runner

The SDK Runner owns a model/tool loop:

```text
model turn
→ final output, handoff, or tool calls
→ tool execution
→ next turn
```

Potential FinHarness use:

```text
thin model-turn or orchestration adapter
```

Boundary requirement:

```text
SDK Runner terminal state
≠ FinHarness terminal state

SDK tool call
→ FinHarness proposed transition
→ FinHarness admission
→ FinHarness dispatch
```

If the SDK must own direct tool execution to function, that path remains
experimental until a safe adapter proves otherwise.

### 12.2 LangGraph

LangGraph persists graph state as checkpoints organized into threads and
super-steps.

Its persistence can support:

- interruption;
- fault recovery;
- graph state inspection;
- time travel;
- forks;
- pending writes.

Potential FinHarness use:

```text
orchestration projection and execution helper
```

Boundary requirement:

```text
LangGraph checkpoint
≠ canonical AgentRunTrace
```

LangGraph replay after a checkpoint may re-execute downstream nodes, including
LLM calls, APIs, and interrupts.

Therefore:

```text
LangGraph replay
≠ FinHarness historical hydration
```

A future adapter must map framework operations to FinHarness's precise hydrate,
resume, retry, or fork semantics.

### 12.3 Temporal or Durable Task-style runtimes

These systems use durable event histories and deterministic orchestration
replay.

Potential FinHarness use:

- long-running waits;
- crash recovery;
- timers;
- external events;
- durable activity scheduling;
- worker routing;
- version isolation.

Boundary requirement:

```text
workflow history
supports runtime recovery
but does not replace
AgentRunTrace, authority, domain receipts, or reconciliation
```

A future adapter must keep model calls and other nondeterministic operations out
of deterministic orchestration code or capture them as explicit activities and
FinHarness observations.

### 12.4 AWS Step Functions-style immutable definitions

Step Functions supports immutable state-machine versions and aliases that route
new executions between versions.

Potential lesson:

```text
publish immutable orchestration definitions
pin execution at start
canary new versions
roll back by routing new work to an old version
```

FinHarness should borrow the versioning idea, not assume a managed state machine
service is required.

## 13. Strategy Shapes

### 13.1 Fixed reducer

```text
observation
→ deterministic reducer
→ next transition
```

Advantages:

- easiest to reason about;
- minimal dependencies;
- easy exact tests;
- strong current fit.

Limitations:

- difficult to express parallelism;
- branch growth may become tangled;
- runtime visualization is limited.

### 13.2 Single loop with policy modules

```text
observe
→ plan
→ admit
→ act
→ evaluate
→ stop or repeat
```

Advantages:

- supports richer replan and evaluation;
- retains one control loop;
- incremental evolution from current code.

This should be the default near-term shape.

### 13.3 Explicit static graph

```text
fixed nodes
fixed edges
typed graph state
```

Advantages:

- visible control flow;
- explicit branch and join points;
- better representation of interrupts.

Activation signal:

- current reducer has repeated branching defects;
- static topology is stable across the task family;
- graph representation reduces complexity measurably.

### 13.4 Bounded parallel graph

```text
admitted independent branches
→ bounded parallel execution
→ typed join
```

Prerequisites:

- result contracts;
- budget accounting;
- cancellation;
- duplicate-work detection;
- aggregation semantics;
- child WorkRequest contract when branches are Agentic.

### 13.5 Dynamic RunPlan

```text
model or planner proposes topology
→ kernel validates plan
→ immutable RunPlanVersion
→ execution under fixed bounds
```

The dynamic planner may choose:

- nodes;
- ordering;
- parallel groups;
- specialists;
- evaluation points.

It cannot choose:

- authority;
- new tool capabilities;
- domain truth;
- effect permissions;
- canonical record types;
- unlimited recursion or budget.

Dynamic topology remains research-only until static patterns produce measured
limitations.

## 14. Candidate RunPlanVersion

If future dogfood justifies dynamic or explicit graph planning, the plan should
become an immutable candidate artifact before execution.

Candidate fields:

```text
run_plan_id
root_work_request_ref
strategy_version_ref
ContextWorld_ref
node definitions
typed edge conditions
tool and capability refs
budget allocations
parallelism limits
join policies
evaluation points
stop points
human interrupt points
child WorkRequest templates, if separately authorized
definition hash
admission report ref
```

A model-produced plan is only a candidate.

The kernel must reject:

- unknown nodes;
- unversioned schemas;
- unsupported transition types;
- cyclic plans without a bounded loop policy;
- unbounded recursion;
- undeclared tools;
- capability escalation;
- missing terminal paths;
- branches with no cancellation policy;
- joins that discard conflicting evidence;
- plans using stale or substituted world refs.

## 15. Strategy State Versus Canonical Run State

A framework may need internal state that is not useful as canonical history.

Examples:

```text
node cursor
ready queue
checkpoint metadata
worker lease
retry timer
framework interrupt token
serialized call stack
```

Such state should be classified:

### 15.1 Derivable projection state

Can be rebuilt from canonical run history.

Preferred.

### 15.2 External operational state

Required by a runtime and persisted outside FinHarness canonical records.

Allowed only when:

- identity is linked;
- loss is classified;
- recovery behavior is explicit;
- it cannot authorize domain effects;
- it can be removed on runtime replacement.

### 15.3 Canonical semantic state

Required to interpret responsibility or decide admission.

Must be represented in the canonical run contract and owned by FinHarness, not
left only inside the runtime checkpoint.

The implementation proposal must classify every persisted field into one of
these categories.

## 16. Schema Evolution

### 16.1 Closed canonical events

Unknown canonical event types or required fields must fail closed.

Do not deserialize unknown events into generic dictionaries and continue.

### 16.2 Additive optional fields

An optional field may be added only when:

- absence has one deterministic meaning;
- older records remain valid;
- old code will not incorrectly interpret absence as authority or success;
- the field does not change event ordering.

### 16.3 Event upcasting

If historical event representations require conversion for reading:

```text
stored event
→ version-specific reader
→ canonical in-memory representation
```

The upcaster must be:

- pure;
- deterministic;
- versioned;
- read-only;
- tested against historical fixtures.

It must not rewrite historical receipts merely to make new code simpler.

### 16.4 No silent semantic reinterpretation

A field named `completed` in an old record cannot be reinterpreted under a newer,
stricter completion rule without preserving the original classification.

A derived current view may report:

```text
historical_terminal = completed_under_v1
current_assessment = insufficient_under_v2
```

It must not pretend the original event said something else.

## 17. Deployment and Rollout Posture

A future orchestration implementation should support at least:

### 17.1 Immutable strategy publication

Once used by a run, a strategy version is immutable.

A code fix that changes behavior creates a new version unless formally proved
representation-compatible.

### 17.2 Pin new executions

New WorkRequests resolve a strategy version at admission time.

They must not default to an unversioned "latest" strategy.

### 17.3 Canary or bounded rollout

New strategy versions should be evaluated through:

- offline replay over canonical traces;
- shadow decisions without dispatch;
- synthetic and adversarial corpus;
- bounded internal dogfood;
- limited new-run routing;
- comparison against the prior strategy.

### 17.4 Rollback

Rollback routes **new work** back to the prior accepted version.

Existing runs remain pinned unless an explicit migration contract exists.

### 17.5 Drain and retirement

A strategy version may be retired only when:

- no active run depends on it, or a supported compatibility worker remains;
- historical reading still works;
- evaluation and incident records are retained;
- projection data can be deleted or rebuilt;
- removal does not orphan canonical traces.

## 18. Offline Replay Modes

The term "replay" should be qualified in all tools and documentation.

### 18.1 Trace validation replay

Purpose:

```text
validate event order, hashes, refs, schemas, and reducer outcomes
```

External calls:

```text
none
```

### 18.2 Strategy simulation replay

Purpose:

```text
feed historical observations into a candidate strategy
compare proposed transitions with historical transitions
```

External calls:

```text
none by default
```

Output:

```text
counterfactual evaluation artifact
```

It does not alter the original run.

### 18.3 Model re-evaluation

Purpose:

```text
ask a model to make a new decision using a historical ContextWorld
```

This is a new experiment or fork, not historical replay.

It must bind:

- current model/provider version;
- exact historical inputs;
- no-effect policy;
- new output identity;
- lineage to the original run.

### 18.4 Tool or effect retry

A repeated external operation is a new attempt.

It requires:

- retry admission;
- idempotency key or duplicate-effect protection;
- explicit attempt identity;
- current authority and world validation;
- reconciliation.

It must never be called "replay" without qualification.

## 19. Dynamic Configuration

A run must not read mutable global configuration during hydration and derive
different control flow.

Potentially behavior-changing configuration includes:

- enabled tools;
- tool schemas;
- provider routing;
- model selection;
- prompt templates;
- retry counts;
- timeout values;
- budget limits;
- evaluation thresholds;
- stop conditions;
- feature flags;
- safety policy;
- runtime topology.

Behavior-changing configuration must be:

- frozen into the run version vector;
- resolved through an immutable policy version; or
- recorded as an explicit external event before it affects the run.

## 20. Human Interrupts

A future runtime may support pauses and human approval.

The framework's interrupt token cannot be the full governance record.

A FinHarness interrupt must bind:

```text
WorkRequest
canonical trace event
exact state and world versions
requested human action
allowed responses
expiry
resume policy
authority requirement
```

A human response must become a canonical admitted event before resume.

Changing or deleting a framework checkpoint must not delete the human decision.

## 21. Cancellation

Cancellation semantics must be explicit across:

```text
root run
tool attempt
model call
child WorkRequest
parallel branch
runtime task
external effect
```

The first runtime experiment must answer:

- Does cancellation stop scheduling or guarantee work has stopped?
- What happens to an in-flight provider call?
- What happens to an in-flight tool?
- Can an external effect complete after cancellation?
- How is late completion classified?
- Does cancellation consume terminal budget?
- Can a cancelled run be resumed?
- Is resume a continuation or a new WorkRequest?
- How are child runs or branches cancelled?
- What does framework-level cancellation map to in FinHarness?

No strategy may treat "cancellation requested" as proof that an external effect
did not occur.

## 22. Retry and Idempotency

Runtime automatic retry is not automatically safe.

Every retryable operation must classify:

```text
pure computation
read-only external call
candidate artifact write
canonical record append
domain mutation
external effect
```

The retry policy must depend on the operation class.

Examples:

- pure calculations may be recomputed;
- read-only calls may be retried under budgets and freshness policy;
- candidate writes require idempotent identity;
- canonical append requires duplicate-event protection;
- domain mutations require command identity;
- external effects require effect identity and reconciliation.

A workflow engine's "at least once" or "durable activity" guarantee cannot
replace FinHarness effect semantics.

## 23. Evaluation and Stop Versioning

Issue #279 makes evaluation control stop.

Therefore a run must bind the evaluation and stop policies that determined its
terminal result.

Changing:

- success threshold;
- unsupported-claim rule;
- freshness requirement;
- provenance rule;
- false-progress detection;
- human-boundary classification;
- allowed blocker set;

may change whether the same observation sequence terminates.

These changes require explicit policy versions.

Historical runs remain terminal under the policy used at the time.

Current analysis may re-evaluate them under a newer policy, but the new
assessment must be a derived evaluation artifact.

## 24. Orchestration and Model Nondeterminism

The model is allowed to be nondeterministic.

The canonical system must make the nondeterminism observable and bounded.

Each model decision should eventually bind:

```text
model/provider snapshot
input refs
instruction and schema versions
tool visibility
budget state
output hash
parsed typed decision
parse/admission result
```

Historical hydration reads the recorded typed decision and output refs.

It does not ask the model to reproduce the same answer.

A strategy simulation may intentionally run a new model call, but that is a
new counterfactual artifact.

## 25. Activation Gates

No orchestration framework or explicit graph implementation may activate until
all mandatory gates pass.

### Gate A — Canonical Agent foundation

Required:

```text
#291 canonical AgentRunTrace
#439 typed Semantic Observation
#440 side-effect-free hydration/replay
#287 one real DecisionPort
#284 exact ContextWorld
#278 bounded retry/replan/no-progress
#279 evaluation-controlled stop
```

### Gate B — Current reducer stress evidence

Dogfood must show a specific problem, such as:

- branching logic has become materially hard to verify;
- current state representation cannot express a required interrupt;
- bounded parallelism has a measured benefit;
- resume semantics cannot remain local;
- the run duration requires durable timers or external events;
- repeated incidents show recovery logic is fragile;
- runtime visualization materially reduces operator error.

Framework preference is not evidence.

### Gate C — Frozen semantic contract

Before evaluating a runtime, freeze:

- canonical event types;
- transition union;
- ContextWorld binding;
- tool admission;
- budget accounting;
- evaluation and stop;
- terminal classifications;
- hydrate/resume/retry/fork definitions.

### Gate D — Two implementation options

At least two options must be evaluated:

```text
extend the local reducer
adopt/adapt one mature runtime
```

A third option may be included when evidence warrants it.

The comparison must include removal cost, not only feature breadth.

### Gate E — Historical corpus

Maintain a corpus of canonical traces covering:

- success;
- partial result;
- blocked admission;
- recoverable error;
- terminal error;
- stale world;
- human escalation;
- budget exhaustion;
- duplicate request;
- cancellation;
- restart;
- missing or corrupt artifact.

### Gate F — Version coexistence proof

Demonstrate:

```text
v1 run remains readable
v2 new run uses new strategy
v1 and v2 can coexist
new code cannot silently execute an incompatible v1 run
rollback routes new runs back to v1
```

### Gate G — No domain migration

Prove that removing the candidate runtime requires no migration of:

- CapitalState;
- EvidenceSet;
- DecisionCase;
- Mandate or Grant;
- execution records;
- canonical AgentRunTrace semantics.

### Gate H — #427 decision boundary

The final supported runtime dependency remains owned by #427 and cannot be
decided solely by this research contract.

## 26. Minimum Experimental Slice

If activated, the first experiment should be:

```text
one single-Agent task family
one existing read-only tool path
one fixed strategy
one optional alternate strategy version
one local process
no scheduler
no multi-Agent
no dynamic topology
no execution
no long-running background task
```

Recommended experiment:

```text
current reducer v1
vs
explicit static graph v2

using the same:
ContextWorld
DecisionPort
tool contracts
Semantic Observations
evaluation policy
stop policy
canonical AgentRunTrace projection
```

The experiment should measure whether the graph reduces complexity or improves
recovery without changing semantic output.

## 27. Conformance Test Matrix

| Invariant | Local reducer | Static graph | External durable runtime |
| --- | --- | --- | --- |
| One WorkRequest / one canonical trace | required | required | required |
| Exact ContextWorld binding | required | required | required |
| Tool dispatch through FinHarness admission | required | required | required |
| Runtime checkpoint non-canonical | n/a or required | required | required |
| Side-effect-free historical hydration | required | required | required |
| Explicit resume boundary | required | required | required |
| Retry creates new attempt | required | required | required |
| Fork preserves original history | required | required | required |
| Evaluation controls stop | required | required | required |
| Terminal state FinHarness-owned | required | required | required |
| Version pinning | required | required | required |
| Old/new strategy coexistence | required | required | required |
| Runtime projection rebuild | required | required | required |
| No authority expansion | required | required | required |
| Runtime removal without domain migration | required | required | required |

## 28. Adversarial and Destructive Fixtures

Any implementation proposal must include at least:

1. Deploy a reordered strategy while a v1 run is nonterminal.
2. Remove a node used by an in-flight run.
3. Change a tool input schema used by a historical event.
4. Change an evaluation threshold and prove historical terminal truth is not
   rewritten.
5. Delete runtime checkpoints and hydrate from canonical trace.
6. Corrupt a runtime checkpoint while canonical trace remains intact.
7. Corrupt canonical trace while runtime checkpoint appears healthy.
8. Ask framework replay to resume after an LLM node and prove it does not occur
   during historical hydration.
9. Attempt to repeat a side-effecting tool during replay.
10. Resume with an incompatible strategy version.
11. Run a newer worker against a newer run using old code.
12. Retry after response loss and prove duplicate effect prevention.
13. Change global feature flags during hydration.
14. Change provider routing during an in-flight run.
15. Expire authority while a runtime task remains queued.
16. Invalidate ContextWorld while the strategy is waiting.
17. Receive a late tool result after cancellation.
18. Fork a historical run and prove the original remains immutable.
19. Delete the runtime library and inspect historical runs using FinHarness
    canonical readers.
20. Rebuild runtime projection and compare identities and states.
21. Return a framework terminal success before FinHarness evaluation.
22. Framework reports failure after the canonical run already completed.
23. Duplicate a transition callback.
24. Deliver events out of order.
25. Execute parallel nodes whose join drops contradictory evidence.
26. Migrate strategy state with an unknown field.
27. Upcast an old event and prove the upcaster is pure and deterministic.
28. Attempt to run an unversioned "latest" strategy.
29. Roll back routing for new runs while old v2 runs remain active.
30. Retire a version while an active run still requires it.

## 29. Evaluation Matrix

| Dimension | Baseline reducer | Candidate runtime/strategy | Acceptance direction |
| --- | --- | --- | --- |
| Semantic correctness | measured | measured | no decrease |
| Unsupported claims | measured | measured | no increase |
| Authority violations | 0 | 0 | any violation blocks |
| Effect duplication | 0 | 0 | any duplication blocks |
| Historical hydration | required | required | 100% |
| Version coexistence | required | required | 100% |
| Recovery after process loss | measured | measured | candidate improvement |
| Operator diagnosability | measured | measured | material improvement |
| Code complexity | measured | measured | justified reduction |
| Runtime dependency weight | current | measured | justified |
| Storage duplication | current | measured | bounded and classified |
| Removal cost | low | measured | no domain migration |
| Latency | measured | measured | acceptable |
| Cost | measured | measured | acceptable |
| Trace completeness | required | required | 100% |
| Checkpoint rebuildability | n/a/current | measured | required |
| Cancellation correctness | measured | measured | deterministic |
| Retry classification | measured | measured | deterministic |
| Human review burden | measured | measured | no unjustified increase |

## 30. Security and Privacy Questions

Before activation, the implementation proposal must answer:

- What data is stored in runtime checkpoint/history?
- Does it include private financial context, prompts, model outputs, or secrets?
- Can payload encryption be applied independently of runtime metadata?
- Who can inspect, fork, resume, cancel, or retry runs?
- Can runtime administrators bypass FinHarness authority checks?
- Can a replay API cause an external effect?
- Are provider credentials ever serialized into workflow history?
- How are runtime event histories retained and deleted?
- Does framework telemetry export sensitive data?
- Can an old worker execute a new policy accidentally?
- Can a new worker reinterpret an old run under changed authority rules?
- What is the blast radius of compromised checkpoint storage?
- Which runtime state must remain local-owned?
- Can runtime aliases or routing configuration alter the consequence class of
  new work without a FinHarness policy change?

## 31. Framework Selection Criteria

A mature runtime should be evaluated on:

### 31.1 Semantic fit

- Can FinHarness own tool dispatch?
- Can FinHarness own terminal state?
- Can exact typed observations be injected?
- Can a run bind exact versions?
- Can resume be separated from replay?
- Can effects be kept outside historical hydration?

### 31.2 Versioning

- immutable definitions or equivalent;
- execution pinning;
- old/new version coexistence;
- compatibility routing;
- rollback for new runs;
- safe retirement;
- replay tests.

### 31.3 Operational fit

- local development;
- SQLite or current persistence compatibility, where relevant;
- process restart;
- cancellation;
- timeouts;
- concurrency;
- observability;
- clean dependency profile;
- no mandatory hosted service for the first slice.

### 31.4 Removal and fallback

- exportable history;
- adapter isolation;
- no provider-specific objects in domain models;
- ability to revert to the local reducer;
- ability to inspect historical runs after dependency removal.

### 31.5 Governance fit

- no implicit authority;
- no framework-owned human approval record;
- no automatic effect retry without FinHarness classification;
- exact identity and provenance;
- least-privilege runtime access.

## 32. Reference-First Options

### Option 1 — Extend the local reducer

Adopt when:

- runs remain short;
- no durable waiting is needed;
- branches remain understandable;
- restart can be handled by #440;
- graph complexity would exceed benefit.

Advantages:

- least dependency;
- direct semantic control;
- easiest removal;
- existing code path.

Risks:

- local code may accumulate workflow-engine features;
- ad hoc branching;
- weaker visualization;
- future scheduling pressure.

### Option 2 — Adapt a graph runtime

Adopt when:

- explicit branch/join semantics are repeatedly needed;
- interrupt and checkpoint features provide measured value;
- its checkpoint is kept as a projection;
- replay semantics can be safely adapted.

Risks:

- graph state becomes de facto truth;
- framework tool execution bypass;
- checkpoint replay repeats external calls;
- tight schema coupling.

### Option 3 — Adapt a durable execution runtime

Adopt when:

- runs wait for hours or days;
- timers and external events are necessary;
- crash recovery is a demonstrated product need;
- version coexistence is required operationally;
- deterministic orchestration constraints are acceptable.

Risks:

- event-history duplication;
- payload/privacy concerns;
- operational infrastructure;
- deterministic-code constraints;
- automatic retries conflicting with effect semantics.

### Option 4 — Managed state-machine service

Adopt only when:

- hosted operations are justified;
- workflow definitions and aliases solve a demonstrated need;
- data residency and privacy are acceptable;
- local-first product constraints have changed.

This is unlikely to be the first FinHarness choice.

## 33. Failure and Rollback Criteria

The candidate strategy/runtime must be rejected or reverted if:

```text
runtime checkpoint becomes required to interpret domain truth
historical hydration invokes an external call
replay repeats an effect
old runs are silently interpreted by new incompatible logic
version pinning is absent
runtime success bypasses FinHarness evaluation
runtime retries bypass operation identity
ContextWorld can be substituted
authority changes are read from mutable global config
runtime removal requires domain migration
runtime history is the only copy of Semantic Observations
cancellation loses late-effect classification
strategy change materially increases human review burden without product gain
dependency complexity exceeds demonstrated recovery or orchestration value
```

Rollback must:

- disable routing of new runs to the candidate strategy;
- preserve old strategy readers;
- preserve canonical traces;
- retain runtime artifacts only as historical operational evidence;
- remove framework code without rewriting domain records;
- return new runs to the last accepted strategy version.

## 34. Decision Rule After Research

### Adopt

Select one bounded runtime/strategy because it solves a measured orchestration or
recovery problem while preserving all conformance invariants.

### Adapt

Use only a narrow feature:

- static graph visualization;
- checkpoint projection;
- durable timer adapter;
- version routing;
- offline replay validator.

### Reject

Keep the local reducer because a mature runtime adds more lifecycle complexity
than it removes.

### Continue Research

Continue only when the first experiment isolates a specific unresolved
variable.

Do not continue because dynamic graphs are fashionable.

## 35. Non-Goals

This contract does not define:

- a generic workflow engine;
- an enterprise scheduler;
- cross-day autonomous Agents;
- a distributed task queue;
- multi-Agent topology;
- A2A;
- MCP;
- long-term memory;
- general Skill compilation;
- model-provider routing;
- automatic workflow synthesis;
- self-modifying orchestration;
- live capital execution;
- business-process automation outside the FinHarness product loop.

## 36. Open Research Questions

1. Is the current local reducer sufficient after #278 and #279?
2. What exact run durations justify durable timers?
3. Should `OrchestrationStrategyVersion` be a DomainRecord, artifact descriptor,
   configuration record, or immutable code manifest?
4. Which elements of the RunVersionVector belong directly in the trace root?
5. Can a runtime checkpoint always be rebuilt from the canonical trace?
6. Which runtime-only data is expensive or impossible to reconstruct?
7. How should strategy-state schema migration be represented?
8. Should old strategy code remain deployed or be interpreted through a stable
   replay reducer?
9. How long should inactive strategy versions remain runnable?
10. How should local-first operation constrain runtime choice?
11. Can deterministic parallel tools solve the first graph use cases without an
    Agent graph?
12. When does a static graph become simpler than a reducer?
13. How should shadow strategy decisions be stored?
14. Should a counterfactual replay be an EvaluationReport or a separate
    experimental artifact?
15. How should runtime cancellation map to canonical cancellation?
16. Which version changes require human acknowledgement?
17. How should emergency security fixes affect pinned old runs?
18. Can an in-flight run be safely terminated rather than migrated?
19. Should long-running runs use continue-as-new style segmentation?
20. How are workflow aliases or rollout routing governed and receipted?
21. Can a runtime service operator inspect private financial payloads?
22. What cleanup is required after a runtime experiment?
23. How should framework upgrades be tested against canonical historical traces?
24. What exact observed threshold activates #427?
25. Can one adapter support both local reducer and external durable runtime
    without becoming a generic workflow abstraction?

## 37. Confirmation

This contract is serving its purpose while all of the following remain true:

```text
Current FinHarness Agent work does not require a graph framework.

Every run can name the strategy that interpreted it.

Historical hydration never repeats model, tool, API, Agent, or effect calls.

Runtime checkpoint and workflow history remain replaceable operational layers.

Old and new strategy versions may coexist without rewriting historical truth.

Evaluation, stop, authority, and effects remain FinHarness-owned.

A future runtime can be removed without migrating CapitalState, Evidence,
DecisionCase, authority, execution, or canonical Agent run history.
```

## 38. Suggested Future Issue Shape

Only after the activation gates pass, create one bounded Issue under #277, for
example:

```text
AR-ORCH-01:
Pin one alternate read-only orchestration strategy version to canonical Agent
runs and prove v1/v2 coexistence
```

The first implementation Issue should own only:

```text
immutable strategy identity
→ run pinning
→ one alternate strategy
→ canonical transition adapter
→ v1/v2 coexistence tests
→ rollback for new runs
```

It should not simultaneously implement:

- a hosted runtime;
- multi-Agent;
- dynamic topology;
- scheduler/daemon;
- long-term memory;
- MCP or A2A;
- provider routing;
- execution;
- a new event store;
- migration of historical domain records.

A later Issue, if justified, may evaluate one mature runtime adapter.

## 39. Suggested Repository Integration

Recommended path:

```text
docs/architecture/agent-runtime-reference/research-contracts/
2026-07-19-orchestration-strategy-versioning-research-contract.md
```

Suggested links:

1. Add a reference from
   `docs/architecture/agent-runtime-reference/14-lifecycle-release-governance.md`.
2. Add a reference from the runtime-neutral Agent governance ADR.
3. Add a cross-link from the delegation research contract because child-run
   orchestration also requires version pinning.
4. Do not add this dormant contract to current capability claims in generated
   system catalogs.

## 40. References

### FinHarness

- Runtime-neutral Agent governance kernel ADR:
  `docs/adr/2026-07-19-runtime-neutral-agent-governance-kernel.md`
- Delegation and Child WorkRequest research contract:
  `docs/architecture/agent-runtime-reference/research-contracts/2026-07-19-delegation-child-workrequest-ontology-research-contract.md`
- Program:
  https://github.com/zycxfyh/FinHarness/issues/277
- Replan, retry, fallback, and no-progress:
  https://github.com/zycxfyh/FinHarness/issues/278
- Evaluation-controlled stop:
  https://github.com/zycxfyh/FinHarness/issues/279
- ContextWorld:
  https://github.com/zycxfyh/FinHarness/issues/284
- DecisionPort:
  https://github.com/zycxfyh/FinHarness/issues/287
- Canonical AgentRunTrace:
  https://github.com/zycxfyh/FinHarness/issues/291
- Semantic Observation:
  https://github.com/zycxfyh/FinHarness/issues/439
- Hydration/replay:
  https://github.com/zycxfyh/FinHarness/issues/440
- Runtime dependency ADR:
  https://github.com/zycxfyh/FinHarness/issues/427

### External primary references

- OpenAI Agents SDK — Running agents:
  https://openai.github.io/openai-agents-python/running_agents/
- LangGraph — Persistence:
  https://docs.langchain.com/oss/python/langgraph/persistence
- LangGraph — Time travel:
  https://docs.langchain.com/oss/python/langgraph/use-time-travel
- Microsoft Durable Task — Programming model:
  https://learn.microsoft.com/en-us/azure/azure-functions/durable/programming-model-overview
- Microsoft Durable Functions — Orchestration versioning:
  https://learn.microsoft.com/en-us/azure/azure-functions/durable/durable-orchestration-versioning
- Microsoft Durable Functions — Versioning challenges:
  https://learn.microsoft.com/en-us/azure/azure-functions/durable-functions/durable-functions-versioning
- Temporal architecture — event-sourced workflow history:
  https://github.com/temporalio/temporal/blob/main/docs/architecture/README.md
- Temporal architecture — History Service:
  https://github.com/temporalio/temporal/blob/main/docs/architecture/history-service.md
- Temporal Worker Versioning:
  https://github.com/temporalio/temporal/blob/main/docs/worker-versioning.md
- AWS Step Functions — versions and aliases:
  https://docs.aws.amazon.com/step-functions/latest/dg/concepts-cd-aliasing-versioning.html
- AWS Step Functions — state-machine versions:
  https://docs.aws.amazon.com/step-functions/latest/dg/concepts-state-machine-version.html
- AWS Step Functions — state-machine aliases:
  https://docs.aws.amazon.com/step-functions/latest/dg/concepts-state-machine-alias.html
