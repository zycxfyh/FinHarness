# Hermes / DeepSeek Worker Pilot Review

Date: 2026-07-10

Status: actioned

## Question

Can Codex retain goal interpretation, constraints, acceptance, exception handling,
and integration while a Hermes-hosted DeepSeek worker completes a bounded
FinHarness implementation task?

## Pilot Contract

The worker received one leaf task: inspect direct Python requirements and their
repository consumers, then add only
`docs/governance/dependency-consumers.json`.

The manager created a failing acceptance test before delegation and recorded its
hash. The worker was forbidden to modify the test, dependency declarations,
lockfile, Taskfile, debt register, or debt verifier. Hermes ran in an isolated
Git worktree with only terminal and file toolsets, checkpoints enabled, no
delegation toolset, and a ten-turn limit.

## Observed Result

- Hermes completed ten DeepSeek API turns in about three minutes without a
  provider connection failure.
- The worker respected the write boundary and did not alter forbidden files.
- It produced no patch or manifest before exhausting the turn budget.
- It repeatedly issued narrow searches instead of switching early to one AST
  inventory pass.
- Its final summary reported 24 base dependencies, while `pyproject.toml`
  declares 25.
- It identified the correct next technique only after the implementation budget
  was exhausted.

The pilot therefore failed its delivery and factual-accuracy criteria. Scope
compliance alone was insufficient for acceptance.

## Manager Takeover

Codex rejected the empty worker result and completed the task independently:

- added an audit-only dependency consumer manifest without moving dependencies
  or changing debt status;
- covered every direct base and development requirement exactly once;
- distinguished distribution names from import names;
- recorded current import and Taskfile evidence plus bounded grouping advice;
- marked dependencies with no observed consumer as removal candidates rather
  than deletion authorizations;
- strengthened the acceptance test to recompute import consumers from the AST,
  so plausible-looking but false path lists cannot pass.

`ENG-DEBT-0005` remains active. The pilot creates evidence for the next
packaging decision; it does not prove grouped installs or base-only runtime
behavior.

## Decision

Do not use the current Hermes / DeepSeek setup for repository-wide inventory,
architecture classification, debt closure, or acceptance ownership. Codex owns
those tasks and the final integration decision.

DeepSeek may be retried only for a smaller implementation leaf where all of the
following are true:

- the input inventory is already supplied rather than discovered by the worker;
- one or two files are writable;
- the behavioral test is frozen and independently owned;
- the task can be completed within a few tool calls;
- failure produces no partial governance claim;
- Codex reviews every changed line and reruns deterministic gates.

Until a later pilot demonstrates reliable delivery, delegation is an optional
optimization, never a dependency of the FinHarness engineering process.

## Follow-up

1. Use the manifest to decide dependency moves one group at a time.
2. Add grouped installation and base-only runtime probes before changing the
   debt status.
3. Keep `ENG-DEBT-0005` active until the canonical verifier observes those
   runtime facts.
4. Prefer Codex-only implementation for the security boundary and Agent Work
   Loop architecture slices.
