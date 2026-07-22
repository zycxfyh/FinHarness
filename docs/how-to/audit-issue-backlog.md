# Inspect Issue Labels

GitHub Issues and pull requests are useful coordination records. Their labels are optional views, not permission to perform reversible repository work and not evidence that a result is complete.

Run the advisory report from a checkout:

```bash
task issues:audit
```

To target an explicit repository:

```bash
task issues:audit -- --repo zycxfyh/FinHarness
```

The report notes missing, duplicate, or unknown `plane:*`, `type:*`, and `status:*` labels when those labels are in use. Findings do not fail the command and do not require editing an Issue merely to satisfy taxonomy cardinality.

Use labels when they reduce coordination cost, for example:

- `status:active`, `status:dormant`, and `status:deferred` for shared backlog views;
- `plane:*` for a useful primary domain view;
- `type:*` when the work kind matters.

A direct request, observed defect, or existing task may proceed without first completing a classification form. Real dependencies belong in native Issue relationships when durable coordination is needed. Product behavior, tests, Git history, and consequence-specific recovery remain the evidence for the work itself.
