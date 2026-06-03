# Review: Research Asset Library

Date: 2026-06-02
Status: implemented-mvp
Related proposal: /root/projects/finharness/docs/proposals/2026-06-02-research-asset-library.md
Related receipt:
- /root/projects/finharness/data/receipts/cognitive-graph/20260602T163532Z-research-asset-library.json
- /root/projects/finharness/data/receipts/engineering-delivery/20260602T164157Z-research-asset-library-mvp.json
Related module: docs/research/README.md

## Summary

The Research Asset Library MVP was implemented as a lightweight asset and
validation boundary outside the ten-layer graph. It adds StrategySpec,
MathMethodSpec, and ReferenceCard contracts, initial sample assets, and tests
that verify catalog loading and key permission boundaries.

## Expected

```text
asset directories exist
each asset family has at least one high-quality sample
architecture docs explain the ten-layer relationship
tests cover spec loading and reference-boundary validation
standard project checks pass
```

## Actual

```text
3 StrategySpec samples added
6 MathMethodSpec samples added
10 ReferenceCard samples added
typed loader added in src/finharness/research_assets.py
architecture and research docs updated
focused and full checks passed
```

## Evidence

```text
PYTHONPATH=src uv run ruff check src/finharness/research_assets.py tests/test_research_assets.py
  All checks passed.

PYTHONPATH=src uv run python -m unittest tests.test_research_assets
  Ran 4 tests in 0.005s; OK.

task test
  Ran 105 tests in 6.485s; OK.

task check
  Rust tests: 4 passed.
  Ruff: All checks passed.
  Python tests: Ran 105 tests; OK.
  Backtrader experiment completed.
  promptfoo smoke eval: 1 passed.
```

## Classification

architecture asset boundary

## Root Causes / Conditions

The ten-layer MVP needed a reusable research-knowledge layer, but adding more
LangGraph layers would blur lifecycle orchestration with asset governance. The
cleaner boundary is an external asset library that can be cited by L5-L10.

## Lessons

Research assets should be versioned as evidence contracts, not embedded as
strategy logic. External tools and standards are useful references only when
their authority boundary is explicit.

## Actions

```text
keep StrategySpec/MathMethodSpec/ReferenceCard as non-executing assets
wire future ten_layer_graph enhancements to asset ids and summaries only
run engineering_delivery_graph to seal changed files, docs, checks, and lessons
```
