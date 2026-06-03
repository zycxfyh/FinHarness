# Lesson: Research Asset Library

Date: 2026-06-02
Status: active
Source reviews:
- /root/projects/finharness/docs/reviews/2026-06-02-research-asset-library.md
Source ideas:
- /root/projects/finharness/ideas/2026-06-02-research-asset-library.md
Affected modules:
- ten-layer graph
- research assets
- engineering delivery governance

## Lesson

Reusable financial research knowledge should be stored as non-executing assets
before it is wired into workflow behavior.

## Why It Matters

Strategy ideas, math methods, and institutional/tool references are different
kinds of authority. Putting them into one trading workflow too early makes it
easy to confuse a reference with a decision, a method with an implementation,
or a strategy contract with execution permission.

## Evidence

```text
Research assets loaded through src/finharness/research_assets.py.
tests/test_research_assets.py validates counts, layer refs, and live-write rejection.
task check passed after adding the asset library MVP.
```

## Rule / Heuristic

Use this order for future capabilities:

```text
cognitive_graph proposal
-> non-executing asset contract
-> focused loader/boundary tests
-> ten-layer graph citation or handoff
-> engineering_delivery_graph receipt
```

## Where It Should Live

```text
docs/research/README.md
docs/architecture/ten-layer-langgraph-map.md
src/finharness/research_assets.py
```
