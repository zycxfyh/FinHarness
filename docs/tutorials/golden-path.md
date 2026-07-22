# Synthetic Golden Path Tutorial

This is the supported isolated synthetic proposal/review/receipt replay demo for
FinHarness. It uses no real ledger, broker account, live execution, API key, or
network call. It is deliberately narrower than the canonical first-capital-review
journey planned under #455.

The goal is to observe these current mechanics once:

```text
direct-seeded synthetic state -> governed proposals -> synthetic human review events
-> receipt replay -> bounded summary
```

## Before You Start

Run the commands from your own FinHarness checkout:

```bash
cd /path/to/FinHarness
task --list
```

If this is a fresh checkout, `task setup` syncs dependencies from lockfiles. That
can install or update local packages, so run it deliberately. The synthetic demo
itself does not need an API key or a brokerage account.

## What This Path Proves

By the end, you should have seen:

- synthetic personal-capital state direct-seeded into an isolated State Core;
- capital-allocation candidates recorded as governed proposals;
- a high-risk proposal rejected rather than blindly approved;
- a low-risk proposal approved as review evidence, still not execution authority;
- review events and compare marks written as receipts;
- proposal and review-event receipt files replayed from disk;
- `execution_allowed=false` held end to end.

This demo does not prove canonical capital import, capital-truth readiness, Daily
Brief generation, a persistent cockpit workspace, external user validation,
Agent dogfood, profitable alpha, live-trading authority, broker compliance, best
execution, tax/accounting correctness, or institutional-grade data quality.

## Step 1 - Check Mature Wheels

```bash
task wheels:check
```

Expected shape: a list of installed core wheels and optional provider status.

Boundary proven: FinHarness uses mature wheels for heavy mechanics. A wheel is an
evidence source or tool, not trading authority.

## Step 2 - Run The Receipt-Consumption Demo

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
  "artifact_root": "/tmp/finharness-golden-path-...",
  "cleanup_hint": "rm -rf /tmp/finharness-golden-path-...",
  "execution_allowed": false
}
```

The exact ids, temporary directory, and receipt filenames change on every run.
The stable facts are the detector kinds, the replay result, and
`execution_allowed=false`.

Boundary proven: FinHarness can write synthetic proposals and review events, then
read the receipt files back. The DB mirror is useful, but the receipt chain remains
the evidence root for this isolated demo.

## Step 3 - Inspect The Output

Look for these fields in the command output:

```text
proposal_receipt_ref
review_event_receipt_ref
observability_receipt_ref
replayed
replay_gaps
artifact_root
cleanup_hint
```

If `replayed` is `false`, read `replay_gaps`. A broken receipt chain is reported
as a bounded data gap, not hidden behind a successful-looking summary.

The temporary artifact directory remains on disk after the command exits so it
can be inspected. Use the emitted `cleanup_hint` when that evidence is no longer
needed.

## Step 4 - Keep The Workspace Boundary Explicit

`task decisions:golden-path` creates an isolated temporary artifact workspace and
reports its `artifact_root`. It does not provide a supported `--state-db` /
`--receipt-root` handoff to a later cockpit command. Starting `task api:serve` or
`task cockpit:review` with their defaults therefore does not open the demo
workspace; it opens the normal persistent workspace instead.

To inspect a persistent cockpit, choose the workspace explicitly:

```bash
STATE_DB="$PWD/.local/finharness-review/state-core.sqlite"
RECEIPT_ROOT="$PWD/.local/finharness-review/receipts"
task api:serve -- --state-db "$STATE_DB" --receipt-root "$RECEIPT_ROOT" --port 8765
```

Open `http://127.0.0.1:8765/cockpit/`. This mode is read-only; every write fails
closed. It can inspect only the persistent workspace named above, not the
synthetic demo output.

To record governed human confirm, reject, defer, scaffold-revision, or review
events, stop the read-only server and start review mode against the same paths:

```bash
task cockpit:review -- --state-db "$STATE_DB" --receipt-root "$RECEIPT_ROOT" --port 8765
```

Reuse exactly `$STATE_DB` and `$RECEIPT_ROOT` when restarting so the same
receipt-backed review state is reopened. Review evidence still grants no execution
capability.

## Optional Next Steps

The following tasks operate on the normal persistent product workspace, not the
isolated synthetic demo:

```bash
task beancount:import -- path/to/ledger.beancount
task personal-finance:import -- path/to/export.csv
task brief:daily
task decisions:scan
task review:annual
task lessons:draft
```

They are not part of the proof above. In particular, running them does not convert
the synthetic demo into a canonical import/readiness/Daily Brief journey.

For the live task list, use `task --list`. For maintained command facts, use
[Command Reference](../reference/commands.md).
