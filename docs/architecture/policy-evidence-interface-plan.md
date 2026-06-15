# Policy & Evidence Interfaces — Plan (Phase 5, for Codex)

**Design-only / inventory phase. Do NOT add any production dependency and do NOT
adopt a policy engine or provenance tool in this phase.** Adopting OPA / Cedar /
Casbin / OpenLineage / MLflow / DVC / Sigstore is a new-dependency decision that
needs explicit user approval first (same rule as Pandera). This phase produces
**contracts and recommendations**, not engine integration.

**Prerequisite / sequencing:** start only after Phase 3's `task check` is green.
This is the last phase and the least urgent — receipt and rule semantics must be
stable before any external engine/store is considered.

## Part A — PolicyInterface (express, then evaluate)

### A1. Inventory the implicit rules (the deliverable)

Today the project's discipline rules live as code scattered across modules. Write
**one explicit policy-contract document** (`docs/architecture/policy-contract.md`)
that inventories them, each with: rule id, source `file:line`, what it checks,
its fail-closed default, and who can change it (human attester). Cover at least:

- `trading_guard` thresholds (hard-stop drawdown, consecutive losses, cooldown,
  written-thesis requirement).
- `risk_gate` checks (mandate, instrument allowlist, max notional, concentration
  cap, drawdown state, behavior reset, order-language, human review).
- `okx_policy` read/write allowlist and the live-write double opt-in.
- `execution` live-block default.
- `rule_change_ledger` lineage requirement (lesson → receipts).

This inventory is valuable on its own: it makes the safety surface auditable in
one place and is the prerequisite for any future engine.

### A2. Evaluate an engine (recommendation only)

After the inventory, write a short recommendation: would OPA / Cedar / Casbin add
value, or does the explicit contract + existing Python checks already suffice?
Bias: **do not adopt an engine just to have one.** A policy engine can *express*
rules but cannot supply this project's domain discipline. Recommend adoption only
if it removes real duplication or adds real auditability, and flag it as a
user-approved new dependency.

### A3. Red lines

- The policy contract documents rules; it does not become an execution authority.
- `trading_guard`, `risk_gate`, human attestation, and the live block stay the
  enforcers regardless of any future engine.

## Part B — EvidenceInterface (inventory, then evaluate)

### B1. Inventory current provenance (the deliverable)

Write `docs/architecture/evidence-inventory.md`: what receipts/lineage already
capture (market data receipts, validation receipts, execution receipts, rule-change
receipts, the `quality_backend` disclosure, hashes/refs). Identify gaps: what
provenance is NOT yet captured (e.g. artifact signing, cross-run lineage).

### B2. Evaluate provenance/storage tools (recommendation only)

Assess OpenLineage / MLflow / DVC / Sigstore strictly as **storage/provenance
adapters that never replace FinHarness receipt semantics** (claim / evidence /
non-claim / review). Recommend at most one as an optional future adapter, flagged
as a user-approved new dependency. Default recommendation may well be "not yet —
receipts are the source of truth and are sufficient for current scope."

### B3. Red lines

- Receipts remain the source of truth. Any external store is an additional copy /
  index, never the authority and never a replacement for receipt semantics.
- No new dependency added in this phase.

## Acceptance for Phase 5

- [ ] `docs/architecture/policy-contract.md` written (rule inventory with
      `file:line` + fail-closed defaults).
- [ ] `docs/architecture/evidence-inventory.md` written (current provenance + gaps).
- [ ] Short engine/tool recommendations included, each flagging any adoption as a
      separate user-approved new-dependency decision.
- [ ] No production dependency added; no engine/store wired; `task check` still
      green (docs-only change).
- [ ] Report what was written; surface the adoption decisions back to the user.
