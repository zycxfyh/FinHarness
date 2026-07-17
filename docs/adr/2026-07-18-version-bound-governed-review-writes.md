# ADR: Make governed review writes version-bound and atomic

Date: 2026-07-18
Status: accepted

## Context

FinHarness governed review writes (Attestation, Scaffold revision, ReviewEvent)
read the current Proposal version in one SQLite transaction, then commit domain
effects in a separate transaction. Between those two transactions, another
writer can advance the Proposal to a new version (v1 → v2). The stale write
then commits against v2 — the user who reviewed v1 unknowingly writes into its
successor.

This is a real TOCTOU (time-of-check-to-time-of-use) gap, not a theoretical
corner case.

## Why Idempotency-Key does not solve stale-state

Idempotency-Key (via the keyed-mutation protocol) prevents duplicate domain
effects for the same logical operation. It does NOT prevent a stale operation
from succeeding once:

```text
User sees Proposal v1 → creates request body with v1 assumption
→ idempotency key is minted
→ another writer revises to v2
→ stale request succeeds against v2 (one domain effect, not duplicate)
```

Idempotency guarantees at-most-once for a given key+body. Stale-state
admission is an independent concern: the body itself must declare which
version it was authored against.

## Current TOCTOU

Every governed write follows this pattern:

```text
1. Open Session(engine)          ← version read
2. Read Proposal row
3. Close Session                 ← gap opens
4. Open new Session(engine)      ← write path
5. Read Proposal row again       ← may now see different version
6. Construct domain objects
7. write_records([...], engine)  ← commits against wrong version
```

The attestation route adds a `require_current_proposal_version()` call
between steps 3 and 4, but that call also opens its own independent Session —
the gap still exists.

## ProposalVersion identity vs content hash

`proposal_version_id` is the receipt_id of the immutable proposal receipt
that anchors a specific revision. It is a stable identity that survives
content hash collisions:

```text
v1: content A → version_id = receipt_xxx
v2: content B → version_id = receipt_yyy
v3: content A → version_id = receipt_zzz  (≠ receipt_xxx)
```

`hash(v1) == hash(v3)` but `version_id(v1) != version_id(v3)`. This is
critical: a revert to prior content is a genuine new revision that must
invalidate stale expectations. Content-hash CAS would incorrectly accept
a v1 expectation against v3.

## Transaction strategy

**BEGIN IMMEDIATE on the same connection**: the version check and the domain
write must share one SQLite write transaction. The approach:

1. Route handler resolves the expected `ProposalVersionExpectation` from the
   request body
2. A new session-aware resolver `require_current_proposal_version_in_session()`
   reads and validates the current Proposal row inside the same Session that
   will later commit the domain effects
3. The domain write function receives this Session (not a bare Engine) and
   uses it for all reads and writes
4. `session.begin()` with `BEGIN IMMEDIATE` to acquire the write lock at the
   start of the check

Alternative: exact CAS (`UPDATE ... WHERE receipt_ref = expected_ref`) —
also valid but requires the CAS to be in the same transaction as the remaining
writes and to verify affected row count == 1.

The `write_records` / `upsert_records` helpers currently own their Session
lifecycle. The version-bound path will bypass them and use the in-transaction
Session directly for `session.add()` / `session.flush()`.

## API request contract

All four governed write request models become:

```python
expected_proposal_version_id: str   # required, non-blank
expected_proposal_receipt_ref: str  # required, non-blank
```

`AttestationCreateRequest` drops the Optional compatibility escape.
`ProposalScaffoldRevisionRequest`, `ReviewEventCreateRequest` gain the fields.
`ScaffoldRevisionCandidateApplyRequest` gains `expected_proposal_version_id`.

Missing or blank → 422. Extra fields → 422 (extra=forbid).

## Typed conflict contract

A stale expectation produces:

```json
HTTP 409
{
  "detail": {
    "code": "proposal_version_conflict",
    "message": "The proposal version changed before this review write was committed.",
    "proposal_id": "<id>",
    "expected": {
      "proposal_version_id": "<expected>",
      "receipt_ref": "<expected>"
    },
    "current": {
      "proposal_version_id": "<current>",
      "receipt_ref": "<current>"
    },
    "execution_allowed": false
  }
}
```

All four routes use the same `proposal_version_conflict` code. Stale conflict
is a terminal rejection, not an ambiguous transport outcome.

## Row / receipt / response / mutation binding

### Row-level

New columns on `Attestation` and `ReviewEvent`:

```text
bound_proposal_version_id: str | None   (nullable for legacy, non-null for new)
bound_proposal_receipt_ref: str | None  (nullable for legacy, non-null for new)
```

### Domain receipt

Attestation receipt gains:

```json
{
  "admitted_proposal_version_id": "<id>",
  "admitted_proposal_receipt_ref": "<ref>"
}
```

ReviewEvent receipt gains the same fields.

Scaffold revision receipt gains:

```json
{
  "admitted_proposal_version_id": "<id>",
  "admitted_proposal_receipt_ref": "<ref>",
  "resulting_proposal_version_id": "<new-id>",
  "resulting_proposal_receipt_ref": "<new-ref>"
}
```

### Response

`AttestationCreateResponse` gains:

```python
admitted_proposal_version: ProposalVersionView
```

`ReviewEventCreateResponse` gains the same.

`ProposalScaffoldRevisionResponse` gains:

```python
admitted_proposal_version: ProposalVersionView
resulting_proposal_version: ProposalVersionView
```

`ProposalVersionView`:

```python
class ProposalVersionView(BaseModel):
    proposal_id: str
    proposal_version_id: str
    receipt_ref: str
```

### Identity mutation binding

The identity receipt's `body_sha256` cryptographically binds the expected pair
through the request body. Reconciliation verifies that the final domain
evidence uses the same admitted version.

## Legacy compatibility

Legacy rows (created before this ADR) have NULL `bound_proposal_version_id`
and `bound_proposal_receipt_ref`. They remain readable. Read models
(AttestationReviewView) already surface `bound_*` fields; existing code treats
NULL as "pre-version, assume current" or "stale: true".

Schema migration adds columns with `nullable=True` and increments
`STATE_CORE_SCHEMA_VERSION`.

## Reconciliation

Each reconciliation resolver must verify the full version binding chain:

- Attestation: row.bound_version_id == receipt.admitted_version_id == response.admitted_version_id
- ReviewEvent: row.bound_version_id == receipt.admitted_version_id == response.admitted_version_id
- Scaffold: admitted pair consistent, resulting pair consistent, supersedes matches previous_receipt_ref

Tamper fail-closed: any mismatch produces `reconciled_rejected`, never
`reconciled_applied`.

## Rollback

Code revert: remove new columns, drop user_version migration. Schema
compatibility: legacy paths continue to work because new columns are
nullable. No data is invented for legacy rows.

## Non-goals

- #389 recovery UX (Pending Operations, Outcome unknown)
- DecisionCase / DecisionRecord / DecisionReadiness
- Content-hash CAS as version identity
- Live execution or broker adapter changes
- PostgreSQL or distributed locking
- Generic workflow engine
