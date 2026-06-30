# Interface Reference

This reference lists the major current FinHarness interfaces, the external or
mature-wheel owner of heavy work, and the local boundary FinHarness keeps.

Use this as a lookup page. For system ownership, read
[System Map](../architecture/system-map.md). For layering, read
[Capital OS Layering](../architecture/capital-os-layering.md).

## Interface Table

| Interface | External / mature owner | Local FinHarness owner | Primary docs/tasks |
| --- | --- | --- | --- |
| PersonalCapitalImportInterface | Beancount / `bean-query`, user-generated FinHarness CSV | Read-only mirror into State Core, source refs, reconciliation-by-source | `task beancount:import`, `task personal-finance:import` |
| StateCoreInterface | SQLite / SQLModel | Queryable mirror, DecimalText money, receipt index, atomic writes | `statecore/`, [Receipt Reference](receipts.md) |
| CapitalMapInterface | Local deterministic views | Net worth, cash runway, concentration, liabilities, obligations, data gaps | `exposure.py`, `task brief:daily` |
| IPSInterface | User policy | Receipt-backed Investment Policy Statement, threshold mapping, compliance check | `ips.py`, `/ips/current`, `/ips/check` |
| ProposalInterface | Local governed commands | Proposal creation, decision scaffold revision, high-risk confirmation gate, receipts | `task decisions:scan`, `statecore/proposals.py` |
| ReviewInterface | Local governed commands + deterministic read models | Attestation, scaffold revision, annotation, archive/reopen, compare marks, annual review, proposal review queue triage | `/review/queue`, `task review:annual`, `review_read.py` |
| RiskRegisterInterface | Local deterministic read model | Derived risk register view over review queue signals; no risk acceptance, scoring, scenario generation, or writes | `/risk/register`, `risk_register.py` |
| ResearchEvidenceInterface | yfinance/mature data adapters where enabled | Historical/descriptive evidence, source grades, data gaps, no prediction | `research_evidence.py`, `task decisions:research-smoke` |
| AgentToolInterface | OpenAI Agents SDK, local Hermes bridge | Profile-selected Agent tools resolved through `AgentToolEntry`, profile-aware context projection, evidence provider registry, and the runtime pipeline; default profile is read-only baseline; review-draft profile can create append-only governed proposal drafts; review-note profile can create append-only `AgentReviewNoteDraft` artifacts on existing proposals; scaffold-candidate profile can create append-only `AgentScaffoldRevisionApplyCandidate` artifacts from risk register items for human-confirmed apply; stronger permissions graduate through explicit runtime contracts and governance carriers | `agent_context.py`, `agent_context_projection.py`, `agent_capabilities.py`, `agent_evidence.py`, `agent_tools.py`, `agent_runtime.py`, `proposal_queue_checks.py`, `review_read.py`, `task agent:describe`, `task agent:run` |
| CockpitInterface | FastAPI + static frontend | Read/review product surface, including exposure, IPS policy, proposals, review, no execution endpoints | `task api:serve` |
| SecurityScanInterface | pip-audit, gitleaks, Trivy, uv | Scanner aggregation, redaction, fail-closed missing/timeout result | `task security:audit`, `task security:scan` |
| EvidenceInterface | Possible future OpenLineage/MLflow/DVC/Sigstore adapter | Receipt schema, claim boundaries, non-claims, review hooks | [Receipt Reference](receipts.md), [Evidence Inventory](../architecture/evidence-inventory.md) |

## Common Interface Rules

- Mature wheels can compute or retrieve evidence; they do not grant authority.
- FinHarness records source, quality, lineage, receipt, and authority boundary.
- Every suggestion/proposal needs evidence, assumptions, limitations, non-claims,
  and `execution_allowed=false`.
- Human attestation is review evidence, not execution authorization.
- Archived live-trading code is not a current interface.
- Agent capability profiles are explicit product postures resolved through a
  runtime `AgentToolEntry` registry/factory, not permission bypasses; Agent tool
  metadata exposes capability, toolset, side-effect, availability, evidence
  provider ids, profile-aware context projection, and authority-boundary claims.
  The Agent runtime pipeline resolves visible/hidden/unavailable tools and
  normalizes dispatch results/errors plus evidence envelopes without creating
  approval, recommendations, or execution authorization by implication. New
  Agent permissions should be opened through explicit profiles, tool entries,
  context projection policies, evidence providers, review/approval contracts,
  and tests rather than by broad prompt language. Agent-created proposal drafts
  are review objects.
- Agent-created proposal drafts expose review provenance (`created_by=agent`,
  active profile, context/source refs, receipt ref, and human-review state) in
  proposal review responses.
- Agent-created review notes are typed append-only review artifacts on proposal
  timelines. They may surface findings, risks, open questions, evidence refs,
  source refs, context-pack refs, and data gaps; they are not approval,
  attestation, scaffold revision, rejection, recommendation, or execution
  authorization.
- Agent-created proposal drafts expose read-only queue checks (`pass`/`warn`/`block`,
  block codes, blocked transition scope, recovery hints, source refs, receipt
  refs) without granting approval, attestation, or execution authority. A
  `human_review_required` block means the draft must move through human review;
  it is not a reason to keep the draft out of the review queue.
- Proposal review tasks and evidence requests are read-only projections derived
  from proposals, attestations, review events, and queue checks. They are not a
  separate mutable Kanban board and do not create approval or execution authority.
- Review queue triage is a deterministic read model derived from proposals,
  attestations, archived state, review events, AgentReviewNoteDraft payloads,
  receipt index rows, and proposal queue checks. It prioritizes human review
  work and next actions; it is not approval, rejection, attestation, execution
  authorization, or investment advice.
- Risk register v0 is a deterministic read model derived from review queue
  signals. It turns data gaps, stale context, duplicate candidates, policy
  mismatches, counter-evidence needs, Agent-reported risks, and open questions
  into comparable risk objects; it is not a persistent risk table, risk
  acceptance workflow, scoring model, scenario generator, approval, execution
  authorization, or investment advice.
- Agent-created scaffold revision apply candidates are typed append-only review
  artifacts derived from existing risk register items. They carry
  `scaffold_patch`, `proposed_scaffold`, `changed_fields`, preflight/rollback
  context, risk coverage, and human confirmation requirements, but they do not
  mutate proposals. Their preflight, risk coverage, and rollback fields are
  Agent-supplied candidate payload until a later system preflight recomputes
  them. Applying the patch requires a later human-confirmed flow.
- There is no current Agent approval, live order, fund transfer, broker write API,
  or receipt deletion/overwrite interface. Those are future capability candidates
  only if they receive purpose-built runtime profiles, command paths, receipts,
  review/approval surfaces, and failure modes.
- Any new production dependency still needs explicit user approval before being
  added.

## Adapter Acceptance Checklist

Before a new adapter is considered complete:

- The existing caller-facing interface remains stable or has a migration note.
- Tests characterize the old behavior where applicable.
- Tests prove the adapter path is exercised.
- Receipts or summaries disclose backend/tool name and version when relevant.
- The adapter output includes a clear non-authority boundary.
- No current docs mention task names that are absent from `Taskfile.yml`.
