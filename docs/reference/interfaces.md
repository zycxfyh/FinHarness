# Interface Reference

This reference lists the major FinHarness interfaces, the mature wheels or
external systems that own the heavy work, and the local boundary FinHarness
keeps.

Use this as a lookup page. For rationale, read
[Mature Wheel Control Plane](../architecture/mature-wheel-control-plane.md).

## Interface Table

| Interface | Mature owner | Local FinHarness owner | Primary docs/tasks |
| --- | --- | --- | --- |
| MarketDataInterface | OpenBB, yfinance, official broker/exchange data | Source disclosure, OHLCV contract, freshness notes, raw/normalized refs, receipts | [Market Data module](../modules/01-market-data.md), `task market-data:graph` |
| DataQualityInterface | Pandera | Required OHLCV contract, quality verdict, soft-path null/outlier semantics, quality backend disclosure | [Data quality spec](../architecture/data-quality-interface-pandera-spec.md) |
| IndicatorInterface | TA-Lib, pandas-ta, vectorbt indicators | Feature names, state labels, lineage, non-advice output, `execution_allowed=false` | [Indicators module](../modules/02-indicators.md), `task feature:macd`, `task feature:squeeze` |
| ResearchInterface | vectorbt | Parameter sweep/research evidence, validation handoff, rejected alternatives, no proposal authority | [Research spec](../architecture/research-interface-vectorbt-spec.md), `task validation:graph` |
| PerformanceInterface | QuantStats, vectorbt stats | Local summary schema and validation receipt fields | `task experiments`, `task validation:graph` |
| PortfolioRiskInterface | Riskfolio-Lib | Requested concentration evidence only; mandate caps and review remain in Risk Gate | [Portfolio risk spec](../architecture/portfolio-risk-interface-riskfolio-spec.md), `task risk-gate:graph` |
| ExecutionEngineInterface | NautilusTrader paper model, official venue tooling | Dry-run default, adapter allowlist, no-live block, execution receipt | [Execution spec](../architecture/execution-interface-nautilus-spec.md), `task execution:graph` |
| SecurityScanInterface | pip-audit, gitleaks, Trivy, uv | Scanner aggregation, redaction, fail-closed missing/timeout result, release-blocking summary | `task security:audit`, `task security:scan` |
| PolicyInterface | Possible future OPA/Cedar/Casbin adapter | Trading mandate, behavior stops, human approval, live block | [Policy Contract](../architecture/policy-contract.md) |
| EvidenceInterface | Possible future OpenLineage/MLflow/DVC/Sigstore adapter | Receipt schema, claim boundaries, non-claims, review hooks | [Receipt Reference](receipts.md), [Evidence Inventory](../architecture/evidence-inventory.md) |

## Common Interface Rules

- Mature wheels can compute, scan, simulate, optimize, or shape orders.
- FinHarness records source, quality, lineage, receipt, and authority boundary.
- Mature wheel output may be evidence or a request, never a permission grant.
- `risk_gate`, `trading_guard`, human attestation, lesson-to-rule lineage, and
  receipts are non-replaceable discipline.
- Any new production dependency still needs explicit user approval before being
  added.

## Adapter Acceptance Checklist

Before a new adapter is considered complete:

- The existing caller-facing interface remains stable or has a migration note.
- Tests characterize the old behavior where applicable.
- Tests prove the mature adapter path is exercised.
- Receipts or summaries disclose backend/tool name and version when relevant.
- The adapter output includes a clear non-authority boundary.
- No cap, live block, human confirmation, or lesson-to-rule rule is weakened.
