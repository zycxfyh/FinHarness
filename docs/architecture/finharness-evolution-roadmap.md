# FinHarness Evolution Roadmap

Status: current
Updated: 2026-07-11
Owner: architecture + product governance

This is the maintained plan for evolving FinHarness after the 2026-07-10
repository audit. It is not a product-completion claim. Current system status
comes from `system-catalog.yml`; engineering debt comes from
`docs/governance/debt-register.json`; Agent Work Loop closure comes from
`task agent:work-loop-acceptance`.
Long-term control ownership is governed by
[`2026-07-11-agent-native-control-ownership.md`](../adr/2026-07-11-agent-native-control-ownership.md).

## 1. Executive Decision

FinHarness should evolve toward an **Agent-native Personal Capital Operating
System**. The human principal owns goals, capital constitution, delegation, and
veto power. The Capital Agent owns the objective-level
observe–reason–plan–act–verify–learn loop. FinHarness is the deterministic
Harness that makes that autonomy admissible, observable, recoverable, and
revocable. Classical engines provide effect correctness; they are not the
permanent owner of workflow intent.

The 2026-07-11 external-research and code audit rebases the order of work:

Near-term work repairs the evidence floor, capital world model, versioned
decisions, and Agent loop together. These foundations do not exist to keep the
Agent subordinate. They exist so that higher autonomy can be granted without
replacing safety with prompt trust.

The roadmap therefore advances on two axes:

1. **World fidelity:** capital facts → versioned decisions → Scenario → Outcome
   → Learning.
2. **Agent autonomy:** context-aware assistance → tool use → observation-driven
   loop → delegated Decision Review → autonomous paper management →
   mandate-bound real action → continuous capital operation.

This means velocity is measured by contracts closed and legacy surface removed,
not by PR count, model count, receipt count, or version labels.

## 2. Current Truth Baseline

| Area | Audited status | Consequence |
| --- | --- | --- |
| Execution Kernel | canonical | All new execution work uses `execution/*`; legacy ActionIntent/PaperValidation gets no new callers. |
| ActionIntent + PaperValidation | legacy | Preserve reads/migration evidence; define deletion boundaries; do not extend product capability. |
| Agent Operating Surface | semantically consumable | Tools, envelopes, playbooks, evaluators, memory, search, workspace, and trace primitives may be reused. |
| Agent Operating Cycle v0.1 | current AUT2 foundation | One bounded cycle is observation-driven, admitted, durable, searchable, reviewable, and terminally reduced; cross-cycle session/resume is absent. |
| Agent Work Loop / Agent Operating Cycle v0.1 | 15/15 acceptance contracts pass; AUT2 foundation current | Typed arguments, observation-driven decisions, independent budgets, preflight, autonomy admission, terminal receipts/results/search/workspace, and every declared stop reducer have behavioral evidence. This does not grant AUT3 decision authority. |
| Registered engineering debt | 10 resolved; 0 active | All currently registered debts pass, but the register is incomplete: test collection, capital truth, decision versioning, execution monotonicity, API contracts, and architecture cycles are verified material debts to add. |
| Python merge gate | false green | `check:ci` passed 954 unittest-discovered cases, but two known pytest-only Agent files contribute 38 tests while unittest runs 0 of them. |
| Capital-state truth | partial | Position lacks valuation currency/time/source and mixed-currency totals are still calculated; Scenario and Agent cannot treat it as a trusted current baseline. |
| Decision integrity | partial | Attestation binds `proposal_id`, not an immutable ProposalVersion receipt/hash; revisions do not supersede old decisions. |
| Real external execution | absent | No live adapter, broker SDK, credential loader, funded-account path, or network submit. |

## 3. What the PR History Actually Says

### Phase A — Candidate-chain expansion (#78–#102, 2026-07-01 to 2026-07-05)

ActionIntent preflight, simulation, trade-plan/order-ticket candidates,
authority bindings, review gates, objective fit, and Paper Validation were added
as many receipt-backed objects and routes. This proved governance vocabulary,
but it also created an execution-shaped shadow chain.

**Lesson:** a receipt-backed object is not automatically the correct domain
object. Judgment artifacts, authority traces, workflow outputs, and execution
facts must not be collapsed into one StateCore chain.

### Phase B — Product/data/governance stabilization (#103–#113)

The Capital Workbench roadmap, data catalog/quality console, route semantics,
engineering debt register, receipt-backed write registry, and fail-closed local
write capability were added.

**Lesson:** #111–#113 were high-leverage because they made ownership and write
boundaries inspectable. Their ledgers later drifted because status truth was
not yet checked against implementation.

### Phase C — Classical Execution migration (#114–#124, 2026-07-08)

The abstraction taxonomy exposed category errors; #116–#120 created the
Execution Kernel schema, services, simulated adapter, API, and cockpit; #121
introduced the legacy bridge; #122–#124 promoted the new mainline and downgraded
old documentation.

**Lesson:** execution lifecycle, state transitions, receipts, adapters, and
reconciliation are classical software responsibilities. This was the correct
architectural pivot.

### Phase D — Execution debt paydown (#125–#152)

The repository fixed flaky signals, registry alignment, deprecation markers,
projection cardinality, illegal lifecycle transitions, receipt contracts,
adapter isolation, browser smoke, and legacy documentation. #142 introduced
`ExecutionCapabilities` vocabulary; enforcement was deferred until EXEC-01.

**Lesson:** the hardening work was valuable, but two `current` debt ledgers and
stale general-register entries showed that closure reports cannot be their own
evidence.

### Phase E — Agent cognition primitives (#158–#189, 2026-07-08 to 2026-07-09)

AgentRunReceipt, ContextTrust, EvaluationReport, AuthorityTransition,
PlanningPolicyView, deliberation receipts, AgentCognitionFlow, semantic
evaluators, and ContextUsePolicy established provider-neutral cognition and
evaluation primitives.

**Lesson:** this phase built useful typed artifacts. It did not build an
observation-driven runtime, and its deterministic nature was appropriate.

### Phase F — Agent Operating Surface (#190–#217, 2026-07-09 to 2026-07-10)

Runtime receipt bridging, strict tool registry, availability snapshots, tool
result envelopes, context trust maps, search, memory, playbooks, evaluator
discovery, operating flow, and hydrated review workspace became semantically
consumable. #206–#217 were important hardening and integration work.

**Lesson:** these are reusable operating primitives. Their individual semantic
tests do not prove that one end-to-end work cycle consumes all of them.

### Phase G — Work Orchestrator scaffold (#218–#227, 2026-07-10)

#219–#225 added request/result models, context freeze, a bounded pre-requested
tool batch, playbook metadata binding, a fixed cognition bridge, search-index
rebuild, stop-reason literals, and memory-draft helper. #226 called a structural
presence smoke “semantic”; #227 promoted Wave 2.2 to completed.

**Lesson:** ten same-day PRs optimized for artifact presence. They did not
transport real tool arguments, consume observations to choose the next action,
enforce `max_steps`, reduce all stop paths, link the final run receipt, persist
the result, hydrate the workspace, or make the result searchable by work ID.

### Phase H — Truth recovery and first enforcement (#228 ancestry)

| Commit | Slice | Effect |
| --- | --- | --- |
| `c7be442` | TRUTH-01 | Downgraded Wave 2.2 claims to runtime truth and locked smoke counts. |
| `17ef59a` | TRUTH-02 | Made the system catalog the canonical lifecycle/status source. |
| `3d6d1fa` | TRUTH-03 | Unified engineering debt and made every debt status executable. |
| `33fadd6` | EXEC-01 | Enforced immutable execution capabilities at service/command/API boundaries. |
| `fcb4d86` | LOOP-01 | Added the intentionally red 15-contract Agent closure gate. |

The logical commits remained separate in git history and reached `main` through
#228. The PR also added the first SEC-BOUNDARY-01 implementation.

### Phase I — DeepSeek stabilization chain (#228–#233, audited 2026-07-10)

| PR | Slice | Audited result |
| --- | --- | --- |
| #228 | SEC-BOUNDARY-01 | Useful database/HTTP/legacy guards, but premature closure: the threat model itself still names missing broker-registry and machine-checkable consumer guards. Debt reopened. |
| #229 | DEVEX-02 | Valid: mise/CI converge on Node 22 and an unconsumed Rust install is removed. |
| #230 | DEVEX-01 | Direction valid; post-merge correction makes CI and research layers compose their lower-cost layer instead of copying its command list. |
| #231 | DEPS-01 | Invalid closure: six empty group keys are scaffolding, not dependency ownership or a dead-dependency review. Debt reopened. |
| #232 | STATECORE-01 | Model movement valid; post-merge correction removes the new module's reverse dependency on the compatibility monolith and adds semantic metadata/re-export tests. |
| #233 | FRONTEND-01 | Initial extraction was nominal: state remained in app.js and forms bypassed the shell. Post-merge correction extracts real state/actions and routes all three writes through the shared contract. |

**Lesson:** CI success proves the checked contract, not the prose claim. A debt
verifier must prove the desired semantics; file existence, symbol presence, or
empty configuration keys are not closure evidence.

## 4. Responsibility Model

### 4.1 Four control roles

```text
Human Principal / Constitutional Plane
  goals -> values -> capital constitution -> mandate -> veto/revocation
                         |
                         v
Capital Agent / Teleological Control Plane
  observe -> reason -> plan -> choose tools/skills -> act -> verify -> learn
                         |
                         v  typed requests / decisions / escalation
FinHarness Harness / Admissibility and Recovery Plane
  world model -> policy -> capability -> budget -> invariant -> receipt
  -> transaction boundary -> monitoring -> recovery -> rollback/escalation
                         |
                         v
Deterministic Financial Engines / Effect Plane
  Decimal/FX/accounting -> risk/scenario math -> persistence
  -> execution protocol -> reconciliation -> external effects
```

The Human Principal has ultimate sovereignty but need not approve every step
forever. The Capital Agent increasingly owns how an objective is achieved. The
Harness decides whether a proposed decision or action is admissible under the
current mandate and runtime state. Deterministic engines guarantee that an
admitted calculation, transition, transaction, or broker operation is executed
correctly.

### 4.2 Ownership matrix

| Responsibility | Primary owner | Boundary rule |
| --- | --- | --- |
| Goals, values, irreversible prohibitions, delegation ceiling | Human Principal | Constitutional choices cannot be inferred from model confidence. |
| Mandate grant, expansion, suspension, revocation, exceptional override | Human Principal + Harness | Explicit, scoped, expiring, revocable, and receipt-backed. |
| Goal decomposition, planning, tool/skill choice, action ordering, replanning | Capital Agent | Agent owns strategy within mandate; Harness validates admissibility. |
| Evidence interpretation, counterargument, Scenario design, explanation | Capital Agent | Claims bind facts, assumptions, gaps, and uncertainty. |
| Monitoring, anomaly response, outcome evaluation, lesson proposal | Capital Agent | May autonomously continue, stop, or escalate within the granted level. |
| Financial facts and world-model versions | Harness + deterministic adapters | Typed, migrated, fresh, reconciled, and provenance-bound. |
| Capability, budget, timeout, idempotency, stop/retry ceiling | Harness | Enforced before effects; prompt text is never the boundary. |
| Policy/mandate admissibility, escalation, kill switch, recovery | Harness | Same gate applies to every entry point and survives restart. |
| Tool registry, schema validation, dispatch, receipt, search | Harness | Every Agent action crosses a typed and testable membrane. |
| Decimal/FX/accounting/risk/Scenario calculations | Deterministic engines | Reproducible inputs and versioned math; no free-form model arithmetic. |
| Persistence, transaction, execution protocol, reconciliation | Deterministic engines | Effect correctness and atomicity remain classical even when Agent chose the action. |
| Human review workspace | Harness projection | Human can supervise, inspect, intervene, or revoke at every autonomy level. |

### 4.3 Non-negotiable boundary laws

1. Raw model text never mutates StateCore or calls a broker; Agent decisions
   enter the Harness as typed requests.
2. Outside the active mandate, Agent output is a candidate. Inside the mandate,
   an Agent decision may become effective after deterministic admissibility.
3. Harness gates validate authority, freshness, policy, schema, budget,
   idempotency, and autonomy level before effects.
4. The Agent may own whether, when, why, and in what order to act. The Execution
   Kernel owns atomic submission, state transitions, and reconciliation.
5. Every effect has a durable receipt; every failed, partial, denied, or
   escalated cycle has a linked terminal trace and recovery state.
6. Human approval is never inferred. Human involvement evolves explicitly from
   in-the-loop to on-the-loop to over-the-loop as evidence supports delegation.
7. Mandate expansion, high-impact irreversible action, constitutional conflict,
   and unresolved ambiguity always escalate to the Human Principal.
8. Legacy routes receive compatibility fixes and deletion work only.
9. A maturity or autonomy label changes only after its executable acceptance
   gate passes.

## 5. Debt Paydown Before Expansion

The following block is mechanically checked against the canonical register.

<!-- active-debt:start -->
(no active debt)
<!-- active-debt:end -->

Rules:

- The canonical register may grow; status truth is evaluated per debt and never
  inferred from a fixed total or a test count.
- Their registered status does not block isolated Agent contract work.
- A debt is closed only when `scripts/verify_debt_register.py` agrees.
- “No active registered debt” is not a claim that no material debt exists. The
  2026-07-11 evidence audit identified new entries that E0-02 must register.

## 6. Delivery Roadmap

The accepted detailed execution plan is
[`2026-07-11-finharness-evolution-execution-plan.md`](../proposals/2026-07-11-finharness-evolution-execution-plan.md).
Its workstreams are constrained by a two-axis maturity lattice, not one serial
classical-first chain.

```text
World fidelity
W0 trustworthy capital facts
-> W1 versioned decisions and mandate
-> W2 deterministic Scenario world
-> W3 outcomes and reconciliation
-> W4 learning with proven policy consumption

Agent autonomy
AUT0 context-aware assistant
-> AUT1 tool-using reviewer
-> AUT2 observation-driven durable loop
-> AUT3 delegated Decision Review
-> AUT4 autonomous paper capital manager
-> AUT5 mandate-bound real-world operator
-> AUT6 continuous personal capital agent
```

E0 evidence repair and E1 containment support both axes. D0/D1/P0/O0 raise
world fidelity. LOOP/A0 slices raise Agent autonomy. Work can proceed in
parallel where the cross-axis entry gate is satisfied; neither axis is a
permanent servant of the other.

| World × autonomy milestone | Minimum admissible capability |
| --- | --- |
| W0 + AUT1 | Agent may inspect state, detect missing data, and request evidence. |
| W1 + AUT2 | Agent may autonomously assemble a complete review packet and replan from observations. |
| W2 + AUT3 | Within a review mandate, Agent may complete Scenario comparison and make an effective planning decision; out-of-mandate cases escalate. |
| W3 + AUT4 | Agent may run paper actions, monitor, reconcile, and replan under limits with human-on-the-loop. |
| W4 + AUT5 | A separately authorized program may permit bounded real actions by asset, notional, frequency, loss, expiry, and kill switch. |
| Mature AUT6 | Continuous capital management with human-over-the-loop constitutional control and exception handling. |

AUT5 and AUT6 are north-star states, not authorization to implement live
execution in the current program.

### Phase 0 — Truth and execution control (complete locally)

TRUTH-01/02/03/04, EXEC-01, and LOOP-01 establish truthful status, one debt
source, current abstraction placement, service-enforced execution capabilities,
and a semantic closure gate.
Do not squash away their logical boundaries during review.

### Phase 1 — Architecture and safety stabilization

| Slice | Plane | Prerequisite | Deliverable | Exit gate | Explicit deferral |
| --- | --- | --- | --- | --- | --- |
| TRUTH-04 (complete locally) | Classical governance | TRUTH-02 | Execution models/services/routes/adapter/bridge classified in abstraction inventory; legacy targets point to existing kernel. | ENG-DEBT-0009 verifier passes; docs-current green. | No runtime refactor. |
| SEC-BOUNDARY-02 | Classical + Human security | TRUTH-04 | Dedicated paper-legacy trust boundary: canonical consumer manifest (SEC-02A), AST import guard (SEC-02B), broker-registry isolation (SEC-02C). | Closed: ENG-DEBT-0002 resolved; threat-model gaps reconciled. | No paper feature, live path, or new route. |
| DEVEX-02 | Classical toolchain | none | One Node major across mise/CI; Rust removed or tied to a named consumer. | Complete: ENG-DEBT-0008 resolved; Node 22 unified, Rust removed. | No dependency upgrades. |

Use `security-best-practices` for execution/API control changes and the installed `playwright` for frontend golden paths.

### Phase 2 — Reliable delivery and dependency ownership

| Slice | Plane | Prerequisite | Deliverable | Exit gate | Explicit deferral |
| --- | --- | --- | --- | --- | --- |
| DEVEX-01 | Classical tooling | stage timing evidence | `check:fast`, `check:ci`, `check:research`; documented merge aggregate. | Complete: ENG-DEBT-0004 resolved; 3 named layers, check aliases check:ci. | No test deletion/quarantine. |
| DEPS-01/02 correction | Classical packaging | DEVEX-01 | Machine-readable import/task consumer inventory; evidence-owned groups; executable base/data/research/agent/eval profiles. | Complete after audit hardening: ENG-DEBT-0005 resolved; paper/security remain honestly empty, base imports the core API without optional wheels, the Agent profile explicitly composes data + research + agent, and isolated profiles run in CI. | No speculative upgrades or removals. |

The purpose is ownership, not a smaller dependency count at any cost.

### Agent Harness foundation lane — formerly Phase 3

The dedicated 15-contract gate is the minimum Harness foundation for AUT2. It
is not the end of the Agent product. No PR may change an autonomy label merely
because it adds a new class or receipt.

<!-- agent-open:start -->
<!-- agent-open:end -->

| Slice | Classical responsibility | Agentic responsibility | Contracts closed | Exit rule |
| --- | --- | --- | --- | --- |
| LOOP-02 Typed ToolRequest | Frozen `AgentWorkToolRequest`, argument schema validation, backward-compatible request adapter. | Choose tool and concrete arguments. | `real_tool_arguments` | Real successful tool call proves arguments reach handler and trace. |
| LOOP-03 Step reducer | Step counter, budget reducer, terminal taxonomy, deterministic test decision port. | Choose next action from goal + snapshot + preceding observation. | `observation_driven_decision`, `max_steps_effective`, `unavailable_tool_stop`, `all_stop_paths_reduced` | Every declared stop path has a behavioral test; no preselected batch loop. |
| LOOP-04 Work preflight | Freeze/validate required context, trust policy, playbook and evaluator availability before dispatch. | Select playbook and interpret non-blocking guidance. | `playbook_requirements_enforced` | Missing required context stops before tool/cognition effects. |
| LOOP-05 Terminal artifact chain | Finalize/link AgentRunReceipt, persist AgentWorkResult, store resolvable tool refs, index by work ID. | Produce terminal synthesis content and gaps. | `final_agent_run_receipt_linked`, `tool_result_refs_are_artifacts`, `work_result_persisted`, `result_searchable_by_work_id` | Success/partial/failure all produce one linked, searchable terminal chain. |
| LOOP-06 Review hydration | Deterministically hydrate/persist workspace projection from terminal refs. | Supply findings/options/explanation for human review. | `review_workspace_hydrated` | Workspace reads receipts, not in-memory placeholders. |
| LOOP-07 Closure audit | Run all gates, performance/size bounds, failure injection, documentation rebase. | No new capability. | 15/15 | Only here may naming graduate to AUT2 / Agent Operating Cycle v0.1. |

All fifteen contracts pass and must remain green:
`real_tool_arguments`, `observation_driven_decision`,
`context_snapshot_frozen`, `max_steps_effective`,
`max_tool_calls_effective`, `unavailable_tool_stop`,
`playbook_requirements_enforced`, `final_agent_run_receipt_linked`,
`tool_result_refs_are_artifacts`, `work_result_persisted`,
`review_workspace_hydrated`, `result_searchable_by_work_id`,
`evaluation_report_linked`, `execution_boundary_closed`, and
`all_stop_paths_reduced`.

#### Implementation ledger — autonomy control foundation

This ledger records the framework now proven by the 15-contract AUT2 gate:

| Slice | Status | Evidence | Remaining boundary |
| --- | --- | --- | --- |
| AUT-CONTROL-01 W/A lattice and admission | implemented scaffold | `autonomy_control.py`; behavioral positive/negative tests | Produces evidence only; no dispatch or effect integration. |
| AUT-CONTROL-02 StateCore authority adapter | implemented scaffold | `agent_autonomy_adapter.py`; dynamic grant/mandate tests | Legacy vocabulary maps only through AUT3; no AUT4+ inference. |
| AUT-CONTROL-03 Work context propagation | implemented scaffold | `AgentWorkRequest` / `AgentWorkResult` carry Agent, W/A, mandate and grant identifiers | Harness runtime ceiling remains separate from the Agent request. |
| AUT-CONTROL-04 Dispatch admission binding | implemented | Every attempted dispatch crosses typed admission first; reports are persisted and denied attempts fail before runtime dispatch | Effect-command integration remains a later AUT4/AUT5 concern. |
| AUT-CONTROL-05 Terminal control evidence | implemented | Admission, tool artifacts, AgentRunReceipt, WorkResult, search index and hydrated workspace form a terminal chain across declared stop paths | Restart/resume/session semantics remain a later durability wave, not part of AUT2. |

The control plane may be developed in parallel with LOOP-02 through LOOP-06,
The runtime may now be named AUT2 / Agent Operating Cycle v0.1. AUT3 still
requires W1/W2 world prerequisites and an explicit delegated-review program.

Do not add AgentSession, checkpoint/resume, scheduling, subagents, or MCP tools
while building AUT2. Those are later Harness mechanisms triggered by measured
continuous-operation, retry, delegation, or external-tool needs—not permanent
non-goals.

### Phase 4 — Structural modularity

| Slice | Plane | Deliverable | Exit gate |
| --- | --- | --- | --- |
| STATECORE-01 | Classical | Extract low-coupling personal-finance models behind an acyclic shared model base; retain `models.py` re-exports. | Complete after audit correction: 9 models extracted; class identity and metadata registration proven. |
| FRONTEND-01 | Classical UI | Extract `api.js`, real shared `state.js`, and `actions.js` ReviewActionShell before new views. | Complete after audit correction: all three governed write forms use the shell; semantic jsdom boundary test passes. |

These slices are refactors. They must not introduce product features, schema
changes, or a frontend framework migration.

### Product workflow lane — rebased by P0/A0/O0

Entry criteria for W2 deterministic Scenario work are E0 evidence repair,
trustworthy W0/D0 capital inputs, and W1/D1 versioned decisions. AUT2 may be
built in parallel, but AUT3 delegated Decision Review requires both W1 and W2.
Paper/execution autonomy requires W3/O0 hardening.

Historical candidate sequence, superseded where the accepted plan is more
specific:

1. **Paper Execution Review** over ExecutionReport/PositionDelta/Reconciliation,
   with performance/PnL/scenario comparison as read models.
2. **Agent Work Queue** exposing persisted WorkResult and hydrated workspace to
   humans; no autonomous apply.
3. **Delegated candidate application** graduated from human-confirmed to
   mandate-effective only after an already-governed command has freshness,
   limits, rollback, and escalation evidence.
4. **Authority Contract design** after paper behavior produces enough
   evidence to define scope, caps, expiry, revocation, monitoring, and kill
   switches.

No new work may build on legacy PaperValidation or ActionIntent writes.

### AUT5 — External/live authority (north star, not authorized in this program)

This phase requires a new user decision and a separate C3 program:

- real user need and supported broker/venue;
- threat model and credential lifecycle;
- legal/compliance review appropriate to deployment;
- funded-account and environment isolation;
- submit-live capability default false with explicit grant/revocation;
- notional/turnover/drawdown/cooldown limits;
- independent monitoring, kill switch, incident and rollback plan;
- paper-to-live evidence and human approval.

Until all entry criteria exist, current implementation remains simulated. This
is an evidence gate for when autonomy may expand, not a permanent claim that a
Capital Agent can never own an execution objective.

## 7. PR and Review Policy

Every future PR declares:

- logical slice ID and owned plane;
- canonical system and module placement;
- active debt or acceptance contract affected;
- default-path invariant;
- failure/rollback behavior;
- tests that prove semantics, not object presence;
- documentation status that may change, if any;
- explicit non-goals.

Review order:

1. architecture placement;
2. safety and authority boundary;
3. semantic acceptance evidence;
4. compatibility/migration;
5. implementation quality;
6. documentation claim.

Documentation merges last in a chain and may only summarize evidence already
green on the exact commit.

## 8. Gate Model

| Gate | Purpose | Required evidence |
| --- | --- | --- |
| Truth gate | Prevent status/roadmap drift. | system catalog, debt verifier, docs-current. |
| Classical correctness gate | Protect state/effects. | schema, lifecycle, idempotency, receipt, capability, failure tests. |
| Agent semantic gate | Prove judgment loop behavior. | `task agent:work-loop-acceptance` 15/15 plus deterministic fakes. |
| Product gate | Prove a human workflow. | API/UI golden path, review usability, artifact lineage. |
| Authority gate | Permit stronger consequence. | threat model, explicit contract, human decision, revocation, incident controls. |

A lower gate cannot be replaced by a higher-level demo. A polished cockpit does
not prove state correctness; a model demo does not prove authority; a smoke
does not prove semantic closure.

## 9. Skills and Tools in the Delivery System

| Capability | Use |
| --- | --- |
| `security-threat-model` | Trust boundaries, abuse cases, paper-legacy deletion and any future provider/live surface. |
| `security-best-practices` | API, credential, capability, dependency, and execution control review. |
| `playwright` | Real-browser golden paths after frontend modularization; not a substitute for service tests. |
| GitHub repository/CI/review workflows | PR genealogy, unresolved review threads, failing Actions, and intentional publication. |
| `rg`, git history, AST/static tests | Repository truth and causal audit. |
| pytest/unittest, mypy, ruff, Taskfile | Classical verification and repeatable local gates. |
| promptfoo/evaluators | Agent-output and boundary evaluation after deterministic runtime contracts. |

Tool use follows ownership: browser tooling proves UI journeys; security
workflows prove trust assumptions; Agent evals do not replace deterministic
service, receipt, or capability tests.

## 10. Success Metrics

Near-term:

- one current system catalog and one current engineering-debt register;
- reduce the 2 evidence-backed active debts to 0 without adding parallel registries;
- Agent acceptance moves monotonically from 4/15 to 15/15;
- Agent autonomy is named explicitly as AUT0/AUT1/AUT2 rather than inferred
  from object count;
- no new legacy callers, writes, models, or product docs;
- every stacked slice passes its owned tests and full merge gate.

Product-stage:

- humans can locate source/evidence/receipt/workspace lineage for every Agent
  work result;
- paper review measures decision and execution quality without live effects;
- state-changing commands show capability, authority, freshness, and human
  decision evidence;
- failure and denial paths are as observable as success paths.
- at each cross-axis milestone, the Agent completes more of the objective while
  human attention moves from per-step approval toward supervision and exception
  handling;
- autonomy expansion is measured by mandate-contained completion, escalation
  quality, intervention rate, recovery success, and absence of boundary breach.

## 11. Update Protocol

Update this roadmap only when at least one underlying fact changes:

- a canonical debt verifier changes state;
- an Agent acceptance contract closes or regresses;
- a system catalog lifecycle status changes;
- a phase entry/exit gate is met;
- a user authorizes a new product/authority phase.

Every update must change the corresponding machine-readable source or test in
the same PR. Narrative confidence alone is not a roadmap event.
