# 11 Execution Environment

Hermes treats execution as a combination of environment, workspace, path, credentials, timeout, output budget, process cleanup, and observability.

FinHarness should not rush to give the capital Agent terminal/browser/file-write authority. The lesson to import now is execution-boundary thinking.

## Hermes Pattern

Hermes terminal execution is not just `subprocess.run`. It models:

- local/docker/cloud/SSH-style backends;
- spawn-per-call execution;
- session snapshots;
- authoritative CWD/workspace resolution;
- workdir validation;
- env sanitization;
- sudo/session credential scope;
- timeout and interrupt;
- output draining;
- background process behavior;
- file read budgets;
- cleanup and disk usage warnings.

The same action can have different risk depending on environment and mounted state.

## FinHarness Mapping

FinHarness execution-like actions include more than trading:

- proposal draft creation;
- receipt-backed review write;
- simulation run;
- document parse;
- evidence projection;
- queue check;
- report generation.

Each should bind to explicit scope:

```text
statecore_id
receipt_root
portfolio_scope
proposal_id
surface
profile
environment = read_only | review_draft | simulation | paper
live_execution_allowed = false
```

## Atomicity

Governance state writes must be atomic:

- proposal write attempted is not proposal landed;
- proposal landed is not receipt landed;
- receipt landed is not human reviewed;
- human reviewed is not executed.

Each stage needs separate state and verification.

## Credentials

Rules:

- model provider secrets must not leak to subprocesses;
- broker secrets must not enter model context;
- receipts must not contain credentials;
- provider errors must be sanitized;
- chat should not collect broker passwords.

Future credential setup should be out-of-band, scoped, read-only first, and invisible to the model.

## Bounded Work

Long jobs need:

- timeout;
- heartbeat;
- cancel token;
- cleanup;
- bounded output;
- partial-result policy;
- structured error;
- cancellation receipt or event.

Large financial artifacts should be projected as summary plus source refs, not dumped wholesale into the prompt.
