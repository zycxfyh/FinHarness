# DataQualityInterface Plan (Pandera-first)

Design-only document for replacement step 3 of the
[mature wheel control plane](mature-wheel-control-plane.md). **No production
dependency is added by this document.** Installing `pandera` (or any alternative)
requires explicit user approval before implementation begins.

## 1. Problem: two OHLCV validation surfaces, hand-written

Today OHLCV validation is split across two hand-written code paths with
overlapping but non-identical invariants:

| Surface | File | Behavior | Invariants enforced |
| --- | --- | --- | --- |
| Strict normalizer | `indicators/shared.py::validate_ohlcv` | raises `ValueError`, returns normalized frame | required columns present, non-empty, OHLC numeric, OHLC `> 0` |
| Soft verdict | `market_data.py::build_quality_report` | never raises, returns `MarketDataQuality` | missing columns, duplicate timestamps, non-positive OHLC, `high < low`, null counts, staleness |

Both re-implement column/numeric/positivity checks by hand. That is the
self-built wheel to retire. The mature wheel (Pandera) should own the
**structural dataframe contract**; FinHarness should own the **verdict semantics,
freshness, and the no-execution boundary**.

Note the invariants are *not* the same across the two paths. The migration must
preserve each path's current behavior exactly — see §6. In particular:

- duplicate timestamps are **counted (soft)**, never raised;
- staleness is **time-relative**, not a static schema invariant;
- `volume` is coerced to numeric but its nulls/sign are **not** currently
  enforced in either path — do not silently add new invariants.

## 2. Canonical OHLCV schema

One schema object, consumed by both a strict and a soft entrypoint.

Columns (order = `REQUIRED_OHLCV` = `date, open, high, low, close, volume`):

| Column | Dtype | Nullable | Value constraint | Source of truth today |
| --- | --- | --- | --- | --- |
| `date` | datetime (UTC) | no | — | `normalize_ohlcv` produces `datetime64[ns, UTC]` |
| `open` | float64 | no | `> 0` | strict raises; soft flags `open_non_positive` |
| `high` | float64 | no | `> 0` | same |
| `low` | float64 | no | `> 0` | same |
| `close` | float64 | no | `> 0` | same |
| `volume` | float64 | **yes (current behavior)** | none enforced today | coerced numeric only |

Cross-field / dataframe-wide checks:

- **enforced today (keep):** `high >= low` (soft `high_below_low` flag),
  no duplicate `date` values (soft `duplicate_timestamps` count).
- **candidate future checks (NOT enforced today — list, do not enable silently):**
  `high >= max(open, close)`, `low <= min(open, close)`, monotonic `date`,
  `volume >= 0`. Adding any of these is a behavior change that needs its own
  characterization test + receipt note, not a free rider on this migration.

Freshness (`stale`) stays **out of the schema**. It depends on `datetime.now()`
and `max_staleness_days`; a static dataframe contract must not own wall-clock
time. It remains a `build_quality_report` responsibility and a source-freshness
note.

## 3. Error modes to preserve (strict path)

These exact `ValueError` messages are part of the caller contract (indicators,
`vectorbt_runner`, `latest_snapshot`) and are asserted by tests. Pandera's
`SchemaError` must be **caught and re-raised as `ValueError` with the same text**
— never let `SchemaError` leak to callers.

| Condition | Current message |
| --- | --- |
| missing columns | `OHLCV data missing columns: {missing}` |
| empty frame | `OHLCV data is empty` |
| non-numeric OHLC | `OHLC data contains non-numeric values` |
| non-positive OHLC | `OHLC prices must be positive` |

## 4. Target module shape

New module `src/finharness/data_quality.py` holding the schema and two
entrypoints derived from it:

```text
data_quality.py
  OHLCV_SCHEMA            # the single Pandera DataFrameSchema
  validate_ohlcv_strict(frame) -> pd.DataFrame   # raises ValueError (§3)
  assess_ohlcv_quality(frame, *, required_columns, max_staleness_days)
                                                 -> MarketDataQuality (verdict)
```

Wiring (thin wrappers, import paths preserved):

- `indicators/shared.py::validate_ohlcv` becomes a thin delegate to
  `validate_ohlcv_strict`. The public name and signature stay identical so
  `macd`, `squeeze`, `vectorbt_runner`, and `latest_snapshot` are untouched.
- `market_data.py::build_quality_report` delegates **structural** checks to the
  schema in `lazy=True` mode (collect all failures), then keeps:
  - freshness (`stale`, age note),
  - verdict assembly (`ok`, `row_count`, `null_counts`, `outlier_flags`, `notes`),
  - translation of collected `SchemaError` cases into `MarketDataQuality` fields.

Strict path uses `lazy=False` (fail fast → first error → mapped `ValueError`).
Soft path uses `lazy=True` (collect → translate to verdict, never raise). One
schema, two failure-handling policies.

## 5. Boundary: schema pass is not execution authority

Hard rule, identical to the indicator and research adapters:

- A passing schema means **the dataframe shape is valid**, nothing more.
- `MarketDataQuality.ok == True` is a *data* verdict, not a *trade* permission.
- `data_quality.py` must never emit `execution_allowed`, never feed
  `risk_gate`/`execution` directly, and never short-circuit human review.
- `MarketDataQuality` stays a frozen pydantic model with no authority field;
  the execution boundary remains owned by `risk_gate` and `execution`.

This keeps Pandera in the same role TA-Lib/vectorbt/Riskfolio occupy: heavy
mechanics in, evidence out, zero authority.

## 6. Tests to write FIRST (characterization, before swapping impl)

Write these against **current** behavior and get them green on the existing
hand-written code. Only then introduce Pandera and prove the same tests stay
green — that is the proof the swap is behavior-preserving.

1. `tests/test_indicators_shared.py` (or extend existing):
   - missing columns → `ValueError("OHLCV data missing columns: ...")`
   - empty frame → `ValueError("OHLCV data is empty")`
   - non-numeric OHLC → `ValueError("OHLC data contains non-numeric values")`
   - non-positive OHLC → `ValueError("OHLC prices must be positive")`
   - happy path returns columns in `REQUIRED_OHLCV` order with numeric dtypes
   - `volume` NaN currently passes strict (lock the current quirk so the swap
     does not accidentally tighten it)

2. `tests/test_market_data.py::build_quality_report`:
   - happy frame → `ok=True`, empty `outlier_flags`, `duplicate_timestamps=0`
   - duplicated `date` → `duplicate_timestamps` counted, `ok=False`
   - `high < low` row → `high_below_low` in `outlier_flags`, `ok=False`
   - non-positive close → `{col}_non_positive` flag, `ok=False`
   - nulls → `null_counts` populated
   - stale: `max_staleness_days` exceeded → `stale=True` + age note, but
     `stale` alone does **not** force `ok=False` (current behavior — lock it)

3. `tests/test_data_quality_boundary.py`:
   - a fully valid frame produces a verdict object with **no** execution field
   - assert `MarketDataQuality` has no attribute granting execution authority

## 7. Pandera vs Great Expectations — recommendation: Pandera

| Criterion | Pandera | Great Expectations |
| --- | --- | --- |
| Integration model | in-process schema object, decorator/function | data context, expectation suites, validation store |
| Operational surface | none (pure library) | config dir, stores, optional Data Docs/server |
| Fit with current code | direct — pandas frames, sync, library-style | heavy — built for pipelines/multi-source/data docs |
| Strict + soft from one definition | yes (`lazy=False` vs `lazy=True`) | awkward (suite results, not raise semantics) |
| Dependency weight | light | large transitive tree |
| When it wins | typed in-process dataframe contracts | shareable data docs, multi-team suites, profiling |

**Pandera** matches this codebase: the work is in-process pandas validation
behind two function entrypoints, and one schema object cleanly yields both the
raise path and the verdict path. Great Expectations' value (Data Docs, suites,
cross-source profiling) is operational surface this control plane does not need
and would have to maintain. Revisit GE only if data quality later needs
shareable, multi-team, multi-source evidence docs.

## 8. Acceptance criteria

Before the hand-written checks are retired:

- `indicators/shared.validate_ohlcv` keeps its name, signature, and exact error
  messages; `SchemaError` never leaks to callers.
- `MarketDataQuality` shape and field semantics are unchanged; the verdict still
  distinguishes structural failures, outliers, nulls, and freshness.
- Characterization tests in §6 are green on the old code first, then green again
  unchanged after the Pandera swap (adapter path proven exercised).
- No `execution_allowed` / authority field is introduced into the data layer;
  `risk_gate`, `execution`, human review, and non-live defaults are untouched.
- A receipt/quality note discloses the schema backend and `pandera` version when
  the verdict is emitted (parallels `METRICS_BACKEND`, `MACD_BACKEND`).
- Adding `pandera` to production dependencies is a **separate, user-approved**
  step. This document does not authorize it.

## 9. Open question for the user

`pandera` ships two engines (`pandas` and an optional `polars` one). The pandas
engine is the only one needed here. Confirm before install whether the
lightweight `pandera` (pandas extra) is acceptable as a new production
dependency, or whether you want to keep the hand-written checks and only adopt
the single-schema refactor without the external wheel.
