# ADR: AgentAuthorityGrant As Mandate-Bound Credential

Status: accepted

Date: 2026-07-03

## Context

`CapitalMandate` now records the human-attested policy domain that future
authority objects may cite. It deliberately does not grant an Agent identity,
approve a trade plan, create broker authority, or authorize execution.

The next authority object must therefore answer a narrower question:

```text
Does this Agent currently hold a bounded authority credential under an active
CapitalMandate, and is the requested scope within that credential?
```

This must not become a large execution permission system. Hermes-style runtime
patterns suggest separating caller authorization, tool visibility, approval UX,
runtime validation, and actual execution boundaries. FinHarness needs the same
separation, but with capital-domain policy enforced as hard product logic rather
than a prompt-level convention.

## Decision

Add `AgentAuthorityGrant` as a StateCore v0 object:

- mandate-bound: every grant references `capital_mandate_id`;
- receipt-backed: every grant writes a `state_core_agent_authority_grant`
  receipt and `ReceiptIndex` row;
- dynamically validated: validation re-checks the grant and linked mandate at
  use time;
- structured: validation returns `allowed`, closed `deny_reasons`, scope booleans,
  and explicit non-authority flags.

Grant creation fails closed unless:

- the referenced `CapitalMandate` exists and is `active`;
- `agent_id`, `issued_by`, and `issued_reason` are present;
- `grant_scope` is within the mandate's asset/action/autonomy scope;
- `grant_scope` contains no execution, approval, broker, or preflight-bypass
  semantics.

Grant validation fails closed when:

- the grant is missing, revoked, suspended, or expired;
- the linked mandate is missing or no longer active;
- the current grant scope exceeds the current mandate scope;
- requested scope exceeds grant scope;
- grant or requested scope contains forbidden execution, approval, broker, or
  preflight-bypass semantics.

The deny reason set is closed so later preflight or authority layers can consume
results without parsing prose.

## Non-Claims

`AgentAuthorityGrant` is not authentication. It does not prove who or what an
Agent is outside FinHarness.

`AgentAuthorityGrant` does not approve trade plans, submit orders, create broker
authority, bypass preflight, authorize execution, or replace future
`AuthorityContract` work.

`AgentAuthorityGrant` is not a profile/tool runtime bypass. Agent profiles remain
product postures; stronger runtime abilities still need explicit tools, evidence
carriers, receipts, tests, and review contracts.

## Consequences

Future `SuitabilityCheck`, `AuthorityContract`, order-ticket, paper/live
execution, or broker-submission work may consume `AgentAuthorityGrant` validation
results, but may not treat them as execution authorization.

The receipt is audit evidence. Current grant state and current mandate state are
the authorization facts used by validation.

Any future exception path must explain how it preserves default-deny behavior
when no active mandate-bound grant exists.
