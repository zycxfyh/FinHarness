# Agent Harness

## Current Shape

The OpenAI Agents SDK layer lives in `src/finharness/agent_tools.py`.

Tools are registered once in `AGENT_TOOL_REGISTRY`, then exposed through
capability profiles in `agent_capabilities.py`.

Default profile tools:

- `get_quote_snapshot`
- `get_historical_risk_metrics`
- `evaluate_latest_risk_note`
- `get_capital_summary_context`
- `get_current_ips_context`
- `get_ips_check_context`
- `get_open_proposals_context`
- `get_proposal_timeline_context`

The `review-draft` profile adds:

- `draft_governed_proposal_from_context`

The `review-note` profile adds:

- `draft_agent_review_note_from_context`

The agent is named `Finance Research Harness Agent`.

Use `build_finance_research_agent(profile_name=...)` to create a runtime Agent
for a specific profile. Unknown profiles and profile tool names that are missing
from the registry fail closed.

## Local Checks

Describe the registered agent and tools:

```bash
task agent:describe
task agent:describe -- --profile review-draft
task agent:describe -- --profile review-note
```

Run tool-level tests without any model or API key:

```bash
task smoke
```

Run the real SDK `Runner` only when `OPENAI_API_KEY` is already present in the environment:

```bash
task agent:run
FINHARNESS_AGENT_PROFILE=review-draft task agent:run
FINHARNESS_AGENT_PROFILE=review-note task agent:run
```

If `OPENAI_API_KEY` is not set, the script exits cleanly and does not attempt to read secret files.

## Safety Defaults

- The agent must state that outputs are educational and not investment advice.
- The agent must disclose that historical data currently comes from yfinance/Yahoo Finance, not TradingView/TV.
- The agent can run promptfoo risk assertions against generated notes.
- The default profile remains read/explain only.
- The `review-draft` profile can create append-only governed proposal drafts
  for human review, not approvals, recommendations, execution authorization,
  orders, transfers, or broker actions.
- The `review-note` profile can create append-only `AgentReviewNoteDraft`
  artifacts on existing proposals for human review. Review notes may enter the
  proposal timeline, but they are not proposal revisions, attestations,
  approvals, rejections, recommendations, execution authorization, orders,
  transfers, or broker actions.
- `AgentReviewNoteDraft` artifacts are consumed by deterministic review queue
  triage (`/review/queue`) alongside proposals, attestations, archived state,
  receipt index rows, and proposal queue checks. The queue is a read model for
  human reviewer attention and next actions; it is not approval, rejection,
  attestation, recommendation, or execution authorization.
- Risk register v0 (`/risk/register`) derives read-only risk objects from review
  queue signals. It makes evidence gaps, stale context, duplicate proposals,
  policy mismatch, counter-evidence needs, Agent-reported risks, and open
  questions comparable for human review; it is not persistent risk state, risk
  acceptance, scoring, scenario generation, approval, or execution authorization.
