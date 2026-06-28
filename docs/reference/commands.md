# Command Reference

This page lists maintained task entry points. For the complete live list, run:

```bash
task --list
```

Prefer `task ...` entries over ad hoc commands. Passing a command is evidence
for that command's scope only; it is not proof of investment performance or
execution authorization.

## First Run And Verification

| Command | Purpose | Note |
| --- | --- | --- |
| `task status` | Show local lab/tool status. | Read-only. |
| `task setup` | Sync dependencies from lockfiles. | May install/update local packages. |
| `task check` | Standard local verification suite. | Main local gate. |
| `task lint` | Run Python lint checks. | Ruff. |
| `task typecheck` | Run mypy. | Strict on safety-critical core. |
| `task test` | Compile Python and run fast unit tests. | No external services. |
| `task test:integration` | Run slower graph/property integration tests. | Included in `task check`. |
| `task test:frontend` | Run jsdom frontend tests. | Included in `task check`. |
| `task test:browser` | Optional Playwright cockpit smoke. | Not in `task check`. |

## Current Product Loop

| Command | Purpose | Boundary |
| --- | --- | --- |
| `task api:serve` | Serve the local read/review API and cockpit. | No order/transfer/execution endpoint. |
| `task beancount:import -- path/to/ledger.beancount` | Mirror a real Beancount ledger into State Core via `bean-query`. | Read-only mirror. |
| `task personal-finance:import -- path/to/export.csv` | Import a FinHarness-contract CSV into State Core. | Read-only mirror. |
| `task db:migrate` | Apply State Core schema migrations. | Deliberate state change; inspect first. |
| `task brief:daily` | Compute and archive the unified daily brief. | Descriptive summary only. |
| `task decisions:scan` | Record capital-allocation candidates as governed proposals. | No execution authority. |
| `task decisions:golden-path` | Run isolated receipt-consumption demo. | Synthetic/offline/manual demo. |
| `task decisions:research-smoke` | Run opt-in live research smoke. | Manual/network; not in `task check`. |
| `task review:annual` | Record an annual decision retrospective. | Review evidence. |
| `task lessons:draft` | Draft lesson candidates from receipts. | Human promotion still required. |
| `task lessons:promote` | Promote a reviewed lesson into a rule change. | Human action with lineage. |
| `task rules:audit` | Verify rule changes have lesson-to-receipt lineage. | Included in `task check`. |

## Governance, Quality, And Security

| Command | Purpose |
| --- | --- |
| `task governance:check` | Run EOS machine guardrails. |
| `task governance:policies` | List the governance policy registry. |
| `task governance:graphs` | List graph assets by status/consumer/owner. |
| `task governance:dashboard` | Build governance dashboard receipt/report. |
| `task docs:current-check` | Check maintained docs against live Taskfile/current facts. |
| `task repo:intelligence` | Build local repo intelligence graph, doc, and receipt. |
| `task receipt:usage-audit` | Audit receipt references and consumption. |
| `task quality:governance` | Run quality governance graph with authoritative checks. |
| `task release:preflight` | Run release preflight graph with authoritative checks. |
| `task project:governance-adapter` | Adapt workstation project-governance receipts. |
| `task hardening:gate` | Run local MVP hardening checks. |
| `task hardening:redteam` | Run local adversarial boundary checks. |
| `task security:scan` | Run dependency, gitleaks, and Trivy scans. |
| `task security:audit` | Run pip-audit through the hardening gate. |
| `task security:sbom` | Generate SBOM/provenance artifacts. |
| `task security:fuzz` | Run deterministic governance-boundary fuzz baseline. |
| `task redteam:tools-check` | Record red-team tool readiness. |
| `task redteam:dryrun-config-check` | Validate promptfoo red-team dry-run contract. |

## Research, Agents, And Evals

| Command | Purpose | Boundary |
| --- | --- | --- |
| `task wheels:check` | Check installed wheels/imports. | Local inventory. |
| `task wheels:data-check` | Check wheels plus provider-backed network data. | Network/provider availability required. |
| `task wheels:size` | Show local wheel sizes. | Inventory only. |
| `task experiments` | Run mature-wheel local Riskfolio experiment. | Experiment evidence only. |
| `task agent:describe` | Describe registered OpenAI Agents SDK tools. | Tool inventory. |
| `task agent:run` | Run the real agent when `OPENAI_API_KEY` is configured. | Agent output is not authority. |
| `task eval:smoke` | Run promptfoo local echo eval. | Eval harness check. |
| `task eval:risk` | Evaluate generated finance risk note. | Overclaim/risk-note check. |
| `task eval:redteam-boundary` | Export and run local red-team boundary corpus smoke eval. | Boundary evidence. |

## Workflows And Utilities

| Command | Purpose |
| --- | --- |
| `task cockpit:daily` | Build deterministic daily portfolio-change brief from an existing receipt. |
| `task observability:trace` | Read a local observability trace-index receipt. |
| `task backup` | Back up State Core SQLite and receipts outside git. |
| `task docs:list` | List project docs. |
| `task vocab:lint` | Run advisory controlled-vocabulary lint. |
| `task smoke` | Run minimal local smoke (`test` + `experiments`). |
| `task ideas:list` | Show Idea Lab backlog. |
| `task ideas:evolve` | Placeholder for manual idea evolution. |
| `task workflow:cognitive` | Run cognitive engineering flow. |
| `task workflow:engineering-delivery` | Run Engineering Delivery Graph. |

## Archived / Removed Entry Points

The old ten-layer trading-signal chain and live-trading entry points were
retired from mainline. Current Taskfile does not expose `okx:*`, `alpaca:*`,
`trading:*`, `guard:*`, `ten-layer:*`, or layer graph tasks. Historical docs may
still mention them, but maintained current docs must not.
