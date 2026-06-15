# Product Roadmap

Author: Codex
Parallel agent: Claude
Status: draft
Date: 2026-06-15
Evidence policy: primary-source-first

This roadmap sequences the benchmark gaps into a backend/frontend path. It is a
draft planning artifact only. It does not authorize code, dependencies, live
trading, or product release.

Parallel input read: [Product Roadmap](../product-roadmap.md).

## Roadmap Principle

```text
trustworthy evidence -> accountable controls -> read-only product surface -> deeper execution review
```

Do not build a polished frontend over weak research or unowned controls. The
danger is not that a UI fails; it is that a good UI makes an unproven system
look like authority.

## Now: Close The Value And Safety Gaps

| Priority | Workstream | Outcome | Acceptance |
| --- | --- | --- | --- |
| 1 | Research rigor ladder | Validation evidence can climb from in-sample to OOS and walk-forward, then trial-discounted evidence. | Validation receipts state rung, trial count, data limits, and cannot claim support above the rung climbed. |
| 2 | Data validity labels | Research evidence discloses provider, adjustment mode, reconciliation state, and unresolved bias. | Receipts expose data-bias limitations until point-in-time/survivorship questions are solved. |
| 3 | Control-owner accountability | A named human owns periodic review of the control system. | Control register and draft certification receipt exist, with non-claim that this is not legal certification. |
| 4 | Aggregate market-access limits | Every mutation-capable paper/live-adjacent path is designed to consume the same limit model. | Shared limit-ledger design covers account, operator, environment, venue, product, symbol, request, remaining limit, and receipt ref. |

Do not do in this phase:

- add new venues or asset classes;
- add autonomous or live execution;
- build frontend polish;
- add new governance graphs unless directly tied to the four workstreams above.

## Next: Build The Product Hinge Safely

| Priority | Workstream | Outcome | Acceptance |
| --- | --- | --- | --- |
| 5 | Read-only backend interface spec | OpenAPI/JSON Schema draft for snapshots, receipts, cockpit, review queue, and module metadata. | Spec has no mutation, order, sizing, or authorization endpoint. |
| 6 | Authorized operator/account model | Runtime attestations become typed and scoped without storing secrets. | Receipts include operator/account/environment/scope/reason where relevant. |
| 7 | Restricted-symbol and erroneous-order model | Broker/venue-like paths get restricted-list and fat-finger controls. | Control decision records restricted-list version, provider tradability, price/size/duplicate/window/open-order checks. |
| 8 | Post-trade/TCA depth | Paper execution quality can be reviewed honestly. | Post-trade receipt includes intended/submitted/filled/canceled/rejected chain and first implementation-shortfall-style metric. |

Do not do in this phase:

- add FastAPI/uvicorn or any production web dependency without explicit user
  approval;
- expose broker credentials or account secrets through docs or UI;
- let frontend display a recommendation without evidence, assumptions,
  limitations, and receipt refs.

## Later: Frontend And External Compatibility

| Priority | Workstream | Outcome | Acceptance |
| --- | --- | --- | --- |
| 9 | Read-only evidence dashboard | Web UI over the read-only backend. | Watchlist, snapshots, validation evidence, risk decisions, receipts, and non-claims are visible; no order controls exist. |
| 10 | Review and annotation surface | Human decisions and review comments can become evidence. | Review writes are explicitly designed, idempotent, receipt-backed, and still non-execution. |
| 11 | Observability compatibility | Workflow/backend traces can be debugged. | Trace IDs connect UI/backend/task/receipt without replacing receipt semantics. |
| 12 | Lineage/records export | External lineage and checksum manifests can index evidence. | Export maps to receipt refs and preserves non-claims; signing/manifest policy is reviewed. |

Do not do in this phase:

- mobile/tablet before the read-only web dashboard is boring and safe;
- smart order routing, allocation, settlement, FIX, or broker-like back office;
- CPCV dependency adoption before lower rungs show value;
- policy/provenance engine adoption before an evidence consumer needs it.

## Route By Capability

| Capability | Build when | Mature method | Local invariant |
| --- | --- | --- | --- |
| Research value | Now | vectorbt, OOS, walk-forward, Deflated Sharpe style discount | Evidence rung caps claims. |
| Data trust | Now | provider disclosure, reconciliation, bias labels | No hidden data-quality overclaim. |
| Control accountability | Now | 15c3-5-inspired owner/review shape | Named human reviews controls; AI proposes only. |
| Backend interface | Next | OpenAPI, JSON Schema, ASVS-aware design | Read-only first; no authority endpoint. |
| Frontend review | Later | WCAG 2.2, evidence dashboard patterns | UI is a window and review queue, not a trigger. |
| Observability | Later | OpenTelemetry | Trace indexes receipt; trace is not receipt. |
| Lineage export | Later | OpenLineage | External lineage does not replace FinHarness receipt. |

## Dependencies Requiring Approval

| Dependency or tool | Possible use | Decision |
| --- | --- | --- |
| FastAPI / uvicorn | Read-only backend implementation after spec | Requires explicit user approval. |
| mlfinlab or equivalent CPCV tooling | Later research-rigor rung | Requires explicit user approval and license review. |
| OpenTelemetry SDK/exporter | Future observability | Requires explicit user approval if added as dependency. |
| OpenLineage client/exporter | Future lineage export | Requires explicit user approval if added as dependency. |

## Value Loop

The roadmap should be judged by externalized decision quality, not by the number
of graphs or receipts:

1. Research evidence survives higher rungs without overclaim.
2. A named human can see what controls were in force.
3. Post-trade receipts expose whether decisions and executions improved.
4. Lessons become human-promoted rule changes with lineage to receipts.
5. Frontend review makes the human slower, better informed, and less likely to
   mistake evidence for authority.

## Non-Claims

- This roadmap does not authorize live trading or autonomous trading.
- This roadmap does not approve any dependency.
- This roadmap does not claim a profitable edge.
- This roadmap does not certify compliance with financial, security, or web
  standards.
