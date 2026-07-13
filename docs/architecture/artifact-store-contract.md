# Shared Artifact Store contract

Status: current STORE-00 foundation. This contract does not claim that existing
domain receipts have already migrated.

## Ownership boundary

Domain services own artifact meaning, validation, lifecycle, and authorization.
The shared store owns immutable bytes, content integrity, descriptor durability,
index reconstruction, and recovery evidence. A trace ID is optional metadata for
lookup; it is never an artifact ID or a substitute for durable bytes.

`ArtifactDescriptor` binds:

- stable `artifact_id`;
- domain schema and schema version;
- SHA-256 and byte length;
- media type and owner domain;
- creation time, source references, and typed JSON metadata.

The `ArtifactStore` and `ArtifactRecoveryPort` protocols are the only new shared
ports. Research, Agent, Authority, Decision, and Execution must use these ports
for new durable artifact forms rather than introduce another receipt registry.

## Local layout and recovery

The local adapter stores content-addressed immutable bytes below `objects/`,
descriptors below `descriptors/`, a replaceable `index.json`, and replay evidence
below `recovery/`. Descriptors and bytes are truth; the index is reconstructable.

The audit distinguishes missing bytes, content/hash or length corruption,
unsupported schema versions, invalid descriptors/indexes, stale index entries,
orphan descriptors, and orphan bytes. Index recovery never deletes evidence and
refuses to proceed when descriptors are invalid. Each applied recovery emits a
before/after receipt with repaired IDs and unresolved findings.

## Migration rule

Existing receipt formats remain readable until their owning Issue supplies a
domain-specific migration, replay comparison, and rollback proof. #263 and #307
must reuse this recovery vocabulary; they must not create competing truth stores.

Verification: `uv run python -m unittest tests.test_artifact_store`.
