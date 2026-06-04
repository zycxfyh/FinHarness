# Repository Governance

Generated for RC0.1 hardening on 2026-06-04.

## Current GitHub Posture

- Repository: `zycxfyh/FinHarness`
- Visibility: `PUBLIC`
- Default branch: `main`
- Viewer permission during audit: `ADMIN`
- Security policy: enabled
- Security policy URL: `https://github.com/zycxfyh/FinHarness/security/policy`
- License: Apache-2.0
- Branch protection for `main`: repository ruleset planned/applied via GitHub
  rulesets
- Repository rulesets: `finharness-main-medium-protection` and
  `finharness-release-strict-protection`
- Main ruleset ID: `17250742`
- Release ruleset ID: `17250754`
- Dependabot config: present
- Code scanning workflow: present
- Scorecard workflow: present

## Current Alerts

- Dependabot: no open alerts after the `aiohttp 3.14.0` lockfile update.
- Code scanning: Token-Permissions is fixed. Branch-Protection and License are
  expected to improve after ruleset/license indexing and a fresh scorecard run.

## RC0.1 Ruleset Policy

The selected policy is:

- `main`: medium protection with admin bypass for solo maintainer velocity.
- `release/*`: strict protection with pull request, status checks, stale review
  dismissal, last-push approval, and review-thread resolution. New release
  branch creation is allowed so a release branch can be cut from a checked
  commit before stricter update rules apply.

Main ruleset:

```json
{
  "name": "finharness-main-medium-protection",
  "target": "branch",
  "enforcement": "active",
  "bypass_actors": [
    {"actor_id": 5, "actor_type": "RepositoryRole", "bypass_mode": "always"}
  ],
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
        "do_not_enforce_on_create": false,
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

Release ruleset:

```json
{
  "name": "finharness-release-strict-protection",
  "target": "branch",
  "enforcement": "active",
  "conditions": {
    "ref_name": {
      "include": ["refs/heads/release/*"],
      "exclude": []
    }
  },
  "rules": [
    {"type": "deletion"},
    {"type": "non_fast_forward"},
    {
      "type": "pull_request",
      "parameters": {
        "required_approving_review_count": 1,
        "dismiss_stale_reviews_on_push": true,
        "require_code_owner_review": false,
        "require_last_push_approval": true,
        "required_review_thread_resolution": true,
        "allowed_merge_methods": ["merge", "squash", "rebase"]
      }
    },
    {
      "type": "required_status_checks",
      "parameters": {
        "strict_required_status_checks_policy": true,
        "do_not_enforce_on_create": true,
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

## FinHarness Boundary

Repository governance is an engineering release control. It does not authorize
live trading, live order routing, or autonomous execution. Provider write paths
remain gated by existing environment and explicit flag checks.
