# Quality Governance Operating Model

FinHarness quality governance is organized by feedback speed and risk.

## Daily Local Work

```text
task repo:intelligence
task check
```

Use this loop while changing ordinary source, docs, and tests.

## Risk Boundary Work

Run the stronger local gate when touching execution, risk, provider, security,
or asset-id boundaries.

```text
task hardening:gate
task eval:redteam-boundary
task quality:governance-checks
```

## Release Work

Before a major push or release:

```text
task release:preflight
```

Then inspect CI for:

```text
security / Local verification
security / CodeQL
security / Gitleaks
security / Trivy filesystem scan
scorecard / OpenSSF Scorecard
```

## P1-P10 Roadmap

| Phase | Status Target | Evidence |
|---|---|---|
| P1 Repo Intelligence | Local graph, Mermaid, receipt | `task repo:intelligence` |
| P2 Quality Governance | Check aggregation and quality receipt | `task quality:governance-checks` |
| P3 Supply Chain | CodeQL, Dependabot, Scorecard | GitHub workflows |
| P4 Release Preflight | Quality plus supply-chain release gate | `task release:preflight` |
| P5 Asset Integration | L5-L10 cite StrategySpec/MathMethodSpec/ReferenceCard IDs | `tests/test_research_asset_handoff.py` |
| P6 Blast Radius | Changed files map to focused checks | `tests/test_repo_intelligence.py` |
| P7 Architecture Visualization | Generated Mermaid repo map | `docs/architecture/generated/repo-intelligence.md` |
| P8 Human Review Gates | Execution/security changes require review | quality decision `human_review` |
| P9 Performance Baseline | Check duration and slow-node tracking | quality receipt `performance_baseline` |
| P10 Operating Model | Agent-readable docs and tasks | this document |

## Occam Boundary

Do not add heavyweight red-team or visualization dependencies to the default
local path unless they prove a gap that existing gates cannot cover.
