# Risk Gate Layer: Institutional Practices

Date: 2026-06-02
Layer: 8 - Risk Gate
Related idea: ../../ideas/2026-06-02-risk-gate-layer-institutional-practices.md
Related proposal: ../proposals/2026-06-02-risk-gate-layer-institutional-practices.md

## Question

How do top institutions, trading firms, brokers, and venues handle the layer
between a proposed trade and execution?

## Short Answer

The eighth layer is not a trader saying "yes". It is an independent,
auditable, pre-execution control layer.

The institutional shape is:

```text
proposal
-> independent risk review
-> portfolio and mandate context
-> limit and permission checks
-> hard blocks for threshold breaches
-> audit trail
-> execution handoff only if allowed
```

For FinHarness, Risk Gate should consume `ProposalSnapshot` and produce
`RiskGateSnapshot`. It must not place orders.

## What Top Institutions Show

### BlackRock / Aladdin: Whole-Portfolio Risk, Shared Data, Stress Tests

BlackRock describes Aladdin Risk as giving a timely understanding of risk,
covering positions and risks across portfolios and teams. It emphasizes one
system, one database, quality-controlled data, thousands of risk factors, and
large-scale stress/scenario testing.

FinHarness translation:

```text
Risk Gate must evaluate the proposal in portfolio context.
It should require a shared source of truth for proposal, account, limit, and
portfolio state.
It should record stress/scenario questions even when the MVP cannot yet run
full risk models.
```

Source:

```text
https://www.blackrock.com/aladdin/benefits/risk-managers
```

### Citadel: Risk Group Independent From Investment Team

Citadel states that its Portfolio Construction and Risk Group operates
independently of the investment team and reports directly to the CEO. It
identifies risk exposures, monitors tolerance levels, and runs constant
monitoring, review, automated testing, and stress scenarios.

FinHarness translation:

```text
Layer 7 can create a proposal.
Layer 8 must be a separate decision object.
The same layer that generated the proposal cannot self-approve it.
```

Source:

```text
https://www.citadel.com/what-we-do/
```

### PIMCO: Convert Views Into Risk Targets

PIMCO says its Investment Committee distills macro views into specific risk
targets that become parameters for every strategy.

FinHarness translation:

```text
Risk Gate must convert proposal language into bounded parameters:
  risk budget request
  permitted instrument universe
  horizon
  scenario sensitivity
  review cadence
  invalidation conditions
```

Source:

```text
https://www.pimco.com/us/en/about-us/our-process
```

### AQR: Active Return Inside A Risk-Controlled Framework

AQR describes systematic investing as disciplined, grounded in economic theory,
and implemented with precision from design to implementation. It also says its
equity goal is active returns within a risk-controlled framework.

FinHarness translation:

```text
Risk Gate should not ask only "is the idea good?"
It should ask "is this candidate still within the intended risk framework?"
```

Source:

```text
https://www.aqr.com/What-We-Do/Our-Approach
```

### SEC Rule 15c3-5: Pre-Trade Credit, Capital, Erroneous Order, And Compliance Controls

The SEC Market Access Rule requires broker-dealers with market access to
establish documented risk controls and supervisory procedures. These controls
must prevent orders that exceed preset credit or capital thresholds, appear
erroneous, fail pre-order regulatory requirements, or involve restricted
trading.

FinHarness translation:

```text
Layer 8 needs hard checks before any Execution handoff:
  max notional
  max quantity intent
  restricted instrument
  permission boundary
  erroneous order language
  auditability
```

Source:

```text
https://www.sec.gov/rules-regulations/2011/06/risk-management-controls-brokers-or-dealers-market-access
```

### FINRA: Thresholds Need Evidence, Aggregation, Review, And Hard Blocks

FINRA highlights effective practices around documented thresholds, periodic
reviews, aggregated credit/capital usage, procedures for threshold changes, and
pre-trade hard blocks. It warns about unsupported thresholds, aggregate exposure
blind spots, and soft warnings that fail to stop threshold breaches.

FinHarness translation:

```text
Risk Gate quality must fail if limits are not documented.
Soft warnings are not enough for threshold breaches.
Any override path needs reason, actor, timestamp, and receipt.
```

Source:

```text
https://www.finra.org/rules-guidance/guidance/reports/2017-report-exam-findings/market-access-controls
```

### CME: Venue-Level Risk Admins, Limits, Permissions, Real-Time Dashboards, Audit Trail

CME describes pre-trade risk management for clearing and trading participants:
monetary limits, delta/DV01, position limits, order blocking/cancel functions,
permissions, real-time dashboards, reports, and audit trails.

FinHarness translation:

```text
Risk Gate should model:
  limit checks
  permission checks
  position/concentration checks
  cancel/kill-switch handoff requirements for later execution
  audit trail for all settings and decisions
```

Source:

```text
https://www.cmegroup.com/solutions/market-access/globex/trade-on-globex/pre-trade-risk-management.html
```

### Interactive Brokers: Real-Time Margin, Multi-Asset Exposure, Pre-Trade Vetting

Interactive Brokers describes real-time monitoring, real-time margining,
multi-asset exposure through Risk Navigator, and automatic pre-trade order
vetting.

FinHarness translation:

```text
Even a paper workflow should check:
  account state
  margin/leverage state
  buying-power proxy
  cross-asset exposure
  pre-trade permission
```

Source:

```text
https://www.interactivebrokers.com/en/whyib/risk-management.php
```

### Jane Street: Real-Time Visibility, Human Judgment, Edge Cases, Tail Risks, Postmortems

Jane Street says it builds critical trading and risk systems in-house, gives
traders real-time visibility into trading activity, treats human judgment as
critical, studies interrelated/tail risks, and uses postmortems for process
improvement.

FinHarness translation:

```text
Risk Gate must produce human-readable reasons, not just booleans.
It should ask tail-risk and interrelation questions.
It should emit review hooks for postmortem and learning.
```

Sources:

```text
https://www.janestreet.com/what-we-do/overview/
https://www.janestreet.com/who-we-are/
```

### Millennium: Independent Decisions Inside A Rigorous Risk Framework

Millennium describes independent decisions, global scale, many daily trades,
and a commitment to consistency through a rigorous risk framework, adaptive
business model, capital stability, technology, and discipline.

FinHarness translation:

```text
Risk Gate should let proposals remain independent while enforcing shared
constraints.
Independent idea generation needs centralized risk discipline.
```

Source:

```text
https://www.mlp.com/approach/
```

## FinHarness Risk Gate MVP

Input:

```text
ProposalSnapshot
ProposalReceipt ref
ProposalCandidate
RiskGateRequest
optional account context
optional mandate context
optional portfolio exposure context
optional drawdown/behavior state
```

Output:

```text
RiskGateDecision
RiskGateCheck
RiskGateQuality
RiskGateLineage
RiskGateSnapshot
RiskGateReceipt
execution_handoff
review_questions
```

Allowed decision values:

```text
approved_for_paper_review
blocked
needs_more_evidence
needs_human_review
rejected
```

Forbidden outputs:

```text
broker order
live execution approval
final position size
leverage instruction
stop loss / take profit order
unreviewed override
```

## Proposed Checks

```text
proposal_quality_check:
  ProposalSnapshot.quality.ok must be true.

source_linkage_check:
  ProposalCandidate must link back to ValidationSnapshot and result ids.

mandate_check:
  candidate must fit allowed objective, asset class, venue, and horizon.

instrument_permission_check:
  symbol/instrument must be allowed for this workflow.

paper_or_live_permission_check:
  MVP allows paper review only; live must be blocked.

max_notional_check:
  candidate cannot exceed configured paper notional cap.

concentration_check:
  candidate cannot create excessive single-symbol or sector concentration.

liquidity_check:
  candidate must have enough liquidity evidence or be blocked.

drawdown_state_check:
  current drawdown or consecutive loss state can block promotion.

behavior_reset_check:
  if behavior guard indicates reset required, block or require human review.

scenario_check:
  candidate must state what scenario would make the risk unacceptable.

order_language_check:
  block order, quantity, leverage, live, approved, execute language.

human_review_check:
  require explicit human review for any paper approval.
```

## LangGraph Shape

```text
source_config
-> load_proposal_snapshot
-> proposal_quality_check
-> mandate_check
-> instrument_permission_check
-> paper_or_live_permission_check
-> exposure_limit_check
-> concentration_check
-> liquidity_check
-> drawdown_behavior_check
-> scenario_check
-> decision
-> quality
-> lineage
-> snapshot
-> receipt
-> consumer_handoff
-> review_hook
-> final
```

Failed path:

```text
quality failed
-> blocked_or_failed_receipt
```

## First MVP Boundary

Keep the first version deterministic:

```text
no broker calls
no live account mutation
no LLM decision authority
paper-review only
human review required
hard block on missing limits
hard block on proposal quality failure
```

The most important institutional lesson is:

```text
Risk Gate is where proposal language becomes permission-aware controls.
It is not where orders are born.
```
