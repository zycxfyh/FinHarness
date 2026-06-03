# Review: Promptfoo Redteam Dry-Run Contract

Date: 2026-06-03
Status: closed-draft
Workflow: langgraph_engineering_delivery_v1
Receipt: /root/projects/finharness/data/receipts/engineering-delivery/20260603T025400Z-promptfoo-redteam-dry-run-contract.json

## Scope

Add promptfoo redteam dry-run contract, validation script, task, CI hook, tests, and hardening gate integration.

## Evidence

Changed files:

- evals/promptfoo/redteam-dryrun.yaml
- scripts/validate_promptfoo_redteam_dryrun.py
- scripts/run_hardening_gate.py
- Taskfile.yml
- .github/workflows/security.yml
- tests/test_hardening_gate.py
- docs/security/mvp-hardening-gate.md
- data/redteam/exports/promptfoo-redteam-dryrun-validation.json

Docs updated:

- docs/security/mvp-hardening-gate.md

Checks:

- task redteam:dryrun-config-check: passed
- test_hardening_gate: passed
- ruff-focused: passed
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
