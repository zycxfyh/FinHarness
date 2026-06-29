# 09 Observability / Diagnostics

Hermes makes the Agent loop observable. The runtime should be able to show what was attempted, which tools ran, which guardrails fired, how much budget was used, and why work stopped.

For FinHarness, observability is not decorative logging. It is how a human reviewer knows whether an Agent-created draft is reviewable.

## Hermes Pattern

Hermes exposes several surfaces:

- developer logs;
- platform/UI callbacks;
- tool results;
- final answer;
- trajectories;
- usage/cost records;
- guardrail decisions;
- plugin observer hooks.

These are different audiences. A tool result for the model, a receipt for audit, a UI event for Cockpit, and a developer log should not be collapsed into one string.

## FinHarness Mapping

An Agent proposal draft should eventually expose:

- active profile;
- visible tools;
- context pack ids;
- source refs;
- receipt refs;
- validation path;
- guardrail findings;
- `execution_allowed=false`;
- `requires_human_review=true`;
- proposal id and review state.

This converts “Agent said it created a draft” into a reviewable runtime fact.

## Tool Pipeline

Mutating Agent tools should be observable as a pipeline:

```text
profile/capability check
-> source/ref validation
-> guardrail classification
-> StateCore/proposal write
-> receipt write
-> review queue visibility
-> structured tool result
```

Each stage can pass, warn, block, or fail.

## Budget And Loop Guards

Hermes tracks iteration budget and repeated tool-call patterns. FinHarness should do the same for:

- repeated reads of the same proposal timeline;
- repeated proposal draft attempts with similar arguments;
- repeated missing-source validation failures;
- repeated queue checks with no state change;
- repeated provider calls returning the same data gap.

The result should be structured:

```json
{
  "action": "warn",
  "code": "duplicate_proposal_draft_attempt",
  "execution_allowed": false
}
```

## Trajectory Is Not Authority

Agent trajectory is useful for diagnostics and evals. It should not become:

- evidence of current portfolio state;
- human attestation;
- receipt of what happened;
- source of policy truth.

Receipts and current source refs remain the audit roots.
