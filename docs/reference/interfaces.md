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
| ReviewInterface | Local governed commands | Attestation, scaffold revision, annotation, archive/reopen, compare marks, annual review | `task review:annual`, `review_read.py` |
| ResearchEvidenceInterface | yfinance/mature data adapters where enabled | Historical/descriptive evidence, source grades, data gaps, no prediction | `research_evidence.py`, `task decisions:research-smoke` |
| AgentToolInterface | OpenAI Agents SDK, local Hermes bridge | Profile-selected Agent tools resolved through `AgentToolEntry`, profile-aware context projection, evidence provider registry, and the runtime pipeline; default profile is read-only baseline; review-draft profile can create append-only governed proposal drafts whose Agent provenance, queue checks, evidence envelope, context budget, and review-task lifecycle projection are exposed on the review surface, with stronger permissions graduating through explicit runtime contracts | `agent_context.py`, `agent_context_projection.py`, `agent_capabilities.py`, `agent_evidence.py`, `agent_tools.py`, `agent_runtime.py`, `proposal_queue_checks.py`, `task agent:describe`, `task agent:run` |
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
- Agent-created proposal drafts expose read-only queue checks (`pass`/`warn`/`block`,
  block codes, blocked transition scope, recovery hints, source refs, receipt
  refs) without granting approval, attestation, or execution authority. A
  `human_review_required` block means the draft must move through human review;
  it is not a reason to keep the draft out of the review queue.
- Proposal review tasks and evidence requests are read-only projections derived
  from proposals, attestations, review events, and queue checks. They are not a
  separate mutable Kanban board and do not create approval or execution authority.
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
