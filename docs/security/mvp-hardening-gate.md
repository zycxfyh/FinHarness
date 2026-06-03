# FinHarness MVP Hardening Gate

This gate is the first security and red-team release boundary for the
FinHarness ten-layer MVP. It does not make the system production-live-capable.
It proves a narrower claim: the local research MVP can be checked for core
engineering, dependency, scanner, and adversarial-boundary failures before a
release candidate is discussed.

## Scope

The gate covers:

- standard local checks through `task check`
- dependency compatibility through `uv pip check`
- secret-finding classification through redacted `gitleaks`
- CI-aligned gitleaks path policy through `.gitleaks.toml`
- dependency and misconfiguration scanning through `trivy`
- adversarial unit checks for asset-id and execution-boundary behavior
- deterministic local red-team payload corpus under `data/redteam/payloads/`
- GitHub security scaffolding through CodeQL, Gitleaks, Trivy, and Dependabot

The gate does not cover:

- autonomous live trading
- broker, exchange, custody, settlement, or tax/accounting correctness
- best-execution certification
- real LLM jailbreak coverage through PyRIT, garak, or promptfoo redteam
- production incident response or SOC operations

## Local Commands

```bash
task hardening:redteam
task security:scan
task hardening:gate
task eval:redteam-boundary
task redteam:tools-check
task redteam:dryrun-config-check
```

`task hardening:gate` writes:

```text
data/receipts/hardening/latest-hardening-gate.json
data/receipts/hardening/latest-gitleaks-redacted.json
```

The report must never include raw secret values. It records counts, rule ids,
blocking file paths, warning file samples, and scanner status.

`gitleaks` uses the repository `.gitleaks.toml` policy by default. That policy
keeps vendored upstream fixtures and generated evidence out of the release
blocking scan. If a raw audit is needed, run an explicit one-off gitleaks scan
outside the release gate and keep the output redacted.

## Release Blocking Rules

Blocking:

- any gitleaks finding in non-ignored project files
- any Trivy vulnerability or misconfiguration reported by the local gate
- any dependency compatibility failure
- any adversarial boundary test failure

Warnings that still require review:

- findings in `vendor/`, `node_modules/`, or `.venv/`
- findings in generated `data/normalized/` or `data/receipts/`
- findings in local ignored `.env*` files

Warnings are not proof of safety. The local classifier keeps these buckets
separate if they appear in a redacted report. The GitHub release scan uses
`.gitleaks.toml` so known vendor fixtures and generated evidence do not fail CI
as project-source leaks.

## Red-Team Boundary Matrix

Current local matrix:

```text
FH-RT-001: prompt-injected research assets remain cite-only
FH-RT-002: unknown or malicious asset ids do not grant execution authority
FH-RT-003: Layer 9 blocks live execution requests in MVP
FH-RT-004: scanner findings are summarized without raw secret material
```

The first payload corpus lives at:

```text
data/redteam/payloads/asset-boundary-v0.json
```

Generated red-team exports live at:

```text
evals/promptfoo/redteam-boundary.yaml
data/redteam/exports/asset-boundary-v0.jsonl
data/redteam/exports/manifest.json
data/redteam/exports/tool-readiness.json
evals/promptfoo/redteam-dryrun.yaml
data/redteam/exports/promptfoo-redteam-dryrun-validation.json
```

It currently covers:

```text
asset_id_injection
asset_id_path_traversal
asset_id_config_injection
prompt_injection_strategy_text
prompt_injection_reference_text
receipt_secret_probe
```

These checks are implemented as unit tests and reported by `task
hardening:redteam`. The same corpus is exported to:

```text
evals/promptfoo/redteam-boundary.yaml
```

`task eval:redteam-boundary` regenerates that file and runs a promptfoo echo
smoke eval with one test per payload. This proves the corpus is promptfoo-ready,
not that an LLM has resisted jailbreak attempts.

The JSONL export is tool-neutral. It is intended as the future input boundary for
PyRIT, garak, or promptfoo redteam adapters. The manifest records tool readiness:
`promptfoo_echo_eval=active_smoke`; mature red-team tools remain `planned` until
they are actually installed, configured, and verified.

`task redteam:tools-check` records local tool availability. At this stage,
`promptfoo` is required for the current smoke gate. `promptfoo redteam`, PyRIT,
and garak are tracked as planned or unconfigured tools until dedicated adapters
and checks are implemented.

`task redteam:dryrun-config-check` validates the promptfoo redteam dry-run
contract. It checks that the target is `echo`, no live/broker/provider endpoint is
configured, local corpus refs are present, and metadata says no dynamic redteam
attack execution occurred.

These checks are intentionally smaller than a real LLM red-team suite. The next
hardening milestone should add mature external red-team tooling:

```text
promptfoo redteam
Microsoft PyRIT
NVIDIA garak
OWASP LLM Top 10 coverage map
```

## GitHub Security Scaffolding

The repository now includes:

```text
.github/workflows/security.yml
.github/dependabot.yml
.gitleaks.toml
```

The workflow runs standard checks, adversarial boundary checks, CodeQL,
red-team tool readiness, promptfoo redteam dry-run contract validation,
promptfoo boundary smoke eval, Gitleaks, and Trivy. Dependabot watches GitHub
Actions, npm, pip, and cargo ecosystems.

## Interpretation

A green hardening gate means:

```text
The research MVP passed the current local release checks.
```

It does not mean:

```text
The system is safe for autonomous live trading.
The system passed institutional red-team review.
The system is compliant with broker, exchange, or performance-reporting rules.
```
