# Documentation Lifecycle Contract Plan

> **Documentation lifecycle:** `historical`
> **Current authority:** [Documentation Lifecycle Contract](../../architecture/documentation-lifecycle.md)
> **Reason:** Exact execution-plan evidence for the first bounded #452 slice.

Baseline: `main@1efd959e8722d4e180e51a2ce08c5cbb4e7de5dc`  
Issue: #452  
Slice: lifecycle contract and machine guard only

## Decisions

- Keep Diátaxis as the document-type model.
- Keep `system-catalog.yml` navigation roots/paths as repository-level lifecycle
  ownership.
- Use visible blockquote banners for exceptions outside those roots.
- Treat only `current` and supported `deprecated` pages as maintained graph
  members.
- Preserve authored history; do not rewrite old claims to appear current.
- Use short redirect stubs for moved paths and forbid duplicate full copies.

## Deferred To Later #452 Slices

- architecture/report migration;
- Idea Lab and musings family classification;
- current-to-history source-link boundaries;
- final reconciliation against the #450 reviewed queue.

No product/runtime behavior, #453 navigation redesign, #454 generated Reference,
#455 executable journey, or documentation publisher is authorized by this plan.
