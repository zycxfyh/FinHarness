# Command Reference

This reference lists the supported task entry points most users need first. For
the complete live list, run:

```bash
task --list
```

Prefer `task ...` entries over ad hoc commands. Commands that mention live
trading still pass through the project's fail-closed gates and do not remove the
need for human attestation.

## First-Run And Verification

| Command | Purpose | Safety note |
| --- | --- | --- |
| `task status` | Show local lab/tool status. | Read-only. |
| `task setup` | Sync dependencies from lockfiles. | May install/update local packages; run deliberately. |
| `task check` | Standard local verification suite. | Passing checks is evidence, not trading permission. |
| `task lint` | Run Python lint checks. | Code quality only. |
| `task test` | Compile Python files and run unit tests. | Test pass does not prove strategy correctness. |
| `task test:properties` | Run property-style governance/boundary tests. | Boundary evidence only. |

## Golden Path Commands

| Command | Purpose | Boundary to notice |
| --- | --- | --- |
| `task wheels:check` | Confirm default mature wheels import locally and report optional OpenBB status. | Mature libraries are evidence/tooling, not authority. |
| `task feature:macd` | Build a real SPY MACD feature snapshot. | Output keeps `execution_allowed=false`. |
| `task feature:squeeze` | Build a real SPY Squeeze feature snapshot. | Output keeps `execution_allowed=false`. |
| `task validation:graph` | Run validation evidence graph. | Human review required before proposal. |
| `task risk-gate:graph` | Run mandate, cap, permission, and review checks. | No live approval or final sizing. |
| `task execution:graph` | Run execution lifecycle graph. | Defaults to blocked/dry-run review evidence. |
| `task lessons:draft` | Draft lessons from receipts. | Drafts do not become rules automatically. |
| `task security:audit` | Run dependency audit through the hardening gate. | Security evidence, not trading authority. |
| `task agent:describe` | List registered agent tools. | Tools are research/risk-note tools, not order-entry tools. |

## Ten-Layer Graphs

| Command | Layer |
| --- | --- |
| `task market-data:graph` | 1 - market data |
| `task indicators:graph` | 2 - indicators/features |
| `task events:snapshot` | 3 - events |
| `task interpretation:graph` | 4 - interpretation |
| `task hypotheses:graph` | 5 - hypotheses |
| `task validation:graph` | 6 - validation |
| `task proposal:graph` | 7 - proposal |
| `task risk-gate:graph` | 8 - risk gate |
| `task execution:graph` | 9 - execution |
| `task post-trade:graph` | 10 - post trade |
| `task ten-layer:graph` | top-level ten-layer orchestrator |

## Governance And Evidence

| Command | Purpose |
| --- | --- |
| `task governance:dashboard` | Build governance dashboard receipt/report. |
| `task governance:certify-controls -- --owner "<name>" --cadence-days 30` | Run control-owner baseline tests and write a human attestation receipt. |
| `task quality:governance` | Run quality governance graph. |
| `task receipt:usage-audit` | Audit receipt references and consumption. |
| `task rules:audit` | Verify promoted rule changes have lesson-to-receipt lineage. |
| `task release:preflight` | Run release preflight graph. |
| `task repo:intelligence` | Build local repo intelligence graph and receipt. |

## Personal Finance State

| Command | Purpose | Boundary |
| --- | --- | --- |
| `task api:serve` | Serve the read-only local API and cockpit at `/cockpit/`. | Local read/review surface; does not create execution endpoints. |
| `task beancount:import -- path/to/ledger.beancount` | Mirror a real Beancount ledger's holdings and liabilities into state core via `bean-query` (no intermediate CSV). | Read-only mirror; not accounting, tax, investment, or execution authority. |
| `task personal-finance:import -- path/to/export.csv` | Import a FinHarness-contract personal-finance CSV into state core, including typed personal-finance rows when present. | Read-only mirror; not accounting, tax, investment, or execution authority. |
| `task brief:daily` | Compute and archive the unified daily brief as a dated receipt. | Descriptive summary; not advice or execution authorization. |
| `task decisions:scan` | Scan the exposure map and record capital-allocation candidates as governed proposals. | Read-only candidates with do-nothing option; human attestation is review evidence only. |

## Trading Guard And State

| Command | Purpose | Safety note |
| --- | --- | --- |
| `task guard:interactive -- --drawdown-pct -3 --consecutive-losses 3` | Evaluate a hypothetical behavioral guard state. | A non-zero exit can be the correct blocked outcome. |
| `task trading-state:show` | Show persisted behavioral trading state. | Read-only state inspection. |
| `task trading:reset-check` | Evaluate behavioral guard against persisted state. | Use when drawdown/losses change behavior. |
| `task trading:validation-report` | Generate trading validation report. | Review artifact only. |

## Venue And Broker Adapters

| Command | Purpose | Safety note |
| --- | --- | --- |
| `task alpaca:paper-check` | Inspect Alpaca paper account state. | Paper-only path. |
| `task alpaca:paper-order-cycle` | Place/cancel a tiny paper order. | Paper broker sandbox only. |
| `task alpaca:paper-strategy-order` | Run a paper order with thesis, risk gate, cancel, and receipt. | Paper-only review flow; `--execute` requires an explicit `--operator` for market-access ledger consumption. |
| `task okx:market` | Fetch public OKX market data. | Read-only. |
| `task okx:live-status` | Read live OKX account/status data. | Read-only. |
| `task okx:live-read -- account balance` | Run allowlisted live read command. | Read-only allowlist. |
| `task okx:demo -- swap orders` | Run allowlisted OKX demo command. | Demo mode. |
| `task okx:live-write -- ...` | Route live write through fail-closed gate. | Requires double env opt-in, attestation, thesis, governed notional ceiling, aggregate market-access ledger, and receipt; CLI request limits can only tighten. |

## Mature-Wheel Experiments

| Command | Purpose | Boundary |
| --- | --- | --- |
| `task experiments` | Run local Backtrader, vectorbt, and Riskfolio experiments. | Experiments disclose `execution_allowed=false`. |
| `task wheels:data-check` | Check wheels plus provider-backed yfinance data calls; OpenBB is checked only if installed. | Needs network/provider availability. |
| `task wheels:size` | Show local wheel sizes. | Inventory only. |
