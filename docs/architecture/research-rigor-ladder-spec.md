# Research Rigor Ladder — Execution Spec (NOW-1 / G01)

Executable spec for the **highest-priority** gap: the validation layer is at the
bottom rung (a single in-sample MA-crossover screen that can currently be labeled
`supported`). This spec makes research climb a rung ladder and enforces **no
`supported` above the rung actually climbed.** It is the only honest road to a
value claim. See [07 Final Merged Plan](industry-benchmark/07-final-merged-plan.md)
and gap **G01/G03**.

**No new production dependency** for the core (OOS, walk-forward, PSR, gating).
The full Deflated Sharpe refinement needs the already-installed `scipy` declared
direct — a small, separate decision flagged in §9. CPCV/`mlfinlab` is deferred.

## 0. Current state (verified)

- `vectorbt_runner.py::run_vectorbt_moving_average_research(history, fast, slow, …)`
  → `VectorbtResearchSummary(start_value, end_value, total_return, trade_count, …)`
  on a fixed-parameter MA crossover over the **whole** history (in-sample).
- `validation.py`:
  - `map_backtest_result(trade_count, total_return)` → `not_testable` /
    `supported` (≥ +2 %) / `weakened` (≤ −2 %) / `inconclusive`. **This lets a
    single in-sample run be `supported` — the overclaim to fix.**
  - `BacktestEvidence(method, window, metrics, result, supports_hypothesis,
    disconfirms_hypothesis, limitations)`; built into a `backtest`
    `ValidationCheckResult` with `confidence="low"`.
  - `backtest_metrics(...)`, `backtest_window(...)`, `BACKTEST_LIMITATIONS`.

## 1. The rung ladder

Add a `ResearchRung` literal (in `validation.py` or the new module):

```python
ResearchRung = Literal["in_sample", "out_of_sample", "walk_forward", "trial_discounted"]
```

| Rung | What it adds | Max claim allowed |
| --- | --- | --- |
| `in_sample` | single fixed-param run over all history (today) | **`inconclusive`** (never `supported`) |
| `out_of_sample` | train/test time split; result judged on the held-out **test** segment | `supported` if the OOS test bar clears |
| `walk_forward` | rolling train→test folds; judged on fold-test consistency | `supported` if a majority of folds clear |
| `trial_discounted` | multiple configs tried; performance discounted for selection bias | `supported` only if the discounted metric clears |

(`cpcv` is a future rung; out of scope here.)

## 2. The hard governance rule (the whole point)

Replace `map_backtest_result` with a **rung-aware** mapping. Pseudocode:

```python
def map_backtest_result(*, rung, in_sample_return, oos, walk_forward, discount, trade_count):
    if trade_count == 0:
        return "not_testable"
    # In-sample can only weaken or be inconclusive — never support.
    if rung == "in_sample":
        return "weakened" if in_sample_return <= -0.02 else "inconclusive"
    if rung == "out_of_sample":
        if oos.test_return >= 0.02 and oos.test_consistent:
            return "supported"
        if oos.test_return <= -0.02:
            return "weakened"
        return "inconclusive"
    if rung == "walk_forward":
        if walk_forward.frac_folds_positive >= 0.6 and walk_forward.mean_test_return >= 0.0:
            return "supported"
        if walk_forward.frac_folds_positive <= 0.4:
            return "weakened"
        return "inconclusive"
    if rung == "trial_discounted":
        # multiple trials => support requires the selection-bias-adjusted probability
        if discount.psr_gt_zero >= 0.95:
            return "supported"
        return "inconclusive"
```

Invariant tests must prove: **`in_sample` can never yield `supported`**, and a
higher-rung `supported` always has the corresponding cleared metric in the
receipt. `supports_hypothesis = result == "supported"`,
`disconfirms_hypothesis = result == "weakened"` (mutually exclusive) stays.

## 3. New module `src/finharness/research_rigor.py` (pure, no new dep)

```python
"""Research-rigor primitives: time splits, walk-forward folds, and the
Probabilistic Sharpe Ratio. Pure functions; no execution authority."""
from __future__ import annotations
import math

GAMMA_EULER = 0.5772156649015329

def standard_normal_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))

def time_train_test_split(n: int, train_frac: float = 0.7) -> tuple[slice, slice]:
    """Chronological split — train is the earlier segment, test the later."""
    if not 0.0 < train_frac < 1.0:
        raise ValueError("train_frac must be in (0,1)")
    cut = max(1, int(n * train_frac))
    return slice(0, cut), slice(cut, n)

def walk_forward_folds(n: int, n_folds: int = 4, min_test: int = 20) -> list[tuple[slice, slice]]:
    """Rolling expanding-train / fixed-forward-test folds, chronological."""
    # returns [(train_slice, test_slice), ...]; each test is forward of its train.
    ...

def probabilistic_sharpe_ratio(*, observed_sharpe, n_samples, skew, kurtosis,
                               benchmark_sharpe=0.0) -> float:
    """PSR: probability the true (per-period) Sharpe exceeds benchmark_sharpe.
    Bailey & Lopez de Prado (2012). kurtosis is non-excess (normal = 3)."""
    if n_samples < 2:
        return float("nan")
    sr = observed_sharpe
    denom = math.sqrt(max(1e-12, 1.0 - skew * sr + ((kurtosis - 1.0) / 4.0) * sr * sr))
    z = (sr - benchmark_sharpe) * math.sqrt(n_samples - 1.0) / denom
    return standard_normal_cdf(z)
```

- `observed_sharpe` is the **per-return-period** Sharpe (not annualized);
  compute it and `skew`/`kurtosis` from the strategy's per-period returns
  (`portfolio.returns()` → pandas `.skew()`, `.kurt()` is *excess*; add 3 for
  non-excess).
- PSR uses **stdlib only** (`math.erf`). This is the NOW-1 discount.
- Unit-test PSR against hand-computed values (e.g., symmetric normal returns,
  `sr=0` → PSR ≈ 0.5; positive `sr`, large `n` → PSR → 1).

## 4. Extend the vectorbt research adapter (`vectorbt_runner.py`)

Add functions that reuse the existing fixed-param crossover but on sub-windows
and that also return a Sharpe + return-series moments:

- `run_vectorbt_ma_oos(history, fast, slow, train_frac=0.7, …) -> OosResult`
  with `train_return`, `test_return`, `test_sharpe`, `test_trade_count`,
  `test_consistent` (= sign(test_return) == sign(train_return)).
- `run_vectorbt_ma_walk_forward(history, fast, slow, n_folds=4, …) -> WalkForwardResult`
  with per-fold test returns, `frac_folds_positive`, `mean_test_return`,
  `mean_test_sharpe`.
- Each keeps `execution_allowed = False`. Failures (too-short window, vectorbt
  error) degrade to a not-testable shape, never raise into the workflow.

## 5. Wire into `validation.py`

- Extend `BacktestEvidence` and `backtest_metrics` to carry: `rung`,
  `trial_count`, and the OOS / walk-forward / discount sub-metrics (nullable).
- `VectorbtBacktestEvidenceProvider` gains a `rung` setting (default
  `out_of_sample`) and an optional `configs` list; when `configs` has > 1 entry it
  runs each, records `trial_count = len(configs)`, picks the best, and applies the
  PSR discount → rung `trial_discounted`.
- The `backtest` `ValidationCheckResult.metrics` records rung + trial_count + the
  cleared/uncleared sub-metrics; `limitations` **names the rung explicitly**
  (e.g., "out-of-sample test segment; no multiple-testing correction") and stays
  free of `BLOCKED_VALIDATION_LANGUAGE`.
- `confidence` stays `"low"` for NOW-1 (may rise with rung later).

## 6. Red lines

- **Evidence, not authority.** Unchanged: backtest results never drive proposal
  authority (`proposal.py::classify_action_type` already excludes `backtest`);
  `execution_allowed=false` everywhere; no order/direction language.
- **No `supported` above the rung climbed** — enforced in §2 and tested.
- **Deliberate behavior change.** In-sample `supported` is intentionally removed.
  Update the affected characterization test(s) in `tests/test_validation.py` with
  a one-line migration note ("in-sample is no longer `supported`; see G01") — this
  is a *deliberate, tested* change, not a silent one.
- **No new production dependency** for §1–§5 (PSR is stdlib).

## 7. Tests

1. **Governance invariant (new):** `in_sample` rung never returns `supported`,
   for any positive in-sample return.
2. **OOS rung:** a frame where train and test both clear the bar → `supported`
   with `oos.test_return` recorded; a frame where train wins but test loses →
   **not** `supported` (overfitting caught) → `inconclusive`/`weakened`.
3. **Walk-forward rung:** majority-positive folds → `supported`; mixed folds →
   `inconclusive`; majority-negative → `weakened`.
4. **PSR pure tests:** `sr=0` → ≈0.5; strong positive `sr`, large `n` → →1;
   `n<2` → NaN.
5. **Trial discount:** with `configs` of length > 1, `trial_count` is recorded and
   `supported` requires `psr_gt_zero ≥ 0.95`; otherwise `inconclusive`.
6. **Adapter-path:** vectorbt is exercised on the sub-windows (patch
   `vbt.Portfolio.from_signals`).
7. **Boundary:** the `backtest` result passes `no_proposal_or_execution_language`;
   `ValidationSnapshot.execution_allowed` is `False`; receipt `metrics` carry rung
   + trial_count.
8. **Characterization update:** the prior in-sample `supported` expectation is
   updated to `inconclusive` with the migration note; all other validation tests
   stay green.

## 8. Acceptance checklist

- [ ] `research_rigor.py` added (pure: split, folds, PSR; stdlib only).
- [ ] vectorbt OOS + walk-forward runners added; `execution_allowed=False`;
      failures degrade, never raise.
- [ ] `map_backtest_result` is rung-aware; **in-sample cannot be `supported`**.
- [ ] `BacktestEvidence`/`backtest_metrics`/provider record rung, trial_count, and
      OOS/walk-forward/discount sub-metrics; limitations name the rung.
- [ ] Backtest still cannot become proposal/risk/execution authority;
      `execution_allowed=false` and no order language anywhere.
- [ ] New tests (§7) green; characterization update has a migration note; the rest
      of the suite green.
- [ ] `uv run ruff check` clean; `task check` passes. (`security:scan` not needed —
      no security surface, no dependency change.)
- [ ] Report with test evidence (counts + pass/fail), not a bare "done".

## 9. Decisions for the user (before/within build)

- **Deflated Sharpe (full multiple-testing deflation)** needs an inverse-normal
  (`ppf`). `scipy` is already installed (transitive via quantstats/vectorbt). Two
  options: (a) ship **PSR only** now (stdlib, zero dependency change) and treat
  full **DSR** as a later refinement; (b) declare `scipy` a **direct** dependency
  (it is already in `uv.lock`; this is hygiene, not a new install) and implement
  DSR now. **Recommend (a)** for NOW-1.
- CPCV / `mlfinlab` stays deferred (new dependency, requires approval).

## 10. Out of scope

- Parameter optimization beyond an optional small `configs` sweep.
- CPCV, capacity analysis, transaction-cost realism beyond current fees/slippage
  (TCA is gap G04, a separate Next-phase spec).
- Any change to data validity (gap G02) — biased data still limits these results;
  the `data_bias_uncontrolled` stamp (G02) is a separate parallel workstream.
