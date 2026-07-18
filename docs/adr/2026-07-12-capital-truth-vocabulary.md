# Capital Truth Vocabulary and Admission Contract

Status: accepted

Date: 2026-07-12

Issue: #252

## Decision

CapitalState, Scenario, Decision, Daily Brief, and Agent consumers use the
executable contract in `finharness.capital_truth`. They must not infer stronger
claims from receipt presence, a database row, or a recent-looking timestamp.

The four times have distinct meanings:

- `effective_at`: when the represented financial fact applies.
- `observed_at`: when a source exposed the fact to FinHarness.
- `valued_at`: the market/FX valuation instant; absent means valuation is incomplete.
- `ingested_at`: when FinHarness durably accepted the observation.

`current` means `observed_at` satisfies the named use-case freshness policy.
Evidence integrity and capital-truth admission are independent dimensions:

- `evidence_integrity` is `intact`, `missing`, `corrupt`, or `unavailable`.
  It describes whether the bounded evidence bytes and bindings can be trusted
  as evidence; it does not admit a capital world.
- `capital_truth_admission` is `admitted`, `partial`, `blocked`, or
  `unavailable`. It incorporates provenance, identity, freshness, valuation,
  FX, reconciliation, and use-case requirements.

`reconciled` additionally requires intact evidence, verified provenance, a
queryable DB mirror matching the receipt root, and deduplicated cross-account
identities. An intact receipt can therefore coexist with partial or blocked
capital admission without making a contradictory claim.

Capital-truth admission is one of:

- `admitted`: all required truth checks pass; the consumer may admit the input.
- `partial`: no hard contradiction exists, but optional valuation is incomplete;
  consumers must not silently treat it as admitted.
- `blocked`: a correctness, identity, provenance, recovery, or freshness
  invariant failed.
- `unavailable`: the bounded owner could not inspect the required evidence.

Mixed currency without current, time-bound FX is always `blocked`. It is never
reduced to a warning. Receipt integrity proves that bytes were retained; it
does not prove financial correctness.

## Source of truth and recovery

Receipts are the immutable evidence root. The database is a queryable mirror.
A missing receipt/index, missing mirror, or mismatch blocks admission. Recovery
replays a valid receipt into the mirror; it never edits the receipt to agree
with the database.

## Counterexamples

The CI-discovered contract suite covers stale snapshots, mixed unconverted
currency, missing receipt/index, stale price, forged provenance, symbol
collision, and duplicate cross-account assets. Every fixture asserts an exact
readiness/admission result. A deliberately incomplete optional valuation is
`partial` and not admitted; all correctness defects are `blocked`.

## Compatibility migration

The ambiguous capital `verified` output is removed rather than retained as a
deprecated alias. Keeping it would preserve the unsafe interpretation this
contract closes.

| Previous field | Replacement |
| --- | --- |
| `CapitalTruthResult.readiness=usable` | `capital_truth_admission=admitted` |
| `CapitalTruthResult.readiness=partial/blocked` | the same value in `capital_truth_admission` |
| `CapitalTruthResult.admitted` | compare `capital_truth_admission` with `admitted` |
| `CapitalTruthResult.verified` | inspect both `evidence_integrity` and `capital_truth_admission`; there is no single equivalent boolean |
| `/ready/truth.verified` | use `evidence_integrity`; separately require `capital_truth_admission=admitted` and `status=usable` for admission |

`/ready/truth.status` remains the truth-readiness probe result. `/health`
continues to own liveness, and `/ready` continues to own operational dependency
readiness. External consumers must reject an unknown response shape and migrate
field reads atomically; no compatibility alias is authoritative.

## Consequences

Downstream migrations reference this vocabulary rather than creating local
definitions. This ADR freezes admission semantics, not accounting, pricing,
FX, reconciliation, or persistence mechanics; mature domain engines continue
to own those calculations.
