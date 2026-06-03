# Review: Promptfoo Red-Team Boundary Export

Date: 2026-06-03
Status: closed-draft
Workflow: langgraph_engineering_delivery_v1
Receipt: /root/projects/finharness/data/receipts/engineering-delivery/20260603T023903Z-promptfoo-red-team-boundary-export.json

## Scope

Export deterministic red-team payload corpus into promptfoo boundary eval and include it in CI local-checks.

## Evidence

Changed files:

- src/finharness/hardening.py
- scripts/export_redteam_promptfoo.py
- evals/promptfoo/redteam-boundary.yaml
- Taskfile.yml
- .github/workflows/security.yml
- tests/test_hardening_gate.py
- docs/security/mvp-hardening-gate.md

Docs updated:

- docs/security/mvp-hardening-gate.md

Checks:

- export_redteam_promptfoo: passed
- test_hardening_gate: passed
- ruff-focused: passed
- task eval:redteam-boundary: passed
- task hardening:gate: passed
- task check: passed

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
