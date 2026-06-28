# PortfolioRiskInterface — Riskfolio Evidence Spec (for Codex)

> Historical / superseded reference (2026-06-28): this spec targeted the retired
> risk-gate integration path. Current proposal/review and exposure facts live in
> `system-map.md`, `module-map.md`, and the Capital OS layering document.

Executable spec for **Phase 2b**. Goal: let Riskfolio-Lib allocation feed the
`risk_gate` as a **reviewed suggestion input**, never as authority to widen a cap
or skip human review. [discipline-layer-baseline.md](discipline-layer-baseline.md)
is the regression guard.

**Prerequisite / sequencing:** start only after Phase 2a's `task check` is green.
This phase touches `risk_gate` itself, so the red lines are tighter than 2a.

## 0. Current state (verified)

- `src/finharness/portfolio_risk.py::optimize_riskfolio_allocation` →
  `RiskfolioAllocationSummary(weights, max_weight, concentration_cap,
  concentration_ok, execution_allowed=False)`. Consumed only by
  `experiments/riskfolio_allocation.py` and tests. It never reaches `risk_gate`.
- `src/finharness/risk_gate.py` `concentration_check`
  ([risk_gate.py:372](../../src/finharness/risk_gate.py)) compares
  `context.requested_symbol_concentration_pct <= context.max_symbol_concentration_pct`.
  Both are fixed `RiskGateContext` fields today (defaults `0.02` and `0.10`).

## 1. The seam

Riskfolio's per-symbol weight becomes the **requested** concentration value the
gate evaluates. The **cap stays human-set** and Riskfolio cannot touch it.

```text
RiskfolioAllocationSummary.weights[symbol]
   -> concentration_request_from_allocation(summary, symbol) -> float
   -> RiskGateContext.requested_symbol_concentration_pct   (the REQUESTED side)
   -> existing concentration_check: requested <= max_symbol_concentration_pct
```

Add a pure helper in `portfolio_risk.py`:

```python
def concentration_request_from_allocation(
    summary: RiskfolioAllocationSummary, symbol: str
) -> float:
    """Per-symbol weight as a risk-gate concentration REQUEST (evidence input).
    Never a cap, never an authority to exceed the mandate."""
    return float(summary.weights.get(symbol.upper(), 0.0))
```

The risk-gate context builder (where `RiskGateContext` is constructed for a
candidate) uses it to set `requested_symbol_concentration_pct` when a Riskfolio
allocation is available. When none is available, the existing default/fixed value
is used unchanged.

## 2. Red lines (the whole point of this phase)

- **Riskfolio sets only the REQUESTED value, never the cap.**
  `max_symbol_concentration_pct` is human/mandate-owned and must not be derived
  from, raised by, or relaxed by any Riskfolio output.
- **The gate re-checks independently.** `RiskfolioAllocationSummary.concentration_ok`
  is the optimizer's own view; the gate must NOT trust it. The authoritative test
  remains `concentration_check` against the mandate cap. A weight that Riskfolio
  marks `concentration_ok=True` but that exceeds the mandate cap must still
  **block** at the gate.
- **A suggested weight above the cap blocks.** If Riskfolio suggests a weight >
  `max_symbol_concentration_pct`, `concentration_check` fails and the decision is
  blocked. That is correct behavior — prove it with a test.
- **Human review unchanged.** `human_review_attested` is still required;
  `live_execution_allowed` stays False; no execution authority is added.
- **Allocation is evidence.** Disclose the Riskfolio backend + that the weight is
  a research suggestion (in-sample, MV optimizer assumptions, historical, not
  predictive) in the check `evidence_refs` / receipt. Keep the text free of
  buy/sell/execution language.

## 3. Tests to write

1. Characterization: `risk_gate` behavior is unchanged when no allocation is
   provided (existing tests stay green).
2. Adapter-path: with a Riskfolio allocation injected,
   `requested_symbol_concentration_pct` equals the symbol's weight; Riskfolio is
   exercised (patch/wrap `rp.Portfolio`, mirror `tests/test_portfolio_risk.py`).
3. Boundary — cap cannot be widened: a Riskfolio weight **above** the mandate cap
   → `concentration_check` fails → decision `blocked`; `max_symbol_concentration_pct`
   unchanged.
4. Boundary — independent re-check: `concentration_ok=True` from Riskfolio but
   weight above the gate cap → still blocked.
5. Boundary — human review: an in-cap suggested weight still requires
   `human_review_attested`; `execution_allowed` stays False.

## 4. Acceptance checklist

- [ ] `concentration_request_from_allocation` helper added to `portfolio_risk.py`.
- [ ] Risk-gate context builder consumes it as the REQUESTED value only.
- [ ] `max_symbol_concentration_pct` (cap) untouched by any Riskfolio path.
- [ ] Gate re-checks independently; Riskfolio `concentration_ok` is not authority.
- [ ] Allocation disclosed as evidence with limitations; no execution/trade
      language; `execution_allowed` False everywhere.
- [ ] New tests (§3) green; existing `risk_gate` / `portfolio_risk` tests green
      unchanged; discipline-baseline tests green.
- [ ] `uv run ruff check` clean on touched files; `task check` passes.
- [ ] Report with test evidence, not a bare "done".

## 5. Out of scope

- Execution adapter work is Phase 3 (separate spec).
- Keep `experiments/riskfolio_allocation.py` as-is.
- Do not add multi-asset portfolio sizing into execution; this phase only feeds
  one concentration request per candidate into the existing gate check.
