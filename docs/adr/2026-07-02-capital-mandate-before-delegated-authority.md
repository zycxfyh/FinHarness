# ADR: CapitalMandate Before Delegated Authority

Status: accepted

Date: 2026-07-02

## Context

FinHarness has moved from read-only capital state into a governed action chain:
IPS, proposals, review, ActionIntentCandidate, action preflight, qualitative
simulation, and TradePlanCandidate. That creates pressure to define the policy
surface for future delegated capital authority before adding any actual
AgentAuthorityGrant, SuitabilityCheck, AuthorityContract, order ticket, or
broker adapter.

The previous North Star wording said "AI never owns execution authority". That
was useful while the system was only read/review, but it is too blunt for the
next design boundary. The durable product rule is more precise:

```text
Agent does not default to a high-consequence identity.
Future delegated identity is possible only through explicit, bounded,
revocable, receipt-backed authority objects.
```

## Decision

Add `CapitalMandate` as a StateCore v0 object above IPS and before any delegated
authority object.

`CapitalMandate` records:

- the source IPS, if present;
- profile snapshot, investment objectives, and risk profile;
- allowed/restricted asset classes and action types;
- autonomy level, limit book, kill-switch rules, and review cadence;
- human attester, written human reason, and explicit confirmation;
- source refs, receipt refs, non-claims, and a receipt ref.

`CapitalMandate` is receipt-backed and active/superseded like IPS. The receipt
is the source of truth; the SQLite row is the query mirror.

`CapitalMandate` is stricter than IPS on authority boundaries:

- `human_attester` is required in the domain record; as amended by #364, the
  HTTP command derives it from server-authenticated `OperatorContext` rather
  than accepting it from the request body;
- `human_reason` is required;
- `explicit_confirmation=true` is required;
- `execution_allowed=false` is enforced;
- `authority_transition=false` is enforced.

It does not replace IPS. IPS remains the user-owned investment policy statement
used for threshold mapping and descriptive compliance checks. CapitalMandate is
the higher policy domain future authority objects may cite.

## Consequences

Future AgentAuthorityGrant, SuitabilityCheck, AuthorityContract, paper/live
execution, or order-ticket work must reference an active CapitalMandate or
explicitly explain why it does not.

CapitalMandate does not itself authorize execution, grant an Agent identity,
approve a trade plan, submit to a broker, or relax any existing backend boundary.

The Product North Star now uses the sharper language "Agent does not default to
high-consequence authority" instead of relying only on the older absolute
"AI never has execution" shorthand.

Documentation that describes IPS / Policy, Capital OS layering, API interfaces,
and system catalogs must mention CapitalMandate once it ships, because the policy
layer now carries more complexity than IPS alone.
