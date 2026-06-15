# Mature Wheel Control Plane

FinHarness should be a local control plane around mature finance, security, and
governance wheels. The project-owned value is not indicator math, return
statistics, order simulation, or dependency scanning. The project-owned value is
the decision discipline around those tools: permission gates, human review,
non-live defaults, lesson-to-rule lineage, receipts, and workflow visibility.

## Target Shape

```text
market data adapters
  -> data quality contracts
  -> indicator and research adapters
  -> performance and validation adapters
  -> risk and portfolio adapters
  -> execution engine adapters
  -> FinHarness guard, receipt, review, and lesson modules
```

The mature wheel owns heavy implementation. FinHarness owns the interface that
callers use locally: input normalization, authority checks, evidence references,
receipt writing, and workflow orchestration.

## System Interfaces

| Interface | Mature adapters | FinHarness keeps |
| --- | --- | --- |
| MarketDataInterface | OpenBB, yfinance, official broker or exchange data | source disclosure, OHLCV contract, freshness notes, receipts |
| DataQualityInterface | Pandera, Great Expectations | required contract, quality verdict, evidence refs |
| IndicatorInterface | TA-Lib, pandas-ta, vectorbt indicators | feature naming, state labels, lineage, non-advice notes |
| ResearchInterface | vectorbt | strategy candidate screening, parameter sweeps, rejected alternatives |
| PerformanceInterface | QuantStats, vectorbt stats | local summary schema and validation receipt fields |
| PortfolioRiskInterface | Riskfolio-Lib, skfolio | risk policy, mandate caps, review requirements |
| ExecutionEngineInterface | NautilusTrader, official venue tooling | dry-run default, adapter allowlist, live-write block, evidence receipt |
| SecurityScanInterface | CodeQL, Semgrep, Gitleaks, Trivy, OSV-Scanner or pip-audit | scanner aggregation, redaction, release-blocking summary |
| PolicyInterface | OPA, Cedar, Casbin, OpenFGA where useful | trading-specific mandate, behavior stops, human approval |
| EvidenceInterface | OpenLineage, MLflow, DVC, Sigstore where useful | receipt schema, claim boundaries, non-claims, review hooks |

## Replacement Order

1. PerformanceInterface: replace local return, drawdown, volatility, and Sharpe
   math with QuantStats while keeping `finharness.metrics` stable for callers.
2. IndicatorInterface: route MACD, Bollinger, RSI, and related formulas through
   TA-Lib or pandas-ta. Keep local state labels and quality notes.
3. DataQualityInterface: move OHLCV quality checks from custom conditionals to a
   dataframe contract adapter. Keep FinHarness quality verdicts.
4. ResearchInterface: add a vectorbt research adapter for parameter sweeps and
   validation snapshots. Keep hypothesis and proposal lineage.
5. PortfolioRiskInterface: add a Riskfolio-Lib adapter for optimization and risk
   budgeting. Keep `risk_gate` as the authority gate.
6. ExecutionEngineInterface: keep fake paper execution as a test adapter only;
   move serious paper/live-parity behavior behind NautilusTrader or official
   broker tooling. Keep live execution blocked unless an explicit policy changes.
7. SecurityScanInterface: make local hardening aggregate standard tool outputs
   instead of acting as a scanner implementation.
8. EvidenceInterface: evaluate OpenLineage, MLflow, DVC, or Sigstore only as
   storage/provenance adapters. Do not replace FinHarness receipt semantics.

## Replacement Progress

| Interface | Status | Evidence |
| --- | --- | --- |
| PerformanceInterface | started | `finharness.metrics` delegates summary statistics to QuantStats |
| IndicatorInterface | started | MACD and squeeze standard calculations delegate to TA-Lib; FinHarness keeps state labels |
| ResearchInterface | started | `vectorbt_runner` delegates MA research screening to vectorbt |
| PortfolioRiskInterface | started | `portfolio_risk` delegates allocation optimization to Riskfolio-Lib |
| DataQualityInterface | started | strict OHLCV validation is Pandera-backed; soft market-data verdict reuses the same price contract while keeping FinHarness verdict semantics |
| ExecutionEngineInterface | started | default paper order shaping uses NautilusTrader typed orders; fake adapter remains for test-only fill scenarios |
| SecurityScanInterface | started | hardening gate treats gitleaks, Trivy, and uv as bounded external scanner adapters with fail-closed missing/timeout results |
| EvidenceInterface | pending | receipt semantics remain local; external provenance adapters not selected |

## Non-Replaceable Discipline

These modules should be deepened, not deleted:

- `trading_guard`: behavior stops, thesis requirements, and operator cooling
  rules.
- `risk_gate`: mandate checks, permission checks, human review, and no-live
  authority.
- `rule_change_ledger` and lesson modules: lesson-to-rule lineage.
- receipt modules and governance graphs: claim/evidence/non-claim visibility.

Policy engines can help express these rules, and lineage/provenance tools can
store evidence, but no generic finance wheel knows this project-specific
discipline.

## Acceptance Criteria

Each replacement step must satisfy all of these before the old implementation is
considered retired:

- The existing FinHarness interface stays stable or has a deliberate migration
  note.
- A mature adapter is used for the heavy calculation or scanning work.
- Characterization tests preserve the current caller contract.
- New tests prove the adapter path is exercised.
- Receipts or summaries disclose the adapter and tool version when relevant.
- `trading_guard`, `risk_gate`, human review, non-live defaults, and receipts are
  not weakened.

## Remaining Gaps After Replacement

Even after all mature adapters are in place, FinHarness still will not prove:

- profitable alpha;
- institutional-grade data correctness;
- best execution, tax, accounting, custody, or legal compliance;
- production incident response;
- authorization for autonomous or live trading.

Those gaps need external data/vendor decisions, human review, operating
procedures, and specialist compliance work. Passing local checks remains
evidence, not authority.
