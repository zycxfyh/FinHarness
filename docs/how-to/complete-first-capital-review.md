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
- multi-world journey: path movement reuses source and batch identity, historical
  queries prevent look-ahead, all current consumers bind one `world_id`, and a
  verified backup restore reproduces that identity;
- every response and Artifact keeps `execution_allowed=false`.

This is synthetic product acceptance, not investment advice, performance proof,
or authorization for a real broker or funded effect.
