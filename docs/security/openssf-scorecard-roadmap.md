# OpenSSF Scorecard Roadmap

Latest inspected Scorecard run: `26942343943` on commit `2d5bead`.

## Classification

| Check | Current posture | Class | RC0.1 action |
| --- | --- | --- | --- |
| Branch-Protection | Main medium protection with admin bypass; release strict protection | GitHub setting, workflow decision | Keep current solo-maintainer posture or move main to PR-only later |
| Code-Review | CODEOWNERS exists, but rulesets do not require code-owner review | GitHub workflow policy | Decide when to enforce code-owner review |
| License | Apache-2.0 selected | Done | Added top-level `LICENSE` and package metadata |
| Fuzzing | No recognized OSS-Fuzz/ClusterFuzzLite integration | RC0.2 local baseline, future quality investment | Added `task security:fuzz`, deterministic corpus, CI fuzz workflow; still not a formal fuzzing service |
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
- Workflow write permissions are scoped at the job level instead of granted at
  the workflow top level.
- Governance dashboard task and receipt exist.
- Property-style boundary tests exist and are part of `task check`.
- `aiohttp` lockfile is upgraded to the patched `3.14.0` version.
- Apache-2.0 license and GitHub rulesets are active.
- Threat model and SSDF control map are established for RC0.2 maturity work.
- Local SBOM and provenance baseline task exists as `task security:sbom`.
- Deterministic fuzz baseline exists as `task security:fuzz` and a CI workflow,
  but Scorecard still does not recognize it as formal fuzzing.
- Trading validation report v1 exists and rejects live/performance overclaims.
- Security response runbook and CODEOWNERS exist as RC0.2 governance evidence.

## Remaining Decisions

- Keep Apache-2.0 unless a future explicit legal decision supersedes it.
- Keep `main` medium protection and `release/*` strict protection aligned with
  the repository governance document.
- Decide whether to move `main` from medium protection to PR-only review
  workflow later.
- Decide whether to require code-owner review on `release/*` and later `main`.
- Decide if a real fuzzing service is worth the operational weight after RC0.2.
- Upgrade local SBOM/provenance baseline to formal SBOM/SLSA attestation once
  the release artifact shape is chosen.
