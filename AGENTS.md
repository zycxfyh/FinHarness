# FinHarness Agent Instructions

## Project Role

FinHarness is an AI-native financial decision operating system.

It is a research, evidence, workflow, risk, execution, and review harness that
can produce governed financial suggestions and staged capital-action workflows.
Those suggestions must be evidence-bound, conditional, auditable, and explicit
about their review state, authority boundary, receipt path, and future review
condition.

Do not pretend the system is advice-free. The point is to help the operator
form better financial judgments. Do prevent advice from becoming a magic answer
or an automatic action: every non-trivial suggestion should expose its evidence,
assumptions, rejected alternatives, risks, authority boundary, receipt path, and
future review condition.

The core loop is:

```text
information -> judgment -> action -> feedback -> process improvement
```

The project should compound through disciplined capture of evidence, ideas,
experiments, receipts, and lessons.

## AI Cognitive Engineering

Treat idea capture as a first-class engineering activity.

Individual ideas may look weak or premature when captured. The value comes from
accumulation, structure, lineage, recombination, scoring, and later evolution.

When a conversation produces a new project direction, market mechanism,
workflow principle, risk lesson, product insight, architecture pattern, or
research hypothesis, preserve it instead of leaving it only in chat.

Default capture destinations:

```text
ideas/backlog.md:
  Small, raw, or queue-like ideas.

ideas/YYYY-MM-DD-*.md:
  More mature executable ideas, hypotheses, experiments, and success signals.

docs/think/YYYY-MM-DD-*.md:
  Higher-level reasoning, first-principles thinking, project direction, and
  cognitive models.

docs/notes/YYYY-MM-DD-*.md or docs/notes/*.md:
  Implementation notes, architecture notes, integration decisions, and
  operating-model research.

docs/proposals/YYYY-MM-DD-*.md:
  Pre-action plans for substantial new layers, workflow redesigns, and
  experiments.

docs/reviews/YYYY-MM-DD-*.md:
  Post-action reviews for failures, surprises, blocked risk gates, bad
  proposals, and experiment outcomes.

docs/lessons/YYYY-MM-DD-*.md:
  Durable lessons distilled from repeated ideas, receipts, reviews, and
  experiments.
```

Prefer this minimum structure for captured ideas:

```text
idea_id
date
source
raw_thought
layer
hypothesis
why_it_might_matter
testable_experiment
success_signal
risk_or_failure_mode
links
status
```

Useful statuses:

```text
captured
clarified
planned
testing
validated
rejected
archived
evolved
```

Periodically run an idea evolution pass:

```text
find duplicates
find forgotten useful ideas
link related ideas
combine 2-3 ideas into an experiment
identify falsified assumptions
promote strong ideas into implementation plans
archive stale ideas with a reason
```

This is part of the product. FinHarness should become a financial idea
evolution system, not only a codebase.

This practice is necessary only when it improves future judgment, experiment
quality, execution safety, handoff, or learning. Do not write documents as
ceremony. Every durable note should reduce future cost, preserve evidence,
clarify a decision, or enable a better experiment.

## Architecture Principle

Use mature wheels for heavy finance mechanics.

FinHarness local code should stay thin:

```text
adapters
governance models
quality reports
lineage
snapshots
receipts
permission boundaries
workflow orchestration
tests
```

Do not hand-roll engines when mature wheels exist.

Current wheel ownership:

```text
OpenBB / yfinance:
  market and reference data access

TA-Lib / pandas-ta:
  indicator math

vectorbt:
  vectorized research and parameter sweeps

Backtrader:
  small event-style baseline backtests

NautilusTrader:
  typed trading data model and catalog/storage concepts

Alpaca / OKX official tooling:
  broker or venue adapters
```

FinHarness owns evidence and boundaries, not exchange semantics, matching,
portfolio accounting, margin engines, or execution engines.

## Layer Map

The working architecture should evolve through layers:

```text
1. Information / market data
2. Indicators / features
3. Events: news, filings, social, macro, on-chain
4. Interpretation: entities, claims, catalysts, risks
5. Hypotheses: thesis generation with disconfirming evidence
6. Validation: backtest, scenario, factor, liquidity, evidence checks
7. Proposal: structured action candidate
8. Risk gate: mandate, sizing, drawdown, leverage, liquidity, behavior
9. Execution: broker/exchange adapter with permission boundaries
10. Review: receipt, attribution, learning, process update
```

Each layer should have:

```text
typed input
typed output
quality report
lineage
receipt
tests
explicit permission boundary
```

Indicators, events, interpretations, and hypotheses do not authorize
execution. They describe state or create proposals only.

## Delivery Method

Prefer vertical slice MVPs over large horizontal architecture projects.

Each substantial build should try to move a small end-to-end workflow forward:

```text
source evidence
-> snapshot
-> interpretation or feature
-> hypothesis
-> validation
-> proposal
-> risk gate
-> receipt
-> review
```

Use this lightweight process:

```text
1. Charter:
   What problem does this layer or slice solve?

2. Boundary:
   What are the typed inputs, outputs, and non-goals?

3. Mature wheel:
   Which existing library owns the domain work?

4. Thin implementation:
   Write only adapters, governance, receipts, and tests locally.

5. Verification:
   Run the smallest relevant checks first, then project checks when needed.

6. Documentation:
   Record what changed, what remains missing, and what idea it supports.

7. Retrospective:
   Capture lessons and update the idea/think base.
```

## Goal-Bound Workflows

Do not treat goal mode as only an open-ended loop.

When a goal is substantial, bind it to an explicit workflow:

```text
goal
-> classify goal type
-> select workflow
-> instantiate workflow state
-> run graph nodes
-> checkpoint evidence
-> require gates where needed
-> write receipt/review/lesson
-> complete only when exit criteria are met
```

Use the agent loop for local reasoning inside a node. Use the workflow graph for
sequence, gates, and state. Use the goal object for persistence, exit criteria,
and completion evidence.

Current workflow bindings:

```text
cognitive_graph:
  ideas, research scans, proposals, reviews, lessons.

engineering_delivery_graph:
  engineering delivery quality gates, receipts, reviews, and lessons.

ten-layer domain chain:
  market data -> indicators -> events -> interpretation -> hypotheses ->
  validation -> proposal -> risk gate -> execution -> post-trade.
```

Archived workflow bindings:

```text
finance_graph:
  deleted in the repo prune; recorded as historical in tests/_graph_registry.py.

trade_graph:
  deleted in the repo prune; recorded as archived in tests/_graph_registry.py.
```

Do not mark a goal complete just because the agent produced a convincing answer.
A goal is complete only when the workflow exit criteria are satisfied and the
required artifacts, checks, receipts, or accepted failure notes exist.

## Module Governance

Maintain module-level memory as the project grows.

Every major layer should have a module document under:

```text
docs/modules/<module-name>.md
```

Each module document should record:

```text
purpose
current responsibilities
non-goals
typed inputs
typed outputs
important files
mature wheels / external systems
quality / lineage / receipt strategy
upgrade log
open risks
next upgrades
```

Use ADRs for significant decisions:

```text
docs/adr/YYYY-MM-DD-short-title.md
```

Use proposals for substantial new layers or cross-cutting changes:

```text
docs/proposals/YYYY-MM-DD-short-title.md
```

Use reviews and lessons to close the loop:

```text
docs/reviews/YYYY-MM-DD-short-title.md:
  what happened, what evidence exists, what surprised us, what should change.

docs/lessons/YYYY-MM-DD-short-title.md:
  durable lessons that should alter future module docs, ADRs, tests, or agent
  behavior.
```

Rule of thumb:

```text
small implementation detail:
  code comments/tests are enough.

module behavior change:
  update the module document upgrade log.

architectural choice:
  write an ADR.

new layer or workflow redesign:
  write a proposal before implementation.
```

This follows the spirit of Rust RFCs, Kubernetes KEPs, Django DEPs, GitLab
architecture blueprints, and ADR/MADR practice: write down why a change exists,
what was considered, what changed, and how success will be verified.

## Agent Platform Direction

Track OpenAI, Claude, Gemini, and other major agent platforms as references,
but keep FinHarness provider-neutral.

The major platforms are converging on:

```text
agent harnesses
managed or sandboxed execution
MCP / tools / apps / connectors
subagents or specialized roles
file and knowledge search
deep research
traceability
interactive app surfaces
```

FinHarness should adopt the durable pattern, not the surface branding.

Durable local objects:

```text
Snapshot
Quality
Lineage
Receipt
Proposal
RiskGate
Review
```

Provider-facing adapters can come later:

```text
OpenAI:
  Responses tools, Agents SDK, Apps SDK, Docs MCP.

Claude:
  MCP tools, plugins, subagent-style workflows, Claude Agent SDK patterns.

Gemini:
  Managed Agents, Interactions API, AGENTS.md/SKILL.md-style versioned agents.
```

Do not hide core project logic inside provider prompts. Agent behavior,
permissions, and workflows should be versioned in repo files when they become
important to the product.

## Safety

Generated analysis is not evidence.

Backtests are not live edge.

Paper trades are not proof of performance.

Future live write paths require explicit environment gates, risk gates,
allowlists, and receipts.
