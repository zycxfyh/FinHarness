# Proposal: FinHarness Evidence-First Evolution Execution Plan

Date: 2026-07-11
Status: accepted for sequencing; implementation slices remain individually reviewable
Related note: `docs/notes/2026-07-11-external-research-synthesis.md`
Related roadmap: `docs/architecture/finharness-evolution-roadmap.md`
Related review: `docs/reviews/2026-07-11-deepseek-wave3-audit.md`

## 1. Problem

FinHarness has more typed governance and runtime objects than closed user
outcomes. Some existing green gates verify structure rather than semantics.
Meanwhile, the next product capabilities—Scenario, Agent tasks, and outcome
review—would consume capital facts and decisions whose currency, time,
freshness, and version identity are not yet reliable enough.

The first revision corrected that dependency but overcorrected in the other
direction: it made the classical product the permanent subject and inserted the
Agent later as a bounded review-packet producer. That confused the current
Human-in-the-loop migration mode with the target architecture.

The target is an Agent-native capital operating system. Trusted facts,
versioned decisions, deterministic Scenario, execution correctness, and
receipts are the world and Harness through which the Agent gains progressively
greater objective-level control. They are not a reason to keep the Agent as a
permanent assistant.

## 2. User and product target

Initial users are self-directed, privacy-sensitive operators with multiple
accounts or meaningful interactions among investment, cashflow, debt, tax,
insurance, and long-term goals. The first complete job is:

> Review a material concentration or allocation decision against a trustworthy
> capital state, compare action with no action, record a version-specific human
> decision, and return at a scheduled horizon to compare expectations with
> outcomes.

Home/Today routes the operator to this job. It is not an engagement feed and
must not create market-noise pressure.

## 3. Governing invariants

1. A green gate must execute the behavior it claims to protect.
2. A monetary aggregate is invalid without currency and valuation time.
3. Mixed currencies are never silently added without time-bound FX evidence.
4. A human decision binds an immutable proposal version, not a mutable ID.
5. Reject and defer remain possible when accept is blocked.
6. Raw model output is not authority. Outside mandate it is a candidate; inside
   mandate an Agent decision may become effective after Harness enforcement.
7. Agent owns the strategy of whether, when, why, and in what order to act as
   autonomy grows. Deterministic services own calculation and effect
   correctness.
8. The current execution substrate remains simulated-only. In the target
   architecture, the Agent may own an execution objective, but never bypasses
   mandate, risk, transaction, or reconciliation gates.
9. Every terminal Agent work outcome is durable and searchable after restart.
10. A receipt proves recorded integrity/provenance, not financial correctness or
   authority.
11. Product and autonomy claims change only after behavioral, restart, and
    negative-path acceptance evidence passes on the same commit.

## 4. Target architecture

```text
Human Principal
  goals + values + capital constitution + mandate + veto/revocation
                              |
                              v
Capital Agent
  observe -> reason -> plan -> choose tools/skills -> act -> verify -> learn
                              |
                              v
FinHarness Harness
  CapitalStateView + DecisionCase + policy/mandate + tools + memory
  + admissibility + budgets + receipts + recovery + escalation
                              |
                              v
Deterministic Engines
  import/accounting/FX + risk/Scenario math + persistence/transactions
  + execution protocol + reconciliation + external effects
```

The Harness owns admissibility and recoverability, not the objective. The Agent
increasingly owns the objective loop. Deterministic engines are the financial
equivalent of a compiler, filesystem, database, and shell: essential physical
law, but not the entity deciding what goal to pursue.

## 5. Two-axis program model

World fidelity axis:

```text
W0 Capital facts
-> W1 Versioned decisions and mandate
-> W2 Scenario world
-> W3 Outcome/reconciliation
-> W4 Learning and effective-policy consumption
```

Agent autonomy axis:

```text
AUT0 Context-aware assistant
-> AUT1 Tool-using reviewer
-> AUT2 Observation-driven durable loop
-> AUT3 Delegated Decision Review
-> AUT4 Autonomous paper capital manager
-> AUT5 Mandate-bound real-world operator
-> AUT6 Continuous personal capital agent
```

| Cross-axis gate | Human mode | Effective Agent responsibility |
| --- | --- | --- |
| W0 + AUT1 | Human-in-the-loop | Inspect facts, find gaps, gather evidence. |
| W1 + AUT2 | Human-in-the-loop | Replan from observations and complete a review packet. |
| W2 + AUT3 | Human-in/on-the-loop by mandate | Complete Decision Review and make mandate-contained planning decisions. |
| W3 + AUT4 | Human-on-the-loop | Run paper actions, monitor, reconcile, evaluate, and replan. |
| W4 + AUT5 | Human-on/over-the-loop by explicit program | Take bounded real actions under asset/notional/frequency/loss/expiry/kill-switch constraints. |
| AUT6 mature state | Human-over-the-loop | Continuously manage delegated objectives; escalate constitutional conflicts and exceptions. |

E0 evidence work and E1 containment support both axes. D0 maps to W0, D1 to
W1, deterministic Scenario work to W2, O0 to W3/W4, and the Agent Harness
slices to AUT1/AUT2. These are parallel workstreams with cross-axis gates, not a
plan to finish classical software and attach an Agent afterward.

### 5.1 Current implementation ledger (2026-07-11)

The first framework cycle has established the autonomy admission vocabulary,
not higher operational autonomy:

| Slice | Current state | Proof | Next dependency |
| --- | --- | --- | --- |
| AUT-CONTROL-01 | W0-W4/AUT0-AUT6 action requirements and typed admission report implemented | behavioral control-plane tests | action-specific limit evaluators |
| AUT-CONTROL-02 | existing CapitalMandate/AgentAuthorityGrant dynamically resolve into AUT0-AUT3 runtime mandates | StateCore adapter integration tests | durable terminal linkage |
| AUT-CONTROL-03 | Agent work request/result carry Agent, W/A, mandate, and grant context; runtime ceiling is Harness-owned | work-loop reducer tests | bind actual world versions rather than caller hints |
| AUT-CONTROL-04 | every attempted tool dispatch crosses admission before runtime dispatch | persisted admission reports and negative dispatch tests | link denied reports into terminal WorkResult/search/workspace |

All current reports remain non-executing evidence. Agent Operating Cycle v0.1
passes 15/15 and establishes AUT2 only; it does not authorize AUT3-AUT6.

## 6. Foundation workstream E0 — Repair the evidence floor

### E0-01: Make every Python test runner explicit

Deliverables:

- add `test:unittest`, `test:pytest`, and `test:all` tasks;
- make `check:fast` consume `test:all`;
- retain both runners initially rather than rewriting the suite;
- add runner sentinels so removing either task produces a failure;
- report per-runner collection and execution counts in CI;
- make System Catalog checks resolve to executable Task targets.

Acceptance:

```text
PYTHONPATH=src uv run python -m unittest \
  tests.test_agent_work_loop_models tests.test_agent_cognition_flow
```

may continue to find zero pytest tests, but `task test:all` must execute the 38
pytest cases and all unittest cases. A deliberately failing pytest sentinel in
a fixture must make the aggregate gate red.

Migration/rollback: Taskfile and workflow only; no runtime or stored-data
change. This is the first implementation slice.

### E0-02: Replace registration counts with evidence-complete debt truth

Deliverables:

- remove fixed assumptions that the repository has exactly ten debts;
- add verifier evidence levels: structural, semantic, runtime, restart,
  clean-environment;
- register the verified new debts instead of saying “10/10 resolved”:
  test-runner collection, repository layer gate, capital valuation/readiness,
  proposal-version decisions, execution monotonicity, frontend/API contract,
  receipt/mirror reconciliation, and current-doc truth consolidation;
- require resolved items to meet their declared evidence level.

Acceptance: adding a valid debt does not break a count assertion; changing a
semantic invariant makes its verifier fail without depending on a separate
test filename or prose token.

### E0-03: Add repository-wide import cycle and layer checks

Deliverables:

- canonical module names and relative-import resolution;
- SCC detection;
- a machine-readable layer matrix covering statecore, execution, agent,
  research, API/frontend composition, legacy, and archive;
- direct and transitive forbidden-edge reports;
- synthetic cycle and forbidden-edge negative fixtures;
- `architecture:check` in `check:ci`.

Minimum laws:

```text
statecore !-> api, frontend, agent cognition, research adapters
execution !-> agent cognition/tools
agent !-> execution commands/adapters
research !-> state write commands or execution
canonical modules !-> legacy write services
api composition !-> archived runtime
```

### E0-04: Consolidate current truth sources

Make `system-catalog.yml` canonical for system ownership/lifecycle, the debt
register canonical for verified debt, and the evolution roadmap canonical for
sequencing. Generate or clearly mark status duplicated in Framework Index,
Module Map, inventories, and old product roadmaps. Current-doc checks must cover
all navigation-reachable documents marked current.

## 7. Containment workstream E1 — Current misleading or unsafe surfaces

These changes prevent current code from communicating or recording a stronger
capability than it has. They can run immediately after E0-01.

### E1-01: Hide or repair the Execution Cockpit surface

Until a stable lifecycle read model exists, remove Execution from ordinary
navigation or label it an advanced Simulation Lifecycle Preview. Immediately:

- remove silent catches and direct raw `fetch` calls;
- fix Controls truth using the actual OpenAPI/router set;
- expose `substrate=simulated` and `live_execution_available=false` in typed
  responses;
- stop using receipt refs as report IDs;
- add API error envelopes and trace IDs;
- add a Chromium negative path proving a failed API cannot render as empty
  success.

### E1-02: Seal the simulated adapter boundary

- replace duck-typed public registry mutation with an explicit factory or
  allowlisted concrete simulated adapter;
- require a capability to register/replace adapters;
- enforce connection/account/draft environment consistency;
- make no-adapter submit fail closed;
- prohibit simulated connection credentials/network flags in model and DB
  constraints;
- add a disguised-network-adapter negative fixture.

This does not authorize live support.

### E1-03: Freeze legacy writes

Inventory current historical-read obligations, then return 410 for legacy
ActionIntent/PaperValidation write routes, remove them from ordinary OpenAPI and
frontend surfaces, and retain only explicit migration/read adapters. Historical
fixtures must remain readable before router removal.

## 8. World workstream W0/D0 — Build trustworthy capital state

### D0-01: Position valuation contract and migration

Add typed fields, with no silent default for existing rows:

```text
instrument_id (nullable during migration)
valuation_currency
unit_price
price_currency
valued_at
price_source_ref
fx_rate / fx_as_of / fx_source_ref (when conversion occurred)
valuation_status
```

Migrate old positions to `valuation_status=unknown_legacy`; do not invent USD.
Update CSV, Beancount, broker-receipt, API, fixtures, and snapshot-diff contracts.

Acceptance fixtures: USD-only, mixed unconverted, converted FX with timestamp,
unpriced, stale, and legacy unknown.

### D0-02: Decimal and time semantics at ingestion

- remove float normalization from broker ingestion;
- validate canonical UTC-aware timestamps;
- distinguish `effective_at`, `valued_at`, `observed_at`, `ingested_at`, and
  `recorded_at`;
- fail Beancount import on loader errors unless the operator explicitly accepts
  a partial import;
- record adapter/schema version and completeness.

### D0-03: ImportBatch and correction semantics

Introduce an ImportBatch/SourceSnapshotManifest that declares source identity,
content hash, full-snapshot versus delta scope, covered domains, record counts,
superseded batch, and commit status. Corrected full snapshots must remove stale
positions. Corrections produce explicit supersession evidence rather than
silent overwrite.

### D0-04: Receipt–mirror reconciliation

Choose and document one recoverable protocol—transactional outbox, canonical DB
envelope with materialized files, or durable saga. Provide crash fixtures for
receipt-before-DB, DB-before-receipt, missing index, deleted file, and rebuild.
The gate must report and repair or quarantine drift after restart.

### D0-05: CapitalStateView and cross-domain DataReadiness

Build one non-persisted or version-addressed read model:

```text
capital_state_ref
effective_at / valued_at
base_currency and per_currency_totals
domain_versions
freshness_by_domain
quality_by_domain
reconciliation_status
data_gaps
readiness: usable | usable_with_warnings | not_ready
blocked_uses
source_refs
```

Rules:

- mixed-unconverted state has per-currency totals and no unified net worth;
- critically stale or incomplete state cannot produce a precise current-state
  headline, Scenario baseline, or allocation rationale;
- `not_ready` still allows gap explanation and data-request preparation;
- Daily Brief, IPS checks, Proposal evidence, and Agent context migrate to this
  projection instead of independently reading latest tables.

## 9. World workstream W1/D1 — Make the decision ledger internally correct

### D1-01: ProposalVersion and DecisionRecord binding

Create stable proposal-version identity from receipt/content hash. Replace or
adapt Attestation into a DecisionRecord that binds:

```text
proposal_id
proposal_version_id
proposal_receipt_ref
proposal_content_hash
decision: accepted_for_planning | rejected | deferred
reason
operator declaration / identity class
created_at
```

Any material revision supersedes the active decision and returns the new
version to needs-evidence or ready-for-review. Conflicting active decisions are
invalid. Existing attestations migrate as `legacy_unbound` and cannot authorize
future execution binding.

### D1-02: One command-consumed DecisionReadiness gate

Unify source completeness, CapitalState readiness, policy evaluation,
counter-evidence, stale context, and duplicate findings. Findings are explicitly
advisory or blocking. The decision command must consume the same report the UI
shows:

- accept requires all blockers resolved;
- reject is always allowed;
- defer requires a reason and next review condition.

No read model may claim a transition is blocked unless the command enforces it.

### D1-03: Effective policy and learning consumer

Resolve base IPS plus active RuleChanges into one EffectiveDecisionPolicy.
Connect it first to deterministic allocation thresholds or DecisionReadiness,
recording policy version and consumed rule IDs on the ProposalVersion. Rename
`lessons_closed` to `lessons_promoted` until a later decision proves actual
consumption.

### D1-04: DecisionCase/Inbox projection

Do not introduce another write subsystem. Build a product projection over
ProposalVersion, evidence, readiness, risks, review events, DecisionRecord,
execution links, and outcome refs. Merge Review Queue, Review Task, and Risk
Register into facets of one Decision Inbox while preserving internal DTOs where
they serve separate code consumers.

## 10. World/product workstream W2/P0 — Material Decision Review

### P0-01: Home/Today as an intake view

Create a stable `HomeTodayView` that answers:

1. When and in what currencies is my state valued?
2. Is it usable, partial, stale, or blocked?
3. What one to three material items need attention?
4. Why do they matter and what is the next action?

Technical receipts and raw paths move behind progressive disclosure. This page
routes into Decision Inbox; it does not optimize daily active use.

### P0-02: Decision Review Workspace

Create one user-language flow: problem, current evidence, missing evidence,
options, do-nothing, consequences, counter-evidence, policy impact, decision,
and review date. Add confirmation for accepting a proposal and explain what the
decision changed. Keep execution approval visibly separate.

Acceptance uses real FastAPI + Chromium for empty, partial, stale, blocked,
accept, reject, defer, revision-supersedes-decision, refresh, and restart paths.
Browser golden paths become required once this workspace is the main product
surface.

### P0-03: Point-in-time EvidencePack

Build a minimal EvidencePack for one concentration question. Every observation
must satisfy `observation_time <= decision_as_of`, include provider/license
class, coverage, freshness/readiness, calculation version, source refs, and a
stance of supports/refutes/neutral. Raw observation and computed metric are
separate artifacts.

### P0-04: Deterministic Concentration Scenario v0

Compare do nothing, future-cashflow dilution, and operator-sized reduction. No
optimizer or Monte Carlo is required. Calculate transparent, replayable deltas:

```text
position value and weight
cash and total assets
HHI
single-stock shock contribution
simple market shock
cash-runway change
estimated cost
tax status: known | placeholder | not computable
```

Every result binds CapitalStateView, ProposalVersion, EvidencePack, assumptions,
calculation version, and data gaps. Partial inputs produce partial results or a
block, never zero-filled precision.

### P0-05: Decision outcome schedule

DecisionRecord stores intended action, expected observation horizon, review
dates, falsifiable assumptions, and the chosen scenario. Schedule is a domain
fact/read model initially; no background scheduler is required. Due reviews
appear in Home/Today.

## 11. Agent Harness workstream — reach AUT2 through one useful task

The Agent task is: **collect counter-evidence and prepare a review packet for an
existing DecisionCase**. At AUT1/AUT2 it may not decide, apply a revision, or
execute. This is the first proving task, not the permanent product position of
the Capital Agent.

### A0-01: Typed ToolRequest, Observation, and WorkState

Add request ID, real arguments, expected side effect, idempotency key, actor,
source observations, durable result artifact, facts/gaps/error, step count,
tool-call count, and terminal state. Backward compatibility may adapt old
`requested_tools`, but production execution no longer loops over names with
empty arguments.

Closes `real_tool_arguments`.

### A0-02: Principal/profile resolution and unified preflight

Before any side effect, validate actor-to-profile assignment, tool capability,
availability, schema, playbook requirements, ContextTrust, budgets, side-effect
policy, and idempotency. AgentScopeGrant remains backend-only unless this
dispatcher becomes its real consumer.

Closes `playbook_requirements_enforced` and prevents profile self-selection from
acting as authorization.

### A0-03: Observation-driven reducer and stop taxonomy

The model or test decision port proposes a candidate action from goal, frozen
context, and preceding typed observations. A deterministic reducer validates
continue/stop and owns independent step/tool budgets and all declared stop
reasons.

Closes `observation_driven_decision`, `max_steps_effective`,
`unavailable_tool_stop`, and `all_stop_paths_reduced`.

### A0-04: Canonical artifact and terminal chain

Persist every ToolResultArtifact, one canonical AgentRunReceipt, an
observation-aware EvaluationReport, AgentWorkResult, and work-ID index. Every
success, partial, denial, exception, and budget stop produces a linked terminal
chain. Schema and hash fragments are verified.

Closes `final_agent_run_receipt_linked`, `tool_result_refs_are_artifacts`,
`work_result_persisted`, and `result_searchable_by_work_id`.

### A0-05: Restart-hydrated review packet and real model bridge

Hydrate the review packet from disk using only `work_id` in a fresh process.
Connect exactly one model runtime to the same lifecycle rather than retaining a
separate unaudited SDK path. Decide after a thin spike whether OpenAI Agents SDK
earns ownership; otherwise use the simpler model interface and remove the
redundant runtime dependency.

Closes `review_workspace_hydrated`. Then strengthen the acceptance gate with
corrupt artifact, partial write, duplicate idempotency, side-effect retry,
finalizer failure, restart, and all-stop negative fixtures. Only 15/15 on these
behavioral checks permits an Agent Operating Cycle label.

No Session, scheduler, checkpoint/resume, subagent, delegation, MCP server, or
automatic long-term memory is included while reaching AUT2. These become
eligible only when a later autonomy level has measured durability or delegation
needs.

## 12. Agent autonomy ladder after AUT2

### AUT3: Delegated Decision Review

Prerequisites: W1 versioned decisions, W2 Scenario, AUT2 durable loop, a scoped
Decision Review mandate, escalation policy, and retrospective evaluation.

The Agent owns evidence collection, Scenario selection, comparison, replanning,
and the planning decision inside mandate. The Harness enforces allowed decision
kinds, uncertainty/data thresholds, notional implications, expiry, and required
escalations. Outside mandate, the result remains a candidate for the Human
Principal.

### AUT4: Autonomous paper capital manager

Prerequisites: W3 outcome/reconciliation, monotonic simulated execution,
idempotency, recovery, monitoring, paper risk limits, and kill switch.

The Agent may create and execute paper plans, observe reports, reconcile state,
evaluate outcomes, and replan without per-step approval. The human moves to
on-the-loop supervision, exception review, and mandate revision.

### AUT5: Mandate-bound real-world operator

This requires a separate user authorization and C3 security/legal program. A
grant is bounded by assets, accounts, action types, notional, frequency,
turnover, loss/drawdown, time, data freshness, environment, and kill switch.
The Agent may decide and initiate admitted real actions; the Harness and
Execution Kernel retain deterministic enforcement and effect correctness.

### AUT6: Continuous personal capital agent

The mature target continuously observes, plans, acts, verifies, learns, and
adapts across delegated personal-capital objectives. Human-over-the-loop
governance retains constitutional goals, values, forbidden actions, mandate
expansion/revocation, extreme-risk decisions, and irreducible conflicts.

Progression is never inferred from model quality or a version label. Every
level requires executable authority, containment, recovery, and outcome gates.

## 13. World-fidelity W3/W4 workstream — paper outcome and learning

### O0-01: Monotonic simulated execution lifecycle

Before Decision-to-Execution binding, implement versioned/CAS transitions,
latest valid PreTradeCheck and Approval binding, submit idempotency, explicit
pending/acknowledged/rejected/uncertain states, and atomic/recoverable submit
recording. Report/delta/reconciliation capabilities become complete and the
post-submit chain is command-orchestrated.

### O0-02: Decision-to-Execution binding

An OrderDraft either declares an independent manual origin or binds a current
accepted ProposalVersion and DecisionRecord. Stale/superseded decisions cannot
stage. Execution Approval remains a separate human act bound to draft hash,
pretrade hash, environment, expiry, and reviewer evidence.

### O0-03: Paper Performance Review

At 20/60 trading-day or 30/90 calendar-day horizons, compare chosen scenario,
do-nothing, and benchmark using point-in-time data, costs, cashflows, and
documented limitations. Separate process quality from outcome quality:

```text
good decision + bad outcome != bad decision
bad decision + favorable outcome != good decision
```

### O0-04: Learning closure

Produce a LessonCandidate with thesis supported/contradicted/inconclusive,
data/execution/timing/discipline error classification, and evidence refs. Human
promotion may alter EffectivePolicy. A later decision must record consumption
before metrics call the lesson behaviorally closed.

## 14. Deferred from the current implementation program

The following are not authorized by the current implementation program. Some
are later autonomy mechanisms or north-star capabilities, not permanent
non-goals:

- real broker adapters, funded accounts, credentials, transfers, or AUT5 real
  execution before its separate authorization program;
- multi-user authentication/RBAC or organization approval workflows;
- full budgeting, tax, accounting, retirement, or Monte Carlo engines;
- generalized Research Workspace before the concentration loop proves use;
- optimizer-led recommendations;
- React/Vue migration before API/read models and page states stabilize;
- microservices, Temporal, OPA, Cedar, OpenLineage, MLflow, or MCP server;
- Session, scheduler, resume, subagents, or multi-agent hierarchy before a
  closed loop and measured operational need;
- more receipt, authority, policy, or review object types without a named
  command consumer and user outcome.

## 15. PR contract

Every slice must declare:

- user or repository outcome;
- authoritative inputs and typed outputs;
- Human Principal, Capital Agent, Harness, and deterministic-engine owner;
- migration and rollback behavior;
- failure/partial/denial semantics;
- affected debt and acceptance contracts;
- behavioral, restart, clean-environment, and browser evidence as applicable;
- explicit non-goals;
- documentation statements allowed to change after the gate passes.

PRs may be split more finely than the slice IDs above. They may not combine
schema migration, product UI, Agent authority, and execution effects merely to
claim a vertical demo.

## 16. Program success measures

Repository:

- all Python test styles execute in the default merge gate;
- no illegal SCC/layer dependency;
- debt status reflects material known debt, not a fixed count;
- clean dependency profiles remain green;
- current documents have one authoritative status source.

Capital and decision correctness:

- no mixed-currency unified total without FX evidence;
- every current capital number has currency, valued-at, readiness, and refs;
- every active decision binds one immutable proposal version;
- revisions visibly supersede decisions;
- command-enforced readiness equals UI-displayed readiness.

Product:

- a user can complete one material decision review without understanding raw
  receipt paths;
- the user can distinguish fact, derived measurement, model draft, simulation,
  and human decision;
- review return, decision change, rule adoption, maintenance burden, retention,
  and willingness-to-pay are measured rather than inferred.

Agent:

- 15/15 strengthened behavioral contracts;
- real arguments and observations influence the next action;
- all terminal states survive restart and hydrate by work ID;
- the first task produces a review packet, not an authority transition.
- AUT3+ milestones measure mandate-contained objective completion, escalation
  precision, human intervention rate, recovery success, and boundary breaches.

Outcome:

- chosen, do-nothing, and benchmark outcomes are comparable at a declared
  horizon;
- process quality and outcome quality are separately reviewable;
- promoted lessons have later-consumer evidence before being called closed.

## 17. Review plan

Re-audit sequencing after each phase boundary, not after an arbitrary PR count.
The first review occurs after E0-01/E0-03 and E1-01, because those slices can
change the apparent quality of every later baseline. The second occurs after
D0-05/D1-02, before Scenario or Agent product integration. The third occurs
after the first user-complete Material Decision Review and before Paper Outcome
or any authority expansion.
