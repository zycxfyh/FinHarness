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
`verified` requires receipt integrity **and** verified provenance. `reconciled`
additionally requires the queryable DB mirror to match the receipt root and
cross-account identities to be deduplicated.

Readiness is one of:

- `usable`: all required truth checks pass; the consumer may admit the input.
- `partial`: no hard contradiction exists, but optional valuation is incomplete;
  consumers must not silently treat it as usable.
- `blocked`: a correctness, identity, provenance, recovery, or freshness
  invariant failed.

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

## Consequences

Downstream migrations reference this vocabulary rather than creating local
definitions. This ADR freezes admission semantics, not accounting, pricing,
FX, reconciliation, or persistence mechanics; mature domain engines continue
to own those calculations.
