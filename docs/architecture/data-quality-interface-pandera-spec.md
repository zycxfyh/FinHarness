# DataQualityInterface — Pandera Execution Spec (for Codex)

Approved: user authorized adding `pandera` as a production dependency
(2026-06-15). This is the executable spec for replacement step 3 of the
[mature wheel control plane](mature-wheel-control-plane.md); it builds on
[data-quality-interface-plan.md](data-quality-interface-plan.md). The
characterization tests in `tests/test_indicators_shared.py` and the extended
`tests/test_market_data.py` are the safety net and **must stay green unchanged**
through this change — that is the proof the swap preserves behavior.

## 0. Design decision Codex must honor

There are two OHLCV validation surfaces with **different** behavior; do not
collapse them into one:

- **Strict path** (`indicators/shared.validate_ohlcv`) — raises, returns a
  normalized frame. Becomes fully Pandera-backed.
- **Soft path** (`market_data.build_quality_report`) — never raises (except the
  legacy `.astype(float)` quirk on non-numeric, §6), returns a `MarketDataQuality`
  verdict with counts/flags/freshness. Stays FinHarness-owned, but its
  **positivity contract is sourced from the same Pandera schema** so strict and
  soft cannot drift.

Pandera owns: dtype + nullability + positivity (and is reused for soft-path
outlier flags). FinHarness keeps: duplicate-timestamp count, null counts,
freshness/staleness, verdict assembly, and the no-execution boundary. We
deliberately do **not** force a whole-frame `DataFrameSchema` onto the soft path
(it validates present-columns-only and must not raise on missing columns) —
forcing it adds risk for no gain.

## 1. Dependency

In `pyproject.toml`, insert alphabetically between `pandas-ta` and `plotly`:

```toml
    "pandera>=0.20",
```

Then `uv lock` (or `uv add 'pandera>=0.20'`). Notes:

- Recent Pandera moved the pandas API to `import pandera.pandas as pa`; the bare
  `import pandera` path is deprecated. Use `pandera.pandas`. Confirm the import
  surface against the version uv actually resolves and pin accordingly.
- Only the pandas engine is needed. Do not pull the polars extra.
- A new dependency is a supply-chain surface → run `task security:scan` after
  `uv lock` (Trivy / uv audit over the new wheel) in addition to `task check`.

## 2. New module `src/finharness/data_quality.py`

Single source of truth for the OHLCV contract. Illustrative implementation —
adapt check/failure-case attribute names to the resolved Pandera version:

```python
"""OHLCV data-quality contract backed by Pandera.

Pandera owns the structural contract (dtype, nullability, positivity).
FinHarness keeps verdict semantics (counts, freshness) and the no-execution
boundary. See docs/architecture/data-quality-interface-pandera-spec.md.
"""
from __future__ import annotations

from importlib import metadata

import pandas as pd
import pandera.pandas as pa
from pandera.errors import SchemaErrors

REQUIRED_OHLCV = ["date", "open", "high", "low", "close", "volume"]
OHLCV_NUMERIC_COLUMNS = ("open", "high", "low", "close", "volume")
OHLC_PRICE_COLUMNS = ("open", "high", "low", "close")
DATA_QUALITY_BACKEND = "pandera"

# Strict contract: dtype + nullability + positivity ONLY.
# No high>=low here — the strict path historically does NOT reject high<low,
# so adding it would change behavior. high>=low lives in the soft verdict only.
OHLCV_STRICT_SCHEMA = pa.DataFrameSchema(
    {
        "date": pa.Column(nullable=True, required=True, coerce=False),
        "open": pa.Column(float, pa.Check.gt(0), nullable=False, required=True),
        "high": pa.Column(float, pa.Check.gt(0), nullable=False, required=True),
        "low": pa.Column(float, pa.Check.gt(0), nullable=False, required=True),
        "close": pa.Column(float, pa.Check.gt(0), nullable=False, required=True),
        "volume": pa.Column(float, nullable=True, required=True, coerce=True),
    },
    strict=False,
    ordered=False,
)

# Positivity-only subset, reused by the soft path to derive per-column flags.
_POSITIVITY_SCHEMA = pa.DataFrameSchema(
    {col: pa.Column(float, pa.Check.gt(0), nullable=False) for col in OHLC_PRICE_COLUMNS}
)


def data_quality_backend_version() -> str | None:
    try:
        return metadata.version("pandera")
    except metadata.PackageNotFoundError:
        return None


def validate_ohlcv_strict(frame: pd.DataFrame) -> pd.DataFrame:
    """Strict OHLCV validation. Behavior-equivalent to the legacy hand-written
    validate_ohlcv: same error messages, same normalized output."""
    missing = [c for c in REQUIRED_OHLCV if c not in frame.columns]
    if missing:
        raise ValueError(f"OHLCV data missing columns: {missing}")
    if frame.empty:
        raise ValueError("OHLCV data is empty")

    working = frame[REQUIRED_OHLCV].copy()
    for col in OHLCV_NUMERIC_COLUMNS:
        working[col] = pd.to_numeric(working[col], errors="coerce")

    # Preserve the exact legacy message: any NaN in OHLC (genuine or coercion
    # failure) is reported as "non-numeric", before positivity is judged.
    if working[list(OHLC_PRICE_COLUMNS)].isna().any().any():
        raise ValueError("OHLC data contains non-numeric values")

    try:
        return OHLCV_STRICT_SCHEMA.validate(working, lazy=True)
    except SchemaErrors as exc:  # only positivity can remain at this point
        raise ValueError("OHLC prices must be positive") from exc


def price_outlier_flags(numeric_ohlc: pd.DataFrame) -> list[str]:
    """Soft-path outlier flags from the SAME positivity contract as strict.

    `numeric_ohlc` must already be numeric (caller uses .astype(float), which
    preserves the legacy raise-on-non-numeric behavior of build_quality_report).
    """
    present = [c for c in OHLC_PRICE_COLUMNS if c in numeric_ohlc.columns]
    flags: list[str] = []
    if present:
        try:
            _POSITIVITY_SCHEMA.validate(numeric_ohlc[present], lazy=True)
        except SchemaErrors as exc:
            bad = set(exc.failure_cases["column"].astype(str))
            flags.extend(f"{c}_non_positive" for c in present if c in bad)
    if {"high", "low"}.issubset(numeric_ohlc.columns):
        if (numeric_ohlc["high"] < numeric_ohlc["low"]).any():
            flags.append("high_below_low")
    return flags
```

API points to verify against the resolved version:

- `exc.failure_cases` is a DataFrame with a `column` column → used to map which
  OHLC column failed positivity. If the attribute/shape differs, adjust the
  mapping but keep the output flags identical (`{col}_non_positive`,
  `high_below_low`).
- `flags` order must match the legacy order: positivity flags in
  `open, high, low, close` order, then `high_below_low` last (the existing test
  in `tests/test_market_data.py` locks flag content; keep order stable).

## 3. Wire the strict path (`indicators/shared.py`)

`validate_ohlcv` becomes a thin delegate; name, signature, and error messages
unchanged. Callers (`macd`, `squeeze`, `vectorbt_runner`, `latest_snapshot`) are
untouched.

```python
from finharness.data_quality import REQUIRED_OHLCV, validate_ohlcv_strict


def validate_ohlcv(frame: pd.DataFrame) -> pd.DataFrame:
    return validate_ohlcv_strict(frame)
```

Keep `REQUIRED_OHLCV` importable from `indicators.shared` (re-export) if anything
imports it from there. `true_range()` was already removed — do not reintroduce.

## 4. Wire the soft path (`market_data.py::build_quality_report`)

Keep everything that is verdict semantics; delegate only the positivity +
cross-field flags. Preserve the legacy numeric handling exactly.

- `missing`, `duplicate_timestamps`, `null_counts`, `stale`, `notes`, `ok`,
  `row_count` → unchanged hand code.
- Replace the per-column positivity loop **and** the `high < low` block with one
  call:

```python
from finharness.data_quality import price_outlier_flags

# numeric view over present OHLC columns; .astype(float) preserves the legacy
# raise-on-non-numeric behavior of the old code.
present_ohlc = [c for c in ("open", "high", "low", "close") if c in frame.columns]
numeric_ohlc = frame[present_ohlc].astype(float)
outlier_flags = price_outlier_flags(numeric_ohlc)
```

`ok = not missing and duplicate_timestamps == 0 and not outlier_flags` stays
identical. Do **not** alter `notes` (the staleness test locks its content).

## 5. Backend disclosure (must not disturb locked verdict)

`MarketDataQuality.notes` and field shape are locked by the characterization
tests — do **not** add a backend note there. Disclose the schema backend at the
receipt/lineage layer instead, parallel to `METRICS_BACKEND` / `MACD_BACKEND`:

- Preferred: when the data receipt is written, include
  `DATA_QUALITY_BACKEND` + `data_quality_backend_version()` in the lineage /
  receipt metadata (additive, non-breaking). If there is no clean slot without
  changing a locked test, add an **optional** field to `MarketDataLineage`
  (e.g. `quality_backend: str | None = None`) — additive only — and a small test
  for it.
- Do not introduce any `execution_allowed` / authority field into the data
  layer.

## 6. Behaviors to preserve EXACTLY (do not "fix" silently)

These are current behaviors locked by tests or by caller contract. Changing any
of them is a separate change with its own test + receipt note, not a free rider:

- Strict error messages verbatim (§2): missing / empty / non-numeric / positive.
- `volume` NaN passes the strict path (nullable=True, no positivity check).
- Strict path does **not** reject `high < low` (only the soft verdict flags it).
- Soft path counts duplicates and null_counts on the **original** frame, over
  **all** columns (not just OHLCV).
- Soft path's `.astype(float)` raises on non-numeric OHLC today (uncaught). This
  spec keeps that quirk. It is a candidate future cleanup — list it, do not
  enable a silent change.
- `stale=True` records `stale` + an age note but does **not** force `ok=False`.
- `MarketDataQuality` carries no execution authority field.

## 7. Tests

1. **Existing characterization tests stay green, unchanged** — this is the
   primary proof. Run `tests/test_indicators_shared.py`, `tests/test_market_data.py`,
   `tests/test_indicators.py` before and after; no edits to their assertions.
2. New `tests/test_data_quality.py` (adapter-path proof the wheel is exercised):
   - `isinstance(OHLCV_STRICT_SCHEMA, pa.DataFrameSchema)` and
     `DATA_QUALITY_BACKEND == "pandera"`, `data_quality_backend_version()` not None.
   - `validate_ohlcv_strict` raises the four exact messages (negative,
     non-numeric, empty, missing) — proving the Pandera-backed path emits the
     legacy contract.
   - `validate_ohlcv_strict` returns columns in `REQUIRED_OHLCV` order with
     numeric OHLCV dtypes; `volume` NaN passes.
   - `price_outlier_flags` returns `{col}_non_positive` for a negative column and
     `high_below_low` for an inverted bar, in the locked order.
   - boundary: `data_quality` exposes no `execution_allowed` symbol; a valid
     frame produces a verdict with no authority field.

## 8. Acceptance checklist

- [ ] `pyproject.toml` adds `pandera>=0.20`; `uv lock` updated.
- [ ] `data_quality.py` added; `OHLCV_STRICT_SCHEMA` is the single contract.
- [ ] `indicators/shared.validate_ohlcv` delegates; name/signature/messages
      unchanged; `SchemaError`/`SchemaErrors` never leak to callers.
- [ ] `build_quality_report` delegates positivity + `high_below_low` to
      `price_outlier_flags`; counts / null_counts / stale / notes unchanged.
- [ ] Backend disclosed at receipt/lineage layer; `MarketDataQuality` shape and
      `notes` untouched; no authority field added anywhere.
- [ ] Existing characterization tests green **unchanged**; new
      `tests/test_data_quality.py` green.
- [ ] `uv run ruff check` clean on touched files.
- [ ] `task check` passes.
- [ ] `task security:scan` passes (new dependency reviewed).

## 9. Verification commands

```bash
uv lock
uv run ruff check src/finharness/data_quality.py src/finharness/indicators/shared.py \
  src/finharness/market_data.py tests/test_data_quality.py
uv run python -m unittest \
  tests.test_data_quality tests.test_indicators_shared tests.test_market_data \
  tests.test_indicators -v
task check
task security:scan
```

Report results with test evidence (counts + pass/fail), not a bare "done" — the
project rejects unverified completion claims.
