# Documentation & Onboarding Architecture Plan

How FinHarness should structure its docs and onboarding, based on how top
engineering orgs do it. Written after a full system dogfood exposed the real
problem: the guidance is scattered, types are mixed, and some features have no
entry point at all. This is a plan; writing each doc is sequenced follow-up work.
No external docs tool/site/generator is adopted without user approval.

## 1. The problem (verified)

FinHarness is **heavy on explanation and light on the docs a newcomer needs**.
The `docs/` tree concentrates in `architecture/`, `think/`, `adr/`, `notes/`
(all "why" material), plus `reviews/`, `lessons/`, `operations/` (runtime
evidence). Entry points (`README`, `AGENTS.md`, `CONTEXT.md`, `GUIDE.md`,
`week-01.md`, `wheels.md`) overlap and mix purposes. There is:

- no single, authoritative, end-to-end **golden path** a first-time user follows;
- no **task-based** entry ("I want to X" → the one doc for X);
- no **command/interface/receipt reference**;
- and several `task` commands with no documentation at all.

Per Diátaxis, **mixing documentation types is the single most common cause of
confusing documentation** — which is exactly the symptom here.

## 2. How top orgs solve this (researched)

- **Diátaxis** — four distinct doc types, never mixed: **tutorial** (learning,
  hand-held), **how-to** (task recipe for someone who already knows the basics),
  **reference** (facts: accurate, complete, no interpretation), **explanation**
  (the "why": background, architecture, trade-offs).
- **Golden path / paved road** (Spotify "Golden Path", Netflix "Paved Road") —
  one opinionated, officially supported, end-to-end path to a working result. The
  **target audience is a new hire**: if a newcomer can stay on the path, they
  reach a working state without learning every internal detail.
- **Stripe "docs as product"** — organize **task-based, not architecture-based**
  ("I need to accept payments", not "here is our object model"); the canonical
  flow is **pick a goal → copy a working example → test it → verify it → expand**;
  docs quality is a first-class engineering concern (Stripe even ties it to
  promotion), so docs evolve with the code instead of rotting.

## 3. Diagnosis — current docs mapped onto Diátaxis

| Diátaxis type | What FinHarness has | Gap |
| --- | --- | --- |
| Tutorial (learn) | `GUIDE.md` (partial golden path), `week-01.md` | No single first-run tutorial that is **executable and proven green** |
| How-to (do a task) | scattered in `README` task list, `notes/` | No per-job recipes ("run the gate", "add a wheel adapter", "do a safe paper trade") |
| Reference (facts) | `Taskfile.yml`, `wheels.md`, `AGENTS.md`, `policy-contract.md` | No command reference, no interface/module reference, no receipt-schema reference |
| Explanation (why) | `architecture/*`, `think/*`, `adr/*`, `notes/adopt-not-invent` | **Over-invested** — this is the project's strong (and crowded) area |

The shape is **inverted** from what a newcomer needs: deep "why", thin "how".

## 4. Target structure

```text
docs/
  README.md            # the MAP: task-based entry — "I want to X" -> link
  tutorials/           # learning-oriented, hand-held (the golden path)
  how-to/              # task recipes, one per real job
  reference/           # facts: commands, interfaces, receipts, config/env
  explanation/         # the "why": architecture, ADRs, loop topology, doctrine
  reviews/ lessons/ operations/   # runtime evidence (NOT part of the 4 types)
```

Existing explanation docs move (or are indexed) under `explanation/`. Runtime
evidence (`reviews/`, `lessons/`, `operations/`, generated receipts) stays
separate — it is artifacts, not authored documentation.

## 5. The one Golden Path (highest priority)

Define **one** supported end-to-end path and keep it green. It already exists as
a proven sequence — the dogfood run on 2026-06-15:

1. `task setup` / `task check` — install and verify.
2. `task wheels:check` — confirm the mature wheels load.
3. `task feature:macd` — pull real data, compute an indicator (TA-Lib + Pandera),
   see `execution_allowed=false`.
4. `task validation:graph` — research/backtest evidence (vectorbt), **human
   review required before proposal**.
5. `task risk-gate:graph` — mandate/cap checks, no live authority.
6. `task execution:graph` — `blocked_before_submit`, live blocked.
7. Read the receipt — claim / evidence / non-claim.

Each step = a real command + its expected output + **the safety boundary it
demonstrates**. Target audience: a first-time user. This tutorial doubles as a
**regression check for the docs** (if the golden path drifts, the tutorial fails).

## 6. Engineering-progression model (so docs don't rot)

- **Docs-as-code**: docs live in the repo and change in the same PR as the code
  (this is why specs belong in-repo).
- **Definition of done includes docs**: a new interface or wheel adapter is not
  "done" until its how-to + reference entry exist. (Stripe: docs are first-class.)
- **Dogfood on a cadence**: `task check` is necessary but not sufficient — the
  2026-06-15 dogfood found a real bug (list-shaped receipt crash) that 289 green
  tests missed. Walk the golden path regularly.
- **ADRs for decisions** (already in `docs/adr/`) — keep.
- **Onboarding test**: a newcomer using only the golden path + how-tos should
  reach a working, safe state **without** reading the explanation docs.

## 7. FinHarness-specific red lines

- This is a trading system: the golden path and how-tos **must teach the safety
  boundaries** (no-live default, human confirmation, `execution_allowed=false`)
  as first-class content, not footnotes. Onboarding that makes trading feel easy
  without the brakes is dangerous.
- Docs carry the same **claim / evidence / non-claim** discipline as receipts:
  tutorials must state what the system does **not** prove (no profitable edge, no
  live authority, no institutional data guarantee).

## 8. Sequenced plan (for Codex)

1. Create `docs/{tutorials,how-to,reference,explanation}/` and a `docs/README.md`
   map (task-based entry). Low risk, mechanical.
2. **Write the one golden-path tutorial** from the verified 2026-06-15 dogfood
   (commands + real outputs + the boundary each step proves). Highest priority —
   it is the missing thing and it is already proven to work.
3. Reclassify/move existing explanation docs under `explanation/` with an index.
4. Write the missing **reference**: a command reference (from `Taskfile.yml`), the
   mature-wheel interface reference (the control-plane table), receipt schema,
   config/env vars.
5. Write high-value **how-tos**: run a feature snapshot; run the ten-layer flow;
   do a safe paper trade; **add a new mature-wheel adapter** (this last one
   encodes the whole migration discipline as a repeatable recipe).
6. Add a "docs definition-of-done" note to the contributing guide.

## 8a. Implementation status (2026-06-15)

This plan has been implemented as a docs-as-code baseline:

| Plan item | Status | Artifact |
| --- | --- | --- |
| Diátaxis directories and task map | done | `docs/README.md`, `docs/tutorials/`, `docs/how-to/`, `docs/reference/`, `docs/explanation/` |
| Golden path tutorial | done | `docs/tutorials/golden-path.md` |
| Explanation reclassification | indexed, not moved | `docs/explanation/README.md` points to `architecture/`, `adr/`, `think/`, `notes/`, and related explanation folders |
| Command reference | done | `docs/reference/commands.md` |
| Mature-wheel interface reference | done | `docs/reference/interfaces.md` |
| Receipt reference | done | `docs/reference/receipts.md` |
| Config/env reference | done | `docs/reference/config-env.md` |
| Feature snapshot how-to | done | `docs/how-to/run-feature-snapshot.md` |
| Ten-layer flow how-to | done | `docs/how-to/run-ten-layer-flow.md` |
| Safe paper-trade review how-to | done | `docs/how-to/safe-paper-trade-review.md` |
| Mature-wheel adapter how-to | done | `docs/how-to/add-mature-wheel-adapter.md` |
| Lesson-to-rule promotion how-to | done | `docs/how-to/promote-lesson-to-rule.md` |
| Docs definition of done | done | `CONTRIBUTING.md` |

The explanation files were indexed rather than physically moved. That keeps git
history and existing links stable while still giving newcomers a single
Diátaxis-style doorway.

## 9. Out of scope / acceptance

- This document is the plan. Each doc above is follow-up work.
- No external docs site/generator/tool is adopted here; doing so is a separate
  user-approved decision.
- Done when: the four directories exist, the golden-path tutorial is written and
  green, `docs/README.md` routes by task, reference pages cover commands /
  interfaces / receipts / config, high-value how-tos exist, and docs definition
  of done is recorded.

## Sources

- Diátaxis framework — https://diataxis.fr/
- Spotify, "How We Use Golden Paths to Solve Fragmentation" —
  https://engineering.atspotify.com/2020/08/how-we-use-golden-paths-to-solve-fragmentation-in-our-software-ecosystem
- Stripe docs teardown (docs-as-product, task-based) —
  https://www.moesif.com/blog/best-practices/api-product-management/the-stripe-developer-experience-and-docs-teardown/
