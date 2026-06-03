# Quality Governance Graph

`quality_governance_graph` turns existing checks into an auditable quality
decision. The underlying tools remain authoritative.

```text
source
  -> repo_intelligence
  -> checks
  -> security_gate
  -> redteam_gate
  -> performance_baseline
  -> decision
  -> receipt
```

## Authoritative Checks

```text
task check
task hardening:gate
task eval:redteam-boundary
```

## Performance Baseline

The graph records `duration_seconds`, `budget_seconds`, slow checks, and total
check duration in the receipt. This is an observation gate in the MVP: slow
checks are visible, but they do not block release by themselves.

## Decisions

```text
passed:
  all required checks passed and no high-risk human review surface was detected

human_review:
  required checks passed, but changed files touch execution/security boundaries

blocked:
  at least one required check failed or is missing
```

## Boundary

The graph is a governance surface. It never grants autonomous live trading
permission and always records `execution_allowed=false`.
