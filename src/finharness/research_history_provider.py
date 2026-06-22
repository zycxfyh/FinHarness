"""RE2: the historical-market-data evidence provider for ``concentration_high``.

This is the real adapter behind RE1's :class:`ResearchEvidenceProvider` seam. It
answers exactly one question — ``historical_risk_profile`` — for the top symbol of a
concentrated holding, and only with **read-only descriptive window statistics**:
realized volatility, maximum drawdown, conditional VaR, average volume.

Hard boundaries (enforced here as code, not reviewer memory):

* **Never an optimizer / forecast.** This module does not import or call
  ``optimize_riskfolio_allocation`` (target weights = advice). A grep/AST probe over
  this module must find no optimizer reference.
* **Network-isolated and testable.** The provider takes an injected
  :class:`MarketHistorySource`. The default adapter is a best-effort wrapper over
  ``market_data`` (may hit the network/cache); unit tests inject a pure fixture source
  and assert no network is touched. Data quality therefore does not depend on the
  network being up the day a test runs.
* **No-data → ``data_gap``, never crash, never invent.** A bad symbol, an unreachable
  source, or a history too short to compute statistics each produce a disclosed gap and
  an otherwise-empty result.
* **Bad input never reaches the network.** ``subject`` is normalized and validated
  against a closed character set/length *before* the source is consulted; an invalid
  symbol short-circuits to a gap and the source is never called.
* **Past-tense, descriptive claim only.** The single evidence item carries a templated
  past-tense claim ("Over {window}, {symbol}'s observed ... was ...") with no
  future-looking language; this is an additional RE2 constraint on top of the RE1
  redline.

Output shape is fixed: **exactly one** aggregate evidence item of kind
``historical_risk_profile`` whose ``value`` has exactly the four whitelisted keys. RE2
itself writes no ``Proposal`` and adds no endpoint; it references market-data receipts
only through ``source_refs``/``lineage``.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol, runtime_checkable

import pandas as pd

from finharness.portfolio_risk import returns_from_close_prices
from finharness.research_evidence import (
    REQUIRED_NON_CLAIMS,
    ResearchEvidence,
    ResearchEvidenceRequest,
    ResearchEvidenceResult,
    ResearchTimeWindow,
)
from finharness.restricted_symbols import normalize_symbol

# Descriptive window-statistic keys. The provider emits exactly these four under
# ``value`` — a closed whitelist asserted by tests, RE3, and the frontend.
RISK_PROFILE_VALUE_KEYS: tuple[str, ...] = (
    "realized_volatility",
    "max_drawdown",
    "conditional_var",
    "average_volume",
)

# Closed window → calendar lookback. Mirrors the RE1 ``ResearchTimeWindow`` literal.
TIME_WINDOW_LOOKBACK_DAYS: dict[ResearchTimeWindow, int] = {
    "trailing_1y": 365,
    "trailing_3y": 365 * 3,
}

# Human-readable window labels for the past-tense claim template.
TIME_WINDOW_LABELS: dict[ResearchTimeWindow, str] = {
    "trailing_1y": "the trailing 1 year",
    "trailing_3y": "the trailing 3 years",
}

# Symbol input guard: uppercase tickers/fund symbols only. ``normalize_symbol`` is an
# OKX/USDT normalizer underneath, so RE2 wraps it with an explicit ticker shape check
# before anything goes out over the network.
_SYMBOL_PATTERN = re.compile(r"^[A-Z0-9][A-Z0-9.\-]{0,14}$")

# RE2 is scoped to one detector. A request from any other detector is unsupported and
# is disclosed as a gap rather than answered with an off-scope risk profile.
SUPPORTED_DETECTOR_KIND = "concentration_high"

# OHLCV columns the provider needs to compute its four statistics.
REQUIRED_OHLCV_COLUMNS: tuple[str, ...] = ("close", "volume")

# Annualization factor for daily realized volatility (trading days/year).
TRADING_DAYS_PER_YEAR = 252

# Minimum return observations needed to report meaningful window statistics. Below
# this the provider discloses a "history too short" gap rather than guess.
MIN_RETURN_OBSERVATIONS = 20

# 95% confidence for the conditional VaR tail.
VAR_CONFIDENCE = 0.95

# Future-looking markers banned from the claim. The RE1 redline already blocks
# advice/forecast prose; this is the extra RE2 past-tense guard so a template change
# cannot quietly introduce forward-looking phrasing.
_FUTURE_CLAIM_MARKERS: tuple[str, ...] = (
    "will ",
    "expected",
    "likely",
    "is high",
    "are high",
    "going to",
    "should ",
    "projected",
)


class InvalidResearchSymbolError(ValueError):
    """Raised when ``subject`` is not a valid normalized ticker/fund symbol."""


def normalize_research_symbol(subject: str) -> str:
    """Normalize and validate ``subject`` into an uppercase ticker/fund symbol.

    Wraps ``restricted_symbols.normalize_symbol`` (OKX/USDT semantics underneath) with
    a closed character-set/length check. Raises :class:`InvalidResearchSymbolError` for
    anything that is not a plausible symbol so the caller can short-circuit to a
    ``data_gap`` *without* consulting the market-history source.
    """
    if not isinstance(subject, str) or not subject.strip():
        raise InvalidResearchSymbolError("research subject is empty")
    normalized = normalize_symbol(subject)
    if not _SYMBOL_PATTERN.match(normalized):
        raise InvalidResearchSymbolError(
            f"research subject {subject!r} is not a valid symbol"
        )
    return normalized


@dataclass(frozen=True)
class MarketHistory:
    """A normalized OHLCV window plus provider status for replay.

    ``ohlcv`` columns follow the local contract: ``date/open/high/low/close/volume``.
    The provenance fields flow into the evidence ``lineage`` so a reviewer can replay
    where the numbers came from.
    """

    symbol: str
    ohlcv: pd.DataFrame
    source: str
    as_of: str
    package_versions: dict[str, str | None] = field(default_factory=dict)
    reconciliation: dict[str, Any] = field(default_factory=dict)
    source_refs: tuple[str, ...] = ()


@runtime_checkable
class MarketHistorySource(Protocol):
    """Injection seam for historical OHLCV.

    Implementations may hit the network (default adapter) or be pure (test fixture).
    ``history`` should raise on any failure (unreachable, unknown symbol, empty);
    the provider converts the failure into a disclosed ``data_gap``.
    """

    def history(self, symbol: str, *, lookback_days: int) -> MarketHistory: ...


@dataclass(frozen=True)
class FixtureMarketHistorySource:
    """Pure, network-free source backed by an in-memory OHLCV table.

    Used by unit tests so coverage never depends on the network. An empty/short frame
    is returned as-is (the provider discloses the resulting gap); an unknown symbol
    raises, exercising the failure path.
    """

    frames: dict[str, pd.DataFrame]
    source_name: str = "fixture"
    as_of: str = "1970-01-01T00:00:00+00:00"
    reconciliation: dict[str, Any] = field(
        default_factory=lambda: {"status": "fixture_unreconciled"}
    )

    def history(self, symbol: str, *, lookback_days: int) -> MarketHistory:
        if symbol not in self.frames:
            raise KeyError(f"no fixture history for {symbol}")
        frame = self.frames[symbol]
        return MarketHistory(
            symbol=symbol,
            ohlcv=frame.copy(),
            source=self.source_name,
            as_of=self.as_of,
            package_versions={"fixture": None},
            reconciliation=dict(self.reconciliation),
            source_refs=(),
        )


@dataclass(frozen=True)
class MarketDataHistorySource:
    """Default best-effort source: a thin adapter over ``market_data``.

    Best-effort by design — it may hit the network/cache via OpenBB and is therefore
    **not** unit-tested (tests inject :class:`FixtureMarketHistorySource`). Kept
    deliberately thin so the network surface stays in ``market_data``, not RE2. Raises
    on any failure, which the provider converts into a disclosed ``data_gap``.
    """

    provider: str = "yfinance"

    def history(self, symbol: str, *, lookback_days: int) -> MarketHistory:
        from finharness import market_data

        end = datetime.now(UTC)
        start = end - timedelta(days=lookback_days)
        raw = market_data._fetch_openbb_history(
            symbol,
            start.date().isoformat(),
            end.date().isoformat(),
            provider=self.provider,
        )
        ohlcv = market_data.normalize_ohlcv(raw)
        return MarketHistory(
            symbol=symbol,
            ohlcv=ohlcv,
            source=f"market_data.openbb:{self.provider}",
            as_of=market_data.now_utc(),
            package_versions={
                "openbb": market_data.package_version("openbb"),
                "finharness": market_data.package_version("finharness"),
            },
            reconciliation=market_data.default_reconciliation(),
            source_refs=(),
        )


def _annualized_volatility(returns: pd.Series) -> float:
    return float(returns.std(ddof=1) * math.sqrt(TRADING_DAYS_PER_YEAR))


def _max_drawdown(close: pd.Series) -> float:
    wealth = close / close.iloc[0]
    drawdown = wealth / wealth.cummax() - 1.0
    return float(drawdown.min())


def _conditional_var(returns: pd.Series) -> float:
    threshold = returns.quantile(1.0 - VAR_CONFIDENCE)
    tail = returns[returns <= threshold]
    if tail.empty:
        return float(threshold)
    return float(tail.mean())


def build_risk_profile_claim(
    symbol: str,
    window: ResearchTimeWindow,
    value: dict[str, float],
) -> str:
    """Build the fixed past-tense claim and assert it carries no future-looking prose.

    Defense in depth on top of the RE1 redline: a future-tense template edit trips this
    guard before the claim is ever handed to :class:`ResearchEvidence`.
    """
    label = TIME_WINDOW_LABELS[window]
    claim = (
        f"Over {label}, {symbol}'s observed realized volatility was "
        f"{value['realized_volatility']:.1%}, maximum drawdown was "
        f"{value['max_drawdown']:.1%}, 95% conditional VaR (daily) was "
        f"{value['conditional_var']:.2%}, and average daily volume was "
        f"{value['average_volume']:,.0f}."
    )
    lowered = claim.lower()
    hit = [marker for marker in _FUTURE_CLAIM_MARKERS if marker in lowered]
    if hit:
        raise ValueError(
            f"historical claim must be past-tense/descriptive; future markers: {hit}"
        )
    return claim


@dataclass(frozen=True)
class HistoricalRiskProfileProvider:
    """RE2 provider: historical descriptive risk profile for a concentrated symbol.

    Honors the RE1 redlines and the four RE2 lock-ins (input guard, closed window,
    single aggregate item, past-tense claim). Failures are disclosed as ``data_gaps``;
    the source is never consulted for an invalid symbol.
    """

    source: MarketHistorySource

    def provide(self, request: ResearchEvidenceRequest) -> ResearchEvidenceResult:
        # 0. Scope guard: RE2 only answers for its own detector. Anything else is
        # disclosed as a gap and the source is never consulted.
        if request.detector_kind != SUPPORTED_DETECTOR_KIND:
            return ResearchEvidenceResult(
                data_gaps=(
                    f"detector {request.detector_kind!r} is not supported by the "
                    f"historical risk-profile provider; no market history requested.",
                ),
            )

        # 1. Input guard runs BEFORE the source so a bad symbol never reaches the network.
        try:
            symbol = normalize_research_symbol(request.subject)
        except InvalidResearchSymbolError as exc:
            return ResearchEvidenceResult(
                data_gaps=(f"{exc}; no market history requested.",),
            )

        window: ResearchTimeWindow = request.time_window
        lookback_days = TIME_WINDOW_LOOKBACK_DAYS[window]

        # 2. Fetch history; any source failure becomes a disclosed gap, never a crash.
        # The source contract is "raise on any failure", so a broad catch is correct
        # here: every failure mode collapses to one disclosed data gap.
        try:
            history = self.source.history(symbol, lookback_days=lookback_days)
        except Exception as exc:
            return ResearchEvidenceResult(
                data_gaps=(
                    f"market history unavailable for {symbol}: "
                    f"{type(exc).__name__}.",
                ),
            )

        # 3. Compute descriptive returns; reuse the shared returns builder.
        ohlcv = history.ohlcv
        if ohlcv is None or ohlcv.empty:
            return ResearchEvidenceResult(
                data_gaps=(f"market history for {symbol} contained no rows.",),
            )
        missing = [col for col in REQUIRED_OHLCV_COLUMNS if col not in ohlcv.columns]
        if missing:
            return ResearchEvidenceResult(
                data_gaps=(
                    f"market history for {symbol} is missing columns {missing}.",
                ),
            )
        try:
            returns = returns_from_close_prices(ohlcv[["close"]])["close"]
        except ValueError as exc:
            return ResearchEvidenceResult(
                data_gaps=(
                    f"market history for {symbol} is not usable for statistics: "
                    f"{exc}.",
                ),
            )
        if len(returns) < MIN_RETURN_OBSERVATIONS:
            return ResearchEvidenceResult(
                data_gaps=(
                    f"market history for {symbol} too short over {window} to compute "
                    f"window statistics ({len(returns)} observations).",
                ),
            )

        # 4. Aggregate descriptive window statistics — exactly the four whitelisted keys.
        close = pd.to_numeric(ohlcv["close"], errors="coerce").astype(float)
        volume = pd.to_numeric(ohlcv["volume"], errors="coerce").astype(float)
        value: dict[str, float] = {
            "realized_volatility": _annualized_volatility(returns),
            "max_drawdown": _max_drawdown(close),
            "conditional_var": _conditional_var(returns),
            "average_volume": float(volume.mean()),
        }

        # Never emit an invented/unusable number: a non-finite statistic (e.g. NaN from
        # non-numeric volume, inf from a degenerate window) is disclosed as a gap, not
        # rendered into a claim.
        non_finite = sorted(k for k, v in value.items() if not math.isfinite(v))
        if non_finite:
            return ResearchEvidenceResult(
                data_gaps=(
                    f"market history for {symbol} yielded non-finite statistics "
                    f"{non_finite}; cannot describe risk profile.",
                ),
            )

        claim = build_risk_profile_claim(symbol, window, value)

        # 5. Provider status into lineage so the evidence is replayable.
        lineage: dict[str, Any] = {
            "provider": "HistoricalRiskProfileProvider",
            "source": history.source,
            "as_of": history.as_of,
            "package_versions": dict(history.package_versions),
            "reconciliation": dict(history.reconciliation),
            "observation_count": len(returns),
            "lookback_days": lookback_days,
        }

        evidence = ResearchEvidence(
            kind="historical_risk_profile",
            claim=claim,
            evidence_grade="historical_market_data",
            value=value,
            time_window=window,
            source_refs=history.source_refs,
            lineage=lineage,
            limitations=(
                "Single-window descriptive statistics, not a forecast.",
                "Market-data reconciliation may be single-source; verify source_refs.",
            ),
            non_claims=REQUIRED_NON_CLAIMS["historical_market_data"],
        )
        return ResearchEvidenceResult(items=(evidence,))
