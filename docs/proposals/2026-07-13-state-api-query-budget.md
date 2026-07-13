# State API query budget mini-RFC

## 1. Change Class

**C3.** The slice changes default read behavior at the financial-state boundary:
collections become bounded and historical positions require explicit snapshot scope.

## 1b. Product Claim / Layer / Thin Slice

This advances the L1/L2 Capital Map read surface. The thin slice is bounded State
API collections plus an equivalent, aggregate-backed dashboard summary; it adds no
write, advice, or execution capability.

## 1c. Module Placement / System Boundary

The change stays inside the existing API/Cockpit System and State Core read-model
boundary from `system-map.md`. Routes continue to read State Core through SQLModel;
no second persistence or truth system is introduced, and no cockpit tab is added.

## 2. Current behavior

State collection routes load complete tables by default. Position reads can combine
all snapshots, snapshot history is unbounded, and dashboard counts/sums instantiate
complete model collections.

## 3. Target behavior

The default collection page is 100 rows, callers may request at most 200, and
`offset` follows a deterministic order. Position reads require `snapshot_id`.
Dashboard counts and totals use SQL aggregates and bounded current projections.

## 4. Surface Inventory

- **Inputs:** existing filters plus `limit` and `offset`; required position `snapshot_id`.
- **Outputs:** existing bare JSON arrays and unchanged dashboard response schema.
- **External calls / network:** none.
- **Failure surface:** invalid/missing scope and out-of-budget limits return FastAPI 422.
- **User-visible surface:** bounded result sizes; unscoped position history is rejected.
- **Excluded:** writes, schema migrations, current/as-of resolution, and keyset cursors.

## 5. Default Path Invariant

The response shapes and small-data ordering remain unchanged, but collection size is
intentionally bounded. OpenAPI contract tests lock the 100/200 budget, compatibility
tests lock existing small responses, and large-history tests lock deterministic pages
and explicit position scope. This default change is authorized by issue #347.

## 6. Traceability Matrix

| Design commitment | Code | Test | Gate probe |
| --- | --- | --- | --- |
| Bounded deterministic collections | `api/routes_state.py` | `test_state_collections_apply_documented_query_budget`; `test_large_history_is_bounded_and_pages_are_stable` | OpenAPI min/default/max and page assertions |
| Explicit position history scope | `api/routes_state.py` | `test_large_history_is_bounded_and_pages_are_stable` | Missing scope and limit 201 both return 422 |
| Aggregate dashboard with current-revision semantics | `api/routes_cockpit.py` | dashboard aggregate/open-count tests | Captured SQL rejects full-table model selects |
| Governance classification stays current | attestation consumer inventory | inventory/current-doc tests | `task governance:inventory` |

## 7. Test / Gate Plan

`task check:timed` covers unit, OpenAPI contract, integration, frontend, governance,
architecture, and isolated dependency profiles. Design review checks the deliberate
default change and read-only boundary; implementation review checks SQL aggregation,
attestation semantic parity, stable pagination, and absence of network/writes. Required
GitHub security and local-verification checks provide the independent merge gate.

## 8. Product Surface Review

Operators receive predictable response sizes and cannot silently mix historical
position snapshots. The existing dashboard remains visually unchanged while its cost
scales with aggregate queries instead of history size.

## 9. Not Claimed / Debt

This does not claim snapshot-isolated pagination across concurrent writes, keyset
cursors, a generic pagination envelope, or authoritative current/as-of resolution.
Those remain separate work, including #258 and the retention/compaction track.

## 10. Release Decision

**Merge now after required CI succeeds.** The slice removes unbounded financial-state
reads, preserves response schemas, has explicit rollback by reverting the route/query
change, and is covered by large-history, SQL-shape, semantic-parity, and full-gate tests.
