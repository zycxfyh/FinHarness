# Contributing

Read [FinHarness Current System](docs/current-system.md) and
[Agent Instructions](AGENTS.md) before substantial work. GitHub Issues and pull
requests own mutable work state; this file does not duplicate an implementation
sequence.

## Before changing the repository

1. Confirm the repository, exact `main` SHA, owning Issue or existing defect
   context, branch, and requested outcome.
2. Locate the canonical production owner, direct consumers, relevant tests, and
   current user/operator documentation.
3. Decide whether the change is reversible. Reserve hard pre-action gates for
   secrets, external effects, destructive migration, authority escalation,
   unique evidence, and final evidence bound to the wrong commit.
4. Use the mechanism-selection order in `AGENTS.md`:
   delete a duplicate, use the canonical boundary, adopt a standard or mature
   capability, add the smallest adapter/policy, and create a new abstraction
   only for an observed gap with a replacement or deletion target.
5. State explicit non-goals before introducing a cross-cutting mechanism.

A bounded bug fix does not require ceremonial research, a proposal, an ADR, or a
new Issue when an existing owner already contains the problem.

## Implement a vertical slice

Prefer:

```text
real input
-> canonical domain boundary
-> user/operator-visible result
-> relevant failure path
-> evidence and recovery
```

Keep the change small enough to review as one responsibility. Do not create a
parallel state store, registry, workflow identity, roadmap, policy language, or
financial engine merely for future flexibility.

Use `task ...` entries instead of ad hoc package-manager or global Python
commands. Run the smallest relevant checks during development.

## Documentation

Update maintained prose only when the change:

- enables or changes a real supported task;
- changes a durable user/operator boundary;
- assigns a canonical fact owner;
- preserves unique decision or failure evidence;
- materially reduces restart, diagnosis, or handoff cost.

Commands belong to `Taskfile.yml`, API facts to the effective route graph and
models, schemas to their source models, system lifecycle to
`system-catalog.yml`, and work state to GitHub. Do not copy these into another
mutable table.

Historical proposals, reviews, lessons, notes, and roadmaps do not need updating
for ordinary implementation changes.

## Final candidate

1. Review the actual diff and remove temporary diagnostics, duplicate mechanisms,
   generated drift, and stale claims.
2. Mark the pull request Ready only when the responsibility and rollback boundary
   are stable.
3. Run the required changed-surface and exact-head final checks.
4. Record only the exact final head, checks actually run, unresolved material
   debt, and recovery boundary.
5. Merge with the expected head SHA so review and evidence cannot silently refer
   to an older commit.

CI success proves the checked contracts passed. It does not prove that the
product direction or abstraction is correct.
