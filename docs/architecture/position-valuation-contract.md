# Position Valuation and FX Provenance

`Position` separates a holding from the evidence needed to value it. Quantity
may be known while monetary value is unknown; adapters must preserve that
holding with `market_value = null` instead of omitting it or writing zero.

## Typed contract

An admitted direct valuation records `valuation_currency`, `market_value`,
`unit_price`, `price_currency`, `valued_at_utc`, and `price_source_ref`, with
`valuation_status=valued`. The components reconcile as:

```text
quantity × unit_price = market_value
```

When price and valuation currencies differ, `fx_rate`, `fx_as_of_utc`, and
`fx_source_ref` are also mandatory, status is `valued_converted`, and:

```text
quantity × unit_price × fx_rate = market_value
```

The allowed non-admitted states are `unpriced`, `fx_missing`, `stale`, and
`unknown_legacy`. Missing or stale price/FX evidence, component disagreement,
or mixed output currencies blocks a unified total. Per-currency admitted
components remain visible so absence is not confused with zero.

## Migration and adapters

State Core migration v10 makes `market_value` nullable and adds the provenance
columns. Every pre-v10 row becomes `unknown_legacy`; migration does not infer a
currency, price, timestamp, or FX observation from its old aggregate value.

CSV, Beancount, and broker-receipt adapters retain unpriced positions and emit
blocking findings. Beancount values are admitted only when dated price evidence
exists. API position responses expose the same fields. Snapshot diffs publish a
base currency and unified totals only when every component is admitted and
reconciled.

Verification:

```bash
uv run python -m unittest tests.test_position_valuation \
  tests.test_statecore_store tests.test_statecore_diff \
  tests.test_personal_finance tests.test_beancount_adapter \
  tests.test_statecore_snapshot_ingest tests.test_statecore_api
```
