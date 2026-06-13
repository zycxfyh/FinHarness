# Think: Target State B and Loop Topology Selection

Date: 2026-06-12
Scope: project direction — what B actually is, and which loops follow from it
Source: audit of the LangGraph layer (2026-06-12) + loop-architecture-selection
discussion (ABC framing; see abc-thinking-system and Ordivon)

## 1. The category error to fix first

The candidate phrasing of the goal was:

```text
"a system that can deeply research instruments, understand indicators,
 and let AI assist with option selection, trading, and review"
```

In ABC terms this is **C-language, not B-language**. "A system that can X" is a
transformation structure. B must be a *state of the world* with comparators, or
the project optimizes "the system exists and is well-governed" instead of "the
state changed".

The audit evidence shows exactly this failure mode in progress: 19 graphs,
70 tracked receipts, threat model, SBOM, release preflight — and at the same
time zero real LLM calls (all Hermes providers are stubs), one toy backtest in
`experiments/`, no closed feedback edge anywhere, and `risk_context` supplied
manually on every run. Governance compounds; judgment does not. That is what
an implicit B of "build the system" produces.

## 2. Root B, stated as a state

> **B-root: By a checkpoint date, every trading decision I make is produced
> under structured evidence, with loss bounded by structure rather than
> willpower, and decision quality has a measurable, lesson-driven improvement
> trajectory.**

The operator is the subject of B. FinHarness is C. Alpha is explicitly **not**
part of B: returns are too noisy to serve as a comparator on this horizon, and
a noisy comparator teaches loops to optimize luck. Process quality is
controllable; P&L is an outcome we observe, not a done-condition we gate on.

### B decomposed into testable predicates

```text
B1 evidence-on-demand (observation):
  For any watchlist symbol, the system produces within minutes an evidence
  package: price/indicator state, recent events, and N candidate hypotheses
  each with an explicit falsification condition.
  Comparator: freshness/coverage quality gates (deterministic, exist today)
  + periodic human spot-check.

B2 decision discipline (judgment):
  No entry without a written thesis + invalidation + size + max loss; the
  system drafts, the human edits — low friction, not ceremony.
  Comparator: receipt existence (trading_guard already checks thesis) +
  post-hoc compliance rate.

B3 bounded loss (safety):
  No path — human error or AI error — can lose more than the configured
  budget. Live write paths require independent multi-party authorization.
  Comparator: deterministic checks. Closest to DONE today per audit.

B4 compounding judgment (learning):
  Month-N decision quality > month-1, and the improvement is attributable:
  each rule/threshold/checklist change carries lineage to a lesson, which
  carries lineage to receipts.
  Comparator: post-trade attribution + lesson→rule-change lineage.
  Completely missing today. This predicate IS the project's reason to exist.

B5 boundary (non-goals, permanent):
  The system never trades autonomously. READY/PASS never authorizes live
  action. Alpha discovery is downstream of B1–B4, never a substitute.
```

B4 is the discriminating predicate. B1–B3 can be satisfied by a pipeline;
only B4 requires loops.

## 3. Comparator inventory (what the loops may trust)

Loop quality is bounded by comparator quality. Ranked for this project today:

```text
strong   risk gate / guard checks      deterministic, tested
strong   execution lifecycle checks    deterministic, tested
medium   backtest metrics (vectorbt)   programmatic, but overfitting risk
medium   post-trade attribution        programmatic, small-sample noise
weak     LLM judging LLM output        do not build loops on this yet
```

Design rule that follows: **LLM goes in generator positions only; evaluator
positions stay programmatic or human** until we have local evidence that an
LLM evaluator agrees with ground truth on our own receipts. No multi-agent
voting either — same model, correlated errors, not independent evidence.

## 4. Loop topology derived from B

Apply the razor: a module is a loop only if it has its own state, target,
comparator, action, and stop/escalation condition. Otherwise it is a step.

The ten layers are not ten peers. They regroup into four real loops plus
functions:

```text
LOOP 1  Observation loop        (body: L1–L4, seed: daily_evidence_graph)
  state: latest evidence per watchlist symbol
  target: freshness + coverage
  comparator: existing deterministic quality gates
  action: scheduled refresh (cron) — currently one-shot, must become recurring
  stop: quality ok / escalate on repeated source failure

LOOP 2  Hypothesis research loop   (body: L5–L6, generate-and-test)
  state: hypothesis registry with status (captured → testing → validated/
         falsified/archived)
  target: each hypothesis reaches a terminal status with evidence
  comparator: programmatic backtest/scenario checks (vectorbt) — NOT the LLM
  action: LLM drafts hypotheses + falsification conditions (first real LLM
          integration goes HERE, in the generator seat)
  stop: terminal status or budget cap per hypothesis

LOOP 3  Per-trade loop            (body: L7–L10, supervisory + human gate)
  state: TradingState (drawdown, consecutive losses, cooldown) — persisted,
         not hand-fed per run as today
  target: B2 + B3 hold for this trade
  comparator: risk gate checks (deterministic) + human approval as a real
              LangGraph interrupt, not a default-True boolean
  action: proposal → gate → paper execute → post-trade
  feedback edge (MISSING TODAY): post_trade writes TradingState back; next
  risk gate run reads it. Without this edge L7–L10 is a pipeline, not a loop.

LOOP 4  Lesson loop               (slow learning; does not exist today)
  state: lesson registry + the rule set it governs (thresholds, checklists,
         allowlists, prompt templates)
  target: B4 — every rule change traceable to lesson to receipts
  comparator: HUMAN (per the maturity table, LLM-driven self-improvement is
              the least mature loop form; AI only drafts lesson candidates
              from receipts, human promotes them to rule changes)
  action: periodic pass over post-trade receipts and reviews
  stop: per-cycle cap on rule changes; conflicting lessons escalate to human

NOT loops (steps/functions): indicators (L2 math), events fetch (L3),
interpretation (L4 transform), receipt writing, lineage hashing.

EXISTING governance loops (engineering_delivery, quality_governance,
release_preflight): mature, keep, do not multiply further.
```

Loop interconnection is blackboard-style, matching what already works here:
loops communicate through persisted snapshots/receipts under `data/`, never
through direct agent-to-agent chat. The receipt store is the blackboard.

## 5. Topology-selection rationale (per problem feature)

```text
A (market state) unobservable & drifting  → observation loop first (Loop 1)
B clear + comparator programmatic         → generate-and-test (Loop 2)
high consequence, irreversible            → supervisory + human authorization
                                            (Loop 3, interrupt at the gate)
comparator weak (self-judging LLM)        → no reflection loops; external
                                            tools or human instead
long horizon                              → persistent state + staged receipts
                                            (Loop 3 state, Loop 4 registry)
limited budget                            → single loop per concern; escalate
                                            complexity only on failure
                                            threshold, never preemptively
```

## 6. Build order (smallest edges that close loops)

```text
1. Close Loop 3's feedback edge: persist TradingState across runs; risk gate
   reads it instead of taking hand-fed risk_context. Deterministic, small.
2. Make Loop 1 recurring: watchlist file + scheduled daily_evidence run.
3. First real LLM call: hypothesis drafting in Loop 2 generator seat,
   evaluated by vectorbt-backed validation. Replaces the Hermes stub.
4. Loop 4 v0: AI drafts lesson candidates from post-trade receipts into
   docs/lessons/ as proposals; human promotes; rule changes carry lineage.
5. Convert the default-True human_review_attested into a LangGraph
   interrupt + checkpointer at the risk gate (also fixes audit finding #1).
```

Items 1–2 are pure plumbing and close real loops before any intelligence is
added. Item 3 is the first moment FinHarness produces machine judgment — and
it lands in the only seat where today's comparators can check it.

## 7. Build log (2026-06-12, same day)

The five build-order items were implemented and verified:

```text
1. DONE  trading_state_store.py persists TradingState; risk_gate_graph reads
         it (load_trading_state node), post_trade_graph writes it back
         (persist_trading_state node). Corrupt state fails closed.
2. DONE  Loop 1 recurring: data/watchlists/equity-core.json + rolling date
         window in run_daily_evidence_graph.py + hermes cron job 1c5c39fab470
         ("FinHarness daily evidence (Loop 1)", 30 7 * * 2-6, no-agent mode).
3. DONE  HermesHypothesisDraftProvider implemented over `hermes -z` via
         hermes_bridge.py. Fail-closed to deterministic templates; raw
         exchanges persisted under data/cache/hermes-drafts/. First real run
         produced cited, falsifiable hypotheses — and the quality gate caught
         a false positive ("sell-side analyst" tripping \bsell\b), fixed with
         negative lookaheads across all five layer gates.
4. DONE  lesson_loop.py + scripts/run_lesson_draft.py + task lessons:draft.
         Drafts to docs/lessons/drafts/; human promotes. First real pass
         scanned 5079 receipts, 273 quality failures to review.
5. DONE  human_review_attested now defaults False in risk_gate, execution,
         post_trade. Interactive risk-gate build pauses with a LangGraph
         interrupt; resume requires attest=true plus a written reason.
         CLI: scripts/run_risk_gate_graph.py --interactive | --attest-human-review.
```

Observed in the first real generate→evaluate cycle: the LLM produced better
hypotheses than the templates AND the deterministic comparator caught both a
real risk (recommendation language) and its own false positive. The loop
design held; the comparator needed calibration. That is the expected shape of
this system working.

## 8. What this rules out

- No autonomous trading loop, at any maturity level (B5).
- No LLM-evaluates-LLM loops until calibrated against local receipts.
- No multi-agent debate/voting (correlated errors ≠ independent evidence).
- No new governance graphs; governance is the most mature part already.
- No optimizing for P&L as a gate condition; attribution is for learning,
  not authorization.
