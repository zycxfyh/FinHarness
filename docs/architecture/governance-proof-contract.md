# Governance Proof Contract

FinHarness governance claims are bounded by the strongest evidence actually
executed. A green check proves its registered claim only; it does not prove
overall maturity, debt closure outside the register, or product fitness.

## Evidence levels

From weakest to strongest for a specific claim:

1. `structural`: parses files, schemas, dependency graphs, or configuration.
2. `semantic`: evaluates typed relationships or executable invariants without
   exercising the production interaction.
3. `runtime`: executes the production path and observes effects or denials.
4. `restart`: proves the result survives process/store reconstruction.
5. `clean-environment`: rebuilds the required environment from declared inputs.
6. `product`: validates a real user journey and outcome.

Levels are not interchangeable. Test collection or test count is telemetry,
not an evidence level and never closes debt by itself.

## Verifier registration

Every canonical debt verifier is a `VerifierSpec` in
`scripts/verify_debt_register.py` and must declare:

- the exact claim it supports;
- the owning domain;
- one evidence level;
- the minimum evidence level required to close the debt;
- the production paths under proof;
- a sunset condition for deletion or replacement.

When the executed verifier is weaker than the closure level, the spec must also
name the canonical execution owner, destructive fixture, and the identity claim
defined by #386. This metadata is a dependency declaration, not proof that the
owner ran. The debt remains active until a consumer binds the owner's successful
result to that exact identity; structural success alone cannot resolve it.

The verifier executes its proof. Merely finding a symbol, test filename, or
minimum registration count is insufficient for semantic/runtime claims. The
register may grow without updating a fixed total; IDs and verifier bindings,
not the number of entries, are the stable contract.

`identity_claim` reuses #386's `pr_head`, `merge_ref`, and `main_commit`
vocabulary. This contract must not infer or classify SHAs itself. CI identity is
owned by the commit-identity workflow and its single manifest; proof consumers
must reject a missing, skipped, cancelled, stale, or different-SHA owner result.

## False-green fixture

`tests/test_debt_register.py` contains destructive false-green fixtures. One
adds an unguarded POST route while preserving every token accepted by the former
API verifier. Two more create all source tokens accepted by the execution and
frontend verifiers without executing their denial/no-effect fixtures. Structural
evaluation stays useful, but the closure check rejects both runtime claims.

## Claim boundary

A passing debt verifier means only that the desired state for that registered
debt currently matches repository evidence. It does not mean:

- all material debt has been discovered;
- a test count demonstrates correctness;
- semantic evidence demonstrates restart or clean-environment behavior;
- engineering evidence demonstrates product value.
