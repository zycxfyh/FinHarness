# Review: RC0.2 security maturity baseline: threat model and SSDF control map

Date: 2026-06-04
Status: closed-draft
Workflow: langgraph_engineering_delivery_v1
Receipt: /root/projects/finharness/data/receipts/engineering-delivery/20260604T083343Z-rc0-2-security-maturity-baseline-threat-model-and-ssdf-control-map.json

## Scope

Add repository-grounded threat model, SSDF control map, and documentation drift tests without changing trading authority.

## Evidence

Changed files:

- docs/security/finharness-threat-model.md
- docs/security/ssdf-control-map.md
- tests/test_security_maturity_docs.py
- docs/security/openssf-scorecard-roadmap.md
- docs/architecture/generated/repo-intelligence.md
- docs/operations/governance-dashboard-latest.md
- data/receipts/governance-dashboard/latest.json

Docs updated:

- docs/security/finharness-threat-model.md
- docs/security/ssdf-control-map.md
- docs/security/openssf-scorecard-roadmap.md

Checks:

- uv run ruff check tests/test_security_maturity_docs.py: passed
- uv run python -m unittest tests.test_security_maturity_docs: passed
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
