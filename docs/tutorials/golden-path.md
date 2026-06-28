# Golden Path Tutorial

This is the supported first-run path for FinHarness. It runs in an isolated
synthetic environment: no real ledger, no broker account, no live execution, no
network requirement.

The goal is to see the current product loop once:

```text
synthetic state -> decisions:scan -> governed proposals -> human review events
-> receipt replay -> bounded summary
```

## Before You Start

Use the project task entry points:

```bash
cd /root/projects/finharness
task --list
```

If this is a fresh checkout, `task setup` syncs dependencies from lockfiles. That
can install or update local packages, so run it deliberately. The golden path
itself does not need an API key or a brokerage account.

## What This Path Proves

By the end, you should have seen:

- synthetic personal-capital state seeded into State Core;
- capital-allocation candidates recorded as governed proposals;
- a high-risk proposal rejected rather than blindly approved;
- a low-risk proposal approved as review evidence, still not execution authority;
- review events and compare marks written as receipts;
- proposal and review-event receipt files replayed from disk;
- `execution_allowed=false` held end to end.

It does not prove profitable alpha, live-trading authority, broker compliance,
best execution, tax/accounting correctness, or institutional-grade data quality.

## Step 1 - Check Mature Wheels

```bash
task wheels:check
```

Expected shape: a list of installed core wheels and optional provider status.

Boundary proven: FinHarness uses mature wheels for heavy mechanics. A wheel is an
evidence source or tool, not trading authority.

## Step 2 - Run The Receipt-Consumption Golden Path

```bash
task decisions:golden-path
```

Expected shape:

```json
{
  "ok": true,
  "proposals": 2,
  "detector_kinds": [
    "cash_buffer_low",
    "concentration_high"
  ],
  "timeline_entries": 2,
  "replayed": true,
  "execution_allowed": false
}
```

The exact ids, temporary directory, and receipt filenames change on every run.
The stable facts are the detector kinds, the replay result, and
`execution_allowed=false`.

Boundary proven: FinHarness can write proposals and review events, then read the
receipt files back. The DB mirror is useful, but the receipt chain remains the
evidence root.

## Step 3 - Inspect The Output

Look for these fields in the command output:

```text
proposal_receipt_ref
review_event_receipt_ref
observability_receipt_ref
replayed
replay_gaps
```

If `replayed` is `false`, read `replay_gaps`. A broken receipt chain is reported
as a bounded data gap, not hidden behind a successful-looking summary.

## Step 4 - Serve The Cockpit

In a second terminal:

```bash
task api:serve
```

Open:

```text
http://127.0.0.1:8765/cockpit/
```

The cockpit is a read/review surface. It may let a named human attest or reject
a proposal, but that attestation is governance evidence, not execution
authorization.

## Optional Next Steps

After the isolated path, mirror real personal-finance state read-only:

```bash
task beancount:import -- path/to/ledger.beancount
task personal-finance:import -- path/to/export.csv
```

Then build current-state artifacts:

```bash
task brief:daily
task decisions:scan
task review:annual
task lessons:draft
```

For the live task list, use `task --list`. For maintained command facts, use
[Command Reference](../reference/commands.md).
