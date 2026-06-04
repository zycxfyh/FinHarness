# Review: RC0.2 SBOM and provenance baseline

Date: 2026-06-04
Status: closed-draft
Workflow: langgraph_engineering_delivery_v1
Receipt: /root/projects/finharness/data/receipts/engineering-delivery/20260604T084411Z-rc0-2-sbom-and-provenance-baseline.json

## Scope

Add local SBOM and provenance baseline generation without new dependencies or formal attestation claims.

## Evidence

Changed files:

- scripts/generate_security_sbom.py
- docs/security/sbom-and-provenance.md
- tests/test_security_sbom.py
- Taskfile.yml
- package.json
- docs/security/ssdf-control-map.md
- docs/security/openssf-scorecard-roadmap.md
- data/security/sbom/finharness-sbom.json
- data/security/provenance/finharness-provenance-baseline.json
- docs/architecture/generated/repo-intelligence.md
- docs/operations/governance-dashboard-latest.md
- data/receipts/governance-dashboard/latest.json

Docs updated:

- docs/security/sbom-and-provenance.md
- docs/security/ssdf-control-map.md
- docs/security/openssf-scorecard-roadmap.md

Checks:

- uv run ruff check scripts/generate_security_sbom.py tests/test_security_sbom.py: passed
- uv run python -m unittest tests.test_security_sbom: passed
- task security:sbom: passed
- task repo:intelligence: passed
- task check: passed
- task hardening:gate: passed
- task release:preflight: passed
- task governance:dashboard: passed

## Gate Result

```text
status: pass
quality_ok: True
```

## Remaining Debt

- no scoped debt

## Follow-Up

Update module docs, tests, or delivery rules if this review exposes a repeated
process failure.
