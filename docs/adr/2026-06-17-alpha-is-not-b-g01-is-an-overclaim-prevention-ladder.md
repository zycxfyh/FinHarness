# ADR: Alpha/Edge Is Not B; G01 Is an Overclaim-Prevention Ladder, Not an Edge-Discovery Engine

Date: 2026-06-17
Status: accepted
Clarifies: docs/architecture/industry-benchmark/07-final-merged-plan.md (§1, §5)
Anchored on: docs/think/2026-06-12-target-state-b-and-loop-topology.md (governing roadmap)
Deciders: FinHarness project operator and Claude

## Context

The governing roadmap (target-state-B, 2026-06-12) is unambiguous that alpha is
not the goal:

```text
B-doc line 36:  "Alpha is explicitly not part of B."
B-doc line 71:  "Alpha discovery is downstream of B1-B4, never a substitute."
Rationale (B-doc §2): returns are too noisy a comparator on this horizon; a
noisy comparator teaches loops to optimize luck. Process quality is
controllable; P&L is observed, not gated on.
```

The industry-benchmark effort (Codex series 00-06, merged 2026-06-15) compared
FinHarness to top institutions. That frame imported an institutional premise —
*an institution exists to find tradeable edge* — and the merged plan re-attached
**value** to **edge evidence**, contradicting the governing roadmap:

```text
merged-plan §1:   "a product whose value is not yet proven"
merged-plan §62:  "This phase decides whether the project has value."
merged-plan §5:   "the value loop ... the first honest evidence of any edge"
```

Per merged-plan line 44 this value-question phrasing was "folded in from Claude,"
so the drift is shared, not Codex-only. A later conversation amplified it further
by calling the open question "does the research have edge." Left uncorrected, the
project's success metric silently becomes *did we find alpha*, which is exactly
the failure mode B-doc §1 named ("the system exists" / optimize luck).

### Evidence from the first real ladder climb (2026-06-17)

The G01 ladder was exercised for the first time on real cached history
(`data/cache/{spy,nvda}_history.csv`), MA 20/50 crossover, via the existing
`VectorbtBacktestEvidenceProvider` (diagnostic only, not committed):

```text
symbol  in_sample     out_of_sample   walk_forward      trial_discounted
NVDA    inconclusive  inconclusive    supported(1 trade) not_testable (too short)
SPY     inconclusive  supported(1tr)  supported(4 tr)   INCONCLUSIVE
```

The discriminating result: SPY looked "supported" at single rungs, but the top
rung — which penalizes multiple-testing (PSR / Deflated-Sharpe-style) — pulled it
back to **inconclusive**. The ladder did its job: it refused to let a flattering
single backtest become an edge claim. It also exposed two real weaknesses:
history is too short to reach the top rung (NVDA), and the comparator called a
**1-trade** result "supported" (calibration bug: no minimum-trade-count gate).

The value of that climb was **not** finding edge. It was demonstrating the
validator bites. That distinction is the whole point of this ADR.

## Decision

**Alpha/edge is not part of B. The edge *claim* is an object inside C, which the
system reviews. FinHarness is measured by the trustworthiness of its verdicts,
never by whether it ever finds an edge.**

The banned equation (no document, receipt, UI, or agent may collapse it):

```text
"supported" (empirical support, on this data, at this rung)
  != "edge proven"  != "B achieved"  != "safe to trade"  != execution authority
```

Concrete rules:

```text
1. Alpha/edge is never a B predicate. B stays B1-B5 (decision quality), and B5
   keeps alpha permanently downstream.
2. An edge claim is a C-level object: Loop 2 tests hypotheses to terminal status
   (validated / falsified / archived). Rendering "supported" is allowed and
   necessary — a ladder that can never say "supported" is not a discriminating
   instrument.
3. G01's job is overclaim prevention, not edge discovery:
   "G01 is not an edge-discovery engine; it is an edge-CLAIM validation and
    overclaim-prevention ladder."
4. "Project value" means verdict quality (calibration, honesty, false-edge
   rejection), not P&L and not the existence of an edge.
5. The following may NEVER be labeled an edge: in-sample results, short samples,
   low trade counts, PSR-only / multiple-parameter-selected results without a
   multiple-testing penalty, or results without realistic cost/slippage.
6. Product surfaces (future API/UI) must not display "edge proven" / "alpha
   found" / "safe to trade" (reaffirms merged-plan line 106).
```

## Considered Options

### Option 1: Keep merged-plan §1/§5 as written
```text
- success metric silently becomes "find alpha"
- directly contradicts the governing B-doc; re-litigates B every planning pass
```

### Option 2: Purge the word "edge" everywhere
```text
- over-correction; a validator must be able to say "supported"/"weakened"
- destroys the ladder's discriminating value and Loop 2's terminal verdicts
```

### Option 3: Ban the equation, keep the vocabulary, fix the framing (chosen)
```text
- edge claim stays a reviewable C-object; alpha stays out of B
- success = verdict quality; surgical edits to merged-plan §1/§5/§62 only
- adds the defining sentence to G01
```

## Consequences

```text
+ One direction again: decision quality (B), not alpha discovery.
+ The validator keeps its teeth (can say supported/weakened/inconclusive).
+ Surfaces are protected from edge/alpha overclaim language.
- merged-plan §1/§5/§62 and gap-register G01 are edited to match (see Links).
- Anyone reintroducing "value = edge" must override this ADR explicitly.
```

## Confirmation

Working if: no document, receipt, or surface equates "supported" with "edge
proven" or with B; G01 is described as overclaim prevention; planning sequences
toward verdict quality and decision discipline, not toward finding alpha.

## Links

```text
docs/think/2026-06-12-target-state-b-and-loop-topology.md            (governing)
docs/architecture/industry-benchmark/07-final-merged-plan.md         (edited §1/§5/§62)
docs/architecture/industry-benchmark/03-gap-register-codex.md        (G01 row clarified)
docs/architecture/research-rigor-ladder-spec.md                      (G01 spec)
```
