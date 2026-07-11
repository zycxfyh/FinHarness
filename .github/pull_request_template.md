## Issue linkage

<!-- Close leaf implementation issues only. Program issues such as #277 use Refs. -->

Closes #
Refs #277

## Baseline

- Baseline `main` SHA:
- Exact head SHA:
- Merge-result SHA, if verified:

## Scope

- What changed:
- User/developer impact:
- Changed files or domains:

## Non-goals

-

## Invariants and boundaries

- Invariants protected:
- Authority/permission boundary:
- Receipt/artifact path:
- Mature wheel or external system used:

## Negative evidence

- Negative fixture:
- Failure observed before the fix:
- Failure observed if the invariant is deliberately broken:

## Persistence and recovery

- Restart/persistence evidence, or why this change is intentionally non-persistent:
- Migration/replay behavior:
- Rollback strategy:

## Verification

- [ ] Relevant focused tests
- [ ] `task check`, or a documented narrower reason
- [ ] Exact-head CI/check evidence recorded
- [ ] Clean-environment evidence when dependency/install behavior changed
- Commands and results:

## Documentation and product claims

- Current docs changed:
- Product/maturity/autonomy claims changed:
- System catalog or interface docs changed:

## Safety checklist

- [ ] No caller-supplied trust state
- [ ] No caller-supplied authority identity
- [ ] No new parallel receipt, artifact registry, or current-state resolver
- [ ] No capability claim based only on model fields or test counts
- [ ] Deferred gates remain closed
- [ ] New write paths update the write/consumer registry
- [ ] Review conversations are resolved or explicitly dispositioned

## Change classification

- [ ] C0 — docs, tests, rename, dependency maintenance
- [ ] C1 — single-module behavior
- [ ] C2 — cross-module, user-visible, or default behavior
- [ ] C3 — financial, tax, network, automation, authority, or security boundary

## Abstraction classification

| Artifact | Current form | Correct layer | Migration path |
| --- | --- | --- | --- |
|  |  |  |  |
