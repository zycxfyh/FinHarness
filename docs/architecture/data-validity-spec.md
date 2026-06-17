# Data Validity — Execution Spec (NOW-2 / G02)

Executable spec for the second NOW-phase gap. It pairs with the research-rigor
ladder ([NOW-1](research-rigor-ladder-spec.md)): rigor on biased data is
worthless, so research evidence must **disclose** the data's bias and adjustment
state. This phase makes the disclosure honest; it does **not** fully solve
survivorship / point-in-time bias (that stays explicitly open). See gap **G02**
in [07 Final Merged Plan](industry-benchmark/07-final-merged-plan.md).

**No new default production dependency** (yfinance `auto_adjust` is already
present; the OpenBB adapter is optional in the hardened default environment).
Reconciliation is best-effort and offline-safe.

## 0. Current state (verified)

- `data_entry.py::fetch_yfinance_history` fetches with **`auto_adjust=False`** —
  raw, **unadjusted** prices. Splits/dividends are uncontrolled.
- `market_data.py`: `SourceSpec` (provider/upstream_source/…), `MarketDataQuality`
  (ok/row_count/…/notes), `MarketDataLineage` (source/fetch_config/…/
  quality_backend). None disclose adjustment, reconciliation, or bias state.
- Single source (yfinance). No second-vendor cross-check. No survivorship or
  point-in-time control. The validation backtest (NOW-1) runs on this data but
  its limitations do not yet name the data bias.

## 1. Deliverable A — corporate-action adjustment disclosure

- Switch `fetch_yfinance_history` to **`auto_adjust=True`** (split/dividend
  adjusted) and make the mode an explicit, recorded parameter:
  `adjustment: Literal["raw", "auto_adjust"] = "auto_adjust"`.
- **Disclose** it: add `adjustment` to `SourceSpec` (additive field, default
  `"auto_adjust"`) and into `MarketDataLineage.fetch_config`.
- **Deliberate behavior change.** Adjusted prices differ from raw; this changes
  feature/return values. Update affected characterization tests with a one-line
  migration note ("prices now corporate-action-adjusted; see G02"). Not silent.

## 2. Deliverable B — second-source reconciliation (best-effort, offline-safe)

- Add `reconcile_close(symbol, start, end, *, second_provider)` that fetches the
  same window from a callable second provider or an optional OpenBB provider and returns
  `{provider, second_provider, max_close_divergence_pct, overlap_rows}`.
- Record it in `MarketDataQuality` via a **new optional field**
  `reconciliation: dict | None = None` (additive — does not change existing
  fields, does not break locked quality tests).
- **Fail-open to disclosure, not fail-closed.** A missing/unconfigured/erroring
  second provider yields `reconciliation = {"status": "single_source_unreconciled"}`
  and a `notes` entry — it must **not** set `ok=false` and **not** raise.
  Reconciliation is an evidence-quality signal, not a safety gate.
- Keep it keyless where possible; if the optional second source is unavailable or
  needs credentials, treat "no credentials" as `single_source_unreconciled`.

## 3. Deliverable C — the `data_bias_uncontrolled` stamp (the core)

Two-place disclosure so no research result can overclaim:

- **Data layer (source of truth):** add `data_bias_controls` to `MarketDataLineage`
  (additive), e.g. `["survivorship_uncontrolled", "point_in_time_uncontrolled"]`,
  until those are solved.
- **Research layer (carries it into the verdict):** the validation backtest
  evidence ([NOW-1] `BACKTEST_LIMITATIONS` / the per-rung limitations) gains a line:
  *"Data bias uncontrolled: survivorship and point-in-time not guaranteed;
  prices `<adjustment>`; reconciliation `<status>`. Evidence only."* Keep it free
  of `BLOCKED_VALIDATION_LANGUAGE`.

This guarantees: a research conclusion always travels with the bias state of the
data it stands on.

## 4. Red lines

- **No new default production dependency** (yfinance present; OpenBB optional).
- **All disclosure is additive** — new optional fields with defaults on frozen
  pydantic models; do **not** change `MarketDataQuality.ok` semantics, the locked
  `notes` for staleness, or any existing field. Locked data-quality tests stay
  green.
- **Reconciliation never blocks** and never flips `ok`/`execution_allowed`.
- **This phase discloses bias; it does not claim to remove it.** Do not label data
  survivorship-bias-free or point-in-time. Those remain open (a later phase).
- `execution_allowed=false` and all NOW-1 governance unchanged.

## 5. Tests

1. `fetch_yfinance_history` uses `auto_adjust=True` and the snapshot/lineage
   records `adjustment="auto_adjust"`.
2. Reconciliation present: with a stub second provider, `MarketDataQuality.
   reconciliation` carries `max_close_divergence_pct` and `overlap_rows`.
3. Reconciliation absent: no/failing second provider →
   `reconciliation={"status":"single_source_unreconciled"}`, `ok` unchanged, no
   raise.
4. Bias stamp present in `MarketDataLineage.data_bias_controls` **and** in the
   validation backtest evidence limitations.
5. Characterization update: the auto_adjust price change is reflected with a
   migration note; existing data-quality tests stay green (additive fields only).
6. Boundary: nothing in this phase grants execution authority;
   `execution_allowed=false` everywhere.

## 6. Acceptance checklist

- [ ] `fetch_yfinance_history` is `auto_adjust=True` with a recorded `adjustment`.
- [ ] `SourceSpec.adjustment`, `MarketDataLineage.data_bias_controls`, and
      `MarketDataQuality.reconciliation` added as additive optional fields.
- [ ] `reconcile_close` best-effort, offline-safe, never blocks.
- [ ] Bias stamp travels into research/validation limitations.
- [ ] Deliberate auto_adjust change has a migration note; locked data-quality
      tests stay green; new tests (§5) green.
- [ ] `uv run ruff check` clean; `task check` passes. (`security:scan` not needed.)
- [ ] Report with test evidence, not a bare "done".

## 7. Out of scope (stays open)

- **Solving** survivorship / point-in-time bias (needs a survivorship-free,
  point-in-time vendor — a data-vendor decision, future phase). This phase only
  **discloses** it.
- Intraday/tick data, vendor SLAs, full multi-vendor consensus.
- TCA (G04) and the aggregate-limit ledger (G06) are separate specs.
