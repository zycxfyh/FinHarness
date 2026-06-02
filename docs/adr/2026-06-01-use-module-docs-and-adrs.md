# ADR: Use Module Docs And ADRs

Date: 2026-06-01
Status: accepted
Deciders: FinHarness project operator and Codex

## Context

FinHarness is evolving from a collection of scripts into an AI-native financial
decision operating system.

The project now has multiple layers:

```text
market data
indicators
events
interpretation
hypotheses
validation
proposals
risk gates
execution
review and learning
```

Chat history, scattered notes, and code alone are not enough to preserve why a
module exists, why it changed, what it owns, and what it must not do.

Top projects use similar mechanisms:

```text
Rust RFCs
Kubernetes KEPs
Django DEPs
GitLab architecture blueprints and handbook pages
ADR / MADR decision records
```

## Decision

FinHarness will use three persistent document types:

```text
docs/modules/<module>.md
  Current truth and upgrade log for each major module/layer.

docs/adr/YYYY-MM-DD-short-title.md
  Architecture decisions and their rationale.

docs/proposals/YYYY-MM-DD-short-title.md
  Before-code proposals for substantial new layers or workflow redesigns.
```

Every active major layer should have a module document.

Substantial module behavior changes should update that module's upgrade log.

Architectural choices should get an ADR.

New layers or broad workflow redesigns should get a proposal before
implementation.

## Considered Options

### Option 1: Keep Only Code And Chat History

Pros:

```text
fast
low ceremony
```

Cons:

```text
weak memory
hard to audit evolution
easy to repeat old debates
hard for future agents to understand why choices were made
```

### Option 2: One Giant Project Journal

Pros:

```text
simple location
chronological history
```

Cons:

```text
hard to find module-specific state
hard to separate ideas, decisions, and implementation history
grows into an unreadable log
```

### Option 3: Module Docs + ADRs + Proposals

Pros:

```text
module memory is close to module concepts
decisions have durable rationale
large changes can be reviewed before code
future agents can resume work from current-state docs
matches top-project governance patterns
```

Cons:

```text
more documentation work
risk of stale docs if not updated with code
requires discipline to avoid over-documenting tiny changes
```

## Consequences

Positive:

```text
FinHarness gains explicit project memory.
Each module can record why it upgraded and what remains risky.
New agents can orient faster.
Ideas, decisions, implementation, and retrospectives stay distinct.
```

Negative:

```text
Every substantial change now carries documentation overhead.
The team must keep module docs aligned with code and tests.
```

Neutral:

```text
Small implementation details still do not need ADRs.
Docs should scale with impact.
```

## Confirmation

This decision is working if:

```text
active modules have docs under docs/modules/
substantial upgrades append upgrade-log entries
major architecture choices have ADRs
new layer proposals appear before broad implementation
future summaries cite module docs instead of reconstructing history from chat
```

Immediate evidence:

```text
docs/modules/01-market-data.md
docs/modules/02-indicators.md
docs/notes/2026-06-01-module-governance-top-projects.md
AGENTS.md Module Governance section
```

## Links

```text
docs/notes/2026-06-01-module-governance-top-projects.md
AGENTS.md
docs/modules/01-market-data.md
docs/modules/02-indicators.md
```
