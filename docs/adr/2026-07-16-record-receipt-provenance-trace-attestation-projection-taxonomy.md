# Record, receipt, provenance, trace, attestation, and projection taxonomy

Status: Accepted

Date: 2026-07-16

Issue: #404

Baseline: `main@dc41df4f573ad02611330ea27e04f8f3584bbecb`

## Context

FinHarness historically uses *receipt* for several unrelated things: durable
domain writes, operation retry state, artifact lineage, Agent activity, CI
identity evidence, and query indexes. A shared suffix, JSON envelope, directory,
or SQLite row does not give those records the same authority, mutability,
retention, or reconstruction semantics.

The current repository already exposes the distinction:

- `ReceiptIndex` says the indexed file remains truth and the row is lookup only;
- `AgentRunReceipt` says it records activity rather than business state;
- `Attestation` is historical review evidence but legacy consumers still use it
  as current decision truth;
- keyed-mutation identity receipts own request/outcome replay, not domain effect
  authority;
- `ArtifactDescriptor` and import manifests bind immutable bytes and derivation;
- commit-identity manifests make repository/build claims, not financial claims.

The correction must classify those roles without building a universal record
platform or rewriting durable history.

## Reference-First decision

Classification: **B — Adapt**.

We adopt mechanics from mature specifications:

- [CloudEvents 1.0.2](https://github.com/cloudevents/spec/blob/v1.0.2/cloudevents/spec.md)
  for an event-shaped record's identity/source/type/time envelope;
- [W3C PROV-DM](https://www.w3.org/TR/prov-dm/) for Entity, Activity,
  Agent, generation, usage, derivation, attribution, and association;
- [OpenTelemetry Trace API](https://opentelemetry.io/docs/specs/otel/trace/api/)
  for traces, spans, links, events, and terminal status;
- [in-toto Attestation Framework v1.2](https://github.com/in-toto/attestation/blob/main/spec/README.md)
  for subject/predicate/envelope separation and
  [SLSA v1.2 provenance](https://slsa.dev/spec/v1.2/provenance) for build claims;
- [PostgreSQL materialized-view semantics](https://www.postgresql.org/docs/current/rules-materializedviews.html)
  for directly non-authoritative, refreshable derived state.

These references own mechanics. FinHarness owns financial truth admission,
authority, decision validity, currentness, retention policy, and the meaning of
each domain record.

## Decision

### Six explicit categories

| Category | One purpose | Truth owner | Authority boundary |
| --- | --- | --- | --- |
| `DomainRecord` | Authoritative domain fact, transition, or decision history | Owning domain plane | Only the owning domain write/admission policy may confer domain authority or Judgment validity |
| `OperationReceipt` | Integrity-bound operation attempt, outcome, retry, and recovery evidence | Bounded operation producer | Receipt presence never grants domain authority, financial evidence status, or decision validity |
| `ArtifactProvenance` | Artifact origin, derivation, attribution, and integrity binding | Artifact producer or qualified external source | Provenance supports admission assessment but does not itself admit capital facts or evidence |
| `AgentRunTrace` | Ordered durable execution history for one bounded Agent invocation | Agent runtime | Trace content is not business state, authority, or admitted financial evidence without explicit domain policy |
| `BuildAttestation` | Authenticated build/verification claim bound to subjects | Authenticated build or verification system | Build truth is repository/supply-chain scoped and is not financial evidence without explicit domain policy |
| `ProjectionIndex` | Disposable discovery/query acceleration | None; the declared upstream remains truth | Index presence, freshness, or successful rebuild never proves a domain fact |

Classification is explicit. Class names, suffixes, paths, tables, JSON shapes,
and common fields are not classifiers. There is no universal base class.

### Mutability, retention, and reconstruction

| Category | Mutability | Retention | Reconstruction |
| --- | --- | --- | --- |
| `DomainRecord` | Immutable version or append-only domain history | Domain/legal lifecycle, independent of indexes | Only authoritative history or verified source replay |
| `OperationReceipt` | Append-only or integrity-linked pending-to-terminal transition | Retry/recovery/audit horizon; extend while referenced | Typed reconciliation may record a proven outcome but cannot fabricate a domain effect |
| `ArtifactProvenance` | Immutable statements with append-only correction/invalidation | At least subject artifact and evidence lifecycle | Only from verifiable entities, activities, agents, and bytes |
| `AgentRunTrace` | Append-only canonical trace events with one terminal run outcome | Agent recovery and audit lifecycle with policy-governed redaction | Canonical persisted trace records and referenced immutable artifacts; never sampled telemetry |
| `BuildAttestation` | Immutable authenticated statement; supersession creates another | Subject artifact, release, and verification lifecycle | Rerun or authenticated reissue, never PR prose reconstruction |
| `ProjectionIndex` | Replaceable and non-authoritative | Disposable under lifecycle policy | Delete and deterministically rebuild from declared sources at a bound generation/high-water mark |

### Reference direction

References preserve lineage; they do not transfer authority.

- A `DomainRecord` may cite domain records, artifact provenance, and operation
  receipts. The receipt remains audit evidence rather than the source of the
  domain fact.
- An `OperationReceipt` may cite the affected domain identity, prior receipts,
  provenance, or a runtime trace. It may not turn any of them into an effect.
- `ArtifactProvenance` links domain subjects, operations, and other provenance
  statements through PROV-aligned relations.
- `AgentRunTrace` may link context/domain identities, artifacts, receipts, and
  related traces without replacing them.
- `BuildAttestation` binds authenticated predicates to artifact subjects and
  related build attestations only.
- A `ProjectionIndex` may point to any upstream category, but no authoritative
  category may depend on an index as its truth input.

### Existing overloaded surfaces and migration owners

Each overloaded surface is split into specific components. Each component has
one target category, an exact owner Issue list, a current conformance level,
and a disposition. Current role, current conformance, and target category are
separate claims. A migration target does not claim that an existing surface
already satisfies the target category.

| Surface | Component | Role | Conformance | Target | Issue owner(s) | Prereqs |
| --- | --- | --- | --- | --- | --- | --- |
| StateCore receipt-backed domain writes | `canonical_domain_state` | receipt-backed canonical domain payload or state history | `partial` | `DomainRecord` | #258, #267–#271 | — |
| | `mutation_operation_evidence` | mutation attempt, terminal outcome, retry, and reconciliation evidence | `partial` | `OperationReceipt` | #383 | — |
| | `receipt_discovery_index` | lookup rows over canonical receipt or artifact bytes | `partial` | `ProjectionIndex` | #395 | — |
| `ReceiptIndex` | `generic_receipt_index_rows` | replaceable discovery projection over canonical receipt or artifact inventory | `partial` | `ProjectionIndex` | #395 | — |
| Agent receipt search generations | `search_generation_index` | generated search projection over retained Agent records | `partial` | `ProjectionIndex` | #367 | — |
| `AgentRunReceipt` and trace sink | `canonical_agent_run_trace` | compatibility receipt and trace paths for one Agent work request | `partial` | `AgentRunTrace` | #291 | — |
| Legacy `Attestation` | `historical_review_evidence` | retained historical human review and attestation evidence | `partial` | `DomainRecord` | #273 | — |
| | `current_decision_truth` | legacy consumers treating attestation as current decision or authority truth | `not_yet_conforming` | `DomainRecord` | #271–#273 | — |
| Artifact descriptors and import provenance | `immutable_artifact_descriptor` | immutable artifact identity, source bytes, derivation, and integrity binding | `partial` | `ArtifactProvenance` | #368, #371, #373, #376, #394 | — |
| Keyed-mutation identity receipt | `keyed_mutation_state_machine` | request ownership, pending claim, terminal outcome, replay, and typed reconciliation evidence | `partial` | `OperationReceipt` | #383, #385, #387–#389 | — |
| Commit-identity manifests and CI artifacts | `commit_identity_verification_manifest` | repository verification JSON artifact binding claim, repository, commit SHA, ref type, command, and result | `not_yet_conforming` | `BuildAttestation` | #379 | #386 |
| Market-data/import receipts | `admitted_market_or_capital_state` | domain state admitted from validated market or import data | `partial` | `DomainRecord` | #258 | — |
| | `import_operation_outcome` | import attempt, validation result, failure, retry, and recovery evidence | `partial` | `OperationReceipt` | #373, #376 | — |
| | `imported_source_provenance` | imported source identity, bytes, manifest, lineage, and derivation | `partial` | `ArtifactProvenance` | #373, #376, #394 | — |

The table assigns migration ownership; #404 does not rename schemas, move
files, create compatibility adapters, or claim those migrations complete.
Portfolio and CapitalState snapshot retention and compaction remain owned by
#349. Other record categories retain their existing lifecycle owners.
#404 defines category semantics but does not create a universal retention owner,
retention scheduler, or compaction engine.

## Executable contract

`config/architecture-layers.yml` is the structured owner. The existing
architecture checker freezes:

- the six-category vocabulary and every category's purpose, truth owner,
  authoritative source, mutability, retention, reconstruction, references,
  authority effect, validity effect, and financial-evidence admission rule;
- explicit-only classification and the prohibition on universal bases or
  name/path/storage inference;
- the nine current overloaded-surface mappings, their dispositions, and their
  existing Issue owners.

Destructive fixtures mutate every field in every category and specifically
reject OperationReceipt authority, automatic trace/build evidence admission,
non-disposable or non-rebuildable projections, missing migration owners, and a
universal/inferred classifier.

The checker validates stable structured fields. It does not inspect arbitrary
runtime objects, parse Markdown, or create a new registry/service.

## Consequences

- A suffix such as `Receipt` remains readable historical naming, not taxonomy.
- New work must state its category explicitly at its existing domain boundary.
- Operation success, trace completeness, build verification, and index
  freshness cannot silently promote financial truth.
- Migrations remain in their existing Issues and can proceed incrementally with
  compatibility and rollback evidence.

### Commit identity manifest is not yet a conforming BuildAttestation

The current `finharness.commit_identity_manifest.v1` artifact is repository
verification evidence and a completed prerequisite from #386. It is not yet a
fully conforming BuildAttestation because #404 does not add an in-toto
Statement, predicate type, authenticated envelope, or attestation lifecycle.
The manifest is generated by GitHub Actions, uploaded as a workflow artifact
with 20-day retention, and binds claim/repository/SHA/ref/command/result. Its
`current_conformance` is `not_yet_conforming`. #386 completed the commit
identity proof prerequisite but did not implement the full in-toto Statement,
predicate type, authenticated envelope, or long-term attestation lifecycle.
Full BuildAttestation conformance is owned by #379.

### Agent trace is canonical, not sampled telemetry

The canonical AgentRunTrace is durable and unsampled. OpenTelemetry is an
observability mapping and export mechanism only. A sampled or non-recording
OTel export cannot satisfy canonical trace completeness or restart hydration.
The AgentRunTrace category requires a durable unsampled runtime trace and event
boundary as its authoritative source. Reconstruction must use canonical
persisted trace records, never sampled telemetry. The taxonomy also defines an
`agent_trace_observability_export` contract that explicitly blocks OTel export
from claiming authority, canonical trace completeness, restart hydration,
domain authority, decision validity, or financial evidence admission.

### Retention scope

#349 owns portfolio and CapitalState snapshot retention and compaction only.
It does not own AgentRunTrace retention, BuildAttestation retention, all
OperationReceipt retention, all ArtifactProvenance retention, or GitHub
Actions artifact retention. #404 defines category semantics but does not
create a universal retention engine or scheduler.

## Rejected alternatives

- Universal `Record`/`Receipt` inheritance erases distinct authority and replay
  rules.
- Renaming every Receipt now turns an ADR into a high-risk history migration.
- A new event store, provenance database, trace backend, projection registry,
  or retention engine duplicates existing owners and mature mechanics.
- Category inference from storage or naming creates false semantic proof.
- Signing every local record conflates build trust, domain admission, and
  operator authority.

## Verification

```text
uv run python -m unittest tests.test_architecture_boundaries
task architecture:check
task docs:current-check
task check:ci
```
