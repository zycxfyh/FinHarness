# 05 Delegation Boundary

Hermes separates delegation from durable work:

```text
delegation = bounded fork-join subtask
kanban/task = durable stateful work item
```

This distinction is important for FinHarness because multi-agent systems can easily blur authority. A child Agent summary is useful analysis, not source evidence, not approval, and not execution authorization.

## Hermes Pattern

A delegated child Agent receives:

- a fresh conversation;
- explicit context;
- a restricted toolset;
- its own execution/session boundary;
- a bounded task;
- a summary result returned to the parent.

Mature systems also restrict child Agents:

- child tools are a subset of parent-visible tools;
- recursive delegation is disabled by default;
- approval tools are denied;
- user interaction tools are usually denied;
- memory writes are usually denied;
- timeouts and heartbeats are visible;
- cleanup restores parent runtime state.

## FinHarness Rule

FinHarness should not implement subagents as an authority upgrade.

Future subagents should be read-only analysts by default:

- source summarizer;
- counter-evidence finder;
- receipt consistency checker;
- proposal duplicate checker;
- docs drift checker.

They should not:

- create governed proposals by default;
- approve or reject proposals;
- attest decisions;
- execute orders;
- transfer funds;
- rewrite receipts;
- broaden their own toolset;
- ask the user for approval on behalf of the parent.

## Summary Is Not Evidence

A subagent output should be treated as a note that points back to evidence:

```text
subagent summary -> candidate finding -> parent verifies refs
```

It must not become:

- source of portfolio truth;
- receipt of what happened;
- human attestation;
- policy override;
- execution authorization.

## When To Delegate

Use delegation only when the task is:

- read-only;
- bounded;
- independently checkable;
- easier to parallelize than to keep in a single context;
- returned with source refs or explicit unknowns.

Do not delegate when the task changes state, requires human authority, or depends on subtle product judgment that the parent cannot verify.
