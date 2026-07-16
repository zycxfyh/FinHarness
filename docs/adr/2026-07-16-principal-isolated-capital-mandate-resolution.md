# ADR: Principal-Isolated CapitalMandate Resolution

## Status

Accepted for Issue #365 on `main@76bb0992d507785323686adf4a08f65a41e780cf`.

## Problem

`record_capital_mandate` globally superseded every active compatibility row.
Grant validation then consumed that mutable row status in addition to the
principal-bound version resolver. A Bob mandate could therefore mark Alice
superseded and invalidate Alice grant even though Alice immutable version still
resolved active. Reusing Alice mandate ID also created a Bob version and
overwrote the mirror before any ownership check. Version and lifecycle queries
had only partial ordering, so equal effective times depended on SQLite row
order.

## Decision

The existing boundaries remain canonical:

- HTTP ownership comes from `OperatorContext.principal.principal_id`.
- A mandate series is permanently owned by its one durable
  `CapitalMandateVersion.principal_id`.
- `resolve_capital_mandate(principal_id, at_utc)` is the only currentness owner.
- `CapitalMandate` is a query mirror and compatibility snapshot, not authority
  truth.
- `AgentAuthorityGrant.principal_id` and `mandate_version_id` bind the exact
  policy basis.

An existing ID with another durable owner is rejected before receipt creation,
version creation, activation evidence, ReceiptIndex, or mirror upsert. A legacy
row without a version remains readable but cannot be claimed from
`human_attester`, `legacy_actor_label`, or any other unverified prose.

Mirror supersession is restricted to rows whose durable version owner equals
the new mandate principal. The activation receipt for the new version is the
evidence for a same-principal current-series change; mirror status does not
create lifecycle truth.

## Stable total order

The principal resolver compares eligible immutable versions in descending
order by:

1. `effective_at_utc`: later domain-effective policy wins.
2. `created_at_utc`: for the same effective instant, later recorded policy wins.
3. `version_number`: refines ties within a versioned series.
4. `capital_mandate_id`: stable lexical tie-breaker across distinct series.
5. `mandate_version_id`: stable final tie-breaker for all persisted candidates.

Lifecycle events compare descending `effective_at_utc`, `created_at_utc`, then
`mandate_lifecycle_event_id`. The identifiers have no economic, risk, or
permission meaning; they exist only to eliminate insertion-order ambiguity.
All timestamp comparisons parse persisted UTC values rather than relying on
SQLite text collation.

## Grant behavior

Create-time and use-time checks resolve the grant principal at the validation
time. They require an active result and exact equality of principal, mandate ID,
and mandate version ID. A same-principal new version or different current
mandate ID yields `mandate_version_changed`. Another principal mandate cannot
change the result. Scope validation consumes the immutable bound version policy,
not mutable mirror fields. Locked consumption and downstream ActionIntent and
autonomy consumers reuse the same validator.

## Reference-First classification

- **Adopt:** existing SQLModel/SQLite persistence and transaction patterns.
- **Adapt:** existing receipt writer and append-only lifecycle evidence with
  fail-closed owner preconditions and deterministic ordering.
- **Own:** FinHarness mandate ownership, lifecycle meaning, and exact-version
  grant validity.

No external mechanism is required for this bounded correction. A second
resolver, actor registry, authorization engine, lifecycle framework, store, or
protocol would duplicate existing owners.

## Non-goals and non-claims

This does not implement #366 currency, broker, direction, or grant-scope repair.
It does not implement #390 governed-write CAS or #352 cross-medium commit. It
does not add household, organization, tenant, role, broker, or live-execution
semantics.

Authentication identity is not capital authority. An active CapitalMandate is
not execution authorization. A valid AgentAuthorityGrant is not approval,
preflight bypass, broker submission, or execution authority. All new objects
retain `execution_allowed=false` and `authority_transition=false`.
