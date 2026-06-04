# OpenSSF Scorecard Roadmap

Latest inspected Scorecard run: `26885441201` on commit `b3fbddf`.

## Classification

| Check | Current posture | Class | RC0.1 action |
| --- | --- | --- | --- |
| Branch-Protection | Scorecard finding open | GitHub setting, workflow decision | Documented dry-run ruleset; wait for user confirmation before enforcing |
| Code-Review | No approved changesets observed | GitHub workflow policy | Enable via branch protection after solo workflow decision |
| License | No license file detected | User/legal decision | Added license decision memo; do not create LICENSE yet |
| Fuzzing | No recognized fuzzer integration | Future quality investment | Added lightweight property baseline; defer heavy fuzzer |
| CII-Best-Practices | No badge | External process | Defer until RC process stabilizes |
| Maintained | Repo created within last 90 days | Time/external | Not directly fixable |
| Pinned-Dependencies | Prior findings fixed | Code/CI | Keep GitHub Actions SHA-pinned |
| Security-Policy | Detected with private report link | Code/docs fixed | Keep `.github/SECURITY.md` current |
| Token-Permissions | Explicit workflow permissions present | Code/CI | Continue least-privilege review |
| Dangerous-Workflow | No current finding observed | Code/CI | Continue review in security workflow |

## Before / After

Before RC0.1 hardening:

- Security policy was missing or lacked a linked private reporting path.
- GitHub Actions were version-pinned but not fully SHA-pinned.
- There was no unified governance dashboard.
- Property-style governance invariants were not separated.

After this pass:

- Security policy is detected and has a private report link.
- GitHub Actions are pinned to full commit SHAs.
- Security workflow uses Node 24-ready setup actions where available
  (`astral-sh/setup-uv` v8.2.0 and `go-task/setup-task` v2.1.0).
- Governance dashboard task and receipt exist.
- Property-style boundary tests exist and are part of `task check`.
- `aiohttp` lockfile is upgraded to the patched `3.14.0` version.

## Remaining Decisions

- Confirm branch protection/ruleset enforcement level.
- Confirm license posture.
- Decide whether to add PR-only review workflow for `main`.
- Decide if a real fuzzing service is worth the operational weight for RC0.1.
