# Contributing

Read [FinHarness Current System](docs/current-system.md), [Agent Instructions](AGENTS.md), and the short [Agentic Engineering Principles](docs/engineering/agentic-abstraction-principles.md) before substantial work. Issues and pull requests coordinate durable shared work; they are not prerequisites for every reversible change.

## Before changing the repository

1. Confirm the repository, exact `main` SHA, requested outcome, and working branch.
2. Read the owning Issue or existing defect context when one exists. Create an Issue only when discussion, dependencies, future follow-up, or shared status justify it.
3. Locate the canonical production owner, direct consumers, relevant tests, and current user/operator boundary.
4. Decide whether the consequences are reversible. Reserve hard pre-action gates for secrets, external effects, destructive migration, authority escalation, unique evidence, and final evidence bound to the wrong commit.
5. Delete a duplicate, use the canonical boundary, or adopt a mature capability before creating a new mechanism.

A bounded fix or implementation does not require classification fields, ceremonial research, a proposal, an ADR, or a new Issue merely to begin.

## Implement a vertical slice

Prefer:

```text
real input
-> canonical domain boundary
-> user/operator-visible result
-> relevant failure path
-> evidence and recovery
```

Keep the change small enough to review as one responsibility. Do not create a parallel state store, registry, workflow identity, roadmap, policy language, or financial engine merely for future flexibility.

Use `task ...` entries when they are the maintained project interface. Run the smallest useful checks during development.

## Documentation

Update maintained prose only when the change:

- enables or changes a real supported task;
- changes a durable user/operator boundary;
- assigns a canonical fact owner;
- preserves unique decision or failure evidence;
- materially reduces restart, diagnosis, or handoff cost.

Commands belong to `Taskfile.yml`, API facts to the effective route graph and models, schemas to their source models, system lifecycle to `system-catalog.yml`, and durable work coordination to GitHub when needed. Do not copy these into another mutable table.

Historical proposals, reviews, lessons, notes, and roadmaps do not need updating for ordinary implementation changes.

## Final candidate

1. Review the actual diff and remove temporary diagnostics, duplicate mechanisms, generated drift, and stale claims.
2. Mark the pull request Ready when the responsibility and rollback boundary are stable.
3. Run the checks appropriate to the changed surface and the required exact-head final gate.
4. Record the exact final head, checks actually run, unresolved material debt, and recovery boundary when relevant.
5. Merge with the expected head SHA so review and evidence cannot silently refer to an older commit.

CI success proves the checked contracts passed. It does not prove that the product direction or abstraction is correct.
