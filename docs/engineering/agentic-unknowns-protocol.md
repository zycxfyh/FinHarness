# Agentic Unknowns Protocol

Status: current
Scope: engineering / product-development workflow
Non-runtime: true

This protocol exists to prevent product-shape drift and expensive late pivots
when using coding agents. It is a lightweight way to manage unknowns before and
during implementation. It is not a runtime governance object.

## Why This Exists

FinHarness learned through the #87-#100 mainline that many late corrections were
not implementation bugs. They were map-vs-territory corrections: a prompt,
spec, or PR title pointed in one direction, while the real codebase, product
boundary, financial semantics, or user benefit required a narrower path.

The goal is not to add ceremony. The goal is to make agents useful as unknown
discovery partners before they become implementation accelerators.

## Map Vs Territory

The map is what the agent receives before work starts:

- prompts;
- specs;
- plans;
- docs;
- current context;
- PR titles and issue summaries.

The territory is where the work must actually hold:

- the codebase;
- existing tests and APIs;
- receipt lineage;
- real constraints;
- user needs;
- financial semantics;
- runtime behavior;
- product non-goals.

Agents fill gaps in the map with defaults. In FinHarness, generic finance or
engineering defaults can be wrong when they push the product toward execution,
advice, approval, or permission-first semantics.

## Unknown Taxonomy

Use this vocabulary during planning and review:

| Type | Meaning | FinHarness example |
| --- | --- | --- |
| Known knowns | Already clear from the prompt or codebase. | A new review artifact must preserve `execution_allowed=false`. |
| Known unknowns | We know a decision is still open. | Whether a future review gate must cite a current objective-fit record. |
| Unknown knowns | Project preferences that are obvious when seen but not always written down. | Review evidence should not be mistaken for approval. |
| Unknown unknowns | Missing constraints or traps we have not yet noticed. | A free-text field can smuggle broker/order/advice language past structured validation. |

## Product-Shape Drift Risks

The most dangerous unknowns are often not mechanical coding details. They are
places where an agent may apply ordinary finance or platform defaults that do
not fit FinHarness.

Check these risks before medium, mainline, or large PRs:

- capital governance becoming a permission firewall;
- trade planning becoming an order pipeline;
- review evidence being mistaken for approval;
- objective fit being compressed into a gate condition;
- receipt evidence being mistaken for authorization;
- preflight pass being mistaken for approval;
- financial terminology being used in a way that implies advice, suitability,
  broker submission, or execution authorization.

## PR Size Tiers

Use the lightest tier that fits the risk surface. The tier is not determined
only by diff size. A small text change can be high-risk if it changes financial
meaning.

### Small PR

Examples: typo fixes, narrow docs updates, test-only additions, small CI hygiene.

Expected shape:

- one-sentence product intent;
- relevant checks;
- no full unknown ledger unless the change touches product semantics.

### Medium PR

Examples: one new artifact, one API surface, one current-doc update, a bounded
workflow change.

Expected shape:

- product intent;
- blindspot / unknown ledger;
- reference pass;
- implementation plan focused on decisions likely to change;
- notes for conservative choices and follow-ups.

### Mainline / Large PR

Examples: capital-action pipeline changes, authority semantics, review gates,
StateCore models, user-visible financial semantics, cross-module governance.

Expected shape:

- everything from medium PRs;
- architecture interview for questions that would change the data model, API,
  receipt lineage, product boundary, or downstream workflow;
- implementation notes for deviations from plan;
- explainer before merge;
- merge quiz for the human reviewer when the behavior is subtle;
- lesson / follow-up ledger after merge if the PR discovered new durable
  process or product constraints.

## Product Intent Template

For small PRs, one sentence can be enough. For medium and mainline PRs, answer
the fields that affect product shape.

```text
Product intent:
- User benefit:
- Current pain / gap:
- Why now:
- What this must enable:
- What this must not imply:
- Downstream consumer:
- Reversibility:
```

## Blindspot Pass Template

Use before implementation when the work touches unfamiliar code, financial
semantics, authority boundaries, or user-facing interpretation.

```text
Before implementing, do a blindspot pass.

Context:
We are adding <feature>. FinHarness is a personal capital agency workbench,
not an auto-trading system, advice engine, or permission firewall.

Inspect the relevant existing modules, docs, and tests. Identify:
1. Known knowns already clear from the prompt.
2. Known unknowns we must decide before implementation.
3. Unknown knowns likely implicit in this codebase or product direction.
4. Unknown unknowns / likely traps.
5. Places where a normal finance or engineering best practice may be wrong
   for FinHarness.
6. Questions where the answer would change the architecture.

Do not implement yet.
```

## Unknown Ledger Template

This can live in PR notes, a temporary implementation note, or the PR body. It
does not need to become a permanent runtime artifact.

```markdown
# Unknown Ledger

## Known Knowns
- ...

## Known Unknowns
- ...

## Unknown Knowns
- ...

## Unknown Unknowns / Suspected Blind Spots
- ...

## Architecture-Changing Questions
1. ...
2. ...

## Conservative Defaults
- ...

## Stop Conditions
- ...
```

## Reference Pass Template

Before inventing a new shape, compare it with nearby FinHarness artifacts.

```text
Do a reference pass before planning.

Find 3-5 existing FinHarness artifacts closest to this feature. For each,
extract:
- model pattern;
- receipt pattern;
- stale evidence checks;
- non-claims;
- API shape;
- tests we should mirror;
- boundaries we should not copy blindly.
```

Common capital-action references include:

- `ActionIntent`;
- `ActionIntentAuthorityBinding`;
- `ActionIntentPreflight`;
- `ActionIntentSimulationReport`;
- `TradePlanCandidate`;
- `TradePlanReviewGate`;
- `CapitalObjectiveFit`;
- receipt reference docs;
- StateCore store patterns;
- `tests/test_action_intents.py`.

## Architecture Interview Template

Use this when the agent is likely to guess a product decision from an
implementation detail.

```text
Interview me one question at a time.

Only ask questions where my answer would change:
- data model;
- receipt lineage;
- API shape;
- gate semantics;
- product boundary;
- downstream workflow;
- non-claims.

Stop after 5 high-leverage questions.
```

## Implementation Plan Shape

Lead with the decisions most likely to change. Mechanical file lists belong
after the product and architecture decisions.

```markdown
# Implementation Plan

## Decisions Likely To Change
1. Object name:
2. Is this evidence / gate / authority / candidate?
3. Required current evidence:
4. Closed enum values:
5. Non-claims:
6. Downstream consumer:
7. What is intentionally not required in v0:

## Data Model

## API

## Receipt

## Tests

## Docs

## Mechanical Edits
```

## Implementation Notes Template

Mainline PRs should keep notes when implementation reveals edge cases or forces
a deviation from plan. These notes can be temporary, but their important
lessons should be copied into the PR body, ADR, or follow-up issue.

```markdown
# Implementation Notes

## Plan Followed
- ...

## Deviations
- ...

## Conservative Choices
- ...

## Open Questions
- ...

## Reviewer Attention
- ...

## Suggested Follow-Ups
- ...
```

## Conservative Defaults

When an unknown appears during implementation and the answer is not
architecture-changing, choose the lower-authority option:

- default-deny over implicit allow;
- evidence over approval;
- candidate over instruction;
- review path over execution path;
- explanatory text over recommendation;
- current receipt/hash checks over stale references;
- closed enum over open-ended status strings when the value drives behavior.

Record the choice when it may matter to a future reviewer.

## Stop Conditions

Stop and ask for direction when an unknown would change:

- whether an object is evidence, a gate, an authority credential, or a
  candidate;
- whether `allowed=true` or `pass` could be read as approval;
- whether a record can move a workflow closer to order, broker, or execution;
- which receipt/hash is the source of truth;
- whether a human-facing field can carry advice, suitability, approval, or
  broker/order language;
- whether a mainline PR is drifting from personal capital agency into an
  execution or permission system.

## Unknowns Review Before Merge

For medium and mainline PRs, review the unknowns explicitly before merge:

- Which unknowns did this PR resolve?
- Which known unknowns remain?
- Did any unknown get silently converted into a product decision?
- Did the implementation reveal a blind spot?
- Did the PR use FinHarness reference patterns instead of generic finance
  defaults?
- Are the remaining follow-ups documented without overstating current
  capability?

## Explainer And Merge Quiz

For subtle mainline PRs, add a short explainer before merge. The goal is to make
sure the human reviewer understands the behavior, not just the diff.

Useful quiz prompts:

1. What does `allowed=true`, `pass`, or `aligned` mean in this object?
2. Which current receipts or hashes does it bind to?
3. What does it explicitly not authorize?
4. Which downstream artifact may consume it?
5. What happens if a required evidence reference is stale?
6. Which fields are closed enums?
7. Which unknowns were intentionally left for a future PR?

## Relationship To FinHarness Product Philosophy

Good capital decisions are not risk-free. They are decisions that know what
they do not know, turn unknowns into reviewable objects, and slow down at
irreversible boundaries.

This protocol applies the same philosophy to engineering work. A high-quality
agentic PR is not one where the agent never encounters unknowns. It is one
where important unknowns are surfaced, handled conservatively, reviewed, and
preserved as evidence for future work.

## Non-Claims

This protocol is not:

- a runtime object;
- a StateCore model;
- a governance artifact;
- a governance runtime object;
- a receipt kind;
- a change to #100 runtime behavior;
- a replacement for ADRs;
- a replacement for the product north star;
- required in full for every small PR;
- a blocker for trivial maintenance PRs.
