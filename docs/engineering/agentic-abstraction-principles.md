# Agentic Engineering Principles

This document defines FinHarness's stable engineering responsibility model. It is
not an abstraction catalog, implementation roadmap, PR form, or permission
system. Update it only when the responsibility model itself changes.

## 1. Thin core

A capable Agent needs a small, accurate world model:

```text
current product and non-capabilities
+ requested result
+ canonical fact owners
+ production entrypoints
+ consequence boundaries
+ recovery path
```

More context is not automatically better. Every maintained page, registry, and
projection consumes attention and can inject stale or contradictory state.
Source code, executable tests, `Taskfile.yml`, routes, models, Git, and GitHub own
facts they already express. Prose explains durable intent and boundaries; it does
not copy the repository.

## 2. Responsibility split

```text
Human Principal
  owns goals, values, preferences, resources, legitimacy, consequence limits,
  mandate, revocation, and final trade-offs

Agent
  owns exploration, implementation, refactoring, testing, diagnosis, routine
  operation, local planning, and reversible repair within the requested scope

FinHarness
  owns capital-specific meaning, canonical state, admission, authority over real
  consequences, effect dispatch, receipts, reconciliation, replay, and recovery

Deterministic systems
  own calculations, schemas, transactions, invariants, idempotency, and
  replayable facts

Git and GitHub
  own implementation history, collaboration state, reviewed candidates, and
  ordinary rollback
```

Model output is evidence or a candidate until a canonical boundary admits it.
Authentication is not capital authority. Tool possession is not authority to
create every effect the tool could technically reach.

## 3. Recovery before restriction

Treat ordinary code, tests, branches, commits, documentation, and unshipped UI as
reversible work. Prefer:

```text
act -> observe -> repair -> verify -> Git rollback when needed
```

Recovery ownership is explicit:

- Git owns code and documentation rollback;
- verified backups own persistent State Core and receipt-root recovery;
- idempotency, receipts, reconciliation, revocation, and compensation own
  external-effect recovery;
- exact-head checks own final-candidate verification.

Do not create a second history, debt database, deletion ledger, workflow identity,
or proof registry beside those owners.

## 4. Hard boundaries follow consequences

Hard blocking controls are justified for concrete high-loss outcomes:

- secret or credential disclosure;
- destructive persistent-state migration without restore evidence;
- loss of unique evidence or receipts;
- stale or false capital truth entering a claimed decision;
- principal confusion, authority escalation, or revocation bypass;
- duplicate or unauthorized external effects;
- final evidence bound to the wrong commit;
- product surfaces claiming unsupported capability.

Warnings, architectural preferences, prose shape, taxonomy, and ordinary
reversible implementation mistakes do not become blockers by default.

## 5. Extend through stable boundaries

High extensibility comes from a few durable ports, not from prebuilding every
future abstraction. Prefer, in order:

1. delete a duplicate mechanism;
2. use the existing canonical boundary;
3. adopt a standard, official tool, or mature library;
4. add the smallest FinHarness-specific adapter or policy;
5. introduce a new abstraction only after an observed failure proves the earlier
   options insufficient.

FinHarness should own the capital semantics external tools cannot decide:
capital-truth admission, evidence admission, DecisionCase identity,
DecisionReadiness, consequence authority, human review, receipts,
reconciliation, and learning admission. Commodity data access, calculations,
model runtimes, development tools, and execution mechanics should remain
replaceable where mature implementations exist.

## 6. Delivery and proof

Prefer one vertical result:

```text
real input
-> canonical domain boundary
-> user or Agent visible result
-> relevant denial or failure path
-> durable evidence and recovery
```

Agents may directly perform ordinary reversible engineering work. Run the
smallest useful checks while iterating, then freeze the candidate and run the
required exact-head checks. Test counts, receipts, labels, generated diagrams,
or convincing model text do not prove completion; the requested behavior and its
consequence-appropriate evidence do.

New registries, policy languages, Agent loops, workflow engines, state stores,
long-term memory systems, or multi-Agent coordination require a repeated observed
need. Future flexibility alone is not evidence.
