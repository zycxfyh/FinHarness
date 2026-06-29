# 04 Review Lifecycle

Hermes Kanban is not only a board. It is a durable task state machine for long-running work, handoff, blocking, comments, and recovery.

FinHarness does not need to copy the whole Kanban system. It does need the core idea for proposal review: a review object should remain understandable after the Agent session that created it is gone.

## Hermes Pattern

The useful pieces are:

- structured task state;
- ownership and assignee boundaries;
- durable comments;
- block kinds;
- heartbeat and stale-work detection;
- parent/child task links;
- structured completion and handoff;
- attachments as references, not authority;
- idempotency and duplicate prevention.

This is different from short delegation. A durable task queue survives sessions; a delegated subagent call is usually a bounded fork-join operation.

## FinHarness Mapping

For FinHarness, the durable unit is not a generic task first. It is a reviewable proposal and its surrounding evidence.

`proposal_show` or an equivalent review context should eventually expose:

- proposal metadata and status;
- source refs;
- receipt refs;
- context pack refs;
- timeline;
- review events;
- scaffold revisions;
- attestations;
- guardrail findings;
- counter-evidence;
- limitations and non-claims;
- archive state.

## Block Kinds

Borrow the block-kind idea, but make it domain-specific:

| Block kind | Meaning |
| --- | --- |
| `missing_source_refs` | Claim lacks current source evidence |
| `counter_evidence_needed` | Reviewer needs adverse evidence before decision |
| `data_gap` | Required portfolio or market data is missing/stale |
| `duplicate_proposal` | Similar open proposal already exists |
| `stale_context` | Context pack or receipt age is outside acceptable window |
| `policy_mismatch` | Proposal conflicts with IPS/policy facts |
| `human_review_required` | The system can draft but cannot decide |

## Transition Scope

A `block` must name what it blocks. Do not let one word mean every possible
transition.

| Transition | Meaning |
| --- | --- |
| `review_entry` | The draft should not enter the review queue as a distinct ready item yet |
| `human_attestation` | The draft should not become a human decision of record yet |
| `authority_transition` | The draft must not become higher authority state |
| `execution` | The draft must not authorize live action |

`human_review_required` is an authority-boundary block. It blocks
`human_attestation`, `authority_transition`, and `execution`; it does not block
`review_entry`, because entering human review is the required path.

## Review Task Projection

The first FinHarness shape should be a read-only lifecycle projection, not a
new mutable task board:

- `ReviewTask` is derived from proposal state, queue checks, timeline events,
  attestations, and archive state.
- `EvidenceRequest` is derived from queue findings such as `data_gap`,
  `stale_context`, `missing_source_refs`, `counter_evidence_needed`, and
  `policy_mismatch`.
- Task states are review-facing summaries such as `ready_for_review`,
  `needs_evidence`, `blocked`, `completed`, and `archived`.
- The projection can be shown in Cockpit and used by future Agent context packs,
  but it cannot approve, attest, execute, or mutate proposal state.

## Authorship Rule

Review event authors should be derived from authenticated/local runtime context where possible, not accepted as arbitrary caller-supplied truth.

This matters because review events, comments, and attestations are governance facts. A model summary can suggest text, but it cannot become the author of a human decision.

## Later Shape

When the review system grows, consider explicit objects:

- `ReviewTask`
- `EvidenceRequest`
- `GuardrailFinding`
- `ReviewComment`
- `ReviewBlock`
- `ReviewHandoff`

Do not add these just to have more objects. Add them when proposal review needs durable state that cannot be represented cleanly by current proposal/review event records.
