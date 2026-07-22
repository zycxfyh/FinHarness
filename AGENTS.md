# FinHarness Agent Instructions

## Objective

FinHarness is a local-first personal capital review and decision system. The current product objective is a verified material capital decision review:

```text
trusted capital state
-> admitted evidence
-> reviewable decision candidate
-> human decide / defer / reject
-> outcome review and learning
```

Read [`docs/current-system.md`](docs/current-system.md) before substantial work. Do not infer current capability from an old proposal, review, roadmap, note, branch, or conversation.
Use [`Agentic Engineering Principles`](docs/engineering/agentic-abstraction-principles.md) for the stable Human/Agent/Harness/deterministic responsibility split.

## Truth hierarchy

Use the smallest canonical owner for each fact:

```text
requested work and durable coordination:
  the current user/task request; GitHub Issues, pull requests, and native
  relationships when shared tracking is useful

runtime behavior:
  source code and executable tests

commands:
  Taskfile.yml

API operations:
  effective FastAPI route graph and models

configuration and schemas:
  canonical config/model sources and direct environment reads

system ownership and lifecycle:
  docs/architecture/system-catalog.yml

product direction:
  docs/product/product-thesis.md and docs/product-north-star.md

historical evidence:
  ADRs, proposals, reviews, notes, old roadmaps, archived files, and Git history
```

A prose document may explain or link to a machine-owned fact. It must not become a second mutable registry.

## Start substantial work

1. Confirm the repository, exact `main` SHA, requested result, and working branch.
2. Read the relevant Issue or PR when one exists; do not create one merely to unlock reversible work.
3. Identify the production owner, direct consumers, relevant tests, and current user/operator boundary.
4. State the failure being solved and whether its consequences are reversible.
5. Prefer the smallest change that advances one end-to-end result.
6. Record explicit non-goals only when adding or changing a cross-cutting mechanism.

Do not start from a historical implementation plan and assume its remaining checklist is still useful.

## Engineering order

Use this order:

1. delete or retire a duplicate mechanism;
2. use the existing canonical repository boundary;
3. use a standard-library, platform, official, or mature-project capability;
4. add the smallest adapter or FinHarness-specific policy needed;
5. add a new abstraction only after the earlier options are demonstrably insufficient.

"Future flexibility" is not evidence for a new platform layer. Do not create a second state store, workflow identity, SHA classifier, authorization language, event log, provenance format, Agent loop, documentation registry, or financial engine without an observed gap and a named replacement or deletion target.

FinHarness should own capital-specific semantics that external tools cannot decide: capital-truth admission, evidence admission, decision meaning, DecisionReadiness, consequence authority, review, receipts, and learning. Mature tools should own commodity data, calculation, execution, and platform mechanics where suitable.

## Delivery method

Prefer a vertical slice over a horizontal architecture project:

```text
real input
-> canonical domain boundary
-> user/operator-visible result
-> relevant failure path
-> evidence and recovery
```

During development:

- act directly on ordinary reversible repository work;
- run the smallest useful checks first;
- keep Draft pull requests cheap and diagnostic;
- do not repeatedly invalidate exact-head full evidence for minor intermediate edits;
- freeze the final candidate, run the required exact-head checks, review the actual diff, and merge with the expected head SHA;
- do not treat CI green as proof that the product direction or abstraction is correct.

A convincing model answer, generated artifact, receipt count, test count, label, or completed form does not prove task completion. Completion requires the requested user or system result and the evidence appropriate to its consequences.

## Documentation rule

Create or update maintained documentation only when it:

- enables a real supported task;
- explains a durable decision or boundary that code cannot express;
- assigns one canonical fact owner;
- preserves unique evidence that Git history alone cannot make discoverable;
- materially reduces future diagnosis, restart, or handoff cost.

Ordinary reversible implementation details belong in code, tests, commits, and optionally the coordinating Issue. They do **not** require a proposal, module upgrade log, review, lesson, idea record, or roadmap update by default.

Use an ADR only when a durable rationale will matter after the implementation changes. Use a proposal only when a substantial cross-cutting choice must be reviewed before implementation. Preserve historical evidence as authored; do not continuously synchronize it with current code.

## Work-state rule

GitHub coordinates durable shared work; it is not a per-change permission system.

- A direct request, assigned task, or observed defect may start reversible work without first completing an Issue form or taxonomy.
- Use an Issue when dependencies, discussion, future follow-up, or shared status make the record valuable.
- Use labels when they improve a view. Missing or duplicate `plane:*`, `type:*`, or `status:*` labels are not product failures and do not block implementation.
- A deliberately deferred capability remains a shared decision; discuss changing that consequence boundary rather than bypassing it silently.
- Program bodies describe stable outcomes and investment logic; they must not copy changing child status.
- Avoid creating a new Issue when an existing owner can accept the finding without mixing responsibilities.
- Close or transfer temporary owners when their bounded purpose is complete.
- Do not run competing implementation paths against the same state or effect owner.

## Irreversible safety kernel

Use hard blocking controls only for failures that cannot be cheaply undone:

- secret or credential disclosure;
- real external execution, transfer, deployment, DNS, or cloud mutation;
- destructive user-data or schema migration without restore evidence;
- authority escalation or bypass;
- loss of unique receipt, provenance, or recovery evidence;
- final review/test evidence bound to the wrong commit;
- current product surfaces claiming unsupported capability.

Treat ordinary internal code, tests, documentation, branches, commits, and unshipped UI as reversible unless evidence shows otherwise. Prefer fast detection, clear logs, Git rollback, repair, backup, idempotency, and reconciliation over speculative pre-action gates.

Current capital execution remains simulated-only. There is no real broker SDK, funded-account connection, credential loader, external venue submission, live trading, transfer, or tax submission path. Raw model text never owns canonical state or creates an external capital effect.

## Minimum completion report

For substantial work, report only:

- exact final head;
- changed responsibility and deleted duplicate responsibility;
- checks actually run and their result;
- unresolved material debt;
- rollback or recovery boundary when relevant.

Do not create ceremonial artifacts solely to restate information already present in the request, diff, checks, and Git history.
