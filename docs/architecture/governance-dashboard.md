# Governance Dashboard

The governance dashboard is the RC0.1 evidence index for FinHarness. It does
not replace the release preflight graph and never grants execution authority.

## Position

```text
repo_intelligence_graph -> quality_governance_graph -> release_preflight_graph
                                      \                     /
                                       \                   /
                                        governance_dashboard
```

The dashboard consumes summaries and receipts from existing governance flows:

- Repo intelligence: inventory, changed surface, required checks, security
  surface, and Mermaid code map.
- Quality governance: standard checks, hardening gate, red-team boundary,
  performance baseline, and release decision.
- Hardening gate: dependency check, Gitleaks, Trivy, local red-team checks, and
  red-team tool readiness.
- Release preflight: release-ready decision, missing supply-chain items, human
  review requirement, and execution boundary.

## Outputs

```text
data/receipts/governance-dashboard/latest.json
docs/operations/governance-dashboard-latest.md
```

The dashboard receipt intentionally repeats `execution_allowed: false`. A green
dashboard means the engineering release evidence is consolidated; it does not
mean live trading, autonomous execution, or legal release approval is granted.

## Non-Circular Dependency

`release_preflight_graph` may be referenced by the dashboard, but release
preflight must not import or depend on the dashboard. This keeps the release
gate authoritative and avoids making a report generator part of the release
decision itself.

## Task Entry

```bash
task governance:dashboard
```

Use `uv run python scripts/run_governance_dashboard.py --run-checks` only when a
fresh authoritative preflight run is desired. The default task is lightweight
and aggregates current local receipts.
