# Contributing

Use the existing project tasks and keep changes small, reviewable, and
evidence-bound.

For the numbered issue → worktree → PR → CI → merge lifecycle, follow
[Manage Issue Worktrees](docs/how-to/manage-issue-worktrees.md). Do not begin the
next implementation until the current issue PR has merged.

## Before You Change Code

1. Read the relevant module doc under `docs/modules/`.
2. Prefer existing task entries over ad hoc commands.
3. Check whether a mature wheel should own the heavy implementation.
4. Keep FinHarness local code focused on adapters, governance models, quality,
   lineage, snapshots, receipts, permission boundaries, workflow orchestration,
   and tests.

## Documentation Definition Of Done

A change is not complete if it creates a new user-facing command, interface,
receipt, adapter, or safety boundary and the docs do not explain how to use and
review it.

Update the smallest relevant docs:

| Change type | Required docs |
| --- | --- |
| New task command | [Command Reference](docs/reference/commands.md) and a how-to if users must run it directly. |
| New mature-wheel adapter | [Interface Reference](docs/reference/interfaces.md), the relevant module doc, and an adapter how-to if repeatable. |
| New receipt/snapshot shape | [Receipt Reference](docs/reference/receipts.md) and evidence inventory if provenance changes. |
| New config/env var | [Config And Environment Reference](docs/reference/config-env.md). |
| New safety rule or boundary | [Policy Contract](docs/architecture/policy-contract.md) plus the relevant how-to/tutorial. |
| New architecture decision | ADR or architecture explanation doc. |

## Safety Documentation Rule

Every tutorial or how-to touching research, risk, execution, broker, or venue
behavior must say:

- what evidence is produced;
- where the receipt is written;
- what `execution_allowed` means for that layer;
- what the command does not authorize;
- whether human attestation is required;
- which stop conditions should make the operator stop and review.

Do not document a trading path as "easy" unless the brakes are visible in the
same document.
