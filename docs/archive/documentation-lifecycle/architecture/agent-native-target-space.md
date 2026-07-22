# Agent-Native Target Space

Status: v1 (2026-07-08)  
Phase: Wave 0 RFC — architecture definition only, no runtime changes.  

## Hard Principles

1. **Every PR must name the new agentic-space dimension it expands.**
   Each change answers: which structural capability does this add for agent cognition?
   And: is this just adding an object, or is it expanding the plane of agent reasoning?

2. **Every new primitive starts receipt-only / projection-only.**
   No StateCore table unless real usage pressure (≥2 integration points) proves it needs persistence.
   Graduation rule: receipt-only → projection/read model → command/read model → StateCore table only when usage pressure exists.

3. **Execution Kernel is frozen for this wave.**
   Do not generalize it into Capital Action Kernel until at least 2–3 non-trade capital actions exist.
   No changes to execution models, services, commands, broker adapter, or execution API routes.

---

## Problem

FinHarness has an Agent Tool Runtime (tool dispatch, context packs, proposal/review receipts,
local evaluators, lesson/rule-change lineage). But it does not have an Agent Cognition Runtime —
a structured plane where agent reasoning, evaluation, deliberation, feedback, and authority
transitions exist as first-class, receipt-backed, traceable artifacts.

Every new agentic concern currently risks being squeezed into the Object/StateCore layer
because no target space exists to guide placement.

## Current State

| Capability | Location | Status |
|---|---|---|
| Tool dispatch | `agent_runtime.py` | Single-shot dispatch with profile gate, structured result/error, evidence envelope, result budget |
| Context packs | `agent_context.py` | Bounded read-only packs (capital summary, IPS, proposals, timeline) |
| Proposal/review | `proposals.py` | Receipt-backed current-state + append-only receipt revision |
| Local evaluators | `scaffold_candidate_preflight.py`, `proposal_queue_checks.py` | Agent proposes, system recomputes |
| Learning lineage | `lesson_loop.py`, `rule_change_ledger.py` | Receipt → lesson → human-promoted rule change |

These are enough to support Wave 0 agent-native primitives. What's missing is the structured
plane that organizes them into a coherent cognition runtime.

## Target Space

The agentic target space has 8 dimensions. Each is a distinct structural concern — not a
file, not a table, not a route. PRs expand one or more dimensions.

### Goal Space

What the agent is trying to accomplish.

```
Goal classes (first wave):
  explain_state
  compare_options
  draft_review_note
  draft_proposal
  request_missing_evidence
  evaluate_candidate
  prepare_plan_draft
  summarize_learning
```

First wave: define goal classes only. No goal runtime. No goal scheduler. No goal state machine.

### Context Space

What the agent sees, plus the epistemological status of each piece.

First wave upgrade: from context pack = bounded DTO to context item = value + source + trust + verification + allowed uses.

Model: `ContextTrust` with source_type, trust_level, verification_status, allowed_uses, source_refs, receipt_refs.

### Action Space

What system actions the agent can take.

```
First-wave action classes:
  read_context
  call_tool
  write_review_artifact
  request_evaluation
  record_trace
  draft_plan
```

No execution action. No broker action. No transfer action.

### Evaluation Space

How the system judges an artifact.

Unified status: `pass / warn / block`.  
Unified finding: `code, severity, message, recovery_hint, blocked_transitions, source_refs, receipt_refs`.

Model: `EvaluationReport` with `EvaluationSubject` and `EvaluationFinding`.

First wave: common projection only. Adapt existing evaluators (scaffold preflight, queue checks).
Do not replace existing evaluator models.

### Authority Space

The structural chain from review/evaluation to action eligibility.

Model: `AuthorityTransitionRecord` — eligibility-only: `eligible / not_eligible / deferred`.

Requires: human attester, human reason, explicit confirmation, at least one EvaluationReport reference.

Not execution authority. Not approval engine. Not policy engine.

### Deliberation Space

How the agent expresses multi-option reasoning, plans, assumptions, and data gaps.

Models: `OptionSetReceipt`, `PlanDraftReceipt` — receipt-only, no StateCore tables.

An `OptionDraft` has: option_id, claim, assumptions, expected_outcomes, data_gaps, evaluation_refs.  
A `PlanDraftReceipt` has: plan_id, objective, steps, stop_conditions, required_evaluations.

No execution connection. No broker connection. No order generation.

### Feedback Space

How results feed back into future agent cognition.

Model: `PlanningPolicyView` — read model from active, traceable `RuleChange` records.

Active traceable rules enter `active_rules`. Untraceable changes surface as `stale_or_untraceable_rules`.
Agent context can expose this as a planning policy pack.

No planner runtime. No auto-rule application.

### Trace Space

The agent's action trail — the most critical dimension for Wave 0.

Model: `AgentRunReceipt` v0 — receipt-only trace of one agent run.

Contains: goal, profile, tool call summaries, artifact refs, evidence refs, data gaps, outcome, stop reason.

Not a DB table. Not a session object. Not automatically written on every dispatch.
It is the first trace primitive, not a new business object.

---

## PR DAG

```
Phase 0 (this doc)
  └─► Phase 1: AgentRunReceipt v0          (Trace Space)
       └─► Phase 2: ContextTrust v0         (Context Space)
            └─► Phase 3: EvaluationReport   (Evaluation Space)
                 └─► Phase 4: AuthorityTransitionRecord (Authority Space)
                      └─► Phase 5: PlanningPolicyView   (Feedback Space)
                           └─► Phase 6: OptionSet/PlanDraft (Deliberation Space)
                                └─► Phase 7: Inventory Sync (Architecture Memory)
```

Each phase is one PR. Each PR branches from main after the previous PR merges.
Each PR states its agentic-space dimension in the PR body.

## Non-goals (this wave)

- No Execution Kernel changes
- No broker changes
- No live authority
- No full workflow engine
- No AgentSession table
- No scheduler
- No UI
- No goal runtime / goal state machine
- No Capital Action Kernel
- No multi-agent session/task runtime
- No execution of plans

## Graduation Rule

```
receipt-only → projection/read model → command/read model
→ StateCore table only when ≥2 integration points depend on it
```

If a primitive only has one consumer after two phases, it stays receipt-only.
If it accumulates consumers and needs structured query, it graduates to projection.
If it needs transactional guarantees, it graduates to StateCore — but that is
an explicit decision, not a default.

---

## Wave 0 Definition of Done

After all 7 phases complete, FinHarness has Agent Cognition Runtime v0:

- Target space defined with 8 agentic dimensions
- Agent run trace recorded (receipt-only)
- Context carries trust metadata
- Evaluations have common projection shape
- Authority transition eligibility is recordable
- Learning lineage feeds planning policy view
- Deliberation has receipt-only option/plan artifacts
- Architecture inventory reflects the new plane

FinHarness does NOT have:

- Full autonomous agent runtime
- Capital Action Kernel
- Multi-agent session/task runtime
- Plan execution engine
