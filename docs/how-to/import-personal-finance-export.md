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
recorded as `0`, and the symbol is disclosed in `data_gaps_unpriced` in the
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
market_value
as_of_utc
```

Optional column:

```text
cost_basis
```

All rows in one file must share the same `as_of_utc`.

Example:

```csv
account_id,account_name,account_kind,venue,symbol,quantity,market_value,cost_basis,as_of_utc
Assets:Brokerage,Brokerage,broker,beancount,SPY,1.5,750.25,700.00,2026-06-19T00:00:00+00:00
Assets:Cash,Cash,cash,beancount,CASH:USD,1000,1000,,2026-06-19T00:00:00+00:00
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
| `position` | `account_id`, `account_name`, `account_kind`, `venue`, `symbol`, `quantity`, `market_value` |
| `liability` | `liability_id`, `name`, `liability_type`, `balance`, `currency` |
| `goal` | `goal_id`, `name`, `target_amount`, `current_amount`, `currency` |
| `cashflow` | `cashflow_id`, `description`, `amount`, `currency`, `event_date`, `category` |
| `tax_event` | `tax_event_id`, `event_type`, `jurisdiction`, `due_date` |
| `insurance` | `policy_id`, `policy_type`, `provider`, `coverage_amount`, `currency` |
| `document` | `document_id`, `document_type`, `title`, `path` |

Optional fields include `cost_basis`, `account_id`, `interest_rate`,
`due_date`, `target_date`, `status`, `frequency`, `estimated_amount`,
`premium_amount`, `renewal_date`, and `related_object_id` where they fit the row
type. Monetary fields (`balance`, amounts, `coverage_amount`, …) are stored as
exact `Decimal`.

### Import

```bash
task personal-finance:import -- path/to/export.csv
```

The task writes:

```text
state-core Account rows
state-core Position rows
state-core Liability / FinancialGoal / CashflowEvent / TaxEvent /
  InsurancePolicy / DocumentRef rows when typed rows are present
one Snapshot (kind=portfolio only when the file has positions; otherwise
  kind=personal_finance so a holdings view is not shadowed)
one personal-finance receipt
one ReceiptIndex row
```

Every generated record keeps `execution_allowed=false`.

## Boundary

This is a read-only adapter around a mature accounting/budgeting export. It is
not tax advice, accounting advice, investment advice, order entry, or a source
of truth replacement for the upstream ledger.
