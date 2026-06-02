# Ideas: Agent-Native Financial OS

Date: 2026-05-31

These ideas come from the recent discussion about external AI trading platforms,
crypto exchange APIs, multi-agent finance systems, and the bottleneck rent alpha
research model.

## IDEA-001: API-Native Agent Trading Harness

Idea:
Build FinHarness around an API-native trading loop instead of ad hoc trading
scripts.

Hypothesis:
The right local product shape is not "AI trades for me", but a controlled loop:
read market/account state, generate a proposal, preview risk, execute only
through explicit gates, reconcile, and write a receipt.

Minimum experiment:
Write a single dry-run workflow that reads OKX market data, creates a mock
order proposal, runs the Rust risk gate, and writes a JSON receipt without live
execution.

Success signal:
The workflow can be reviewed from receipt alone: inputs, proposal, risk
decision, skipped execution, and known limitations are all visible.

## IDEA-002: Bottleneck Rent Alpha Research Protocol

Idea:
Turn the "purple shiso leaf" discussion into a formal Bottleneck Rent Alpha
research protocol.

Hypothesis:
The useful investment object is not a cold small-cap stock. It is a market
mispricing of a binding constraint's shadow price in a growing system.

Minimum experiment:
Create a research template with these fields: system growth, binding
constraint, supply elasticity, substitutability, supplier exposure, financial
elasticity, mispricing, catalyst, and disconfirming evidence.

Success signal:
One AI infrastructure case can be decomposed into facts, inferences,
assumptions, and debts without becoming a buy recommendation.

## IDEA-003: Multi-Agent Investment Committee, Proposal-Only

Idea:
Use a multi-agent committee for analysis, but keep it proposal-only.

Hypothesis:
LLM agents are most useful as analyst, skeptic, risk reviewer, and journal
writer. They should not own live execution.

Minimum experiment:
Run a local multi-role review over one bottleneck thesis: analyst, bear case,
risk gate, and portfolio reviewer. Output one structured proposal and one
rejection/approval rationale.

Success signal:
The final proposal includes an explicit failure mode and cannot bypass the risk
gate.

## IDEA-004: Exchange Tool Boundary

Idea:
Expose exchange access through a strict read / preview / execute tool boundary.

Hypothesis:
Most trading agent failures come from collapsing analysis and execution into
one permission surface. A typed boundary reduces accidental live actions.

Minimum experiment:
Document and implement command categories for OKX or CCXT-style access:
read-only market data, account read, dry-run preview, demo execution, and live
write with environment gate.

Success signal:
Live write commands are impossible unless an explicit environment flag, command
allowlist, and receipt writer are all present.

## IDEA-005: Track Record and Receipt Layer

Idea:
Treat every signal, proposal, preview, order, cancel, fill, and review as a
track-record event.

Hypothesis:
The valuable artifact is not a single trade. It is a durable record that can be
scored over time for PnL, drawdown, false positives, missed risks, and reasoning
quality.

Minimum experiment:
Define a JSON schema for proposal receipts and post-trade review receipts.

Success signal:
Ten paper proposals can be compared without reading chat logs.
