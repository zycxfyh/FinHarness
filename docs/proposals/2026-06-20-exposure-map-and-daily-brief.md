# Slice Plan: Personal Exposure Map → Daily Brief

Status: draft
Date: 2026-06-20
Scope: build the B0 "situational awareness" core the cockpit is currently missing.
Foundation first (exposure/risk map over the state core), then the unified daily
brief on top of it. Adopt mature metrics and reuse existing infrastructure; add no
new dependencies.

This is a planning + execution artifact. It does not authorize live trading,
broker writes, ceiling increases, or compliance claims. It does not claim
investment, tax, or accounting correctness.

## 1. 目标发现 (Goal)

North star B0 ([product-north-star.md](../product-north-star.md)): in 5–10 minutes a
user sees what they hold, what changed, what risks rose, what needs review, what is
blocked, and what past decisions taught them.

Today the cockpit shows **counts** (how many accounts/liabilities), not **awareness**
(net worth, where I'm concentrated, how long my cash lasts, what's due). This slice
closes that gap. It is BlackRock-Aladdin-style "portfolio panorama + risk explanation"
shrunk to one person — borrowing the *thinking*, not institutional scale or compliance.

Done when: from real (or sample) state-core data, the cockpit answers "how am I
exposed and how long is my runway", and a single daily brief assembles
exposure + change + upcoming obligations + open reviews, each backed by a receipt.

## 2. 需求定义 (Requirements)

P0 — Exposure map (foundation):
- Net worth: total assets, total liabilities, net (exact Decimal).
- Allocation / concentration: by holding, by account, by currency; with an
  industry-standard concentration measure.
- Cash runway: cash buffer ÷ recurring net outflow, in months.
- Rate exposure: variable-rate debt total, weighted-average rate, annual interest.
- Upcoming obligations: tax events, insurance renewals, dated cashflows within a
  horizon, sorted by date.
- Data gaps disclosed (unpriced holdings, mixed currency, missing cashflows).
- Read-only, `execution_allowed=false`, with `source_refs` to the snapshot/receipts.

P1 — Daily brief (on top of the map):
- One assembled brief = net worth + change-since-last (reuse `diff` / observations)
  + top exposures/concentration flags + upcoming obligations + open proposals + what
  is blocked. Plain-language, non-claims, written to a receipt.

Non-goals (this slice): return-series risk (vol/drawdown/VaR), FX auto-conversion,
optimization/advice, any execution.

## 3. 架构设计 (Architecture)

```
state core (positions/liabilities/cashflows/tax/insurance) [exact Decimal]
        │  pure, deterministic read
        ▼
  exposure.py: compute_exposure(engine) -> ExposureReport     ← FOUNDATION (E1)
        │
        ├── GET /exposure  (BFF, read-only)                    ← E2
        ├── cockpit "Exposure" view                            ← E3
        └── daily_brief.py: assemble_daily_brief(...)          ← E4
                 reuses diff + observations + exposure,
                 writes a receipt; surfaced at /brief/daily + cockpit Overview
```

Decisions:
- `compute_exposure` is a **pure function** (no writes) → trivially testable and
  reusable by both the endpoint and the brief. Persistence/receipt is the brief's job,
  not the computation's.
- Money stays **exact Decimal**; aggregation is plain Decimal arithmetic, not float
  (do not reintroduce the drift D1/Decimal just removed). pandas is reserved for
  genuine DataFrame/time-series work later, not point-in-time money sums.

Rejected:
- A new persisted `Exposure` state table (it is a derived view; compute on demand,
  receipt only when it feeds a brief/decision).
- A portfolio-optimization library for net-worth allocation (needs return series we
  do not have; that is QuantStats/Riskfolio territory, deferred).

## 4. 任务拆分 (Tasks, done one by one, each behind `task check` + a regression test)

- **E1 — exposure engine.** `src/finharness/exposure.py`: `compute_exposure(engine)`
  → `ExposureReport` (net worth, allocation/concentration with HHI + top-1/top-5,
  cash runway, rate exposure, upcoming obligations, data gaps). Unit tests over a
  seeded state core. FOUNDATION.
- **E2 — exposure endpoint.** `GET /exposure` in `routes_cockpit.py`, read-only,
  `execution_allowed=false`. API test asserts no execution path and correct numbers.
- **E3 — cockpit Exposure view.** Add an "Exposure" tab to `frontend/` reading
  `/exposure`. Served-page test.
- **E4 — daily brief.** `src/finharness/daily_brief.py`: assemble exposure + change
  (reuse `diff`/`observations`) + upcoming obligations + open proposals into one
  brief, write a receipt; `GET /brief/daily`; cockpit Overview shows it. Tests.

## 5–7. 实现 / 评审 / 测试 (gates)

Review gates per task:
- Does it stay read-only and `execution_allowed=false`? (authorization line)
- Is money exact Decimal end-to-end, float only at the display boundary?
- Does it adopt a standard metric / reuse infra instead of inventing?
- Does it serve B0 awareness, or only add ceremony?

Adopt / standard-metric map:
- Concentration → **HHI (Herfindahl–Hirschman Index)** + top-N share (regulator/
  institution standard); reuse `ObservationThresholds.concentration_pct` for the flag.
- Cash runway → standard "months of expenses covered".
- Change-since-last → reuse existing `statecore/diff.py` + `statecore/observations.py`.
- Return-series risk (vol/drawdown/VaR) → **QuantStats/Riskfolio**, deferred until a
  return series exists. FX → beancount prices / yfinance, deferred.

Testing: `task check` green after each task; each task ships a regression test.

## Non-Claims

- The exposure map is descriptive aggregation of mirrored state, not investment, tax,
  or accounting advice, and not a net-worth guarantee.
- Unpriced/mixed-currency/missing-cashflow cases are disclosed as data gaps, not
  silently valued.

## Progress Log

- DONE E1 — `exposure.py` `compute_exposure` (net worth, HHI concentration + top-N,
  cash runway, rate exposure, upcoming obligations, data gaps), exact Decimal,
  float at the boundary. Unit tests. (`task check` green, 439 tests.)
- DONE E2 — `GET /exposure` (read-only, `execution_allowed=false`); API test plus
  the no-execution-path lock updated. (440 tests.)
- DONE E3 — cockpit "Exposure" tab/view over `/exposure`; served-shell test asserts
  the wiring. (440 tests.)
- DONE E4 — `daily_brief.py` `compute_daily_brief` (pure) + `record_daily_brief`
  (writes a dated receipt) reusing exposure + diff/observations; `GET /brief/daily`;
  cockpit Overview shows the brief; `task brief:daily`. Unit + API tests.
  (`task check` green, 445 tests.)
- Live smoke (uvicorn + curl) caught two real bugs, both fixed with regression tests:
  - `_ledger_metadata` doubled relative ledger paths (`task beancount:import` with a
    relative path crashed); beancount already returns absolute include paths, so
    resolve+dedupe is enough.
  - exposure concentration divided by net assets, so a negative cash/margin position
    produced weights > 100%; concentration now uses the positive long book as the
    denominator (weights stay in [0, 1]).
