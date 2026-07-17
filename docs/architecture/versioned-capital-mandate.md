# Versioned CapitalMandate authority boundary

Status: current AUTH-02 foundation.

`CapitalMandateVersion` is the immutable, principal-bound policy and limit-book
record. The legacy `CapitalMandate` row remains a compatibility projection for
AgentAuthorityGrant until AUTH-03 migrates that consumer; it is not the
authoritative version resolver.

Each version binds a stable mandate series, monotonically increasing version,
canonical content hash, authenticated principal, effective/expiry time,
superseded version, policy payload, closed typed limits, kill-switch scope,
source/receipt references, and optional authenticated-actor receipt.

`CapitalMandateLimits` covers product, instrument, action, exact-decimal
notional, frequency window, and loss boundaries. Authentication establishes the
principal but does not itself grant capital authority. Request payloads cannot
supply `principal_id`; the API binds it from `OperatorContext`.

Lifecycle commands append `CapitalMandateLifecycleEvent` plus a receipt. They do
not mutate version history:

- `activated` / `resumed` resolve active;
- `suspended` fails closed immediately;
- `revoked` is terminal for that version;
- expiry is derived at the requested as-of time.

Ordinary suspend and revoke commands do not accept a caller-owned effective
time. The mandate domain acquires its write lock, generates one server UTC
command time, validates the current administrator assertion at that time, and
uses the same value for the event, Receipt, ReceiptIndex, and response
resolution. Scheduled authority reduction is not represented by these
immediate lifecycle commands.

The resolver takes principal and time explicitly, selects the latest effective
version, then applies the latest effective lifecycle event. Historical
resolution therefore remains reconstructable across restart without trusting a
caller-provided profile, prompt, or mandate object.

Verification: `uv run python -m unittest tests.test_versioned_capital_mandates`.
