# Top Finance Wheels Scan

Date: 2026-05-26

Goal: identify mature open-source finance projects we can absorb before writing
our own institutional finance modules.

## Recommendation

Do not hand-roll a full institution-grade engine yet.

Use this stack:

```text
Immediate:
  QuantStats for performance/risk reports
  skfolio or Riskfolio-Lib for portfolio construction
  Beancount-inspired ledger model for accounting/experiment records

Architecture reference:
  QSTrader for signal -> portfolio -> risk -> execution -> accounting separation
  QuantConnect LEAN for full professional engine concepts
  NautilusTrader for event-driven backtest/live parity

Later:
  QuantLib / OpenGamma Strata / ORE for derivatives, pricing, and market-risk analytics
```

## Selection Criteria

Use a project if it gives us one of these:

```text
Institutional process separation
Portfolio construction
Risk analytics
Performance reporting
Accounting / ledger truth
Execution simulation
Backtest-live parity
Instrument pricing
```

Avoid absorbing projects that are:

```text
Broker-region specific unless we need that broker
Too UI-heavy for our current research harness
Dead or mostly unmaintained when a maintained replacement exists
Too heavy before our internal abstractions are clear
```

## Best Candidates

### 1. QuantStats

Use for:

```text
Performance metrics
Risk metrics
Tear sheets
HTML reports
Monte Carlo risk analysis
```

Why it matters:

```text
This maps directly to our reporting layer.
```

Fit:

```text
High. Lightweight and Python-native.
```

Action:

```text
Add after approval as the first reporting wheel.
```

Source:

- https://github.com/ranaroussi/quantstats

### 2. skfolio

Use for:

```text
Portfolio optimization
Risk management
Cross-validation and stress-testing of portfolio models
scikit-learn-style model interface
```

Why it matters:

```text
This maps to our portfolio construction layer.
```

Fit:

```text
High. Modern, Python-native, institution-facing positioning.
```

Action:

```text
Evaluate against Riskfolio-Lib; likely prefer skfolio for ML-style pipelines.
```

Source:

- https://github.com/skfolio/skfolio

### 3. Riskfolio-Lib

Use for:

```text
Mean-risk optimization
CVaR / drawdown / risk parity style allocation
Asset allocation education
```

Why it matters:

```text
This is a very strong portfolio optimization reference and may be easier to
learn from than a full trading engine.
```

Fit:

```text
High for optimization experiments.
Medium for production architecture.
```

Action:

```text
Compare examples with skfolio before choosing one primary optimizer.
```

Source:

- https://github.com/dcajasn/Riskfolio-Lib

### 4. QSTrader

Use for:

```text
Backtesting architecture reference
Signal generation
Portfolio construction
Risk management
Execution
Simulated brokerage accounting
```

Why it matters:

```text
Its README explicitly separates signal generation from portfolio construction,
risk management, execution, and brokerage accounting. That matches our
institutional flow.
```

Fit:

```text
High as architecture reference.
Medium as direct dependency, because we already have Backtrader for basic tests.
```

Action:

```text
Study structure before hand-rolling our portfolio/risk/execution interfaces.
```

Source:

- https://github.com/mhallsmoore/qstrader

### 5. QuantConnect LEAN

Use for:

```text
Professional event-driven architecture
Multi-asset backtesting
Live-trading model
Portfolio accounting
Brokerage models
Fee models
Settlement and margin models
Universe selection
Corporate-action handling
```

Why it matters:

```text
This is one of the most complete open-source trading engines. It is too heavy
for our first loop, but extremely valuable as a reference for what mature
market infrastructure looks like.
```

Fit:

```text
Very high as reference.
Medium-low as immediate dependency due to size and C#/Python system complexity.
```

Action:

```text
Do not integrate now. Use it as the north-star architecture reference.
```

Source:

- https://www.lean.io/
- https://github.com/QuantConnect/Lean

### 6. NautilusTrader

Use for:

```text
High-performance event-driven backtesting
Backtest/live parity
Multi-asset and multi-venue trading systems
Production-grade trading engine concepts
```

Why it matters:

```text
This addresses one of the hardest real trading problems: research code and live
trading code diverging.
```

Fit:

```text
Very high as future execution engine.
Too heavy for our immediate educational research layer.
```

Action:

```text
Do not integrate yet. Study once we need event-driven execution and paper/live
trading parity.
```

Source:

- https://nautilustrader.io/
- https://nautilustrader.io/open-source/

### 7. Beancount

Use for:

```text
Double-entry ledger concepts
Plain-text financial records
Audit-friendly accounting
Experiment ledger inspiration
```

Why it matters:

```text
Institution-grade finance requires record truth. Our experiment ledger and
portfolio accounting should learn from double-entry systems.
```

Fit:

```text
High as conceptual model.
Medium as direct dependency because GPL licensing needs care.
```

Action:

```text
Study the model. Consider implementing a tiny neutral ledger schema rather than
depending directly.
```

Source:

- https://github.com/beancount/beancount/
- https://beancount.github.io/

### 8. Ledger CLI

Use for:

```text
Plain-text double-entry accounting model
Command-line reporting pattern
```

Fit:

```text
High as conceptual reference.
Low as direct integration for our Python-first harness.
```

Source:

- https://ledger-cli.org/
- https://github.com/ledger/ledger

### 9. QuantLib

Use for:

```text
Instrument pricing
Fixed income
Derivatives
Curves
Quantitative finance primitives
```

Why it matters:

```text
QuantLib is a de-facto open-source foundation for quantitative finance pricing.
```

Fit:

```text
High later.
Low now because our current loop is equities/ETF research, not derivatives
pricing.
```

Source:

- https://github.com/lballabio/QuantLib
- https://github.com/quantlib

### 10. OpenGamma Strata

Use for:

```text
Market risk analytics
Pricing and risk calculations
Curves and measures
Institutional Java risk architecture
```

Fit:

```text
High as institutional reference.
Low as immediate dependency because it is Java and outside our Python harness.
```

Source:

- https://github.com/OpenGamma/Strata
- https://strata.opengamma.io/

### 11. Open Source Risk Engine

Use for:

```text
Risk analytics
Pricing engines
Simulation
XVA/sensitivities/regulatory scenarios
QuantLib-based institutional risk concepts
```

Fit:

```text
High later for risk-system study.
Low now for simple ETF/equity research.
```

Source:

- https://github.com/OpenSourceRisk/Engine
- https://orestudio.github.io/OreStudio/

### 12. rotki / Wealthfolio

Use for:

```text
Portfolio tracking
Local privacy-first finance data
Accounting and analytics UX ideas
```

Fit:

```text
Medium as product/UX reference.
Low as core institutional research dependency.
```

Sources:

- https://github.com/rotki/rotki
- https://wealthfolio.app/

## What We Should Absorb First

### Phase 1: Reporting And Portfolio Basics

```text
QuantStats
skfolio or Riskfolio-Lib
Tiny internal experiment ledger inspired by Beancount
```

Why:

```text
These directly strengthen our current Data -> Backtest -> Risk -> Report loop
without forcing a platform rewrite.
```

### Phase 2: Architecture Alignment

```text
Study QSTrader interfaces.
Map our modules to:
  data
  signal
  portfolio
  risk
  execution
  accounting
  reporting
```

### Phase 3: Heavy Platform Decision

Choose one later:

```text
LEAN if we want a complete professional multi-asset algorithmic trading engine.
NautilusTrader if we want high-performance event-driven backtest/live parity.
Keep our own small harness if the goal remains research and learning.
```

## Current Decision

We should not hand-roll portfolio reporting, performance tearsheets, or
optimization from scratch.

Recommended next step:

```text
Add QuantStats as the reporting wheel.
Then run one SPY strategy report from our existing Backtrader workflow.
Then compare skfolio vs Riskfolio-Lib on a tiny 3-ETF portfolio.
```

