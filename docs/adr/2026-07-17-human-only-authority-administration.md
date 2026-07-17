# ADR: Human-Only Authority Administration

## Status

Accepted for Issue #391.

## Context

`OperatorContext` identifies the server-authenticated principal and optional
Agent runtime. `WriteCapabilityDependency` admits authenticated governed writes.
Neither fact proves that the direct actor may administer `CapitalMandate` or
`AgentAuthorityGrant`.

Before this decision, an authenticated Agent runtime, service principal, or
ordinary human could reach authority write routes. Mandate creation could even
persist an Agent runtime ID as `human_attester`. Route-only checks would leave
the domain functions callable without the same authorization decision.

## Decision

FinHarness uses one closed administration chain:

```text
IdentityProvider
→ OperatorContext
→ AuthorityAdministrationAssertion
→ require_authority_administration
→ authority domain mutation
→ existing domain receipt
```

`PrincipalIdentity.principal_kind` is `human`, `service`, or
`legacy_unknown`. Existing local compatibility identities remain
`legacy_unknown` and do not become administrators.

An `AuthorityAdministrationAssertion` is immutable, rejects unknown fields,
binds one principal and provider, carries the single
`authority_administrator` capability, uses `standard` or `elevated`
authentication assurance, names the exact policy version, and has a closed UTC
validity interval. It is supplied only by the configured identity provider.

`src/finharness/authority_administration.py` owns the one policy version and
the exact operation matrix:

- mandate create/replace, mandate resume, and grant create require elevated
  assurance;
- mandate suspend/revoke and grant revoke require a current human
  administrator but permit standard assurance;
- grant consumption remains an Agent-runtime command and is not authority
  administration.

Every public mandate/grant administration function calls the guard itself and
derives authoritative principal/attester/issuer fields from `OperatorContext`.
Routes translate the typed denial to HTTP 403; routes are not the sole defense.
Mandate lifecycle commands accept one canonical operation only. That operation
owns the assurance requirement, expanding/reducing classification, allowed
source states, resulting lifecycle event type, and receipt operation. Callers
cannot independently label an expanding event as a reducing operation.

Authority-reducing commands are immediate, server-timed mutations. Ordinary
suspend/revoke request models contain a reason but no caller-owned effective or
revocation timestamp. After acquiring the domain write lock, the domain
owner generates one UTC command time and uses it for assertion-currentness
checking, the lifecycle or grant mutation, the Receipt/ReceiptIndex, and the
returned domain state. Future or backdated reduction is not an alternate mode
of the ordinary command. A future scheduled reduction would require a separate,
explicitly calibrated protocol and is outside this Issue.

The successful decision is embedded in the existing mandate, lifecycle, grant,
or grant-revocation receipt. It is evidence for that exact effect, not a token,
DomainRecord, or reusable authorization. It does not participate in
`mandate_content_hash`, because policy content identity and submission
authorization evidence are distinct.

## Replay semantics

An exact same-key idempotent response replay may return a historical successful
response after the current administrator capability changes, because it does
not execute another domain mutation. A new key always evaluates the current
server context and policy. Historical identity receipts, domain receipts, and
assertions never authorize a new command.

A denied keyed attempt may retain one terminal `rejected` API mutation identity
receipt so that the transport idempotency protocol can replay the same denial.
That receipt is non-authoritative transport evidence. Denial creates no domain
receipt, `ReceiptIndex`, mirror mutation, lifecycle event, grant mutation, or
database effect, and the rejected identity receipt cannot authorize replay as a
new command.

## Reference-First classification

### Adopt

- the repository's existing `IdentityProvider`, `OperatorContext`,
  idempotency protocol, mandate/grant domain services, and receipt owners;
- NIST SP 800-63B authentication-assurance and step-up concepts as vocabulary
  for provider results.

### Adapt

- add the minimum closed assertion fields to `OperatorContext`;
- reuse one domain guard for the six FinHarness administration operations;
- add the decision payload to existing receipts.

FinHarness does not claim AAL conformance from the `standard` or `elevated`
labels. The repository does not own the authenticator or verifier lifecycle
needed to make that claim.

### Own

- which FinHarness commands expand or reduce authority;
- the human-only and Agent/service exclusion policy;
- the exact evidence required to review an admitted authority mutation.

## Rejected alternatives

- Request roles or assurance headers: caller-controlled and non-authoritative.
- Caller-owned suspend/revoke timestamps: permit delayed kill switches and
  backdated authority evidence.
- Route middleware as the only guard: direct domain calls bypass it.
- Generic RBAC/ABAC, policy registry, or permissions DSL: no demonstrated need
  and a second authorization lifecycle.
- A local MFA provider: authentication mechanics belong to the identity
  provider.
- Dual-confirmation workflow: requires its own persistence/recovery contract
  and is not approximated in this Issue.
- A second administration receipt: duplicates existing domain receipt
  ownership.

## Consequences

- Existing `LocalOperatorContext` applications retain ordinary governed writes
  but receive typed denial for mandate/grant administration.
- No SQLite migration or new dependency is required.
- Historical receipts remain readable but cannot prove #391 conformance.
- Tests must cover unknown fields, Agent-under-admin, service/ordinary human,
  direct domain bypass, exact operation-to-event binding, assertion freshness,
  emergency reduction, server-owned reduction time, future/backdated time
  injection, keyed-denial transport evidence, revoke-versus-consume behavior,
  exact target binding, restart, and replay/currentness separation.
