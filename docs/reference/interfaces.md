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
| ProposalInterface | Local governed commands | Proposal creation, decision scaffold, high-risk confirmation gate, receipts | `task decisions:scan`, `statecore/proposals.py` |
| ReviewInterface | Local governed commands | Attestation, annotation, archive/reopen, compare marks, annual review | `task review:annual`, `review_read.py` |
| ResearchEvidenceInterface | yfinance/mature data adapters where enabled | Historical/descriptive evidence, source grades, data gaps, no prediction | `research_evidence.py`, `task decisions:research-smoke` |
| AgentToolInterface | OpenAI Agents SDK, local Hermes bridge | Tool-bound explanation/eval surfaces, no source-of-truth writes | `task agent:describe`, `task agent:run` |
| CockpitInterface | FastAPI + static frontend | Read/review product surface, no execution endpoints | `task api:serve` |
| SecurityScanInterface | pip-audit, gitleaks, Trivy, uv | Scanner aggregation, redaction, fail-closed missing/timeout result | `task security:audit`, `task security:scan` |
| EvidenceInterface | Possible future OpenLineage/MLflow/DVC/Sigstore adapter | Receipt schema, claim boundaries, non-claims, review hooks | [Receipt Reference](receipts.md), [Evidence Inventory](../architecture/evidence-inventory.md) |

## Common Interface Rules

- Mature wheels can compute or retrieve evidence; they do not grant authority.
- FinHarness records source, quality, lineage, receipt, and authority boundary.
- Every suggestion/proposal needs evidence, assumptions, limitations, non-claims,
  and `execution_allowed=false`.
- Human attestation is review evidence, not execution authorization.
- Archived live-trading code is not a current interface.
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
