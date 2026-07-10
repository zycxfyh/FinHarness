# FinHarness Evolution Roadmap

Status: current
Updated: 2026-07-10
Owner: architecture + product governance

This is the maintained plan for evolving FinHarness after the 2026-07-10
repository audit. It is not a product-completion claim. Current system status
comes from `system-catalog.yml`; engineering debt comes from
`docs/governance/debt-register.json`; Agent Work Loop closure comes from
`task agent:work-loop-acceptance`.

## 1. Executive Decision

FinHarness should evolve as a **classical capital operating core with an
agentic judgment layer**, not as an Agent framework that happens to contain
financial objects.

The order of work is:

1. keep repository truth executable;
2. remove debt that distorts architecture, safety, and delivery signals;
3. close the Agent action-observation-decision loop against semantic contracts;
4. pay structural modularity debt before adding more cockpit or StateCore
   surface;
5. build product workflows over the canonical Execution Kernel;
6. consider stronger authority only after paper evidence, threat models, human
   gates, and explicit capability contracts exist.

This means velocity is measured by contracts closed and legacy surface removed,
not by PR count, model count, receipt count, or version labels.

## 2. Current Truth Baseline

| Area | Audited status | Consequence |
| --- | --- | --- |
| Execution Kernel | canonical | All new execution work uses `execution/*`; legacy ActionIntent/PaperValidation gets no new callers. |
| ActionIntent + PaperValidation | legacy | Preserve reads/migration evidence; define deletion boundaries; do not extend product capability. |
| Agent Operating Surface | semantically consumable | Tools, envelopes, playbooks, evaluators, memory, search, workspace, and trace primitives may be reused. |
| Deterministic Work Orchestrator | scaffolded | It batches pre-requested tools and creates partial artifacts; it is not an Agent Work Loop. |
| Agent Work Loop | 4/15 acceptance contracts pass; 11 open | No operational/closed naming, session layer, scheduling, resume, or authority expansion. |
| Engineering debt | 5 resolved; 5 active | Active items below are prerequisites, not optional cleanup. |
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

### Phase H — Truth recovery and first enforcement (local stacked chain)

| Commit | Slice | Effect |
| --- | --- | --- |
| `c7be442` | TRUTH-01 | Downgraded Wave 2.2 claims to runtime truth and locked smoke counts. |
| `17ef59a` | TRUTH-02 | Made the system catalog the canonical lifecycle/status source. |
| `3d6d1fa` | TRUTH-03 | Unified engineering debt and made every debt status executable. |
| `33fadd6` | EXEC-01 | Enforced immutable execution capabilities at service/command/API boundaries. |
| `fcb4d86` | LOOP-01 | Added the intentionally red 15-contract Agent closure gate. |

These commits are local and stacked on `origin/main` (latest: `d92407d`).
SEC-BOUNDARY-01 (ENG-DEBT-0002) is prepared locally with the threat-model
section, boundary tests, removal ledger, and debt-register resolution.
Publication remains a separate user decision.

## 4. Responsibility Model

### 4.1 Three planes

```text
Agentic Judgment Plane
  goal decomposition -> context relevance -> tool/argument choice
  -> observation interpretation -> options/critique/explanation
                    |
                    v  typed requests / candidate artifacts
Classical Software Plane
  schema -> capability gate -> dispatcher -> deterministic services
  -> database/receipts -> projections/search -> budgets/stop reducer
                    |
                    v  review evidence / explicit transition request
Human Authority Plane
  policy ownership -> evidence acceptance -> approval/attestation
  -> capability grant/revocation -> exceptional risk decision
```

The Agentic plane may choose and explain. The Classical plane validates,
persists, executes deterministic commands, and proves effects. The Human plane
owns authority and policy changes.

### 4.2 Ownership matrix

| Responsibility | Primary owner | Boundary rule |
| --- | --- | --- |
| Financial facts, accounts, positions, policies, proposals | Classical | Typed StateCore facts with migrations and invariant tests. |
| Market/provider ingestion | Classical adapters | External output is evidence with freshness/provenance, never authority. |
| Deterministic calculations and policy checks | Classical | Decimal/time semantics, reproducible inputs, no model judgment. |
| Execution lifecycle and reconciliation | Classical | Agent cannot call adapters or mutate execution state directly. |
| Capability, budget, timeout, stop, retry, idempotency | Classical | Enforced before effects; prompt text is not a security boundary. |
| Tool registry, schema validation, dispatch, result envelope | Classical runtime membrane | Every Agent action crosses a typed, testable tool boundary. |
| Goal decomposition and next-action selection | Agentic | Consumes frozen context and prior observations; remains provider-neutral at the contract. |
| Tool and argument selection | Agentic through classical schema | Model chooses content; runtime validates profile, schema, budget, and side effect. |
| Evidence interpretation, option generation, critique, explanation | Agentic | Produces review artifacts with refs, gaps, assumptions, and non-claims. |
| Hard constraints and eligibility | Classical evaluators | Deterministic blockers cannot be overridden by Agent output. |
| Qualitative evaluation | Agentic evaluator | Findings are evidence for review, not final authority. |
| Memory candidate generation | Agentic | May propose; cannot silently promote or rewrite history. |
| Memory storage, dedupe, provenance, promotion rule | Classical + Human | Promotion requires explicit policy/attestation. |
| Review workspace projection | Classical | Deterministically hydrates receipts and findings for humans. |
| Approval, attestation, policy change, authority grant | Human | Explicit identity/reason/freshness/confirmation; revocable and auditable. |
| Observability, receipts, search, audit, release gates | Classical | Complete even on failure/partial/denial paths. |

### 4.3 Non-negotiable boundary laws

1. A model response never mutates StateCore by itself.
2. Agent choices enter classical software as typed requests.
3. Classical commands validate capability, authority, freshness, schema, and
   idempotency before effects.
4. Every effect has a durable receipt; every failed/partial work cycle has a
   linked terminal trace.
5. Execution remains entirely classical. Agentic output may create a review
   candidate only through an explicitly graduated tool.
6. Human approval is not inferred from conversation or model confidence.
7. Legacy routes receive compatibility fixes and deletion work only.
8. A maturity/version label changes only after its executable acceptance gate.

## 5. Debt Paydown Before Expansion

The following block is mechanically checked against the canonical register.

<!-- active-debt:start -->
| Debt | Priority | Paydown outcome | Order |
| --- | --- | --- | --- |
| ENG-DEBT-0008 | P1 | Unify Node policy; remove or justify Rust CI install. | 1 |
| ENG-DEBT-0004 | P1 | Measured fast/CI/research check layers without weakening merge gates. | 2 |
| ENG-DEBT-0005 | P1 | Consumer-audited dependency groups after check layering. | 3 |
| ENG-DEBT-0006 | P2 | Compatibility-preserving StateCore bounded-context split. | 4 |
| ENG-DEBT-0007 | P2 | Shared governed action shell and frontend API/state modules. | 5 |
<!-- active-debt:end -->

Rules:

- Items 1–2 block new security/toolchain claims.
- Items 3–4 block dependency expansion and research/runtime coupling.
- Items 5–6 block further model and cockpit surface growth, but not the
  isolated Agent Loop contract work in Phase 3.
- A debt is closed only when `scripts/verify_debt_register.py` agrees.

## 6. Delivery Roadmap

### Phase 0 — Truth and execution control (complete locally)

TRUTH-01/02/03/04, EXEC-01, and LOOP-01 establish truthful status, one debt
source, current abstraction placement, service-enforced execution capabilities,
and a semantic closure gate.
Do not squash away their logical boundaries during review.

### Phase 1 — Architecture and safety stabilization

| Slice | Plane | Prerequisite | Deliverable | Exit gate | Explicit deferral |
| --- | --- | --- | --- | --- | --- |
| TRUTH-04 (complete locally) | Classical governance | TRUTH-02 | Execution models/services/routes/adapter/bridge classified in abstraction inventory; legacy targets point to existing kernel. | ENG-DEBT-0009 verifier passes; docs-current green. | No runtime refactor. |
| SEC-BOUNDARY-01 | Classical + Human security | TRUTH-04 | Dedicated paper-legacy trust boundary, cannot-graduate-to-live test, consumer/deletion criteria. | Complete: ENG-DEBT-0002 resolved; 19 boundary tests pass. | No paper feature, live path, or new route. |
| DEVEX-02 | Classical toolchain | none | One Node major across mise/CI; Rust removed or tied to a named consumer. | ENG-DEBT-0008 verifier passes; browser/security workflows green. | No dependency upgrades. |

Use `security-best-practices` for execution/API control changes and the installed `playwright` for frontend golden paths.

### Phase 2 — Reliable delivery and dependency ownership

| Slice | Plane | Prerequisite | Deliverable | Exit gate | Explicit deferral |
| --- | --- | --- | --- | --- | --- |
| DEVEX-01 | Classical tooling | stage timing evidence | `check:fast`, `check:ci`, `check:research`; documented merge aggregate. | ENG-DEBT-0004 verifier passes; CI cannot run fewer mandatory checks. | No test deletion/quarantine. |
| DEPS-01 | Classical packaging | DEVEX-01 | Import/task consumer inventory; scoped data/research/agent/eval/paper/security groups. | ENG-DEBT-0005 verifier passes; clean installs run owned tasks. | No speculative upgrades or removals. |

The purpose is ownership, not a smaller dependency count at any cost.

### Phase 3 — Agent Work Loop semantic closure

The dedicated acceptance gate is the work breakdown. No PR may change the
architecture label merely because it adds a new class or receipt.

<!-- agent-open:start -->
- `real_tool_arguments`
- `observation_driven_decision`
- `max_steps_effective`
- `unavailable_tool_stop`
- `playbook_requirements_enforced`
- `final_agent_run_receipt_linked`
- `tool_result_refs_are_artifacts`
- `work_result_persisted`
- `review_workspace_hydrated`
- `result_searchable_by_work_id`
- `all_stop_paths_reduced`
<!-- agent-open:end -->

| Slice | Classical responsibility | Agentic responsibility | Contracts closed | Exit rule |
| --- | --- | --- | --- | --- |
| LOOP-02 Typed ToolRequest | Frozen `AgentWorkToolRequest`, argument schema validation, backward-compatible request adapter. | Choose tool and concrete arguments. | `real_tool_arguments` | Real successful tool call proves arguments reach handler and trace. |
| LOOP-03 Step reducer | Step counter, budget reducer, terminal taxonomy, deterministic test decision port. | Choose next action from goal + snapshot + preceding observation. | `observation_driven_decision`, `max_steps_effective`, `unavailable_tool_stop`, `all_stop_paths_reduced` | Every declared stop path has a behavioral test; no preselected batch loop. |
| LOOP-04 Work preflight | Freeze/validate required context, trust policy, playbook and evaluator availability before dispatch. | Select playbook and interpret non-blocking guidance. | `playbook_requirements_enforced` | Missing required context stops before tool/cognition effects. |
| LOOP-05 Terminal artifact chain | Finalize/link AgentRunReceipt, persist AgentWorkResult, store resolvable tool refs, index by work ID. | Produce terminal synthesis content and gaps. | `final_agent_run_receipt_linked`, `tool_result_refs_are_artifacts`, `work_result_persisted`, `result_searchable_by_work_id` | Success/partial/failure all produce one linked, searchable terminal chain. |
| LOOP-06 Review hydration | Deterministically hydrate/persist workspace projection from terminal refs. | Supply findings/options/explanation for human review. | `review_workspace_hydrated` | Workspace reads receipts, not in-memory placeholders. |
| LOOP-07 Closure audit | Run all gates, performance/size bounds, failure injection, documentation rebase. | No new capability. | 15/15 | Only here may naming graduate to Agent Operating Cycle v0.1. |

Four contracts already pass and must remain green:
`context_snapshot_frozen`, `max_tool_calls_effective`,
`evaluation_report_linked`, and `execution_boundary_closed`.

Do not add AgentSession, checkpoint/resume, scheduling, subagents, or MCP tools
during Phase 3. Those are triggered only by a closed loop plus measured retry,
resume, or external-tool needs.

### Phase 4 — Structural modularity

| Slice | Plane | Deliverable | Exit gate |
| --- | --- | --- | --- |
| STATECORE-01 | Classical | Extract low-coupling personal-finance models; retain `models.py` re-exports. | ENG-DEBT-0006 verifier; metadata, OpenAPI, migration and import compatibility. |
| FRONTEND-01 | Classical UI | Extract shared ReviewActionShell, `api.js`, and `state.js` before new views. | ENG-DEBT-0007 verifier; jsdom plus installed Playwright golden paths. |

These slices are refactors. They must not introduce product features, schema
changes, or a frontend framework migration.

### Phase 5 — Product workflows on canonical foundations

Entry criteria: Phases 1–3 complete; no P0/P1 architecture or control debt;
Agent closure 15/15; canonical execution and review interfaces current.

Candidate sequence:

1. **Paper Execution Review** over ExecutionReport/PositionDelta/Reconciliation,
   with performance/PnL/scenario comparison as read models.
2. **Agent Work Queue** exposing persisted WorkResult and hydrated workspace to
   humans; no autonomous apply.
3. **Human-confirmed candidate application** only for an already-governed
   classical command with freshness and rollback evidence.
4. **Authority Contract design** only after paper behavior produces enough
   evidence to define scope, caps, expiry, revocation, monitoring, and kill
   switches.

No new work may build on legacy PaperValidation or ActionIntent writes.

### Phase 6 — External/live authority (not planned for implementation)

This phase requires a new user decision and a separate C3 program:

- real user need and supported broker/venue;
- threat model and credential lifecycle;
- legal/compliance review appropriate to deployment;
- funded-account and environment isolation;
- submit-live capability default false with explicit grant/revocation;
- notional/turnover/drawdown/cooldown limits;
- independent monitoring, kill switch, incident and rollback plan;
- paper-to-live evidence and human approval.

Until all entry criteria exist, the correct implementation is no implementation.

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
- 5 active debts trend to zero without adding parallel registries;
- Agent acceptance moves monotonically from 4/15 to 15/15;
- no new legacy callers, writes, models, or product docs;
- every stacked slice passes its owned tests and full merge gate.

Product-stage:

- humans can locate source/evidence/receipt/workspace lineage for every Agent
  work result;
- paper review measures decision and execution quality without live effects;
- state-changing commands show capability, authority, freshness, and human
  decision evidence;
- failure and denial paths are as observable as success paths.

## 11. Update Protocol

Update this roadmap only when at least one underlying fact changes:

- a canonical debt verifier changes state;
- an Agent acceptance contract closes or regresses;
- a system catalog lifecycle status changes;
- a phase entry/exit gate is met;
- a user authorizes a new product/authority phase.

Every update must change the corresponding machine-readable source or test in
the same PR. Narrative confidence alone is not a roadmap event.
