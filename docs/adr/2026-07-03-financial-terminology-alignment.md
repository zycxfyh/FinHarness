# ADR: Align Financial Terminology Without Replacing Governance Primitives

Date: 2026-07-03
Status: accepted

## Context

FinHarness now has current primitives for `CapitalMandate`,
`AgentAuthorityGrant`, `ActionIntentCandidate`, `ActionIntentAuthorityBinding`,
`ActionIntentPreflight`, `ActionIntentSimulationReport`, and
`TradePlanCandidate`. More primitives are expected, including
`TradePlanReviewGate`, `OrderTicketCandidate`, and `BrokerSubmissionGate`.

The code debt is still controlled, but concept debt can accumulate if each new
object is explained only in FinHarness-specific language. External readers may
mistake the project for inventing finance from scratch.

The opposite failure is also possible. Renaming everything to canonical finance
terms would imply authority FinHarness does not have: adviser status, broker
status, fiduciary status, order routing, best execution, or execution.

## Decision

FinHarness will keep internal governance primitives when canonical finance
terms are too broad or authority-implying, while aligning their external meaning
to canonical finance vocabulary.

The durable reference is:

```text
docs/reference/financial-terminology-map.md
```

New capital-governance primitives should be documented with this shape:

```text
Canonical finance term
  <-> FinHarness primitive
  <-> Governance / receipt meaning
```

The financial terminology map is governed by the existing two-layer language
policy in `docs/adr/2026-06-18-controlled-vocabulary-and-two-tier-language.md`.
It extends that policy into capital-market and investment-control vocabulary.

## Boundary

Financial and regulatory references are design analogies, not compliance
claims.

This ADR does not claim FinHarness is:

- a broker-dealer
- a registered investment adviser
- a fiduciary system
- an OMS or EMS
- an exchange or execution venue
- a best-execution system
- a regulatory compliance certification system
- live-trading infrastructure

It also does not authorize renaming current API fields or database models to
canonical finance terms without a separate migration decision.

## Consequences

Positive:

- New primitives can be placed in a finance vocabulary coordinate system.
- External explanations can lead with familiar terms while preserving
  FinHarness-specific governance precision.
- Non-claims remain attached to each authority-bearing concept.

Negative:

- The map must be updated when capital-governance primitives are added or
  promoted.

Neutral:

- This is still lightweight documentation governance. It does not introduce
  FIBO, ISO 20022, SKOS, ontology tooling, or schema migrations.

## Links

- `docs/reference/financial-terminology-map.md`
- `docs/reference/glossary.md`
- `docs/adr/2026-06-18-controlled-vocabulary-and-two-tier-language.md`
- `docs/adr/2026-07-02-capital-mandate-before-delegated-authority.md`
- `docs/adr/2026-07-03-agent-authority-grants-are-mandate-bound-credentials.md`
- `docs/adr/2026-07-03-action-intent-authority-bindings-admit-only-to-next-governance-step.md`
