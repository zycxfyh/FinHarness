# Project Governance Adapter

Date: 2026-06-12
Status: compatibility bridge implemented; source migration not authorized

## Purpose

FinHarness keeps its existing governance graph entrypoints while workstation-lab
continues to mature the generic Project Governance Loop.

The adapter bridges those worlds by reading the workstation-lab FinHarness
project governance receipt and writing a FinHarness-local compatibility receipt.
It is a receipt bridge, not a source migration.

## Compatibility Contract

The adapter preserves these FinHarness surfaces:

```text
run_cognitive_project_flow
run_repo_intelligence_graph
run_quality_governance_graph
run_engineering_delivery_graph

task workflow:cognitive
task repo:intelligence
task quality:governance
task workflow:engineering-delivery
```

It also records current FinHarness output contracts:

```text
ideas/*.md
docs/notes/*-workflow-note.md
docs/proposals/*.md
docs/reviews/*.md
docs/lessons/*.md
data/receipts/cognitive-graph/*.json
data/receipts/repo-intelligence/latest.json
docs/architecture/generated/repo-intelligence.md
data/receipts/quality-governance/latest.json
data/receipts/engineering-delivery/*.json
docs/reviews/*-engineering-delivery.md
```

## Adapter Flow

```text
workstation-lab project-governance-loop receipt
-> FinHarness project_governance_adapter
-> data/receipts/project-governance-adapter/latest.json
```

The adapter reads workstation evidence only when the receipt path exists. It
does not import workstation-lab code at import time and does not execute
workstation commands.

## Boundaries

The adapter does not:

```text
move FinHarness source files
rename graph APIs
change Taskfile entrypoints
change existing FinHarness receipt paths
authorize release, migration, deployment, trading, or live execution
claim quality pass without executed-check evidence in the source receipt
```

Future source migration still requires a separate implementation plan,
FinHarness compatibility tests, a migration receipt, and human approval.

## Run

```bash
task project:governance-adapter
```

The default source receipt is:

```text
/root/workstation-lab/receipts/project-governance-loop/finharness/latest.json
```

The FinHarness adapter receipt is:

```text
data/receipts/project-governance-adapter/latest.json
```
