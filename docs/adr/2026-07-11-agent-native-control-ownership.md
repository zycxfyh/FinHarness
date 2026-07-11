# ADR: Agent-Native Control Ownership

Date: 2026-07-11
Status: accepted
Decision owners: product north star + architecture governance
Related:

- `docs/product-north-star.md`
- `docs/architecture/finharness-evolution-roadmap.md`
- `docs/proposals/2026-07-11-finharness-evolution-execution-plan.md`
- `docs/notes/2026-07-11-external-research-synthesis.md`

## Context

The first 2026-07-11 evolution plan correctly identified current failures in
capital-state truth, decision versioning, Agent loop semantics, execution
atomicity, and test evidence. It then anchored the target architecture too
strongly to those failures:

```text
classical capital operating core
-> Agent judgment/explanation layer
-> human approval for each important step
```

That is an appropriate current safety mode, but not an adequate north star. It
would make deterministic software the permanent owner of workflow intent and
reduce the Agent to drafting artifacts. It would also confuse “the Agent must
not bypass effect enforcement” with “the Agent must never own an execution
objective.”

The target must distinguish four different kinds of control.

## Decision

FinHarness adopts **Agent-Native Personal Capital Operating System** as its
target architecture.

### Human Principal owns constitutional control

The human owns:

- capital goals and value preferences;
- risk constitution and prohibited actions;
- delegation ceiling and mandate scope;
- mandate grant, expansion, suspension, and revocation;
- veto, exceptional-risk, and irreducible-conflict decisions.

Human sovereignty does not imply permanent per-step approval.

### Capital Agent owns teleological control

As autonomy matures, the Agent owns:

- objective decomposition;
- state interpretation and problem discovery;
- evidence collection and counter-evidence;
- Scenario design;
- tool and Skill selection;
- action ordering and replanning;
- monitoring, verification, attribution, and lesson proposals;
- mandate-contained decisions and actions at the authorized autonomy level.

### FinHarness Harness owns admissibility and recovery

The Harness owns:

- typed world state, policy, mandate, and capability resolution;
- tool schemas, budgets, idempotency, stop/retry ceilings, and escalation;
- fact/simulation/model-output distinctions;
- receipts, observability, persistence, restart recovery, and rollback;
- kill switches and revocation enforcement;
- the decision of whether an Agent request is admissible now.

### Deterministic engines own effect correctness

Classical engines own:

- Decimal, currency, accounting, and financial calculations;
- data validation, database transactions, and state-machine legality;
- Scenario math and reproducible measurements;
- execution protocol, broker interaction, and reconciliation;
- atomic and idempotent effects.

They do not own why an objective is pursued or which admissible strategy the
Agent selects.

## Authority rule

```text
outside mandate -> Agent output is a candidate
inside mandate  -> Agent decision may become effective after Harness enforcement
external effect -> deterministic engine commits and verifies the effect
```

Raw model text never mutates StateCore or directly calls a broker. Agent
autonomy is real only when represented by an explicit, scoped, expiring,
revocable, receipt-backed mandate and an executable autonomy gate.

## Autonomy model

```text
AUT0 Context-aware assistant
-> AUT1 Tool-using reviewer
-> AUT2 Observation-driven durable loop
-> AUT3 Delegated Decision Review
-> AUT4 Autonomous paper capital manager
-> AUT5 Mandate-bound real-world operator
-> AUT6 Continuous personal capital agent
```

Human involvement evolves with evidence:

```text
Human-in-the-loop
-> Human-on-the-loop
-> Human-over-the-loop
```

The 15-contract Agent Work Loop gate proves only the AUT2 Harness foundation.
It is not the endpoint of Agent product capability.

## World-fidelity coupling

Autonomy cannot exceed the financial world model it consumes:

```text
W0 trustworthy capital facts
-> W1 versioned decisions and mandate
-> W2 deterministic Scenario
-> W3 outcome and reconciliation
-> W4 learning with proven policy consumption
```

AUT3 requires W1/W2. AUT4 requires W3. AUT5 requires W4 plus a separately
authorized security, legal, credential, incident, and real-execution program.

## Consequences

Positive:

- current safety work becomes an autonomy enabler rather than a permanent
  limitation;
- Agent, Harness, human, and deterministic responsibilities no longer overlap;
- execution strategy can become Agent-owned without allowing direct adapter
  bypass;
- the roadmap can advance world fidelity and Agent autonomy in parallel;
- Human-in-the-loop can deliberately graduate instead of becoming accidental
  product dogma.

Costs and risks:

- mandate and autonomy-level semantics must become executable, not descriptive;
- recovery, monitoring, escalation, and revocation become first-class product
  requirements;
- autonomy evaluation must measure boundary containment and objective outcomes,
  not only model quality;
- AUT5/AUT6 raise security, legal, credential, and incident-response costs and
  remain unauthorized in the current implementation program.

## Rejected alternatives

### Classical product with permanent Agent assistant

Rejected because it anchors the target to current model limitations and keeps
workflow intent outside the Agent.

### Unbounded model control

Rejected because prompt instructions cannot provide authority, transaction
integrity, rollback, or financial correctness.

### Human approval for every action forever

Rejected as a universal target. It remains the default for ungranted,
high-impact, or early-stage capabilities, but evidence-backed mandates may move
humans to supervision and exceptions.

## Verification

Architecture and product documents must preserve all four control owners and
the W/A maturity lattice. Tests must reject both regressions:

1. reducing the Agent permanently to candidate generation;
2. allowing Agent decisions or effects to bypass Harness enforcement.

