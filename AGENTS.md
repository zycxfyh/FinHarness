# FinHarness Agent Instructions

## Objective

FinHarness is a local-first personal capital review and decision system. The
current product objective is a verified material capital decision review:

```text
trusted capital state
-> admitted evidence
-> reviewable decision candidate
-> human decide / defer / reject
-> outcome review and learning
```

Read [`docs/current-system.md`](docs/current-system.md) before substantial work.
Do not infer current capability or authorization from an old proposal, review,
roadmap, note, branch, or conversation.

## Truth hierarchy

Use the smallest canonical owner for each fact:

```text
current work and sequence:
  GitHub Issue/PR state, labels, and native relationships

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

verified engineering debt:
  docs/governance/debt-register.json

product direction:
  docs/product/ and docs/product-north-star.md

historical evidence:
  ADRs, proposals, reviews, notes, archived files, and Git history
```

A prose document may explain or link to a machine-owned fact. It must not become
a second mutable registry.

## Start every substantial task

1. Confirm the repository, exact `main` SHA, Issue, branch, and requested scope.
2. Identify the current production owner, direct consumers, tests, and relevant
   current documentation.
3. State the failure being solved and whether it is reversible.
4. Prefer the smallest change that advances one end-to-end product result.
5. Record explicit non-goals before adding a cross-cutting mechanism.

Do not start from a historical implementation plan and assume its remaining
checklist is still authorized.

## Engineering order

Use this order:

1. delete or retire a duplicate mechanism;
2. use the existing canonical repository boundary;
3. use a standard-library, platform, official, or mature-project capability;
4. add the smallest adapter or FinHarness-specific policy needed;
5. add a new abstraction only after the earlier options are demonstrably
   insufficient.

"Future flexibility" is not evidence for a new platform layer. Do not create a
second state store, workflow identity, SHA classifier, authorization language,
event log, provenance format, Agent loop, documentation registry, or financial
engine without an observed gap and a named replacement/deletion target.

FinHarness should own capital-specific semantics that external tools cannot
decide: capital-truth admission, evidence admission, decision meaning,
DecisionReadiness, mandate/authority policy, review, receipts, and learning.
Mature tools should own commodity data, calculation, execution, and platform
mechanics where suitable.

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

- run the smallest relevant checks first;
- keep Draft pull requests cheap and diagnostic;
- do not repeatedly invalidate exact-head full evidence for minor intermediate
  edits;
- freeze the final candidate, run the required exact-head checks, review the
  actual diff, and merge with the expected head SHA;
- do not treat CI green as proof that the product direction or abstraction is
  correct.

A convincing model answer, generated artifact, receipt count, test count, or
label does not prove task completion. Completion requires the Issue's user or
system outcome and its necessary evidence.

## Documentation rule

Create or update maintained documentation only when it does at least one of the
following:

- enables a real supported task;
- explains a durable decision or boundary that code cannot express;
- assigns one canonical fact owner;
- preserves unique evidence that Git history alone cannot make discoverable;
- materially reduces future diagnosis, restart, or handoff cost.

Ordinary reversible implementation details belong in code, tests, commits, and
the owning Issue. They do **not** require a proposal, module upgrade log, review,
lesson, idea record, or roadmap update by default.

Use:

- an ADR for a durable architectural decision whose rationale will matter after
  the implementation changes;
- a proposal only when a substantial cross-cutting choice must be reviewed
  before implementation;
- a review only when an outcome, failure, or experiment produced reusable
  evidence not already captured by the PR and tests;
- a lesson only when repeated evidence changes future behavior.

Do not rewrite historical evidence to look current. Classify it and point to the
current authority when necessary.

## Work-state rule

GitHub is the mutable work-state system.

- Open Issues define bounded work or explicit future gates.
- `status:active` authorizes implementation.
- `status:dormant` and `status:deferred` do not authorize work.
- Program bodies describe stable outcomes and investment logic; they must not
  copy changing child status.
- Avoid creating a new Issue when an existing owner can accept the finding
  without mixing responsibilities.
- Close or transfer temporary owners when their bounded purpose is complete.

One product mainline may have multiple non-conflicting observations or audits,
but do not run competing implementation paths against the same authority
surface.

## Irreversible safety kernel

Use hard blocking controls for failures that cannot be cheaply undone:

- secret or credential disclosure;
- real external execution, transfer, deployment, DNS, or cloud mutation;
- destructive user-data or schema migration without restore evidence;
- authority escalation or bypass;
- loss of unique receipt, provenance, or recovery evidence;
- final review/test evidence bound to the wrong commit;
- current product surfaces claiming unsupported capability.

Treat ordinary internal code, tests, documentation, and unshipped UI as
reversible unless evidence shows otherwise. Prefer fast detection, clear logs,
Git rollback, and repair over speculative pre-action gates.

Current execution remains simulated-only. There is no real broker SDK, funded
account, credential loader, external venue submission, live trading, transfer,
or tax submission path. Raw model text never mutates canonical state or invokes
an external effect.

## Minimum completion report

For substantial work, report only:

- exact final head;
- changed responsibility and deleted duplicate responsibility;
- checks actually run and their result;
- unresolved material debt;
- rollback/recovery boundary when relevant.

Do not create ceremonial artifacts solely to restate information already present
in the Issue, diff, checks, and Git history.
