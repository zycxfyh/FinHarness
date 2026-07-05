# 02 Prompt / Context Injection

Hermes treats prompt construction as a runtime object, not a static string. The useful pattern is to separate durable identity, selected context, and volatile session facts.

```text
stable prompt parts
-> scanned context files / caller context
-> volatile session facts
-> model-visible prompt
```

For FinHarness this matters because prompt text can accidentally imply authority. A prompt that says an Agent can “review”, “approve”, “execute”, or “manage” capital without profile and receipt boundaries can become a product bug even when the code is safer.

## Hermes Pattern

Hermes separates prompt material into three practical tiers:

| Tier | Examples | Stability goal |
| --- | --- | --- |
| Stable | identity, tool guidance, skills, model/platform hints, profile hints | changes rarely; cache-friendly |
| Context | project instructions, selected context files, caller-provided system message | scoped to workspace/session |
| Volatile | date, session facts, memory snapshot, provider/model facts | changes often; kept explicit |

It also scans context files before injection. Workspace text is useful evidence, but not automatically trusted authority.

## FinHarness Mapping

FinHarness should make Agent prompts inspectable as parts:

| Prompt part | Role |
| --- | --- |
| `governance_floor` | authority boundaries derived from active profile, capability state, receipts, and sources |
| `active_profile` | visible capabilities and absent capabilities |
| `tool_guidance` | only for tools visible to the active profile |
| `context_pack_summary` | source refs, receipt refs, age, and limitations |
| `session_facts` | date/session/model/provider metadata |
| `output_contract` | answer format, citation, non-claim, and review hints |

The active profile should shape both tool visibility and prompt language:

- default profile advertises read/explain scopes only;
- review-draft style profile may describe append-only governed proposal drafting;
- write-capable profiles must name their explicit append-only artifact and runtime
  handler.

## Context Injection Rules

1. Context packs are evidence inputs, not authority.
2. Current source files, receipts, and state snapshots outrank session memory.
3. Prompt guidance must be generated from active capability state where possible.
4. A model-visible instruction must not promise tools that are hidden by profile.
5. Date/session/provider facts belong in volatile prompt parts, not stable identity.

## Review Surface

Agent answers should become easier to audit by exposing:

- active profile;
- visible tool names or toolset summary;
- context pack ids and source refs;
- receipt refs used;
- unavailable or suppressed capabilities;
- limitations and non-claims.

This supports the next product layer: making Agent output reviewable without adding more Agent authority.

## Tests To Add Later

- default profile prompt does not mention proposal drafting as available;
- review-draft prompt mentions proposal drafting but not approval or execution;
- every model-visible tool hint corresponds to a registered visible tool;
- context pack metadata is present before an Agent answer claims to use portfolio state.
