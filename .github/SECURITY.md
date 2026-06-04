# Security Policy

## Supported Scope

Security reports are accepted for the current `main` branch of FinHarness.

FinHarness is a research and governance harness. It does not authorize
autonomous live trading, and all live or mutating provider paths must remain
behind explicit gates.

## Reporting A Vulnerability

Use GitHub private vulnerability reporting when available:
https://github.com/zycxfyh/FinHarness/security/advisories/new

Do not publish exploit details, credentials, tokens, private keys, or live
account data in public issues, pull requests, logs, screenshots, or receipts.

If a private channel is not available, open a public issue with only a minimal
non-sensitive summary and ask for a private follow-up path.

## What To Include

- Affected file, workflow, command, or provider boundary.
- Reproduction steps using fake, paper, or synthetic data.
- Expected impact and whether live read/write permissions could be affected.
- Whether the issue involves secrets, prompt injection, dependency compromise,
  order execution, or receipt leakage.

## Response Model

FinHarness security work should preserve these boundaries:

- No raw secret output in receipts or logs.
- No autonomous live trading authorization.
- Paper/fake-first execution for tests and demos.
- Explicit human review for workflow, security, provider, risk, and execution
  changes.
- Local checks, hardening gates, red-team boundary evals, and CI evidence before
  release claims.

For triage, severity, rotation, release-blocking, and closure evidence, use:

```text
docs/security/security-response-runbook.md
```
