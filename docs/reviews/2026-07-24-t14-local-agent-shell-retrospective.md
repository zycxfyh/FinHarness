# Review: T14 Local Agent Shell

Date: 2026-07-24
Status: P0 complete; P1 actions implemented and release-gated
Related PR: #493
Candidate head before final review hardening: `4abc29cf5bba6470ccf86464ed738f83928651c0`
Classification: architecture, product boundary, identity, recovery, process

Labels used below:

- **Observed**: directly supported by code, tests, Git, CI, or review evidence.
- **Inferred**: reasoned conclusion from observed evidence.
- **Proposed**: future action or rule.
- **Unknown**: not established by this stage.

## 1. Task overview and goal review

### Goal

**Observed.** T14 was intended to create the first usable Agent-native product slice over the existing FinHarness capital core:

```text
local authenticated session
→ admitted Capital World
→ Mission / Belief / Delegation
→ read-only conversation
→ structured offline paper Effect
→ Rust Runtime Job / Attempt
→ systemd Worker
→ simulated execution and reconciliation
→ replayable result
```

The scope deliberately excluded live brokers, funded accounts, hosted multi-user login, schedulers, multi-Agent coordination, bank connections, and autonomous live trading.

### Success criteria

- The browser can inspect Capital World and start a durable Mission.
- Free text cannot directly create an Effect.
- A structured paper Effect derives price and pre-trade position from Capital World.
- Execution passes through the T13 Rust Runtime and existing Execution Kernel.
- Same-key retries do not redispatch the Effect.
- Provider secrets remain server-side.
- `live_execution_allowed=false` remains explicit.
- Failure after domain completion but before HTTP acknowledgement is recoverable.
- Exact-head CI, review resolution, merge, and final-main verification close the stage.

### Actual result

**Observed.** The product slice, tests, real systemd acceptance, and five rounds of review-driven hardening were implemented. At the time this review was first written, PR #493 had not yet completed its final merge cycle, so implementation completion and release completion were kept separate.

**Inferred.** The engineering goal was substantially achieved, but the stage was not complete until exact-head merge and final-main verification.

## 2. Execution process review

### Material stages

1. Audited existing Identity, Capital World, Capital Agent, Runtime, Execution Kernel, API, and Cockpit boundaries.
2. Defined T14 as one vertical product slice instead of a new roadmap or general platform.
3. Added an Agent Shell service, API routes, loopback server, and independent `/agent-ui/` surface.
4. Added keyed Mission creation, read-only conversation, and structured paper Effects.
5. Connected the product path to the real Rust Runtime and systemd Worker.
6. Registered exact keyed-mutation capabilities and architecture ownership.
7. Added unit, JSDOM, acceptance, and recovery tests.
8. Responded to five material automated review findings.
9. Repeatedly reduced formatter noise before amending the single PR commit.

### Important decisions

**Observed.** The browser expresses intent but cannot supply authoritative price, position, executable, environment, or credentials.

**Inferred.** This was the central architectural decision. Without it, the UI would have become a second capital-fact and execution owner.

**Observed.** Conversation and Effect dispatch are separate routes and models.

**Inferred.** This preserves model flexibility while keeping external effects deterministic and testable.

**Observed.** A separate `/agent-ui/` was used rather than immediately rewriting the existing Cockpit.

**Inferred.** Isolation reduced regression risk, although it creates a future dual-surface debt.

### Material failed or incomplete approaches

- Initial Paper Effect recovery was classified as `terminal_replay_only`. Review showed that domain idempotency did not guarantee API-level recovery after acknowledgement loss.
- The first typed resolver assumed the completed domain receipt always existed. A later review showed that the domain-receipt completion write itself could fail after Runtime completion.
- Reserved paper account validation initially checked only broker binding, not `environment=paper` and `funded=false`.
- Provider advice detection initially scanned only `answer` with a local substring list.
- Mission bootstrap initially filtered by Principal but not AgentRuntimeIdentity.
- Broad formatter runs produced unrelated changes in mature API files and had to be reverted and replayed as narrow patches.
- One focused command referenced a nonexistent `tests.test_identity` module; the actual Agent and keyed-mutation tests passed.

### Tool efficiency

**Observed.** Isolated workspaces, exact GitHub head checks, `force-with-lease`, fail-fast tests, real systemd acceptance, and review-thread GraphQL queries were effective.

**Observed.** Efficiency was reduced by serial review discovery, repeated full CI cycles, remote polling, and avoidable formatter churn.

**Inferred.** The main inefficiency was incomplete pre-PR failure modelling, not lack of execution tooling.

## 3. Results and metrics

### Final local evidence before release closure

- 1,277 Python unittest tests passed after the fifth review fix.
- 122 pytest tests passed.
- 41 ordinary Rust Runtime tests passed.
- Real Agent Shell acceptance passed through FastAPI, Rust Runtime, systemd/cgroup, the Python Worker, Execution Kernel, and reconciliation.
- Frontend static contract and JSDOM product journey passed.
- Documentation generation and catalog checks passed.
- Clippy with warnings denied passed.
- The normal paper Effect used Capital World price `1000` and replayed without redispatch.
- The domain-receipt failure injection returned 503, left the identity and domain receipts pending, recovered by observing the same Runtime Job, and preserved `submit calls == 1`.

### Quality assessment

**Observed.** Identity, effect, and recovery boundaries are substantially stronger than a normal local prototype.

**Unknown.** The evidence does not establish production concurrency, long-duration stability, hosted security, real-broker correctness, or broad provider behaviour.

### Goal comparison

Achieved:

- local authenticated Agent session;
- Capital World inspection;
- durable Mission / Belief / Delegation;
- read-only conversation;
- structured offline paper Effect;
- real Runtime and reconciliation;
- server-side provider secrets;
- same-key replay;
- identity terminal-loss recovery;
- domain-receipt completion-loss recovery.

Not part of T14:

- live broker or funded account;
- hosted login;
- external account connectors;
- scheduler or long-running Mission daemon;
- multi-Agent coordination;
- complete onboarding, reporting, or learning product.

## 4. Comparative analysis

### Against the initial path

The initial path was a small product shell. The implementation expanded to include exact identity-bound recovery, provider output redlines, AgentRuntimeIdentity isolation, reserved-account validation, and typed reconciliation.

**Inferred.** This was scope growth in implementation size but not product scope. The extra work was required to make the originally claimed safety and recovery properties true.

### Against a chat-first prototype

A direct chat-to-trade function would have been faster and smaller, but it would have mixed free text, capital facts, authority, and effects. T14 is slower to build but materially safer and more recoverable.

### Against CLI/API only

A CLI-only implementation would have remained thinner, but would not have tested the first-user product journey. The UI made Mission, World, Delegation, and Runtime visible as one product model.

### Against mature practice

Strengths consistent with mature systems:

- idempotency keys and immutable receipts;
- fail-closed capability registry;
- server-side secret custody;
- exact identity binding;
- typed reconciliation;
- acknowledgement-loss fault injection;
- exact-head CI and protected merge;
- real process/runtime acceptance.

Remaining gaps versus production systems:

- no database transaction spanning identity and domain stores;
- no high-concurrency or long-duration evidence;
- no production metrics, SLOs, or alerts;
- file-backed Agent artifacts have no migration/index strategy;
- static local identity is not a hosted authentication system;
- no live broker or external truth reconciliation.

## 5. Success factors and lessons

### What worked especially well

1. **Intent/fact separation.** The UI supplies intent; Capital World supplies authoritative price and position.
2. **Conversation/effect separation.** Free text remains non-executing, while effects use structured requests.
3. **Review as engineering evidence.** Five material review findings were fixed rather than administratively bypassed.
4. **Real Runtime acceptance.** The product path was tested through systemd rather than only mocks.
5. **Diff reduction.** Mature files were restored when formatters produced unrelated churn.

### Start / Stop / Continue

**Start**

- Model acknowledgement-loss and evidence-write-loss before opening a PR.
- Require every effectful keyed route to declare atomic completion, typed reconciliation, or prohibition.
- Run identity, authority, recovery, concurrency, and secret-boundary checklists before CI.

**Stop**

- Stop treating stable domain IDs as proof of end-to-end API recovery.
- Stop broad formatting of mature files during narrow feature work.
- Stop equating green tests with production maturity.
- Stop attempting merge before review threads have fully refreshed.

**Continue**

- Use isolated workspaces and exact-head merges.
- Keep live effects disabled by default.
- Use real Runtime acceptance.
- Resolve reviews with code and tests.
- Keep product layers from owning capital truth or execution programs.

### Root cause: incomplete acknowledgement-loss recovery

1. Domain execution was idempotent.
2. The API was therefore assumed replayable.
3. Identity acknowledgement and domain evidence were persisted separately.
4. Tests initially covered terminal replay but not every write-loss window.
5. Review exposed both terminal identity receipt loss and domain receipt completion loss.

**Inferred root cause.** Domain idempotency was incorrectly treated as equivalent to end-to-end request recoverability.

## 6. Limitations, risks, and improvements

| Issue | Classification | Severity | Probability | Cost | Recommended stage |
|---|---|---:|---:|---:|---|
| Exact-head merge/final-main not yet closed when first written | stage obligation | high | certain | low | P0 |
| Real process kill after Runtime completion not yet tested | next-stage validation | high | medium | medium | P1 |
| Agent UI lacks dedicated real-browser Playwright journey | next-stage validation | medium | medium | low-medium | P1 |
| World drift returns conflict without a complete recovery UX | next-stage product gap | medium | high | medium | P1 |
| Provider redline has no systematic multilingual corpus | next-stage safety gap | medium | medium | medium | P1 |
| Resolver aggregation is coupled through route modules | structural debt | medium | medium | medium | P1 |
| File artifact lookup and schema evolution are not scalable | structural debt | medium-high | high over time | high | P2 |
| Cockpit and Agent UI can drift | structural debt | medium | high | high | P2 |
| Hosted identity, real broker, and long-running operation are absent | explicit non-goal | high if exposed | low in local mode | high | later stage |

## 7. Reproducibility, documentation, and engineering maturity

Reproducible commands include:

```text
task agent:shell
task acceptance:agent-shell
task check:fast
task check:timed
task docs:current-check
cargo clippy -p finharness-runtime --all-features --all-targets -- -D warnings
```

**Observed.** Current-system and system-catalog facts are maintained separately from this historical review.

**Proposed.** Keep future long-task reviews in `docs/reviews/` only when they contain durable lessons, evidence, and actions. Do not make every routine run a prose artifact.

Engineering maturity by dimension:

- modularity: good;
- effect and identity boundaries: strong for current local scope;
- tests: strong but not production-complete;
- recovery: strong for tested acknowledgement windows;
- observability: limited;
- storage scalability: early;
- UX maturity: first usable slice;
- deployment maturity: local only.

## 8. Overall assessment

**Inferred score: 8.4/10 for stage engineering quality, not production readiness.**

The strongest contributions are the real vertical product path and the recovery model. Deductions come from repeated review cycles, implementation size, incomplete pre-PR failure modelling, local-only deployment, and absent long-duration/concurrency evidence.

The project value is architectural: Capital World, Mission, Delegation, Runtime, and Reconciliation now form one observable user journey instead of separate backend concepts.

## 9. Follow-up actions and knowledge retention

### P0

- Finish exact-head CI and review resolution.
- Merge PR #493 without bypass.
- Verify final-main workflows and Agent Shell acceptance.
- Remove the remote branch and close the isolated workspace.

### P1

- Add a real process-level recovery test across API restart.
- Add a dedicated Playwright Agent UI journey.
- Add explicit World-drift inspect/checkpoint/resume UX.
- Add a deterministic multilingual Provider redline corpus.
- Decouple typed resolver aggregation from route modules.

### P2 — deliberately deferred

- Artifact database/index migration;
- unified Cockpit and Agent UI;
- hosted authentication;
- external account connections;
- scheduler, multi-Agent coordination, or live broker support.

### Rules to preserve in tests or engineering policy

1. An effectful keyed route must be atomic, typed-reconcilable, or prohibited.
2. Test both domain-complete/identity-ack-lost and domain-evidence-write-lost windows.
3. Agent-owned artifacts bind both PrincipalIdentity and AgentRuntimeIdentity.
4. Browser and model express intent; system-owned facts determine execution.
5. All provider-authored visible fields use the shared redline policy.
6. Green tests do not establish production maturity; one latency sample is not a workload benchmark.

### Do not add incidentally to P1

- live trading;
- funded brokers;
- multi-user hosting;
- bank connectors;
- schedulers;
- multi-Agent markets;
- full UI rewrite;
- alpha or recommendation models;
- large documentation or governance frameworks.

## P0/P1 action log

### P0 completion

**Observed.** PR #493 was squash-merged without bypass. Final main became `e89cbc9a37fa6878c838182bcaf249f1b77dd75f`; commit identity, security, dependency profiles, browser golden paths, fuzz, and a fresh real Agent Shell acceptance all succeeded. The remote branch and T14 workspace were removed.

### P1 hardening implemented

**Observed.** The five P1 actions from this review were implemented on a branch created from the exact final-main commit:

1. API process recovery now kills the process after Runtime completion, restarts over the same stores, typed-reconciles the pending receipt, and proves one intent, one execution, and the same Runtime Job. The same acceptance runs against the real systemd Runtime on a capable host and a persisted deterministic Runtime observation on a hosted runner without systemd.
2. The Agent UI has a real Chromium Mission/conversation/paper-Effect journey through the API and domain execution path; hosted Chromium uses the portable persisted Runtime fixture, while a separate acceptance owns the real systemd proof.
3. Mission World drift is inspectable and blocks Effects until a keyed, deterministic checkpoint/resume advances the Mission baseline; this recovery is typed-reconcilable.
4. The shared provider redline has a pinned English/Chinese/Japanese corpus with exact blocked and allowed cases.
5. Typed resolver aggregation moved to a domain-neutral registry, removing global registry ownership and Agent special-casing from Proposal routes.

**Observed.** P2 remained deliberately excluded.

## 10. One-sentence summary

T14 proved the first usable FinHarness Agent product path, and its central lesson is that domain idempotency is not end-to-end recoverability: every external effect must survive both acknowledgement loss and evidence-write loss without redispatch.
