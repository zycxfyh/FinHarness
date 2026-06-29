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
| AgentToolInterface | OpenAI Agents SDK, local Hermes bridge | Profile-selected Agent tools resolved through a runtime registry/factory; default profile is read-only; review-draft profile can create append-only governed proposal drafts whose Agent provenance and queue checks are exposed on the review surface, with no approval or execution authority | `agent_context.py`, `agent_capabilities.py`, `agent_tools.py`, `proposal_queue_checks.py`, `task agent:describe`, `task agent:run` |
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
  runtime tool registry/factory, not permission bypasses; Agent-created proposal
  drafts are review objects, not approvals,
  recommendations, or execution authorization.
- Agent-created proposal drafts expose review provenance (`created_by=agent`,
  active profile, context/source refs, receipt ref, and human-review state) in
  proposal review responses.
- Agent-created proposal drafts expose read-only queue checks (`pass`/`warn`/`block`,
  block codes, blocked transition scope, recovery hints, source refs, receipt
  refs) without granting approval, attestation, or execution authority. A
  `human_review_required` block means the draft must move through human review;
  it is not a reason to keep the draft out of the review queue.
- There is no Agent approval, live order, fund transfer, broker write API, or
  receipt deletion/overwrite interface.
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
