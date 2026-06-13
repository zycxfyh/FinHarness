# ADR: Target-State-B Is the Governing Roadmap

Date: 2026-06-13
Status: accepted
Supersedes (as roadmap): docs/architecture/post-mvp-maturity-roadmap.md (2026-06-04)
Deciders: FinHarness project operator and Claude

## Context

The repo carries two roadmaps that point in different directions:

```text
2026-06-04  post-mvp-maturity-roadmap.md
  RC0.3 priorities: recurring security-review graph, monthly governance
  dashboard, branch protection, release-note/checksum policy, formal fuzzing.
  Optimizes: "the system exists and is well-governed."

2026-06-12  docs/think/2026-06-12-target-state-b-and-loop-topology.md
  Eight days later, audits the project and names the above as a category error:
  "19 graphs, 70 receipts ... governance compounds; judgment does not."
  Section 8 rules out new governance graphs ("governance is the most mature part
  already"). Defines B-root and predicates B1-B5; B4 (compounding judgment) is
  the discriminating predicate and "the project's reason to exist."
```

The later document is the project's most recent self-understanding and directly
contradicts the earlier roadmap's emphasis. Leaving both active keeps pulling
work back toward adding governance — the exact failure mode B-doc diagnosed.

## Decision

The 2026-06-12 target-state-B document is the **governing roadmap**. The
2026-06-04 maturity roadmap is demoted to a **keep-warm backlog**.

```text
- North star: B4 — every rule/threshold/checklist change carries lineage to a
  lesson, which carries lineage to receipts. B1/B2/B3 are enablers; B5 is a
  permanent boundary.
- Do not add new governance graphs (B-doc section 8). Security/CI/Scorecard
  keep running as recurring backlog; they are not a horizon.
- Of the maturity roadmap's RC0.3 list, only two items survive the B-doc razor:
  validation depth (StrategySpec/MathMethodSpec lineage) and "defer live-write
  expansion." The rest are frozen, not deleted.
```

Forward horizons (sequenced by reachability, not interest):

```text
H0 DONE  B3 live firebreak (okx_live_gate, 2026-06-13).
H1 DONE(observe)  191 real receipts exist in a 60-day window; B4 raw material
         is present, so H1 is verify/exercise, not new build. Remaining: run a
         real paper cycle end-to-end when convenient (not blocking H2).
H2 DONE(v1)  B4 lesson -> rule-change lineage closed loop. THE north star.
         rule_change_ledger.py + tests; verified end-to-end on the 191 receipts.
         Next increment: thresholds read value+provenance from the ledger.
H3       Validation depth (B2 research correctness; feeds B4 comparator quality).
```

## Considered Options

### Option 1: Keep both roadmaps active

```text
- ambiguous direction; every planning pass re-litigates governance vs judgment
- contradicts the project's own latest analysis
```

### Option 2: B-doc governs; maturity roadmap is keep-warm backlog (chosen)

```text
- one direction, anchored on B4
- governance keeps running but stops expanding
- preserves the two maturity items that survive the B-doc razor
```

### Option 3: Delete the maturity roadmap

```text
- loses a useful external-bar comparison (SSDF/SLSA/DORA anchors)
- destroys planning history; archiving/demoting is enough
```

## Consequences

```text
+ Work sequences toward B4 instead of toward more governance.
+ The maturity roadmap stays available as a reference bar, clearly demoted.
- Anyone citing RC0.3 priorities must check them against the B-doc razor first;
  the maturity roadmap now opens with a demotion banner pointing here.
```

## Confirmation

Working if: the next built artifacts close loop feedback edges and B4 lineage,
not new governance graphs; rule changes become traceable to lessons to receipts;
no new governance graph is added without an ADR overriding this one.

## Links

```text
docs/think/2026-06-12-target-state-b-and-loop-topology.md  (governing)
docs/architecture/post-mvp-maturity-roadmap.md             (keep-warm backlog)
docs/adr/2026-06-13-pragmatism-first-supersedes-rust-first.md
docs/proposals/2026-06-13-b4-lesson-to-rule-lineage.md     (H2 minimal loop)
```
