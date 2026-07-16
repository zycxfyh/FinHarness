# Server-Owned Actors for Governed Review Writes

Status: accepted  
Issue: #364  
Baseline: `main@0b7f146480fdcab3194b7944d6dbec6fd8ce28dd`

## Decision problem

Several governed HTTP commands authenticated an `OperatorContext` but still
accepted `attester`, `human_attester`, or an identity-receipt reference in the
request body. Authentication could therefore identify Alice while the admitted
row and domain receipt named Bob. The real failure is subject substitution at
the admission boundary, not missing transport authentication.

The canonical identity owner is `OperatorContext`. The canonical durable
request-attempt owner is the existing #352 identity mutation receipt. Domain
rows and receipts remain owned by their StateCore commands. Authentication is
not capital authority and actor provenance does not authorize execution.

## Reference-first classification

- **Adopt:** FastAPI dependency injection supplies one server-authenticated
  context to each write handler. Request DTOs use Pydantic `extra="forbid"` so
  removed actor fields fail closed instead of being ignored.
- **Adapt:** OWASP mass-assignment guidance is applied narrowly by allowlisting
  command fields through typed DTOs and keeping actor identity outside caller
  binding. FinHarness additionally records its domain-specific row/receipt
  provenance.
- **Own:** FinHarness owns which authenticated identity authors a governed
  record: use `agent_runtime_id` when an authenticated runtime exists,
  otherwise use `principal_id`. It also owns the distinction between actor
  identity, capital authority, and execution authorization.

No new authentication provider, actor registry, receipt store, lifecycle, or
commit protocol is introduced.

## Executable invariant

For the five routes listed in
`docs/governance/receipt-backed-write-registry.json` under
`authenticated_actor_contract`:

1. caller actor and caller identity-receipt fields are forbidden;
2. the admitted actor is `OperatorContext.authoritative_actor_id`;
3. for keyed writes, the domain receipt uses the actor and canonical reference
   from the executing server identity-mutation claim;
4. typed reconciliation verifies the mutation actor, domain receipt actor, and
   persisted row actor agree;
5. legacy display labels remain explicitly unverified and non-authoritative;
6. all objects continue to carry no capital or execution authority.

The route inventory is exact rather than count-only: route, request model,
forbidden fields, domain actor field, and receipt context are frozen together.

## Adversarial cases

- Alice authenticates but submits `attester=Bob`: DTO validation returns 422
  before domain admission.
- Agent runtime A submits runtime B or a parallel actor field: no request actor
  field exists, and a mutation claim differing from `OperatorContext` is
  rejected.
- A caller supplies another principal's identity receipt to CapitalMandate:
  the request field is forbidden; only the server mutation claim can provide
  the reference.
- A response is lost and the process restarts: the same key replays the exact
  response and actor binding without creating another row.
- A future route is added beside the contract: exact route-inventory tests fail
  until its actor owner and domain fields are reviewed.

## Current and target conformance

Historical records can contain free-text actor labels and are not upgraded to
verified identities. New writes on the five routes conform after this change.
For keyed writes, row, domain receipt, and identity-mutation provenance are
linked. Unkeyed writes still receive the existing post-response identity
receipt, but the domain record does not backfill that reference; completing a
power-loss-safe cross-medium commit remains #352.

## Non-goals

- migrating or certifying historical free-text labels;
- completing #352's cross-medium commit protocol;
- granting capital authority, approval, broker access, or execution authority;
- changing persistence schemas, public read models, authentication providers,
  or dependencies;
- creating a second actor registry or receipt mechanism.

## Primary references

- FastAPI, Dependencies: <https://fastapi.tiangolo.com/tutorial/dependencies/>
- OWASP, Mass Assignment Cheat Sheet:
  <https://cheatsheetseries.owasp.org/cheatsheets/Mass_Assignment_Cheat_Sheet.html>
