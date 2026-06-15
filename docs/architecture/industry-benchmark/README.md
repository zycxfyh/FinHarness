# FinHarness Industry Benchmark Series

Author: Codex
Parallel agent: Claude
Status: draft
Date: 2026-06-15
Evidence policy: primary-source-first

This folder is the Codex-authored industry benchmark and product-roadmap series.
It compares FinHarness with mature financial, backend, and frontend practice
without implementing code.

All documents are drafts. They are not legal advice, investment advice,
compliance certification, release approval, or live-trading authorization.

## Reading Order

| Order | Document | Purpose |
| --- | --- | --- |
| 00 | [Working Agreement](00-benchmark-working-agreement.md) | Evidence rules, authorship, non-goals, and citation policy. |
| 01 | [Current State](01-current-state-finharness-codex.md) | What FinHarness is today, using repo evidence only. |
| 02 | [Industry Benchmark Map](02-industry-benchmark-map-codex.md) | Mature methods and standards to compare against. |
| 03 | [Gap Register](03-gap-register-codex.md) | Plane-by-plane gaps, severity, debt class, and close criteria. |
| 04 | [Solution Research Packs](04-solution-research-packs-codex.md) | Design packs for high-priority gaps. |
| 05 | [Product Roadmap](05-product-roadmap-codex.md) | Now / Next / Later route for backend and frontend work. |
| 06 | [Backend And Frontend Guidance](06-backend-frontend-guidance-codex.md) | PRD, tech-spec, and UI-spec guardrails. |
| 07 | [Final Merged Plan](07-final-merged-plan.md) | **Authoritative** Claude+Codex synthesis: gaps, priority bands, roadmap, frontend doctrine. |

## Reconciliation

Claude wrote a parallel architecture-root analysis (state, gap, solution,
roadmap). The two analyses converged strongly; the divergences (notably Codex's
finer 15c3-5 decomposition) were the signal. Claude's parallel root documents
have been **folded into [07 Final Merged Plan](07-final-merged-plan.md) and
removed** to keep a single source of truth. Start with 07; 00–06 are the
supporting detail.

- [SEC Rule 15c3-5 Market Access Review](../../reviews/2026-06-15-sec-15c3-5-market-access-rule-review.md) — controls anchor.

## Safety Boundary

FinHarness may produce governed advice and evidence. It must not let a receipt,
test, benchmark, library output, dashboard, or AI proposal authorize a trade.
`trading_guard`, `risk_gate`, human confirmation, live blocks,
lesson-to-rule lineage, and receipts remain non-replaceable FinHarness
discipline.
