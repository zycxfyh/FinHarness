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
| `task setup` | Sync locked Python groups, install the editable `src` package, and sync locked JS dependencies. | May install/update local packages. |
| `task doctor` | Verify the locked uv environment and canonical editable package import. | Runs with `PYTHONPATH` removed and reports the resolved module path. |
| `task issue:start -- <issue> --slug <slug>` | Create a numbered issue branch/worktree from current `origin/main`. | Requires an open issue and refuses naming/path collisions. |
| `task issue:status -- [issue]` | Audit worktree numbering, cleanliness, and stale metadata. | Read-only. |
| `task issue:finish -- <issue> [--apply]` | Preview or apply cleanup after verified PR merge. | Dry-run by default; refuses dirty, open, mismatched, or unmerged work. |
| `task issues:audit [-- --repo OWNER/REPO]` | Audit live open Issues for exactly one plane, kind, and lifecycle label. | Read-only; derives from GitHub Issue truth and exits non-zero on missing, multiple, or unknown taxonomy labels. |
| `task pr:body -- <fields>` | Render the concise PR contract with issue and changed-file metadata. | Derives the issue from the numbered branch unless `--issue` is supplied; manual risk and safety evidence remain required. |
| `task pr:check -- --body-file <path>` | Validate issue linkage, scope, risk/classification, validation, and safety evidence. | Read-only; the required `Dependency review` check runs the same contract against the GitHub event. |
| `task governance:inventory` | Check source-derived dependency consumers and attestation summary fields. | Read-only; prints the affected consumer and repair command on drift. |
| `task governance:inventory:update` | Repair source-derived governance inventory fields. | Deterministic and idempotent; never invents manual policy or migration judgments. |
| `task capital:reconcile -- --receipt-root <path>` | Audit capital-import receipt/DB consistency. | Read-only; exits non-zero on findings. |
| `task capital:reconcile -- --receipt-root <path> --apply` | Apply deterministic import repairs and write a recovery receipt. | Never invents missing evidence or grants authority. |
| `task check` | Standard local verification suite. | Alias for the `check:ci` merge gate. |
| `task check:fast` | Ensure locked setup, then lint, typecheck, and run the full Python test gate (compile + unittest + pytest). | Fast local feedback without stale-environment false failures. |
| `task check:ci` | Fast checks, base-profile rebuild, integration, frontend, governance, and rules. | Main merge gate. |
| `task check:timed` | Run the same authoritative CI stages with per-stage duration and outcome evidence. | Writes `.artifacts/check-timing.json`; GitHub Actions also renders a step summary and uploads the JSON artifact. |
| `task check:research` | CI gate plus experiments and eval smoke. | Full research validation. |
| `task lint` | Run Python lint checks. | Ruff. |
| `task typecheck` | Run mypy. | Strict on safety-critical core. |
| `task test:compile` | Run Python compile check. | Syntax-only. |
| `task test:unittest` | Run unittest discovery suite (`unittest.TestCase`-based tests). | No external services. |
| `task test:pytest` | Run pytest-only test files from the pytest manifest. | Pytest-annotated test files only. |
| `task test:all` | Compile + unittest + pytest (complete Python test gate). | Delegated by `task test` and `task check:fast`. |
| `task test` | Compatibility alias for the complete Python test gate (`task test:all`). | Delegates to `test:all`. |
| `task test:integration` | Run slower graph/property integration tests. | Included in `task check`. |
| `task test:frontend` | Run jsdom frontend tests. | Included in `task check`. |
| `task test:browser` | Optional Playwright cockpit smoke. | Not in `task check`. |
| `task deps:probe-base` | Rebuild base-only environment and import the real core API. | Included in `task check:ci`. |
| `task deps:probe-data` | Rebuild base + data and import maintained data consumers. | No provider network calls. |
| `task deps:probe-research` | Rebuild base + research and import research consumers. | No experiment execution. |
| `task deps:probe-agent` | Rebuild the composed data + research + agent runtime profile. | Imports tools; does not call a model. |
| `task deps:probe-eval` | Rebuild base + eval and import the eval wheel. | Does not run an evaluation. |
| `task deps:probe-all` | Run all isolated dependency profiles. | CI also runs a profile matrix. |

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
| `task governance:check` | Run governance inventory drift checks not already owned by the Python and frontend gates. |
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
| `task agent:describe` | Describe registered OpenAI Agents SDK tools; pass `-- --profile review-draft` or `-- --profile review-note` to inspect a non-default profile. | Tool inventory. |
| `task agent:run` | Run the real agent when `OPENAI_API_KEY` is configured; pass `-- --profile ...` or `FINHARNESS_AGENT_PROFILE`. | Agent output is not authority. |
| `task eval:smoke` | Run promptfoo local echo eval. | Eval harness check. |
| `task eval:risk` | Evaluate generated finance risk note. | Overclaim/risk-note check. |
| `task eval:redteam-boundary` | Export and run local red-team boundary corpus smoke eval. | Boundary evidence. |

## Workflows And Utilities

| Command | Purpose |
| --- | --- |
| `task cockpit:daily` | Build deterministic daily portfolio-change brief from an existing receipt. |
| `task observability:trace` | Read a local observability trace-index receipt. |
| `task backup` | Create a capacity-gated, atomically published State Core and receipt backup with bound hashes. |
| `task backup:verify -- BACKUP` | Verify manifest bindings, SQLite integrity, and safe receipt-archive readability. |
| `task backup:prune` | Preview verified retention candidates; pass `-- --apply` to delete them. |
| `task identity:reconcile -- RECEIPT` | Inspect an ambiguous API mutation receipt. `--apply` requires `--reconciled-by` and `--reason`; the typed route resolver verifies domain truth and reconstructs the canonical response. Operators cannot provide response bytes, status, or content type. |
| `task mutations:capabilities-check` | Compare the closed keyed-mutation registry with the effective non-safe FastAPI route graph and exact typed reconciliation dispatcher. Fails on missing/stale routes or resolver drift. |
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
