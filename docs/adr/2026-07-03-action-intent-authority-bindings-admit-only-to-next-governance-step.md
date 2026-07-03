# ADR: ActionIntentAuthorityBinding Admits Only To The Next Governance Step

Status: accepted
Date: 2026-07-03

## Context

`CapitalMandate` records the human-attested policy domain. `AgentAuthorityGrant`
records a mandate-bound Agent credential and dynamically validates the current
grant plus linked mandate. The next mainline gap is not execution, order
creation, or trade approval. It is the authority admission question:

```text
May this author admit this ActionIntentCandidate into downstream capital-action checks?
```

If this is modeled as only `ActionIntent.agent_authority_grant_id`, downstream
preflight will have to reinterpret AgentAuthorityGrant semantics and may drift.
The system needs a receipt-backed admission fact that preserves structured
deny reasons before preflight, simulation, trade-plan review, order-ticket
candidate, or broker submission logic.

## Decision

Add `ActionIntentAuthorityBinding` as a thin, receipt-backed admission artifact.

The binding records:

- `action_intent_id`
- `author_type`: `agent`, `human`, or `system`
- `author_id`
- optional `agent_authority_grant_id`
- resolved `capital_mandate_id` when an Agent grant validates
- requested and validated scope
- `allowed`
- binding-layer deny reasons
- preserved AgentAuthorityGrant validation deny reasons
- receipt refs and non-claims

Rules:

- Agent-authored ActionIntentCandidates must reference
  `agent_authority_grant_id`.
- The server validates AgentAuthorityGrant at binding time and preserves its
  structured deny reasons.
- Human-authored ActionIntentCandidates may omit grants.
- System-authored ActionIntentCandidates may omit grants only when a source
  rule is recorded.
- Denied bindings are still persisted as governance evidence.
- Binding `allowed=true` means only admission into downstream checks.

## Boundary

`ActionIntentAuthorityBinding` is not:

- action preflight
- trade-plan approval
- order-ticket creation
- broker submission
- preflight bypass
- authentication
- AuthorityContract
- execution authorization

Each layer grants admission only to the next governance step, never skipped
execution authority.

## Consequences

#97 can make ActionIntent preflight authority-aware by reading the latest/current
binding result and its receipt, instead of reimplementing grant semantics.

Future freshness and TOCTOU checks can require a current binding that still
matches the current ActionIntent, grant, and mandate state, but that belongs in
preflight or a later gate. This ADR only establishes the admission artifact and
its non-execution boundary.
