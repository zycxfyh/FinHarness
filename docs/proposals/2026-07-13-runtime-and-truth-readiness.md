# Runtime and capital-truth readiness mini-RFC

## 1. Change Class

**C3.** This slice changes a public operational contract and interprets evidence at
the financial-state boundary. It adds no execution or external-network capability.

## 1b. Product Claim / Layer / Thin Slice

This advances the L0 runtime and L1/L2 Capital Map trust surface. The thin slice is
three separate signals: process liveness, operational dependency readiness, and
bounded latest-import capital-truth readiness.

## 1c. Module Placement / System Boundary

The change remains inside the API/Cockpit System and reads the existing State Core
and immutable Artifact Store. `readiness.py` is the shared boundary module for both
new routes; it introduces no persistence system, migration path, cockpit tab, or
reverse dependency into State Core.

## 2. Current behavior

`GET /health` always returns `ok` when the API process answers. It also reports an
optional data-surface dependency, but does not establish that State Core, receipt
storage, immutable artifacts, or current capital evidence are usable. Operators can
therefore mistake liveness for readiness.

## 3. Target behavior

`/health` remains cheap and explicitly claims liveness only. `/ready` checks required
runtime dependencies without initializing or migrating them. `/ready/truth` inspects
exactly the latest materialized production-capital manifest and its directly bound
snapshot, receipt index, receipt file, source artifact, and receipt artifact. It
fails closed while distinguishing missing, corrupt, stale, partial, and unavailable
states.

## 4. Surface Inventory

- **Inputs:** configured State Core path/engine and state-core receipt root.
- **Outputs:** typed readiness status, named checks/findings, non-claims, and HTTP
  200/503 status.
- **External calls / network:** none.
- **Failure surface:** missing/corrupt/old-schema database; missing/divergent evidence;
  stale canonical clock; partial import; unreadable or unwritable local storage.
- **User-visible surface:** two new read-only routes and clearer `/health` non-claims.
- **Excluded:** schema creation/migration, probe writes, full-history artifact scans,
  accounting reconciliation, recommendations, and execution authorization.

## 5. Default Path Invariant

`/health` keeps its 200 status, `status: ok`, `execution_allowed: false`, and trace
behavior; a compatibility test locks those fields while adding explicit non-claims.
The two new routes are opt-in reads. The deliberate semantic change is that clients
now have a non-ambiguous readiness contract, authorized by issue #348.

## 6. Traceability Matrix

| Design commitment | Code | Test | Gate probe |
| --- | --- | --- | --- |
| Liveness makes no readiness claim | `api/app.py` | `test_liveness_does_not_claim_dependency_or_truth_readiness` | Health remains 200 while readiness is 503 |
| Runtime probe is non-mutating and fail-closed | `readiness.py` | corrupt DB and unwritable-storage tests | Original corrupt bytes unchanged; storage mode detected |
| Truth evidence is bounded and directly bound | `readiness.py` | usable and missing-artifact tests | One `LIMIT 1` query plus two artifact IDs |
| Truth states remain distinguishable | `readiness.py` | stale/partial/missing tests | Machine-readable finding categories and 503 |
| Public route semantics remain governed | OpenAPI allowlist and attestation inventory | State API/governance tests | Exact route set and current-view regeneration |

## 7. Test / Gate Plan

`task check:timed` covers unit, API contract, architecture, governance, security,
frontend, and isolated dependency profiles. Design review checks separation of the
three claims and the no-mutation/bounded-work constraints. Independent implementation
review checks fail-closed categories, path confinement, immutable evidence hashes,
and absence of execution authority.

## 8. Product Surface Review

Operators and orchestrators can tell whether the process answers, whether it can
serve its required local dependencies, and whether the current capital evidence is
actually admissible. Failures identify the remediation class instead of collapsing
every defect into a misleading `ok` or an opaque 503.

## 9. Not Claimed / Debt

This probe does not perform complete ledger reconciliation, scan historical imports,
measure disk free-space thresholds, validate every materialized row against receipt
payloads, or prove market/FX suitability for decision use cases. Those require their
own bounded contracts and must not be silently folded into liveness.

## 10. Release Decision

**Merge after required CI and independent gate succeed.** Rollback is a direct revert
of the two routes and shared probe module; no schema or stored data changes require a
data rollback.
