# Replay-safe AgentAuthorityGrant contract

`AgentAuthorityGrant` is a principal- and runtime-bound credential for doing
bounded, non-execution work under one immutable `CapitalMandateVersion`. It is
not authentication, an approval, an order, a preflight bypass, or execution
authority.

## Binding and scope

Every new grant records the authenticated principal, target agent runtime, and
exact mandate version. Its scope may narrow the mandate by product,
instrument, action, direction, notional, and broker. Product, instrument,
action, direction, broker, and notional must be subsets of the mandate's typed
limits. Direction and broker may be open only when the exact mandate version
uses the closed typed `wildcard` mode; an omitted scope is bounded-empty, and
the string `*` is never an implicit wildcard. A new effective version of the
same mandate makes the old grant invalid.

Mandate limits, grant total/per-use limits, requested use, stored consumption,
and receipt usage totals use one closed `{amount, currency}` contract. Amounts
are exact `Decimal` values and currency is a normalized three-letter alphabetic
code. Authority performs no FX conversion: different currencies are
incomparable and fail closed. A grant has one accounting currency derived from
its exact mandate version; all of its consumption rows must carry that same
currency.

At every use, the exact persisted mandate limit book is revalidated through
the closed typed contract. The effective per-use cap is the grant scope's
explicit narrower `max_notional`, or the exact mandate version's
`max_notional` when the grant omits one. An optional grant total cap is an
additional cumulative bound; it never replaces the mandate per-use cap.
Persisted grant currency, total cap, and scope cap are rechecked against that
exact mandate before and after the consumption lock.

Legacy grants remain readable after the State Core migrations. Migrations do
not invent identity, version, or currency bindings. A legacy row with no
currency is classified `legacy_currency_unbound_grant` and cannot enter the
consumption path; a mixed or malformed consumption history is classified
`currency_mismatch` rather than summed as bare numbers.

## Validation and consumption

Validation is read-only and checks grant lifecycle, expiry, principal, runtime,
mandate lifecycle/version, requested scope, usage totals, and optional nonce.
It returns closed deny reasons and never consumes capacity.

Consumption is the only operation that spends capacity. It requires an
authenticated agent runtime and performs the following in one database
transaction:

1. lock the grant/write path;
2. re-check the exact typed mandate money contract, effective per-use cap,
   nonce uniqueness, maximum uses, currency, and exact aggregate notional;
3. append `AgentAuthorityGrantConsumption` and its indexed receipt;
4. commit both or remove the uncommitted receipt.

The unique `(grant_id, nonce)` constraint is the final replay guard. SQLite
uses `BEGIN IMMEDIATE`; databases with row-lock support use `FOR UPDATE`.

## Revocation and non-claims

Only the authenticated owning principal may revoke a grant. Revocation updates
the query projection and appends an indexed before/after lifecycle receipt in
one locked transaction. Expired, revoked, superseded, exhausted, cross-user,
cross-runtime, and replayed uses fail closed.

Grant validation and consumption always return `execution_allowed=false` and
`authority_transition=false`. AUTH-04 admission proofs and any future
execution capability remain separate contracts.
