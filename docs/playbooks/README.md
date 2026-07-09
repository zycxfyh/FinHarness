# Cognition Playbooks

Status: v0 (2026-07-09)
Phase: Wave 2 — Track D

Cognition Playbooks are FinHarness's version of agent skills — domain-specific
review procedures that an agent can load on demand.

They are NOT general "how to use a tool" guides. They are structured cognition
workflows: what to check, what evidence to gather, what evaluators to run,
what stop conditions apply.

## Playbook Metadata

Each playbook is a markdown file under `docs/playbooks/` with YAML frontmatter:

```yaml
name: playbook-slug
version: 0.1.0
space: Evaluation | Deliberation | Review
required_context_packs:
  - capital_summary
  - current_ips
recommended_evaluators:
  - plan_draft_evaluator
side_effects:
  - read
  - append_only_review_write
execution_allowed: false
```

## Progressive Disclosure

Playbooks are loaded in two levels to avoid context pollution:

- **Level 0** (list): name, description, when_to_use — no procedure body
- **Level 1** (load): full procedure including steps, checks, and references

## Proposed Playbooks

| Name | Space | When to use |
|------|-------|-------------|
| ips-drift-review | Evaluation | IPS allocation drifted beyond threshold |
| research-evidence-triage | Evaluation | Evaluating quality of research evidence |
| rebalance-proposal-drafting | Deliberation | Drafting a rebalance proposal |
| liquidity-runway-review | Review | Checking portfolio liquidity runway |
| risk-assumption-challenge | Evaluation | Challenging risk assumptions in a proposal |

## Rules

- Playbooks are read-only for agents; agent cannot modify them
- Playbook updates: SkillUpdateDraft → EvaluationReport → human_attested → promoted
- Playbooks versioned, linked to EvaluationReport
- Loaded by context projection, not auto-injected into prompt
