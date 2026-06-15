# ResearchInterface — vectorbt Evidence Spec (for Codex)

Executable spec for **Phase 2a** of the mature-wheel sequencing
([discipline-layer-baseline.md](discipline-layer-baseline.md) is the regression
guard for any step that touches the decision flow). Goal: lift vectorbt from an
experiment-only script into a **validation evidence producer**, so a research
backtest becomes a `ValidationCheckResult` (evidence), never a proposal or an
order. Builds on [mature-wheel-control-plane.md](mature-wheel-control-plane.md).

## 0. Current state (verified)

- `src/finharness/vectorbt_runner.py::run_vectorbt_moving_average_research` →
  `VectorbtResearchSummary(execution_allowed=False)`. Consumed **only** by
  `experiments/vectorbt_ma.py` and `tests/test_vectorbt_runner.py`. It does not
  reach the validation/proposal lineage. That is the gap.
- The validation layer (`src/finharness/validation.py`) already models evidence:
  `ValidationCheckResult` (per-check evidence), assembled by
  `build_validation_results(...)` from deterministic builders
  (`source_validity_result`, `mechanism_result`, `event_reaction_result`,
  `benchmark_context_result`, `disconfirmation_results`, `limitations_result`).
- The layer is already evidence-only: `ValidationSnapshot.execution_allowed=False`
  and the `no_proposal_or_execution_language` quality gate reject buy/sell/execution
  language. Phase 2a must keep both intact.

## 1. The seam

vectorbt output flows into ONE new `ValidationCheckResult` per job, appended in
`build_validation_results`. Mirror the existing optional-provider pattern
(`ValidationDraftProvider` → `NullValidationDraftProvider` default +
`HermesValidationDraftProvider`) so the deterministic path stays offline and
testable:

```text
BacktestEvidenceProvider (Protocol)
  NullBacktestEvidenceProvider  -> returns a not_testable result (default, offline)
  VectorbtBacktestEvidenceProvider -> wraps run_vectorbt_moving_average_research
```

`build_validation_results(..., backtest_provider=None)` defaults to the Null
provider, so existing deterministic tests are unaffected unless a vectorbt
provider is injected.

## 2. New check type

Add `"backtest"` to the `ValidationCheckType` Literal in `validation.py`:

```python
ValidationCheckType = Literal[
    "source_validity",
    "mechanism",
    "event_reaction",
    "benchmark_context",
    "disconfirmation",
    "limitations",
    "backtest",
]
```

`at_least_one_market_check` keys off `event_reaction` only, so adding `backtest`
does **not** disturb that gate. `backtest` is supplementary evidence, not the
required market check.

## 3. The builder contract

`backtest_evidence_result(*, job, hypothesis, snapshot, provider) -> ValidationCheckResult`

| Field | Value |
| --- | --- |
| `check_type` | `"backtest"` |
| `method` | `VECTORBT_BACKEND` (`"vectorbt.Portfolio.from_signals"`) |
| `window` | the backtest date range string (non-empty; quality gate requires it) |
| `input_refs` | market/indicator snapshot refs from `snapshot`/lineage |
| `metrics` | `{fast, slow, initial_cash, fees, slippage, start_value, end_value, total_return, trade_count}` |
| `result` | conservative `ValidationResult` (see §4) |
| `supports_hypothesis` / `disconfirms_hypothesis` | conservative booleans derived from `result`; not both true |
| `confidence` | **always `"low"`** — a single MA-crossover screen is weak evidence |
| `limitations` | explicit non-claims (see §4), **non-empty** (quality gate requires it) |

## 4. Conservative mapping + red lines (the whole point of this phase)

- **Evidence, not authority.** The backtest result is one `ValidationCheckResult`
  inside the snapshot. It must never become a proposal, an order, or feed
  `proposal_handoff` as authority. `proposal`/`risk_gate` still gate independently
  downstream.
- **`result` mapping is conservative and non-directional:**
  - `trade_count == 0`, history shorter than the slow window, or any runner error
    → `"not_testable"` (never crash, never silent pass).
  - otherwise map historical alignment to `"supported"` / `"weakened"` /
    `"inconclusive"` only. Default to `"inconclusive"` unless clearly aligned.
    Never emit a directional/action word.
- **`limitations` must state the non-claims**, e.g.: "single MA-crossover screen;
  in-sample; costs/slippage only as parameterized; historical, not predictive;
  evidence only, not an execution signal." Keep the text free of
  `BLOCKED_VALIDATION_LANGUAGE` (buy/sell/long/short/order/execute) so
  `no_proposal_or_execution_language` still passes.
- **`ValidationSnapshot.execution_allowed` stays `False`.** Do not add any
  authority field.
- **vectorbt stays a research adapter.** `VectorbtResearchSummary.execution_allowed`
  remains `False`; the provider only reshapes its summary into evidence.

## 5. Tests to write

1. Characterization: `build_validation_results` with the **Null** provider is
   unchanged except for exactly one added `backtest` result per job marked
   `not_testable`; existing result builders untouched. (Lock the new count.)
2. Adapter-path: with `VectorbtBacktestEvidenceProvider`, the `backtest` result
   has `method == VECTORBT_BACKEND`, populated `metrics` (total_return,
   trade_count), `confidence == "low"`, non-empty `limitations`. Wrap/patch
   `vbt.Portfolio.from_signals` to prove vectorbt is exercised (mirror
   `tests/test_vectorbt_runner.py`).
3. Boundary: the `backtest` result passes `no_proposal_or_execution_language`;
   `supports_hypothesis`/`disconfirms_hypothesis` are not both true; the enclosing
   `ValidationSnapshot.execution_allowed` is `False`.
4. Failure path: a too-short history → `not_testable` with non-empty
   `limitations`, no exception.
5. Quality: `build_validation_quality` stays `ok` with the new result
   (`limitations_present`, `result_not_overclaimed`, `lineage_complete`).

## 6. Acceptance checklist

- [ ] `"backtest"` added to `ValidationCheckType`.
- [ ] `BacktestEvidenceProvider` Protocol + Null default + vectorbt impl added.
- [ ] `backtest_evidence_result` builder added; wired into
      `build_validation_results` via injected provider (Null default).
- [ ] vectorbt summary reshaped into evidence; `execution_allowed` stays False
      everywhere; no `proposal_handoff` authority path.
- [ ] Deterministic/offline validation unchanged when no vectorbt provider is
      injected.
- [ ] New tests (§5) green; existing validation tests green unchanged.
- [ ] `uv run ruff check` clean on touched files.
- [ ] `task check` passes. (`security:scan` not required — no security surface.)
- [ ] Report with test evidence (counts + pass/fail), not a bare "done".

## 7. Out of scope (next phases — do NOT start here)

- Riskfolio → `risk_gate` input is **Phase 2b** (separate spec).
- Execution fake → Nautilus is **Phase 3**.
- Keep `experiments/vectorbt_ma.py` as-is; this phase adds the validation path,
  it does not delete the experiment.
