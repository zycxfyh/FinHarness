# Agent Operating Surface

Status: v2 (2026-07-09 — Wave 2 complete)
Phase: Wave 2 complete — 16 PRs (#190–#205) merged.

## One Sentence

FinHarness Wave 2 shifts from "building cognition governance primitives" to
"building an agent operating surface" — the layer that lets a strong agent
actually work, learn, recall, organize tools, load domain playbooks, run
evaluators, and enter human collaboration workspaces.

Governance is not the product. Governance is load-bearing infrastructure for
agent capability expansion.

## Hard Principles

1. **Strong-agent assumption.** Future agents can distinguish draft/evidence,
   plan/execution, policy/authority. The system does not exist to prevent
   conceptual confusion — it exists to give a strong agent stable operating
   interfaces: objects, metadata, routing, memory, search, evaluation,
   collaboration surfaces.

2. **Hermes-inspired narrow waist, edge expansion.** The agent core stays
   thin. New capability lives at the edges via tools, context packs,
   playbooks, evaluators, plugins, memory packs, and workspace projections.
   New core model-tool schema is a last resort.

3. **Governance is infrastructure, not product center.** ContextTrust,
   EvaluationReport, AuthorityTransition, and AgentRunReceipt remain present
   but recede from the narrative center. They are load-bearing walls, not
   the house.

4. **Every new operating surface starts receipt-only or projection-only.**
   No StateCore table unless ≥2 integration points depend on it. The
   graduation rule from Wave 0 still applies.

5. **Execution Kernel remains frozen.** Agent Operating Surface gives the
   agent more capability — but not execution authority. The Execution Kernel
   (OrderDraft → PreTradeCheck → ApprovalRecord → SimulatedBrokerAdapter)
   is unchanged.

## Hermes Reference

Hermes-agent demonstrates a mature agent operating environment: tool
registry, skills, memory, session search, scheduler, plugins, MCP,
subagents, progressive disclosure, platform delivery, self-improvement
loop. It proves that the right shape for a modern agent is:

```text
narrow core waist → expansive operating surfaces
```

FinHarness should absorb this architecture pattern but apply
domain-specific semantics: every tool result becomes an evidence envelope;
every memory proposal requires human attestation; every playbook is
versioned and evaluation-linked; every scheduled cognition snapshots its
evaluator/context/profile versions.

## What Changes from Waves 0–1.3

Waves 0–1.3 built **Agent Cognition Runtime v0**: 7 receipt/projection
primitives, a deterministic cognition flow, semantic hardening, and
escape-hatch closure. These primitives are now the load-bearing structure.

Wave 1.3 proved the flow is semantically governed and not easily bypassed.

Wave 2 does **not** continue adding governance primitives. It builds the
operating surfaces on top of the existing cognition substrate:

- Instead of "one more guardrail," we build **tool registry and availability
  snapshots** so the agent knows what it can use.
- Instead of "one more policy gate," we build **receipt search and domain
  memory** so the agent can learn across runs.
- Instead of "one more lexical evaluator," we build an **evaluator registry
  and a first domain evaluator** so evaluation becomes a capability surface.

## Wave 2 Operating Surfaces

Wave 2 adds 6 operating surfaces across 16 PRs (#190–#205):

| Track | Surface | What the agent gains |
|-------|---------|---------------------|
| A — Tool | AgentToolRegistry v0, availability snapshots | Structured knowledge of available tools, why unavailable |
| B — Runtime | Tool result evidence envelope, receipt bridge | Tool outputs become typed, searchable, evidence-aware |
| C — Memory/Search | Context trust map extraction, receipt search, domain memory drafts | Cross-run learning, recall, memory proposals |
| D — Playbooks | CognitionPlaybook spec, progressive disclosure loader | On-demand domain procedure loading |
| E — Evaluation | Evaluator registry, research evidence evaluator | Discoverable evaluators, first domain review capability |
| F — Work Surface | Operating-inputs flow, review workspace projection, smoke, docs | End-to-end integration, human collaboration surface |

## What This Enables

After Wave 2, the FinHarness agent can:

```text
- discover and inspect its available tools
- understand why a tool is unavailable
- produce structured evidence envelopes from tool results
- have its runtime activity captured as searchable receipts
- search past reviews, plans, and evaluations
- propose domain memory for human attestation
- load review playbooks on demand (IPS drift, rebalancing, evidence triage)
- run a domain evidence-quality evaluator
- enter a human review workspace with structured projections
- exercise agent capabilities while the Execution Kernel stays frozen
```

## What Is Still Frozen

```text
- No StateCore table (receipt-only / projection-only)
- No Execution Kernel change
- No broker connection
- No order/execution object creation
- No AgentSession table
- No autonomous scheduler
- No multi-agent manager
- No CapitalActionKernel
- No agent freely mutating domain memory
- No LLM evaluator marketplace
```

These are not unimportant — they are Wave 3 / Wave 4 concerns, gated on
real operating pressure (≥2 integration points needing session/resume,
receipt search showing real multi-run patterns, etc.).

## PR DAG

```text
#190 (this RFC — architecture only)
  ↓
#191 AgentToolRegistry v0
  ↓
#192 Tool availability snapshot
  ↓
#193 Tool result evidence envelope
  ↓
#194 AgentRuntime → AgentRunReceipt bridge  ← already merged (originally #190)
  ↓
#195 Context projection → trust map extraction
  ↓
#196 Receipt / run search v0
  ↓
#197 Domain memory draft + promotion path
  ↓
#198 CognitionPlaybook spec
  ↓
#199 Progressive disclosure loader
  ↓
#200 Evaluator registry v0
  ↓
#201 Research evidence quality evaluator
  ↓
#202 Run cognition flow from operating inputs
  ↓
#203 Human review workspace projection
  ↓
#204 Agent operating surface smoke
  ↓
#205 Architecture sync (framework-index, target-space, this doc)
```

Each PR branches from main after the previous PR merges. Each PR states
its operating-surface dimension in the PR body.

## Non-goals (this wave)

- Continuing the governance-primitive expansion from Waves 0–1.3
- Building a full autonomous agent runtime
- Connecting to the Execution Kernel
- Adding real broker adapters
- Building a scheduler or cron system
- Creating AgentSession / TaskRuntime tables

## Relationship to Existing Architecture

This RFC extends `agent-native-target-space.md` (Wave 0) and
`framework-index.md`. The 8 agentic-space dimensions (Goal, Context,
Action, Evaluation, Authority, Deliberation, Feedback, Trace) remain
the classification system. Wave 2 adds a new classification axis:
**operating surface** (Tool, Runtime, Memory, Playbook, Evaluation,
Work Surface), orthogonal to the existing dimensions.

A PR in Wave 2 names both:
- Which agentic-space dimension it touches (from the 8)
- Which operating surface it expands (from the 6)
