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
- every response and Artifact keeps `execution_allowed=false`.

This is synthetic product acceptance, not investment advice, performance proof,
or authorization for a real broker or funded effect.
