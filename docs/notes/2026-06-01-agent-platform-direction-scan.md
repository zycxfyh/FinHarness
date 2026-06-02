# Agent Platform Direction Scan

Date: 2026-06-01

Purpose: compare current OpenAI, Anthropic/Claude, and Google/Gemini agent
directions and extract implications for FinHarness.

Sources are official product/docs pages unless noted.

## Compression

The major AI platforms are converging on the same shape:

```text
model
-> agent harness
-> tool/app/connectors
-> sandbox or managed runtime
-> memory / files / state
-> traces / receipts
-> human approval and governance
```

For FinHarness, this confirms the direction:

```text
do not build a single chatbot
build a governed financial decision operating system
```

## OpenAI Direction

Signals:

```text
Responses API as the agentic interface
Agents SDK for orchestration and traces
built-in tools: web search, file search, code interpreter, computer use
remote MCP support
Apps SDK for interactive apps inside ChatGPT
AgentKit / Agent Builder / ChatKit for building and deploying workflows
native sandbox execution for long-horizon agent work
```

Implication for FinHarness:

```text
OpenAI is moving toward hosted tools, agent workflows, app surfaces, and
observable traces.

FinHarness should keep its own receipts and governance models, while exposing
selected capabilities as tools/apps later:

MarketDataSnapshot search
IndicatorSnapshot search
EventSnapshot search
proposal builder
risk gate
review dashboard
```

Design lesson:

```text
Every FinHarness tool should be typed, permissioned, and traceable.
```

## Anthropic / Claude Direction

Signals:

```text
Claude Code style agent harness
Claude Agent SDK
subagents, hooks, MCP, plugins
cloud/web execution for delegated coding tasks
financial-services agent templates
connectors and MCP apps for governed data/tool access
Microsoft 365 add-ins for enterprise workflow surfaces
```

Anthropic's direction is especially relevant because it treats agent work as:

```text
specialized subagents
tool connectivity
workflow hooks
enterprise governance
long-running task delegation
```

Implication for FinHarness:

```text
Use subagent-like roles, but keep them proposal-only unless explicitly
authorized:

market-data auditor
indicator analyst
event monitor
thesis generator
skeptic / disconfirming-evidence finder
risk reviewer
receipt writer
post-trade reviewer
```

Design lesson:

```text
Agent roles are useful; authority must stay outside the agent.
```

## Google / Gemini Direction

Signals:

```text
Gemini app becoming more proactive and agentic
Daily Brief style personalized monitoring
Gemini Agent / Antigravity for complex tasks
Managed Agents in the Gemini API
Interactions API
isolated Linux environments
AGENTS.md and SKILL.md as versionable agent definitions
Deep Research via API
Gemini/Google Finance direction for research surfaces
generative interfaces and dynamic views
```

Implication for FinHarness:

```text
Google is pushing proactive agents, managed runtimes, research agents, and
dynamic UI surfaces.

FinHarness should prepare for:

daily financial brief generation
event monitoring agents
deep research agents over filings/news/social
managed sandbox execution for experiments
dynamic decision dashboards generated from receipts
```

Design lesson:

```text
FinHarness should keep agent behavior versioned in repo files, not only prompts
hidden in chats.
```

## CLAUDE.md Pattern Lessons

Useful patterns from existing `CLAUDE.md` files:

```text
mandatory rules
project structure guide
operation guide
testing commands
compatibility boundaries
security review notes
when to run full verification
how to handle docs and examples
```

FinHarness should use `AGENTS.md` the same way:

```text
project role
AI cognitive engineering rules
layer map
mature-wheel ownership
delivery method
safety boundaries
platform direction
verification commands
```

## FinHarness Platform Strategy

Do not bind the product to one AI provider.

Use a provider-neutral core:

```text
Snapshot
Quality
Lineage
Receipt
Proposal
RiskGate
Review
```

Then expose adapters:

```text
OpenAI:
  Agents SDK / Apps SDK / Responses tools

Claude:
  MCP tools / plugins / subagent-style roles

Gemini:
  Managed agents / Interactions API / AGENTS.md + SKILL.md style definitions
```

The durable asset is not the provider call.

The durable asset is:

```text
evidence-bound financial workflow state
```

## Product Ideas

### IDEA: Daily Edge Brief

Build a daily AI-generated financial brief from:

```text
MarketDataSnapshot
IndicatorSnapshot
EventSnapshot
open hypotheses
portfolio/watchlist state
known risks
```

The brief should produce:

```text
what changed
why it matters
what evidence supports it
what is uncertain
which hypotheses changed
what requires human review
```

### IDEA: Multi-Agent Proposal Committee

Roles:

```text
information scout
indicator analyst
event interpreter
thesis generator
skeptic
risk officer
receipt writer
```

Output:

```text
one structured proposal or rejection
no direct execution authority
```

### IDEA: Receipt-Native Financial App

Use ChatGPT Apps SDK / Gemini dynamic views / Claude artifacts-style surfaces
later to render:

```text
snapshot lineage
feature state
event timeline
hypothesis tree
risk gate result
review scorecard
```

## Sources

- OpenAI Agents SDK:
  https://platform.openai.com/docs/guides/agents-sdk/
- OpenAI tools:
  https://platform.openai.com/docs/guides/tools?api-mode=responses
- OpenAI Agents / AgentKit:
  https://platform.openai.com/docs/guides/agents
- OpenAI Apps SDK:
  https://openai.com/index/introducing-apps-in-chatgpt/
- OpenAI Agents SDK evolution:
  https://openai.com/index/the-next-evolution-of-the-agents-sdk
- OpenAI Docs MCP:
  https://platform.openai.com/docs/docs-mcp
- Anthropic Claude Agent SDK:
  https://www.anthropic.com/engineering/building-agents-with-the-claude-agent-sdk/
- Anthropic Claude financial services agents:
  https://www.anthropic.com/news/finance-agents
- Anthropic MCP / AAIF:
  https://www.anthropic.com/news/donating-the-model-context-protocol-and-establishing-of-the-agentic-ai-foundation
- Anthropic Claude Code plugins:
  https://www.anthropic.com/news/claude-code-plugins
- Google Gemini managed agents:
  https://blog.google/innovation-and-ai/technology/developers-tools/managed-agents-gemini-api/
- Google I/O 2026 developer highlights:
  https://blog.google/innovation-and-ai/technology/developers-tools/google-io-2026-developer-highlights
- Google Gemini app agentic direction:
  https://blog.google/innovation-and-ai/products/gemini-app/next-evolution-gemini-app/
- Google Gemini Deep Research:
  https://blog.google/innovation-and-ai/technology/developers-tools/deep-research-agent-gemini-api/
