# How To Run The Ten-Layer Flow Safely

Use this when you want to exercise the top-level ten-layer orchestrator and see
where the chain stops.

## Preconditions

- Run the [golden path tutorial](../tutorials/golden-path.md) first.
- You are in `/root/projects/finharness`.
- Network-backed data/event steps may depend on provider availability.

## Run The Default Flow

```bash
task ten-layer:graph
```

The default script uses:

```text
symbol=SPY
start=2025-01-01
end=2025-06-30
run_layers=1,2,3,4,5,6,7,8,9,10
requested_mode=dry_run
```

## Run A Narrower Slice

Run only layers 1-4:

```bash
task ten-layer:graph -- --run-layers 1,2,3,4
```

Use a different symbol:

```bash
task ten-layer:graph -- --symbol QQQ --start 2025-01-01 --end 2025-06-30
```

## Read The Final Output

The final JSON should identify:

- which terminal layer was reached;
- output and receipt refs for completed layers;
- whether execution was allowed;
- review or handoff fields for later human review.

## Safety Boundary

Do not add `--execute` or `--paper` until you have reviewed the earlier layer
outputs and understand what the execution layer will consume. Even then, this is
paper/dry-run workflow evidence, not live authorization.

The live execution path is not wired through this tutorial. Live execution is a
separate, gated decision and is not authorized by a successful ten-layer run.

## What This Does Not Prove

- It does not prove every layer is economically correct.
- It does not prove data vendor correctness.
- It does not prove strategy profitability.
- It does not authorize live trading.
