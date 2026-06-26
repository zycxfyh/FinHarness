# Think: Risk Gate Layer

Date: 2026-06-02
Layer: 8 - Risk Gate
Source idea: ../../ideas/2026-06-02-risk-gate-layer-institutional-practices.md

## Core Thought

The eighth layer is the first layer where FinHarness is allowed to say:

```text
this candidate may continue
this candidate is blocked
this candidate needs more evidence
this candidate needs human review
```

It is still not allowed to say:

```text
place this order
use this final size
go live
```

That boundary matters because the Proposal layer creates governed intent, while
Risk Gate creates permission-aware control decisions.

## Mental Model

Layer 7 is research language translated into an action candidate.

Layer 8 is action-candidate language translated into risk-control language.

Layer 9 is the only place where broker/exchange semantics can appear, and only
after Risk Gate allows a handoff.

## The Institutional Pattern

Across asset managers, hedge funds, market makers, brokers, and venues, the
pattern repeats:

```text
independent risk authority
whole-portfolio view
documented limits
pre-trade hard blocks
permission and restricted-list controls
real-time monitoring
audit trail
postmortem/review loop
```

FinHarness should copy that pattern at small scale.

## Design Consequence

Risk Gate should be boring, strict, and deterministic.

That is a feature. The creative work belongs upstream:

```text
interpretation
hypotheses
validation
proposal
```

Risk Gate should be where excitement goes to be measured.

## First Principle

A proposal with good evidence can still be blocked.

Reasons:

```text
wrong mandate
wrong account mode
too much concentration
insufficient liquidity evidence
drawdown state says stop
behavior reset required
human review missing
live permission missing
unsupported limit threshold
```

## Implementation Implication

The MVP should use explicit configured thresholds instead of inference:

```text
max_paper_notional
allowed_symbols
allowed_action_types
max_candidates_per_run
max_symbol_concentration_pct
min_liquidity_evidence
live_execution_allowed=false
human_review_required=true
```

The output should be a decision plus reasons:

```text
decision
blocking_reasons
required_remediations
checks
lineage
receipt
```

## Anti-Pattern To Avoid

Do not let `paper_trade_candidate` become a soft approval.

In FinHarness vocabulary:

```text
paper_trade_candidate:
  "worth asking Risk Gate"

approved_for_paper_review:
  "Risk Gate found no MVP blocker, but Execution is still separate"
```

Even `approved_for_paper_review` is not an order.
