# Complete the First Synthetic Capital Review

Use this acceptance task to prove the current supported product chain without
personal data, network providers, funded accounts, or direct database seeding:

```bash
task acceptance:capital-review
```

The task materializes fresh clocks into checked-in synthetic CSV templates and
runs canonical paths:

```text
complete import
-> truth readiness
-> positions and exposure
-> Daily Brief
-> allocation candidate
-> governed human defer
-> receipt and timeline
-> application restart
-> identity-preserving replay

blocked valuation import
-> raw source Artifact retained
-> capital truth blocked
-> unsupported totals suppressed
-> no decision candidate
-> bounded repair action

mixed-currency import without FX evidence
-> valuation status fx_missing
-> capital truth blocked
-> total assets, net worth, and concentration suppressed
-> no decision candidate

multi-world import
-> stable source identity survives a path move
-> historical as-of excludes later evidence
-> current world selects the later legal batch
-> Ready / Exposure / Cockpit / Agent / Proposal share one world_id
-> backup restore preserves the same world identity
```

By default the workspace is temporary. Preserve the SQLite databases, source
files, and receipts by selecting an empty directory:

```bash
task acceptance:capital-review -- --workspace-root "$PWD/.local/capital-review-acceptance"
```

Expected stable outcomes:

- admitted journey: `capital_truth_admission=admitted`, two positions, one
  concentration candidate, one human deferral, and the same proposal,
  attestation, receipt, and timeline after restart;
- blocked journey: `capital_truth_admission=blocked`, intact source evidence,
  `total_assets=null`, `net_worth=null`, zero candidates, and explicit valuation
  blockers;
- mixed-FX journey: the cross-currency position remains `fx_missing`, unified totals
  and concentration are suppressed, and no review candidate is created;
- multi-world journey: path movement reuses source and batch identity, historical
  queries prevent look-ahead, all current consumers bind one `world_id`, and a
  verified backup restore reproduces that identity;
- every response and Artifact keeps `execution_allowed=false`.

This is synthetic product acceptance, not investment advice, performance proof,
or authorization for a real broker or funded effect.


## Public-data dogfood

Use the pinned Federal Reserve 2022 Survey of Consumer Finances public extract to
exercise the production importer and Capital World with a mature external dataset:

```bash
task dogfood:scf-capital
```

The task verifies the official ZIP SHA-256 before reading data. It selects one
first-implicate household deterministically near the eligible weighted-median
`NETWORTH`, maps aggregate financial/nonfinancial assets, debt categories, and
annual income into a temporary FinHarness workspace, and emits dataset provenance,
selected household identifiers, Capital World trust, and Agent context trust.

SCF observations describe a 2022 survey sample. The dogfood re-clocks the mapped
facts only so current freshness contracts can be exercised; it does not claim the
household is current, representative of every household, or sufficient for a
production performance conclusion. Execution remains disabled.

## Bounded resolver baseline

```bash
task benchmark:capital-world -- --sizes 10,100,1000 --repetitions 5
```

This measures one local SQLite workload with one materialized position-domain batch
per stable source. Treat its numbers only as a regression baseline for that shape,
not as a service-level objective or evidence about concurrency and remote storage.
