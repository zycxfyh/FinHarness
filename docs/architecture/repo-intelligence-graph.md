# Repo Intelligence Graph

`repo_intelligence_graph` is FinHarness' local codebase understanding workflow.
It borrows the useful ideas from GitDiagram, CodeFlow, Emerge, and CodeCharta,
but keeps the implementation local, small, and auditable.

```text
source
  -> inventory
  -> import_graph
  -> task_graph
  -> test_map
  -> blast_radius
  -> security_surface
  -> output
```

## Responsibilities

- Build a repo file inventory.
- Parse first-party Python imports with `ast`.
- Read Taskfile task names and descriptions.
- Map tests to likely first-party modules.
- Infer blast radius from changed files.
- Recommend focused checks for risky surfaces.
- Render a Mermaid graph and JSON receipt.

## Non-Goals

- It does not replace tests, linters, SAST, or CI.
- It does not call external repo visualization services.
- It does not authorize release or trading execution.

## Outputs

```text
docs/architecture/generated/repo-intelligence.md
data/receipts/repo-intelligence/latest.json
```

Both outputs are generated artifacts. They can be regenerated with:

```text
task repo:intelligence
```
