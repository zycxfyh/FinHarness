# FinHarness SSDF Control Map

Date: 2026-06-04
Status: RC0.2 maturity baseline

This document maps FinHarness governance evidence to NIST SP 800-218 Secure
Software Development Framework (SSDF) practice families. It is not a compliance
certification. It is a control map for future release audits.

Reference: https://csrc.nist.gov/pubs/sp/800/218/final

## Control Summary

| SSDF family | FinHarness current evidence | Status | Gap |
| --- | --- | --- | --- |
| PO: Prepare the Organization | Apache-2.0 license, repository rulesets, CODEOWNERS, security policy, governance docs | partial | Main is not PR-only and current rulesets do not require code-owner review |
| PS: Protect the Software | Gitleaks, Trivy, CodeQL, Dependabot, pinned actions, branch rulesets, local SBOM/provenance baseline | partial | No formal CycloneDX/SPDX SBOM or signed SLSA provenance yet |
| PW: Produce Well-Secured Software | Typed layer contracts, tests, hardening gate, red-team corpus, deterministic fuzz baseline, release preflight | partial | No formal fuzzing service recognized by Scorecard |
| RV: Respond to Vulnerabilities | `.github/SECURITY.md`, security response runbook, Dependabot, scanner receipts | partial | No recurring vulnerability review cadence or live-provider dual-control process |

## PO: Prepare the Organization

| Practice intent | Current evidence | Residual work |
| --- | --- | --- |
| Define security requirements | `docs/security/mvp-hardening-gate.md`, `docs/security/finharness-threat-model.md` | Turn high-priority threats into tracked tasks |
| Define roles and responsibilities | `.github/CODEOWNERS`, `docs/operations/repository-governance.md`, GitHub rulesets | Decide whether to require code-owner review in rulesets |
| Establish secure development workflow | `Taskfile.yml`, `task release:preflight`, `task governance:dashboard` | Decide if/when `main` becomes PR-only |
| Define acceptable release evidence | `docs/architecture/release-preflight-graph.md`, `docs/operations/governance-dashboard-latest.md` | Add signed release receipt or checksum policy |

## PS: Protect the Software

| Practice intent | Current evidence | Residual work |
| --- | --- | --- |
| Protect code repository | Apache-2.0 `LICENSE`, `.github/CODEOWNERS`, active main and release rulesets | Decide if/when `main` becomes PR-only and code-owner review is enforced |
| Protect secrets | `.gitleaks.toml`, `src/finharness/hardening.py`, `task hardening:gate` | Add rotation checklist and local secret inventory policy |
| Protect build/release integrity | SHA-pinned GitHub Actions, `uv.lock`, `pnpm-lock.yaml`, Dependabot, `task security:sbom` | Upgrade local SBOM to formal CycloneDX/SPDX and signed SLSA provenance after artifact shape is chosen |
| Protect generated evidence | Receipts under `data/receipts/`, release preflight receipt | Add receipt schema/checksum verification |

## PW: Produce Well-Secured Software

| Practice intent | Current evidence | Residual work |
| --- | --- | --- |
| Design with trust boundaries | `docs/security/finharness-threat-model.md`, ten-layer map | Keep threat model updated when provider/live surfaces change |
| Review and test security properties | `tests/test_hardening_gate.py`, `tests/test_property_baseline.py`, `tests/test_security_fuzz.py`, `task check`, `task security:fuzz` | Decide whether to add formal fuzzing recognized by Scorecard |
| Verify dependencies and configs | Trivy, CodeQL, Dependabot, Scorecard workflow | Add periodic dependency review receipt |
| Prevent unsafe execution semantics | `src/finharness/risk_gate.py`, `src/finharness/execution.py`, `src/finharness/okx_cli.py` | Add dual-control approval before any live-write expansion |

## RV: Respond to Vulnerabilities

| Practice intent | Current evidence | Residual work |
| --- | --- | --- |
| Receive vulnerability reports | `.github/SECURITY.md` private reporting link, `docs/security/security-response-runbook.md` | Add recurring security review cadence |
| Identify vulnerable dependencies | Dependabot and Trivy | Add recurring review receipt for ignored/deferred alerts |
| Analyze and remediate findings | `task hardening:gate`, redacted scanner receipts | Add post-remediation lesson template for security incidents |
| Disclose or document residual risk | Scorecard roadmap and governance docs | Add release notes section for security posture changes |

## RC0.2 Recommended Work Items

1. Decide whether to require code-owner review for `release/*` and later
   `main`.
2. Upgrade `task security:sbom` from local baseline to a mature generator if
   packaging/release artifacts become public.
3. Add signed provenance/SLSA attestation for future packaged releases.
4. Add recurring security review receipts for open Scorecard and vulnerability
   posture.
5. Evaluate whether RC0.3 should add Hypothesis, Atheris, OSS-Fuzz, or
   ClusterFuzzLite beyond the current deterministic governance fuzz baseline.

## Non-Claims

- This map does not certify NIST SSDF compliance.
- This map does not authorize live trading.
- This map does not claim broker, exchange, custody, settlement, tax, or
  performance-reporting correctness.
- This map does not replace `task release:preflight` or GitHub branch rulesets.
