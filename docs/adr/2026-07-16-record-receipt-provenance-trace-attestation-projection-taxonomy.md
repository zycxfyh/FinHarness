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
| `AgentRunTrace` | Ordered telemetry for one bounded Agent invocation | Agent runtime | Trace content is not business state, authority, or admitted financial evidence without explicit domain policy |
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
| `AgentRunTrace` | Append-only events with terminal run outcome | Bounded observability lifecycle and governed redaction | Retained telemetry only; never infer it from business state |
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

| Surface | Target role(s) | Existing owner(s) |
| --- | --- | --- |
| StateCore receipt-backed domain writes | `DomainRecord` + `OperationReceipt` + `ProjectionIndex` | #258, #267–#271, #383, #395 |
| `ReceiptIndex` | `ProjectionIndex` | #395 |
| Agent receipt search generations | `ProjectionIndex` | #367 |
| `AgentRunReceipt` and trace sink | `AgentRunTrace` | #291 |
| legacy `Attestation` | historical `DomainRecord`; current truth migrates | #271–#273 |
| artifact descriptors and import provenance | `ArtifactProvenance` | #368, #371, #373, #376, #394 |
| keyed-mutation identity receipt | `OperationReceipt` | #383, #385, #387–#389 |
| commit-identity manifests and CI artifacts | `BuildAttestation` | completed #386; proof consolidation #379 |
| market-data/import receipts | `DomainRecord` + `OperationReceipt` + `ArtifactProvenance` | #258, #373, #376, #394 |

The table assigns migration ownership; #404 does not rename schemas, move
files, create compatibility adapters, or claim those migrations complete.
Retention/compaction remains owned by #349.

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
