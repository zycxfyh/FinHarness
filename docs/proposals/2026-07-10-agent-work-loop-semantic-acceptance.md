# Agent Work Loop Semantic Acceptance Baseline — mini-RFC

Status: implemented; diagnostic release gate passed
Logical slice: `LOOP-01`
Date: 2026-07-10

## 1. Change Class

**C2.** This slice adds a read-only acceptance probe, tests for the probe, and
architecture truth. It does not change Agent runtime behavior or claim semantic
closure.

## 1b. Product Claim / Layer / Thin Slice

FinHarness will have an executable Agent Work Loop closure gate that fails
until the promised action-observation-decision cycle and artifact chain are
real. The normal repository gate remains green; the dedicated closure command
is intentionally red and explicitly excluded from `task check`.

## 1c. Module Placement / System Boundary

The probe belongs to Agent Cognition Runtime verification. It calls the real
work-orchestrator entry points inside temporary receipt roots and inspects the
resulting artifacts. It may also inspect source for the two architectural
contracts that cannot yet be exercised: tool-argument transport and an
observation-driven next-action reducer.

## 2. PR-Chain Finding

| Chain | What it actually delivered | Missing closure |
| --- | --- | --- |
| #219–#220 | frozen request/result and context snapshot models | no semantic loop |
| #222 | playbook/evaluator metadata binding helper | full loop never calls it |
| #224 | fixed cognition artifacts after a preselected tool batch | no observation-driven decision |
| #225 | work entry point and search-index rebuild | no WorkResult persistence or work-id search hit |
| #226 | structural smoke over object presence | no tool success, receipt link, or workspace assertion |
| #227 | architecture completion claim | claim exceeded runtime evidence |

## 3. Target Acceptance Contracts

- requested tool calls carry real arguments;
- the next action consumes the preceding observation;
- `max_steps` and `max_tool_calls` both stop work;
- unavailable tools and missing playbook context produce exact stop reasons;
- the final AgentRunReceipt is linked;
- tool-result references are receipt/artifact references, not tool names;
- AgentWorkResult is persisted and searchable by `work_id`;
- the review workspace is hydrated and linked;
- EvaluationReport is linked;
- all declared stop reasons have reducer paths;
- `execution_allowed` remains false.

## 4. Surface Inventory

- **Inputs:** real AgentWorkRequest calls, temporary receipt roots, current
  work-loop source.
- **Outputs:** ordered pass/fail checks and a process exit code.
- **Network:** none.
- **Persistence:** temporary files only.
- **Default gate:** unchanged; the closure probe is an explicit task.
- **Excluded:** loop implementation, provider/model selection, sessions,
  checkpoints, retries, scheduling, delegation, execution tools.

## 5. Gate Semantics

`task agent:work-loop-acceptance` exits 1 while any semantic contract is open.
`--report-only` prints the same evidence but exits 0 for planning and CI
diagnostics. Unit tests lock the known-red baseline so partial implementation
cannot silently change the story; closing a check requires updating the
baseline and the architecture status in the same slice.

## 6. Default Path Invariant

No production Agent class, receipt schema, tool registry, context projection,
evaluator, workspace, API, database, or execution behavior changes.

## 7. Traceability Matrix

| Commitment | Location | Test / Gate |
| --- | --- | --- |
| Dedicated red closure gate | script + Taskfile | acceptance probe tests |
| Real runtime evidence | dynamic temporary probes | known-red baseline test |
| No completion overclaim | work-loop plan | docs-current test |
| Normal gate remains green | no default task dependency | full `task check` |

## 8. Release Decision

Merge the diagnostic now; do not release or rename the Agent Work Loop. The
dedicated closure command truthfully exits 1 with 4/15 contracts passing and 11
open, while its known-red baseline tests, both existing Agent smokes, docs
checks, lint, mypy, 884 unit tests, eight integration tests, frontend and
governance checks, the research experiment, and evaluation smoke all pass at
their expected real exit status.
