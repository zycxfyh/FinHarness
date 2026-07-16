# ADR: Agent Authority Money and Scope Fail Closed

## Context

`AgentAuthorityGrant` compared notional amounts after discarding currency and
treated direction and broker dimensions as unbounded by the parent mandate.
That allowed superficially smaller cross-currency values and mandate-absent
scope members to pass. Existing persisted grants and consumptions also lacked a
durable currency binding.

The authority boundary must not own valuation or FX. It must decide only
whether a requested use is inside one exact, principal-owned mandate version.

## Decision

Adopt three-letter alphabetic currency representation and Python `Decimal` for
exact amounts. Adapt the repository's closed Pydantic contracts, TEXT money
storage, receipt-backed writes, SQLModel migrations, and locked consumption
path. Own only FinHarness authority semantics:

- one closed `MonetaryAmount` value is used at mandate, grant, API, validation,
  consumption, result, and receipt boundaries;
- one grant is durably bound to one currency derived from its exact mandate;
- cross-currency comparison is denied; authority never guesses an FX rate;
- direction and broker values are subsets of the mandate version unless that
  dimension has the explicit closed `wildcard` mode;
- omitted scope is bounded-empty and the string `*` has no special power;
- nullable migration columns preserve old rows without inventing currency;
- legacy currency-less grants and mixed-currency histories are typed denials.

Validation remains read-only. Consumption revalidates under the existing write
lock and persists the amount and currency together. Nonce uniqueness, exact
aggregate limits, revocation, expiry, principal/runtime binding, and the
non-execution boundary remain unchanged.

## Adversarial cases

The executable contract rejects a JPY grant or use under a USD mandate, a sell
direction under a buy-only mandate, an unlisted broker, unknown money fields,
ambiguous wildcard-plus-values, legacy null currency after restart, mixed
consumption currencies, replay, and concurrent attempts to spend the same
remaining capacity.

## Consequences and non-goals

New grant and consumption API callers must send `{amount, currency}` rather
than a bare number. No dependency, FX service, currency registry, broker
connection, execution capability, AdmissionProof, or general permissions
framework is introduced. ISO 4217 publication defines the external code
vocabulary; FinHarness validates only the closed three-letter representation
and does not claim to maintain a second currency registry.
