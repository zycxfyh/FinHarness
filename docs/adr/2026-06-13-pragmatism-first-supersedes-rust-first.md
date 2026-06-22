# ADR: Pragmatism-First Supersedes Rust-First

Date: 2026-06-13
Status: accepted
Supersedes: docs/notes/rust-first-local-implementation.md (2026-05-29)
Deciders: FinHarness project operator and Claude

## Context

On 2026-05-29 we adopted a Rust-first rule for new local implementation
(venue adapters, risk gates, receipt writers, workflow executables). The stated
reasons were good ones: typed models, explicit errors, compiled binaries,
"better control around live execution paths," and harder-to-trigger accidental
behavior after a drawdown.

A red-team pass on 2026-06-13 (see
docs/reviews/2026-06-13-redteam-live-path-and-language-doctrine.md) found that
the rule, as applied, had produced the opposite of its goal on the one path
that matters. The live OKX write path was split into a separate Rust crate
(`crates/finharness-cli`) that:

- does not read the Python-persisted behavioral state
  (`data/state/trading-state.json`),
- is never run through the behavioral guard before placing an order,
- never reaches the ten-layer risk gate, and
- enforces no notional/size cap.

Meanwhile the heavily-governed ten-layer pipeline terminates in a
`fake_paper_adapter` that cannot lose money. The result: governance compounded
on the simulated path; the live path stayed thin. The language split was a
direct structural cause — two implementations in two languages meant two
sources of behavioral truth, and the live one used the weaker source.

The original rule also assumed the local layer would keep "sprawling into loose
Python scripts." In practice the Python layer is typed (Pydantic), tested, and
organized into layer modules with receipts and lineage. The premise that Python
here is inherently un-auditable did not hold.

## Decision

The governing principle for new local implementation is now **pragmatism-first**,
not Rust-first.

```text
Choose the language that lets the control plane stay connected, typed, tested,
and auditable with the least duplication — not the language that scores highest
on purity.
```

Concretely:

```text
- Python is the default for FinHarness local control-plane code, because the
  rest of the control plane (LangGraph, risk gate, trading-state store,
  receipts, mature wheels) is already Python. One language, one source of
  truth.
- A second language is justified only by a concrete need (performance,
  isolation, a Rust-only dependency), never by language preference. When it is
  justified, it must still read the same persisted state and pass the same
  gates as the Python path.
- The architectural rules that actually carry the safety value are unchanged:
  adopt-not-invent, thin local code (adapters / guards / receipts / workflows /
  tests), no homemade engines, no agent owns live execution authority.
```

This ADR changes the **language mandate only**. It does not relax any safety
boundary; it removes a rule whose purity cost was buying negative safety.

## Considered Options

### Option 1: Keep Rust-first, finish the migration

Pros:

```text
typed compiled binaries
honors the earlier decision
```

Cons:

```text
keeps two languages and two behavioral-state sources
the live path stays decoupled from Python guard/state/risk-gate until a full
  port lands
refactor driven by language preference, not by a problem
highest effort, lowest near-term safety gain
```

### Option 2: Pragmatism-first, consolidate on Python (chosen)

Pros:

```text
one language, one persisted behavioral-state source
the live OKX path can finally be wired through the guard, the trading-state
  store, a notional cap, and a receipt — the actual red-team fix
the existing typed/tested Python okx_cli.py already mirrors the Rust gate
removes a refactor that exists only for technical tidiness
```

Cons:

```text
loses compiled-binary distribution for the CLI (not a current requirement)
the Rust crate becomes legacy until archived
```

### Option 3: Polyglot with a shared state contract

Pros:

```text
keeps Rust where it adds value, shares one state file/schema
```

Cons:

```text
premature; we have no measured need for Rust here
a shared-state contract is real ongoing complexity for zero current benefit
```

## Consequences

Positive:

```text
The live write path can be hardened in the same language and against the same
  persisted state as every other gate (see the 2026-06-13 proposal).
Doctrine stops optimizing for purity and starts optimizing for a connected,
  auditable control plane.
```

Negative:

```text
crates/finharness-cli is now legacy; its capabilities must be reproduced in
  Python before the Taskfile is re-pointed and the crate is archived.
Several docs asserting Rust-first must be corrected (done with this ADR).
```

Neutral:

```text
"Adopt-not-invent" and "thin local code" remain in force and are untouched.
A future, problem-driven case for Rust (or any second language) is allowed —
  it just needs a real reason and must share state and gates.
```

## Confirmation

This decision is working if:

```text
the live OKX path runs through the Python guard + trading-state store + a
  notional cap + a receipt before any order is placed
there is exactly one persisted behavioral-state source on the live path
no doc still asserts a Rust-first language mandate
a future second language, if any, is justified by a measured need, not taste
```

## Links

```text
docs/reviews/2026-06-13-redteam-live-path-and-language-doctrine.md
docs/proposals/2026-06-13-consolidate-live-path-on-python-and-harden.md
docs/notes/rust-first-local-implementation.md (superseded)
docs/notes/adopt-not-invent-trading-stack.md (still in force, language line corrected)
CONTEXT.md, README.md
```
