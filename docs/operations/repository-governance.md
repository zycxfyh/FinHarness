# Repository Governance

Generated for RC0.1 hardening on 2026-06-04.

## Current GitHub Posture

- Repository: `zycxfyh/FinHarness`
- Visibility: `PUBLIC`
- Default branch: `main`
- Viewer permission during audit: `ADMIN`
- Security policy: enabled
- Security policy URL: `https://github.com/zycxfyh/FinHarness/security/policy`
- License: not configured
- Branch protection for `main`: not enabled
- Repository rulesets: none configured
- Dependabot config: present
- Code scanning workflow: present
- Scorecard workflow: present

## Current Alerts

- Dependabot: two open `aiohttp < 3.14.0` medium alerts were observed during the
  audit. The local lockfile has been upgraded to `aiohttp 3.14.0`; GitHub alert
  closure is expected after the updated lockfile lands on `main` and Dependabot
  re-evaluates it.
- Code scanning: Scorecard still reports open Branch-Protection and License
  findings. Pinned GitHub Action findings are fixed.

## RC0.1 Ruleset Dry Run

Do not apply this automatically while solo development still relies on direct
pushes to `main`. Apply after the user confirms the desired merge workflow.

Recommended minimum ruleset:

```json
{
  "name": "rc0.1-main-protection",
  "target": "branch",
  "enforcement": "active",
  "conditions": {
    "ref_name": {
      "include": ["~DEFAULT_BRANCH"],
      "exclude": []
    }
  },
  "rules": [
    {"type": "deletion"},
    {"type": "non_fast_forward"},
    {
      "type": "required_status_checks",
      "parameters": {
        "strict_required_status_checks_policy": true,
        "required_status_checks": [
          {"context": "Local verification"},
          {"context": "Gitleaks"},
          {"context": "Trivy filesystem scan"},
          {"context": "CodeQL"}
        ]
      }
    }
  ]
}
```

Optional next tier:

- Require pull request before merging.
- Require at least one approving review.
- Dismiss stale approvals after new commits.
- Require Code Owners review after CODEOWNERS exists.

These optional rules improve Scorecard Code-Review and Branch-Protection
posture, but they will change the user's solo development flow. They should be
applied only after the workflow is accepted.

## FinHarness Boundary

Repository governance is an engineering release control. It does not authorize
live trading, live order routing, or autonomous execution. Provider write paths
remain gated by existing environment and explicit flag checks.
