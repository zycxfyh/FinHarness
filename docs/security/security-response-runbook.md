# Security Response Runbook

Date: 2026-06-04
Status: RC0.2 operational baseline

This runbook turns security reports into bounded FinHarness response actions.
It is not a legal, regulatory, broker, exchange, or incident-response
certification.

## Scope

Use this runbook for:

- suspected secret, token, key, credential, or account-data exposure
- live-read or live-write provider boundary failures
- prompt or research-asset injection that could affect execution authority
- dependency, workflow, action, or release-gate compromise
- receipt, report, dashboard, or log leakage
- false release, performance, or live-trading readiness claims

Do not use public issues, public pull requests, public logs, screenshots, or
receipts to share raw secrets, exploit payloads that contain credentials, or
live account data.

## Severity

| Severity | Trigger | Target response |
| --- | --- | --- |
| Critical | Raw secret exposure, live mutating provider action, CI compromise with write authority, or credible path to unauthorized live order/account mutation | Triage immediately, disable or rotate affected capability before normal work resumes |
| High | Live boundary bypass without confirmed mutation, high-impact dependency or workflow compromise, release-preflight bypass, or asset injection that could imply execution authority | Triage same day and block release until fixed or explicitly deferred |
| Medium | Scanner finding, stale vulnerable dependency, receipt evidence weakness, provider freshness failure, or fuzz/property boundary regression without live impact | Triage within one working day |
| Low | Documentation gap, non-blocking Scorecard finding, ownership-map drift, or hardening improvement without active exploit path | Track in normal RC planning |

## Triage Flow

1. Preserve the report privately.
2. Classify the affected boundary: secret, provider, execution, workflow,
   dependency, research asset, receipt, or documentation claim.
3. Reproduce only with fake, paper, synthetic, or redacted data.
4. Run the smallest relevant local check.
5. If live or mutating provider access may be affected, stop expansion work and
   leave live-write gates disabled.
6. Patch only the affected boundary and its closest tests.
7. Run `task security:scan`, `task security:fuzz`, and `task check` before
   claiming closure.
8. Record an engineering delivery receipt and a short lesson when the fix lands.

## Rotation Checklist

If a credential or account boundary may be exposed:

- Do not print or commit the credential.
- Revoke or rotate the provider credential outside this repository.
- Remove exposed material from local logs or generated outputs before sharing
  any evidence.
- Run `task security:scan`.
- Inspect generated receipts for credential-like material without copying raw
  secret values into the response record.
- Record only redacted evidence and the affected path class.

## Release Blocking Rules

Block release claims when any of these are true:

- `task security:scan` fails.
- `task check` fails.
- A high or critical report is unresolved.
- A fix changes `.github/`, `Taskfile.yml`, `src/finharness/authorization.py`,
  `src/finharness/restricted_symbols.py`, `src/finharness/research_assets.py`,
  `src/finharness/data_entry.py`, `src/finharness/providers/`,
  `experiments/archive/live_trading_legacy/`, or security scanner
  configuration without human review.
- Any generated evidence claims `execution_allowed=true` for the MVP.

## Required Evidence

Security closure should include:

- affected files and boundary class
- severity and impact statement
- checks run and their results
- whether credentials, live provider state, or account data were involved
- whether live trading remained unauthorized
- engineering delivery receipt path
- any residual debt or deferred decision

## Non-Claims

- This runbook does not authorize autonomous live trading.
- This runbook does not certify incident-response compliance.
- This runbook does not replace provider-specific rotation procedures.
- This runbook does not replace legal, regulatory, broker, exchange, custody,
  tax, accounting, or performance-reporting review.
