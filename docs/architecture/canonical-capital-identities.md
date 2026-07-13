# Canonical Capital Identities v0

`AccountIdentity` and `InstrumentIdentity` are the W0 equality boundary for
capital state. Human labels and ticker symbols remain display data; they are not
safe join keys.

## Account identity

A canonical account ID is a stable hash of an explicit source namespace and the
source-native account ID. The display name is deliberately excluded. Two
sources may both call an account `Retirement` without colliding.

When two provider-native accounts are known to represent the same real account,
the mapping must name the canonical target explicitly through an
`IdentityAlias`. FinHarness never merges them from matching names.

## Instrument identity

Instrument v0 uses the closed tuple:

```text
symbol + instrument_type + venue/exchange + quote_currency
```

This is intentionally smaller than a security master. It prevents the current
unsafe cases—such as the same symbol representing an equity and option, or
trading on different venues—without claiming corporate-action, FIGI, CUSIP, or
symbology-master coverage.

Provider aliases are separate rows. Their IDs bind identity kind, provider
namespace, provider alias, and mapping version; source receipt references make
the mapping auditable. A mapping revision creates a different alias ID rather
than silently changing history.

## Readiness and compatibility

`Account.canonical_account_id` and `Position.instrument_id` are nullable only
for migration compatibility. New adapters always namespace accounts. They write
an instrument ID only when type, venue, and quote currency are explicit. A
holding with insufficient identity evidence is retained as source evidence and
emits a blocking `instrument_identity_unresolved` finding.

Canonical diff and concentration paths use `instrument_id`. Legacy rows retain
their historical symbol projection only for readability and remain unresolved;
they do not become trusted identities by migration. Migration v9 creates the
identity tables and nullable bindings but never invents identity for old rows.

Cross-account duplicate checks group by snapshot, canonical account, and
instrument. If multiple source account rows project the same canonical pair,
the result is a blocking `cross_account_duplicate` finding.

Verification:

```bash
uv run python -m unittest tests.test_statecore_identities \
  tests.test_personal_finance tests.test_beancount_adapter \
  tests.test_statecore_snapshot_ingest tests.test_statecore_store
```
