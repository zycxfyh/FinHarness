# How-to Guides

How-to guides are task recipes for users who already understand the golden path.
They should answer "how do I do this one job?" without explaining the whole
architecture.

Start with the tutorial first: [Golden Path Tutorial](../tutorials/golden-path.md).

## Available Now

- First safe end-to-end run: [Golden Path Tutorial](../tutorials/golden-path.md).
- Command lookup while recipes are being expanded: [Command Reference](../reference/commands.md).
- Layer-specific responsibilities: [Module Map](../architecture/module-map.md).

| How-to | Use it when | Current entry point |
| --- | --- | --- |
| [Add a mature-wheel adapter](add-mature-wheel-adapter.md) | You are replacing local heavy logic with a mature library. | [Mature Wheel Control Plane](../architecture/mature-wheel-control-plane.md) |
| [Import a personal-finance export](import-personal-finance-export.md) | You have a Beancount ledger or a FinHarness-contract CSV to mirror into state core. | `task beancount:import` / `task personal-finance:import` |
| [Manage governance inventories](manage-governance-inventories.md) | Derived dependency consumers or attestation summaries drift from source declarations. | `task governance:inventory` / `task governance:inventory:update` |
| [Manage issue worktrees](manage-issue-worktrees.md) | You are starting, publishing, or cleaning one numbered issue/PR slice. | `task issue:start` / `task pr:body` / `task issue:finish` |
| [Audit the Issue backlog taxonomy](audit-issue-backlog.md) | Plane, kind, lifecycle, or Program status views may be stale or ambiguous. | `task issues:audit` / GitHub Issue searches |
| [Promote a lesson draft into a rule change](promote-lesson-to-rule.md) | A human has reviewed a lesson and wants traceable rule lineage. | `task lessons:promote`, `task rules:audit` |
| Keep current docs in sync | Current docs mention commands or modules that moved. | `task docs:current-check` |

Archived recipes may preserve old broker or trading workflows as history, but
current how-to entries should use only live `task --list` commands. Safety rule
for every how-to: teach the brake in the same document as the action.
