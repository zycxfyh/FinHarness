# ADR: Identity namespaces and the domain version graph

Date: 2026-07-16
Status: accepted
Issue: #403
Baseline: `main@cf7b7ed7c380daf6c2e7333a83d2dcab7c14ebba`

## Context

FinHarness currently carries several unrelated identifiers as strings:
authenticated principals, Agent runtime invocations, HTTP request/idempotency
keys, external sources, stable domain objects, immutable domain versions, and
Git commits. A display label, local alias, path, request ID, content digest, or
commit SHA can therefore look interchangeable with an authoritative identity
even though each proves something different.

The plane model also permits Truth and Knowledge to reference the same external
`SourceArtifact`. Without one source identity authority, each root could turn a
different display ID or local alias into the identity of that same source.

Finally, the accepted Decision ontology described both
`DecisionCaseVersion -> ScenarioVersion` and the reverse. The canonical
direction from #392 is one-way: a Case freezes the pre-comparison basis, a
Scenario evaluates one exact Case, and a DecisionRecord may cite a Scenario.

## Reference-First decision

Classification: B -- Adapt.

- Adopt [W3C PROV-DM](https://www.w3.org/TR/prov-dm/) qualified-name mechanics:
  an external identifier is interpreted as namespace plus local name, while
  provenance records revision, derivation, and invalidation without erasing
  historical entities.
- Adopt [RFC 9562](https://www.rfc-editor.org/rfc/rfc9562) UUIDv7 for newly
  minted immutable domain version identity, reusing the repository adapter
  already selected by the Decision ontology ADR.
- Reuse Git object/ref identity exactly as owned by #386 and Git documentation.
  A [Git object name](https://git-scm.com/docs/gitdatamodel) identifies a
  repository object; the
  [hash transition](https://git-scm.com/docs/hash-function-transition) is an
  additional reason not to treat a raw SHA as a domain identifier.
- Adapt these mechanics into the existing architecture matrix and checker.
- Own the FinHarness meanings of CapitalState, EvidenceSet, Policy, Proposal,
  DecisionCase, Scenario, ReviewState, DecisionRecord, and their freshness
  rules.

This ADR adds no identity service, source registry, UUID implementation,
database, resolver, or SHA classifier.

## Decision

### Namespace separation

| Namespace | Authority | It must not imply |
| --- | --- | --- |
| `principal` | Authenticated principal context owned by Control | request ownership, Agent identity, or display-name equality |
| `agent-runtime` | One bounded runtime invocation | principal authority or a human DecisionRecord |
| `request` | Correlation and idempotency only | principal, external source, or domain identity |
| `external-source` | Qualified external source key | path, filename, display label, or local alias equality |
| `domain-logical` | Assigned by the owning domain at its logical-identity boundary | an immutable version or repository revision |
| `domain-version` | Issued by the owning domain at its legal version-creation boundary; encoded as an RFC 9562 UUIDv7 | content equality, currentness, or Git identity |
| `git-commit` | Repository object and workflow identity owned by #386 | capital, evidence, policy, proposal, case, or decision identity |

`display_id`, `local_alias`, and path are provenance or presentation tokens,
not identity authorities. `content_digest` is integrity/deduplication evidence,
not version identity. Reverting to identical content may repeat a digest but
must mint a distinct later domain version.

All seven declared namespaces are mutually non-substitutable. They may be
related by an explicit reference or mapping, but no namespace identity may
stand in for another. The UUIDv7 format is only the representation and
generation mechanism for a domain version identifier; authority comes from the
owning domain's legal version-creation boundary, never from the UUID itself or
from its caller.

### One external source identity authority

Truth and Knowledge use the same qualified source key:

```text
(source_namespace, source_native_id)
```

`source_namespace` identifies the external authority or registered source;
`source_native_id` is the stable local name assigned by that authority. Both
planes may reference the resulting `SourceArtifact`; neither owns a separate
source registry or may replace the key with `display_id`, `request_id`,
`local_alias`, or path.

This freezes the identity shape, not the runtime registration/migration
mechanism. Stable imported-source registration and legacy path migration remain
owned by #394.

### Domain version direction

`depends_on` means that the downstream record binds the immutable upstream
identity. It does not mean mutation, ownership transfer, or currentness.

```text
CapitalStateVersion --+
EvidenceSetVersion ---+
PolicyVersion --------+--> DecisionCaseVersion --> ScenarioVersion
ProposalVersion ------+             |            --> ReviewStateVersion
                                    +------------> DecisionRecord
                                                   may cite ScenarioVersion
```

The canonical node contract is:

| Node | Owner | Immutable upstream identity inputs |
| --- | --- | --- |
| `CapitalStateVersion` | Truth | none in this graph |
| `EvidenceSetVersion` | Knowledge | none in this graph |
| `PolicyVersion` | Control | none in this graph |
| `ProposalVersion` | Judgment | none in this graph |
| `DecisionCaseVersion` | Judgment | CapitalStateVersion, EvidenceSetVersion, PolicyVersion, ProposalVersion |
| `ScenarioVersion` | Judgment | exactly one DecisionCaseVersion |
| `ReviewStateVersion` | Judgment | exactly one DecisionCaseVersion |
| `DecisionRecord` | Judgment | exactly one DecisionCaseVersion; may cite ScenarioVersion |

Scenario logical or version identity never participates in Case logical or
version identity. A Case can be resolved before any Scenario exists. Adding,
recalculating, or removing a Scenario leaves the Case immutable. When a Case
becomes non-current, its Scenario versions become non-current without history
being rewritten.

### Currentness, invalidation, and history

Identity and currentness are separate. Every immutable version remains
addressable after it becomes non-current. `Trigger owner` means authority over
the triggering fact. Currentness evaluation remains with each affected node's
owning plane; a Truth-owned admission trigger does not grant Truth authority
over Judgment objects. Each trigger has one exact owner and one exact effect
set:

| Trigger | Owner | Re-evaluated/currentness effects |
| --- | --- | --- |
| Capital-state admission | Truth | CapitalStateVersion; downstream Case and Scenario |
| Evidence admission or withdrawal | Knowledge | EvidenceSetVersion; downstream Case and Scenario |
| Policy activation | Control | PolicyVersion; downstream Case and Scenario |
| Proposal revision | Judgment | ProposalVersion; downstream Case and Scenario |
| Case-basis change | Judgment | DecisionCaseVersion and its Scenario versions |
| Scenario recalculation | Judgment | ScenarioVersion only |
| Review event | Judgment | ReviewStateVersion only |
| Decision recorded | Judgment | append DecisionRecord; do not mutate Case or Scenario |

`DecisionValidity` remains a Judgment-owned recomputable projection. Per #402,
execution state reaches it only after Action/Learning output crosses Truth
readmission; this graph creates no reverse Judgment dependency.

## Executable contract

The existing `config/architecture-layers.yml` owns the structured namespace,
substitution, node, edge, and trigger contract. The existing architecture
checker rejects:

- split Truth/Knowledge source authority or a changed qualified source key;
- substitution between any two declared namespaces, plus
  request/display/alias/path/digest/Git substitution across protected
  namespaces;
- drift in the exact authority semantics for any namespace;
- missing, duplicate, unknown, or multiply owned graph nodes and triggers;
- drift in any node's exact owner, namespace, history, dependencies, or
  citations;
- drift in any trigger's fact owner or exact currentness effect set;
- backward edges and cycles;
- mutable version history or a mutable DecisionRecord.

These are structural invariants. The checker does not parse Markdown or claim
to prove the semantics of arbitrary strings at runtime.

## Relationship to existing contracts

- This ADR preserves #402 plane dependency and object ownership.
- It supersedes the Case/Scenario direction and corresponding trigger row in
  `2026-07-12-decision-ontology-and-version-triggers.md`.
- Current `finharness.decision_ontology.DecisionCaseBasis` still contains a
  pre-correction Scenario reference. #392 remains the implementation owner for
  removing that field, binding ScenarioVersion to CaseVersion, and aligning its
  downstream Issues. #403 does not silently implement or close #392.
- #394 remains the owner of stable imported-source registration, path-derived
  identity migration, and collision handling.
- #386 remains the sole owner of PR head, merge-ref, and final-main Git identity.

## Rejected alternatives

- A universal identity service would add runtime and persistence scope without
  a consumer justified by this ADR.
- Separate Truth and Knowledge source registries would create conflicting
  authority for one external SourceArtifact.
- Bare string prefixes cannot prove namespace authority or graph direction.
- Content-addressed domain versions would collapse distinct historical events
  that happen to restore identical content.
- Git SHA reuse would couple capital-domain identity to repository storage.
- A prose parser would create false semantic certainty; stable structured
  fields and destructive fixtures are sufficient here.

## Verification

```text
uv run python -m unittest tests.test_architecture_boundaries
task architecture:check
task docs:current-check
task check:ci
```

Destructive fixtures cover split source authority, cross-namespace and token
substitution, namespace authority drift, every canonical node field, a
synthetic version cycle, missing or duplicate trigger authority, and an effect
redistribution whose union deceptively remains unchanged.
