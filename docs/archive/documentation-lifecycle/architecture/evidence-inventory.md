# Evidence Inventory

> Historical / superseded reference (2026-06-28): this inventory still records
> old execution/risk-gate/live-trading evidence surfaces. Current system and
> module facts live in `system-map.md`, `module-map.md`, and the security threat
> model.

This document is the Phase 5 EvidenceInterface inventory. It describes what
FinHarness receipts and lineage already capture, what they do not capture yet,
and where provenance tools may later help as adapters. Receipts remain the
source of truth; an external provenance store would be an index or copy only.

## Current Provenance

| Evidence surface | Source | Captured today | Known limits |
| --- | --- | --- | --- |
| Market data source and quality | `src/finharness/market_data.py:40`, `src/finharness/market_data.py:52`, `src/finharness/market_data.py:67` | Provider, upstream source, access method, wheel/version, quality flags, raw hash, normalized hash, refs, and optional catalog ref. | Local hashes prove local content identity, not provider correctness. |
| Market data receipt | `src/finharness/market_data.py:102`, `src/finharness/market_data.py:291`, `src/finharness/market_data.py:315` | Raw JSON, normalized JSON, receipt JSON, eight-layer map, and quality backend/version. | No immutable remote log or signature. |
| Data-quality backend disclosure | `src/finharness/data_quality.py:19`, `src/finharness/data_quality.py:21`, `src/finharness/data_quality.py:73` | Pandera owns structural OHLCV checks; FinHarness keeps null counts, soft flags, and verdict semantics. | Soft-path verdicts remain local review evidence, not data-vendor certification. |
| Validation lineage and receipts | `src/finharness/validation.py:361`, `src/finharness/validation.py:383`, `src/finharness/validation.py:1013` | Hypothesis refs, event/market/indicator refs, method, provider/template fields, output hash/ref, receipt, and `execution_allowed=False`. | Backtest/research evidence is explicitly non-authoritative. |
| Risk-gate checks and receipts | `src/finharness/risk_gate.py:128`, `src/finharness/risk_gate.py:726`, `src/finharness/risk_gate.py:783` | Per-candidate checks, blocked language hits, mandate refs, decision quality, proposal refs, output hash/ref, execution handoff, and receipt. | It records risk-review decisions only; it does not authorize live execution or final sizing. |
| Riskfolio evidence handoff | `src/finharness/portfolio_risk.py:13`, `src/finharness/portfolio_risk.py:27`, `src/finharness/risk_gate.py:444` | Optimizer backend/model/risk measure/objective and weights can feed requested concentration evidence. | Optimizer output is a reviewed suggestion only and cannot relax mandate caps. |
| Execution lineage and receipts | `src/finharness/execution.py:760`, `src/finharness/execution.py:787`, `src/finharness/execution.py:839` | Risk-gate receipt ref, decision ids, adapter name/mode, idempotency keys, order-request hash, output hash, execution snapshot, and receipt. | Live execution remains blocked; no real broker lifecycle evidence is captured by this layer. |
| Execution graph state | `src/finharness/execution_graph.py:56`, `src/finharness/execution_graph.py:243`, `src/finharness/execution_graph.py:295` | Graph defaults to Nautilus paper adapter, preserves live-block events, writes snapshot/receipt, and exposes final review hook fields. | Graph evidence proves local workflow path, not external venue execution. |
| Post-trade lineage | `src/finharness/post_trade.py:115`, `src/finharness/post_trade.py:134`, `src/finharness/post_trade.py:151` | Execution receipt ref, event ids, final status, post-trade status, quality gates, payload/receipt refs, and `order_creation_allowed=False`. | Current post-trade evidence is lifecycle reconciliation, not accounting, tax, custody, or broker-statement proof. |
| OKX live-write receipts | `src/finharness/okx_live_gate.py:192`, `src/finharness/okx_live_gate.py:240`, `src/finharness/okx_live_gate.py:283` | Blocked, errored, and executed live attempts write receipts with request, attester, reason, decision, notional, and guard reasons. | It is a chokepoint for the OKX path only; it does not certify broader compliance or best execution. |
| Lesson-to-rule receipts | `src/finharness/rule_change_ledger.py:40`, `src/finharness/rule_change_ledger.py:72`, `src/finharness/rule_change_ledger.py:131` | Rule changes carry target, old/new value, rationale, human attester, lesson refs, receipt refs, state JSON, and receipt JSON. | The ledger records promoted changes; AI-generated lessons remain drafts until a human promotes them. |
| Receipt usage audit | `src/finharness/receipt_usage_audit.py:275` | Receipt references can be categorized as consumed, draft/candidate, generated runtime/unlinked, or missing. | A reference is evidence of use, not proof of correctness. |

## Gaps

- No artifact signing for receipts, snapshots, docs, or release bundles.
- No append-only immutable log; local files can be changed by a local operator.
- No cross-run lineage graph that queries every receipt, dataset, validation run,
  risk decision, execution attempt, and rule change as a single DAG.
- No dataset versioning beyond local raw/normalized files and content hashes.
- No provider replay guarantee for market data beyond captured local payloads.
- No central human-attestation registry across all modules.
- No formal schema migration registry for receipt versions.
- No external compliance, accounting, tax, custody, best-execution, or incident
  response evidence.

## Provenance Tool Evaluation

OpenLineage, MLflow, DVC, and Sigstore can add storage, indexing, tracking, or
signing value. None of them supplies FinHarness-specific receipt semantics:
claim, evidence, non-claim, human review, behavior stop, and no-live authority.

Recommendation: do not adopt a provenance tool in Phase 5. Current receipts are
sufficient for the local MVP and are more important than a new store. If one
future adapter becomes worth the dependency, prefer OpenLineage first for a
cross-run lineage index, because it maps most directly to the current gap: a
queryable graph of datasets, transformations, validation, risk, execution, and
review artifacts. Even then, OpenLineage events would mirror FinHarness receipts;
they would not replace them.

MLflow may be useful later if experiment/model tracking becomes the dominant
pain. DVC may be useful later if dataset versioning and reproducible data pulls
become the dominant pain. Sigstore may be useful later for artifact signing, but
signing should come after the receipt schema and release boundary stabilize.

Any adoption is a separate user-approved production dependency decision.

Official references checked for this evaluation:

- OpenLineage: https://openlineage.io/docs/
- MLflow: https://mlflow.org/docs/latest/
- DVC: https://dvc.org/doc
- Sigstore: https://docs.sigstore.dev/

## Red Lines

- Receipts remain the source of truth.
- External provenance stores are indexes/copies, not authorities.
- External tools cannot turn research, validation, risk-gate, or execution
  evidence into permission to trade.
- External tools cannot replace human review, live-write gates, or
  lesson-to-rule lineage.
