# Governance Dashboard

Generated at: `2026-06-04T09:05:27Z`

## RC0.1 Posture

- Release ready: `true`
- Release blocked: `false`
- Requires human review: `true`
- Execution allowed: `false`
- Dashboard status: `human_review`

## Repo Intelligence

- Files: `339`
- Total lines: `68938`
- Changed files: `17`

## Required Checks

- `task check`
- `task hardening:gate`
- `task security:scan`

## Quality Governance

- Decision: `human_review`
- Release blocked: `false`
- Performance status: `within_budget`

## Hardening And Red Team

- Hardening gate: `passed`
- Red-team boundary: `passed`

## Mermaid

```mermaid
flowchart TD
  repo["repo_intelligence"]
  quality["quality_governance"]
  hardening["hardening_gate"]
  redteam["redteam_boundary"]
  preflight["release_preflight"]
  dashboard["governance_dashboard"]
  human["human_review_gate"]
  repo --> quality
  quality --> preflight
  hardening --> dashboard
  redteam --> dashboard
  preflight --> dashboard
  dashboard --> human
```
