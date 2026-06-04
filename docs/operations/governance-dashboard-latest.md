# Governance Dashboard

Generated at: `2026-06-04T08:43:55Z`

## RC0.1 Posture

- Release ready: `true`
- Release blocked: `false`
- Requires human review: `false`
- Execution allowed: `false`
- Dashboard status: `ready`

## Repo Intelligence

- Files: `332`
- Total lines: `68356`
- Changed files: `9`

## Required Checks

- `task check`
- `task hardening:gate`

## Quality Governance

- Decision: `passed`
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
