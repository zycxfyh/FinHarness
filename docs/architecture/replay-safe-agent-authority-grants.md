# Replay-safe AgentAuthorityGrant contract

`AgentAuthorityGrant` is a principal- and runtime-bound credential for doing
bounded, non-execution work under one immutable `CapitalMandateVersion`. It is
not authentication, an approval, an order, a preflight bypass, or execution
authority.

## Binding and scope

Every new grant records the authenticated principal, target agent runtime, and
exact mandate version. Its scope may narrow the mandate by product,
instrument, action, direction, notional, and broker. Product, instrument,
action, and notional must be subsets of the mandate's typed limits; direction
and broker are additional grant restrictions because the mandate does not yet
define those dimensions. A new effective version of the same mandate makes the
old grant invalid.

Legacy grants remain readable after the v6 State Core migration. The migration
does not invent identity or version bindings, so those rows cannot enter the
AUTH-03 consumption path.

## Validation and consumption

Validation is read-only and checks grant lifecycle, expiry, principal, runtime,
mandate lifecycle/version, requested scope, usage totals, and optional nonce.
It returns closed deny reasons and never consumes capacity.

Consumption is the only operation that spends capacity. It requires an
authenticated agent runtime and performs the following in one database
transaction:

1. lock the grant/write path;
2. re-check nonce uniqueness, maximum uses, and aggregate notional;
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
