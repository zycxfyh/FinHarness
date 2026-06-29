# 03 Approval / Guardrails

Hermes shows a better pattern than keyword censorship: classify actions and route them through explicit guardrail decisions.

```text
requested action -> hardline floor -> dangerous-action classifier
-> approval-required queue or denial -> structured outcome
```

FinHarness should use this pattern to make boundaries precise without turning governance into friction for its own sake.

## Hermes Pattern

The mature pattern has four layers:

| Layer | Meaning |
| --- | --- |
| Hardline floor | Actions that are never allowed in the current runtime |
| Approval-required actions | Potentially valid, but require explicit human approval |
| Low-consequence actions | Allowed under profile, usually append-only or reversible |
| Read-only actions | Context, explanation, search, and inspection |

The important detail is action-level detection. The system should care about what the tool or command would do, not whether a sentence contains a suspicious word.

Hermes also uses a denial contract:

- denial is final for that attempted action;
- timeout is not consent;
- the Agent must not retry the same operation by rephrasing;
- silence does not become approval;
- approval scope is explicit and bounded.

## FinHarness Boundary

For FinHarness Agent runtime, the hardline absent set should include:

- live order placement;
- fund transfer;
- broker trade;
- receipt deletion or rewrite;
- attestation fabrication;
- Agent approval or rejection of proposals;
- policy override without human review.

Future approval-required actions may include:

- creating certain high-risk review objects;
- approving, rejecting, or attesting proposals;
- overriding IPS or risk-gate findings;
- publishing externally visible artifacts.

Current low-consequence Agent write capability should remain narrow:

- append-only governed proposal draft;
- human-review bound;
- no execution authorization;
- receipt-backed;
- visible in review surfaces.

## Guardrail Result Shape

Guardrail findings should be explicit enough for product review:

| Field | Purpose |
| --- | --- |
| `profile` | Which profile was active |
| `requested_action` | What the Agent attempted or described |
| `classification` | read-only, low-consequence, approval-required, denied |
| `execution_allowed` | Should remain false for current Agent capital actions |
| `source_refs` | Evidence used to evaluate the action |
| `receipt_refs` | Receipts created or consumed |
| `findings` | Human-readable reasons |
| `review_state` | pending, blocked, accepted, rejected, not-applicable |

## Product Implication

The next layer should surface guardrail state in the runtime response and review workspace. This gives the human reviewer a clear answer:

- what was proposed;
- why it was allowed to be drafted;
- why it is not approved or executable;
- which evidence and receipts support the draft;
- what must happen before any human decision.
