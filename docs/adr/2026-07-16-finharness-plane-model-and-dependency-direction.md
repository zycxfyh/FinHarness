# ADR: Canonical plane model and dependency direction

Date: 2026-07-16
Status: accepted
Issue: #402
Baseline: `main@bce62b4859dc73796bef50d9ccff922cbcbd0baa`

## Context

FinHarness has accumulated several useful but incompatible ways to describe
layers: the historical trading chain, current Capital OS L0-L8 presentation,
four control roles, Python import layers, and backlog `plane:*` labels. Terms
such as Receipt, Readiness, Identity, Version, Agent, and verified have then
crossed ownership boundaries without a stable domain direction.

The current repository already has the right engineering mechanism:
`config/architecture-layers.yml` and its executable import-boundary checker.
This decision extends that one matrix with conceptual ownership and dependency
truth. It does not create another registry, service diagram, or runtime layer.

## Reference-First decision

Classification: B/C.

- Adopt ADR/MADR decision records, layered/hexagonal dependency direction, and
  the repository's existing executable import graph.
- Adapt those invariants into one ranked, acyclic FinHarness plane model.
- Own capital-decision meanings that a generic architecture framework cannot
  decide: CapitalState admission, Evidence admission, DecisionCase meaning,
  authority policy, bounded Agent work, and the human review/learning journey.

External frameworks own architecture mechanics. They do not name FinHarness
domain objects or decide capital semantics.

## Decision

### Canonical plane model

The seven domain/product planes and horizontal Assurance are canonical:

| Plane | Purpose | Canonical inputs | Canonical outputs | Owned object families | Forbidden responsibilities | May depend on |
| --- | --- | --- | --- | --- | --- | --- |
| **Truth** | Admit trustworthy, versioned facts about the person's capital world. | Source observations, immutable source artifacts, valuation/reconciliation evidence. | Admitted CapitalState versions and truth findings. | ImportBatch, ImportManifest, CapitalStateVersion, CapitalTruthAdmission. | Evidence interpretation, decision choice, authority grant, product workflow. | None. |
| **Knowledge** | Admit observations and claims with provenance, uncertainty, and counter-evidence. | Source artifacts, external observations, research outputs. | Admitted EvidenceSet versions, gaps, and conflicts. | Observation, Claim, EvidenceSetVersion, EvidenceAdmission. | Capital totals, decision choice, authority grant, external effects. | None. |
| **Control** | Resolve identity, mandate, authority, capability, and admission limits. | Human constitutional choices, admitted capital truth, authenticated principal context. | Effective mandate/authority views and typed admission decisions. | Principal, CapitalMandateVersion, AgentAuthorityGrant, AdmissionDecision. | Fact creation, evidence interpretation, strategy choice, effect execution. | Truth. |
| **Judgment** | Compare scenarios and risk to produce a version-bound human capital decision. | Admitted CapitalState and EvidenceSet versions, effective control views. | DecisionCase versions, readiness/validity, recorded decisions. | DecisionCaseVersion, ScenarioVersion, DecisionReadiness, DecisionRecord. | Source ingestion, authority expansion, Agent runtime control, effects. | Truth, Knowledge, Control. |
| **Agent** | Perform bounded observation, reasoning, tool use, replanning, and handoff. | Admitted truth/evidence, judgment context, effective control views. | Typed work results, candidates, gaps, escalations, handoffs. | AgentWorkRequest, AgentWorkObservation, AgentWorkResult, HumanHandoff. | Canonical fact mutation, human-decision impersonation, self-granted authority, direct effects. | Truth, Knowledge, Judgment, Control. |
| **Action/Learning** | Execute admitted actions through deterministic engines and review outcomes without automatic policy mutation. | Valid decisions, effective control views, admitted action requests, reconciled outcome facts. | Effect/reconciliation results, OutcomeReview, LessonCandidate. | ActionRequest, EffectResult, OutcomeReview, LessonCandidate. | Decision authorship, authority expansion, automatic policy update, unadmitted fact writeback. | Truth, Knowledge, Judgment, Control, Agent. |
| **Product** | Let a human discover, compare, decide, return, review, and learn without internal proof vocabulary. | Domain read models, review commands, Agent handoffs, outcome views. | Human commands, explanations, review state, navigation. | DecisionWorkspace, ReviewJourney, RecoverySurface, ProductExplanation. | Canonical domain truth, inferred policy, hidden authority, duplicated domain workflows. | Every domain plane. |
| **Assurance** | Supply transactions, recovery, indexes, security, CI, observability, and falsifiable proof. | Domain invariants, failure models, repository/runtime events. | Mechanical guarantees, degraded-state evidence, verification results. | IntegrityReceipt, RecoveryProof, ArchitectureAudit, VerificationManifest. | Product roadmap, capital semantics, decision policy, permanent Program ownership. | Horizontal support; not a domain-DAG node. |

Exact names, ranks, dependencies, and object ownership live in the existing
`config/architecture-layers.yml`. The ADR explains why; the matrix is the
machine-readable contract.

### Dependency direction

`depends_on` means a plane may consume a lower-rank plane's admitted output. It
does not authorize mutation of that lower plane.

```text
Truth ─────┐
Knowledge ─┼─> Judgment ─> Agent ─> Action/Learning ─> Product
Truth ─> Control ────────┘      └─────────────────────> Product

Assurance supports every plane horizontally; it is not a product step.
```

Outputs that conceptually feed an earlier plane cross a new admission boundary:

- an execution observation is a Knowledge candidate, not admitted Evidence;
- a reconciled balance is a Truth input, not a direct CapitalState mutation;
- a LessonCandidate is not a policy or mandate update;
- an Agent result is not a human DecisionRecord.

This readmission rule preserves learning without a reverse dependency.

### Relationship to other maps

- L0-L8 remains a product/implementation presentation, not an ownership model.
- the Python import layers remain current code classification and enforcement;
  they need not map one-to-one to conceptual planes;
- Human Principal, Capital Agent, Harness, and deterministic engines remain
  control roles, not additional planes;
- `plane:*` Issue labels name the primary change owner, not every affected plane;
- #277 phase lists remain implementation order, not a replacement DAG.

## Executable invariants

The existing architecture checker rejects a plane model when:

- a dependency points to an equal/higher rank or to Assurance;
- an owned object appears in more than one plane;
- Assurance joins the domain DAG or fails to support every domain plane;
- a plane omits its purpose, inputs, outputs, owned objects, or forbidden
  responsibilities.

The checker still separately rejects Python import cycles and configured direct
or transitive import-boundary violations. Conceptual validity does not pretend
that every current module already has perfect domain placement.

## Counterexamples

### Reverse dependency

```text
Truth depends_on Product
```

Rejected even if no graph cycle is present. A product projection cannot become
the source of capital truth. User input must enter a Truth adapter and pass
admission before it becomes canonical.

### Synthetic double ownership

```text
Truth owns CapitalStateVersion
Knowledge owns CapitalStateVersion
```

Rejected. Knowledge may supply evidence used by Truth admission, but it cannot
be a second owner of CapitalStateVersion.

### Assurance product capture

```text
Assurance owns the review journey because it verifies the journey
```

Rejected. Proof supports Product; it does not become the product or roadmap.

## Rejected alternatives

- Rename all Python packages to mirror the diagram: current module placement is
  a separate migration question and moving files would create risk without a
  behavioral outcome.
- Copy a vendor architecture vocabulary: generic frameworks do not define
  FinHarness capital semantics.
- Add a second YAML/JSON plane registry: it would introduce reconciliation with
  the existing architecture matrix.
- Infer ownership from Issue labels: backlog classification is not executable
  module or domain-object proof.
- Parse prose to prove semantic alignment: stable structure and destructive
  fixtures provide a narrower, falsifiable contract.

## Consequences

New Issues and ADRs can name one primary owner while acknowledging downstream
effects. #403, #404, and #405 may refine identity, record, and Agent object
semantics, but they must preserve this direction or explicitly supersede this
ADR. Action and learning remain gated; this decision authorizes no live effect.

No service, database, runtime framework, dependency, or module move is created
by this ADR.

## Verification

```text
uv run python -m unittest tests.test_architecture_boundaries
task architecture:check
task docs:current-check
task check:ci
```

The destructive fixtures must reject both `Truth -> Product` and duplicate
`CapitalStateVersion` ownership.
