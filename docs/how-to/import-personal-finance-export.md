# Import A Personal-Finance Export

There are two read-only ways to get personal-finance state into the cockpit.
Neither replaces your accounting tool or creates execution authority.

## Option A: Connect a real Beancount ledger (recommended)

Use this when you keep a Beancount ledger. FinHarness reads it directly with the
mature `bean-query` engine (`beanquery`) — no intermediate CSV to hand-write:

```bash
task beancount:import -- path/to/ledger.beancount
```

This mirrors `Assets:` holdings into accounts/positions and `Liabilities:`
balances into liability rows, with a receipt. Holdings need `price` directives
in the ledger for market value; otherwise the quantity is kept, market value is
recorded as null with `valuation_status=unpriced`, and the symbol is disclosed in `data_gaps_unpriced` in the
snapshot and receipt. Account root names other than `Assets`/`Liabilities` can
be passed to `ingest_beancount_ledger(..., assets_root=..., liabilities_root=...)`.

## Option B: Import a FinHarness-contract CSV

Use this when your tool can export a CSV. The CSV shape below is **defined by
FinHarness**, not by any upstream tool — produce it from Beancount
(`bean-query`/`bean-report`), a budgeting app export, or a script of your own.

### Holdings-Only CSV Contract

Use this simpler shape when the upstream tool only exports accounts and
positions.

Required columns:

```text
account_id
account_name
account_kind
venue
symbol
quantity
currency
as_of_utc
```

Optional column:

```text
cost_basis
market_value
valuation_currency
unit_price
price_currency
price_source_ref
fx_rate
fx_as_of_utc
fx_source_ref
effective_at_utc
observed_at_utc
valued_at_utc
source_namespace
instrument_type
instrument_venue
```

All rows in one file must share the same clocks. New exports should provide the
three explicit optional clocks; `as_of_utc` is retained as a compatibility
projection and produces a `partial` finding when one of them is absent. All
timestamps must include a UTC offset.

For a readiness-complete position import, provide `instrument_type` and
`instrument_venue` (exchange/MIC where available). `source_namespace` identifies
the upstream provider; when omitted it is derived from the adapter and source
path. Missing instrument identity fields do not discard the holding, but they
produce a blocking `instrument_identity_unresolved` finding and leave
`Position.instrument_id` null. A symbol alone is never treated as identity.

Also provide `market_value`, `valuation_currency`, `unit_price`,
`price_currency`, `valued_at_utc`, and `price_source_ref` for an admitted direct
valuation. If the two currencies differ, `fx_rate`, `fx_as_of_utc`, and
`fx_source_ref` are mandatory. Missing evidence retains the holding but produces
a blocking valuation finding; it is never interpreted as zero.

Example:

```csv
account_id,account_name,account_kind,venue,symbol,instrument_type,instrument_venue,quantity,market_value,cost_basis,currency,valuation_currency,unit_price,price_currency,price_source_ref,effective_at_utc,observed_at_utc,valued_at_utc,as_of_utc
Assets:Brokerage,Brokerage,broker,beancount,SPY,equity,ARCX,1.5,750.00,700.00,USD,USD,500.00,USD,provider:close,2026-06-19T00:00:00+00:00,2026-06-19T00:05:00+00:00,2026-06-19T00:00:00+00:00,2026-06-19T00:05:00+00:00
Assets:Cash,Cash,cash,beancount,USD,cash,global,1000,1000,,USD,USD,1,USD,ledger:cash,2026-06-19T00:00:00+00:00,2026-06-19T00:05:00+00:00,2026-06-19T00:00:00+00:00,2026-06-19T00:05:00+00:00
```

### Typed CSV Contract

For broader personal-finance state, include a `record_type` column. Supported
values are:

```text
position
liability
goal
cashflow
tax_event
insurance
document
```

All rows still share one `as_of_utc`. Each row type requires its own columns:

| record_type | Required columns beyond `record_type` and `as_of_utc` |
| --- | --- |
| `position` | `account_id`, `account_name`, `account_kind`, `venue`, `symbol`, `quantity`, `currency` |
| `liability` | `liability_id`, `name`, `liability_type`, `balance`, `currency` |
| `goal` | `goal_id`, `name`, `target_amount`, `current_amount`, `currency` |
| `cashflow` | `cashflow_id`, `description`, `amount`, `currency`, `event_date`, `category` |
| `tax_event` | `tax_event_id`, `event_type`, `jurisdiction`, `due_date` |
| `insurance` | `policy_id`, `policy_type`, `provider`, `coverage_amount`, `currency` |
| `document` | `document_id`, `document_type`, `title`, `path` |

Optional fields include `cost_basis`, `account_id`, `interest_rate`,
`due_date`, `target_date`, `status`, `frequency`, `estimated_amount`,
`premium_amount`, `renewal_date`, and `related_object_id` where they fit the row
type. Monetary fields (`balance`, amounts, `coverage_amount`, …) must be decimal
text and are stored as exact `Decimal`; float input and missing/invalid currency
fail closed.

### Import

```bash
task personal-finance:import -- path/to/export.csv
```

The task writes:

```text
state-core Account rows
state-core Position rows
state-core AccountIdentity / InstrumentIdentity / IdentityAlias rows
state-core Liability / FinancialGoal / CashflowEvent / TaxEvent /
  InsurancePolicy / DocumentRef rows when typed rows are present
one Snapshot (kind=portfolio only when the file has positions; otherwise
  kind=personal_finance so a holdings view is not shadowed)
one personal-finance receipt
one ReceiptIndex row
one stable ImportBatch and one ReceiptManifest row
immutable source-evidence and receipt artifacts in the shared Artifact Store
explicit full/delta coverage, completeness, five clocks, and structured findings
```

Every generated record keeps `execution_allowed=false`.

Both adapters currently declare full-source coverage. Re-importing identical
content reuses the same batch, manifest, and receipt bytes. If the process stops
after evidence is stored but before State Core commits, running the same import
again completes the same batch. Existing receipts from before this contract stay
readable as `legacy_unmanifested`; they are not assigned invented provenance.

## Boundary

This is a read-only adapter around a mature accounting/budgeting export. It is
not tax advice, accounting advice, investment advice, order entry, or a source
of truth replacement for the upstream ledger.
