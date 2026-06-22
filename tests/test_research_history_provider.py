from __future__ import annotations

import ast
import unittest
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd
from pydantic import ValidationError

from finharness.research_evidence import (
    REQUIRED_NON_CLAIMS,
    ResearchEvidence,
    ResearchEvidenceRequest,
    ResearchTimeWindow,
)
from finharness.research_history_provider import (
    MIN_RETURN_OBSERVATIONS,
    RISK_PROFILE_VALUE_KEYS,
    TIME_WINDOW_LOOKBACK_DAYS,
    FixtureMarketHistorySource,
    HistoricalRiskProfileProvider,
    InvalidResearchSymbolError,
    MarketHistory,
    build_risk_profile_claim,
    normalize_research_symbol,
)

_MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "finharness"
    / "research_history_provider.py"
)


def _ohlcv(rows: int, *, start: float = 100.0, step: float = 0.5) -> pd.DataFrame:
    dates = pd.date_range("2023-01-01", periods=rows, freq="D", tz="UTC")
    # Deterministic, strictly positive, mildly oscillating closes.
    close = [start + step * i + (2.0 if i % 3 == 0 else -1.0) for i in range(rows)]
    return pd.DataFrame(
        {
            "date": dates,
            "open": close,
            "high": [c + 1.0 for c in close],
            "low": [c - 1.0 for c in close],
            "close": close,
            "volume": [1_000_000 + 1_000 * i for i in range(rows)],
        }
    )


def _request(
    subject: str = "SPY", window: ResearchTimeWindow = "trailing_3y"
) -> ResearchEvidenceRequest:
    return ResearchEvidenceRequest(
        detector_kind="concentration_high",
        subject=subject,
        question="historical_risk_profile",
        time_window=window,
    )


@dataclass
class _SpySource:
    """Records whether the source was consulted; never touches the network."""

    inner: FixtureMarketHistorySource
    calls: list[tuple[str, int]] = field(default_factory=list)

    def history(self, symbol: str, *, lookback_days: int) -> MarketHistory:
        self.calls.append((symbol, lookback_days))
        return self.inner.history(symbol, lookback_days=lookback_days)


class HistoricalRiskProfileProviderTest(unittest.TestCase):
    def _provider(self, frames: dict[str, pd.DataFrame]) -> HistoricalRiskProfileProvider:
        return HistoricalRiskProfileProvider(source=FixtureMarketHistorySource(frames=frames))

    # --- happy path / output shape ---------------------------------------------------
    def test_single_aggregate_item_with_whitelisted_value_keys(self) -> None:
        provider = self._provider({"SPY": _ohlcv(120)})
        result = provider.provide(_request())
        self.assertEqual(len(result.items), 1)
        item = result.items[0]
        self.assertEqual(item.kind, "historical_risk_profile")
        self.assertEqual(set(item.value), set(RISK_PROFILE_VALUE_KEYS))
        self.assertEqual(item.evidence_grade, "historical_market_data")
        for claim in REQUIRED_NON_CLAIMS["historical_market_data"]:
            self.assertIn(claim, item.non_claims)
        self.assertFalse(result.data_gaps)
        self.assertFalse(result.execution_allowed)

    def test_lineage_carries_provider_status_for_replay(self) -> None:
        provider = self._provider({"SPY": _ohlcv(120)})
        item = provider.provide(_request()).items[0]
        self.assertEqual(item.lineage["provider"], "HistoricalRiskProfileProvider")
        self.assertEqual(item.lineage["source"], "fixture")
        self.assertIn("as_of", item.lineage)
        self.assertIn("reconciliation", item.lineage)
        self.assertEqual(item.lineage["lookback_days"], TIME_WINDOW_LOOKBACK_DAYS["trailing_3y"])

    def test_claim_is_past_tense_descriptive(self) -> None:
        provider = self._provider({"SPY": _ohlcv(120)})
        claim = provider.provide(_request()).items[0].claim
        self.assertIn("observed", claim)
        self.assertIn("was", claim)
        for marker in ("will ", "expected", "likely", "is high"):
            self.assertNotIn(marker, claim.lower())

    # --- input guard: bad symbol never reaches the source ----------------------------
    def test_invalid_symbol_short_circuits_without_calling_source(self) -> None:
        spy = _SpySource(inner=FixtureMarketHistorySource(frames={"SPY": _ohlcv(120)}))
        provider = HistoricalRiskProfileProvider(source=spy)
        result = provider.provide(_request(subject="not a symbol!!"))
        self.assertEqual(result.items, ())
        self.assertTrue(result.data_gaps)
        self.assertEqual(spy.calls, [])  # source must never be consulted

    def test_normalize_research_symbol_rejects_garbage(self) -> None:
        for bad in ("", "   ", "a/b", "toolongsymbolxxxxx", "buy now"):
            with self.assertRaises(InvalidResearchSymbolError):
                normalize_research_symbol(bad)
        self.assertEqual(normalize_research_symbol("spy"), "SPY")

    # --- scope guard: only the supported detector is answered ------------------------
    def test_unsupported_detector_returns_gap_without_calling_source(self) -> None:
        spy = _SpySource(inner=FixtureMarketHistorySource(frames={"SPY": _ohlcv(120)}))
        provider = HistoricalRiskProfileProvider(source=spy)
        result = provider.provide(
            ResearchEvidenceRequest(
                detector_kind="cash_buffer_low",
                subject="SPY",
                question="historical_risk_profile",
                time_window="trailing_3y",
            )
        )
        self.assertEqual(result.items, ())
        self.assertTrue(result.data_gaps)
        self.assertEqual(spy.calls, [])  # off-scope detector must not reach the source

    # --- data gaps: missing / short / failing history --------------------------------
    def test_unknown_symbol_in_source_becomes_data_gap(self) -> None:
        provider = self._provider({"SPY": _ohlcv(120)})
        result = provider.provide(_request(subject="QQQ"))
        self.assertEqual(result.items, ())
        self.assertTrue(result.data_gaps)

    def test_short_history_becomes_data_gap_not_crash(self) -> None:
        provider = self._provider({"SPY": _ohlcv(MIN_RETURN_OBSERVATIONS - 5)})
        result = provider.provide(_request())
        self.assertEqual(result.items, ())
        self.assertTrue(any("too short" in gap for gap in result.data_gaps))

    def test_empty_history_becomes_data_gap(self) -> None:
        provider = self._provider({"SPY": _ohlcv(0)})
        result = provider.provide(_request())
        self.assertEqual(result.items, ())
        self.assertTrue(result.data_gaps)

    def test_missing_volume_column_becomes_data_gap_not_crash(self) -> None:
        frame = _ohlcv(120).drop(columns=["volume"])
        provider = self._provider({"SPY": frame})
        result = provider.provide(_request())
        self.assertEqual(result.items, ())
        self.assertTrue(any("missing columns" in gap for gap in result.data_gaps))

    def test_non_numeric_volume_becomes_data_gap_not_nan_claim(self) -> None:
        frame = _ohlcv(120)
        frame["volume"] = "n/a"
        provider = self._provider({"SPY": frame})
        result = provider.provide(_request())
        self.assertEqual(result.items, ())
        self.assertTrue(any("non-finite" in gap for gap in result.data_gaps))

    # --- closed time window ----------------------------------------------------------
    def test_time_window_is_closed_literal(self) -> None:
        for bad_window in ("trailing_5y", "next_quarter"):
            with self.assertRaises(ValidationError):
                ResearchEvidenceRequest(
                    detector_kind="concentration_high",
                    subject="SPY",
                    question="historical_risk_profile",
                    time_window=bad_window,
                )

    # --- claim template guard --------------------------------------------------------
    def test_build_claim_rejects_future_markers(self) -> None:
        # A value that would render a forward-looking number is irrelevant; the guard
        # is on phrasing. Directly assert the past-tense template guard fires if the
        # markers ever appear by monkeypatching the label.
        import finharness.research_history_provider as mod

        original = dict(mod.TIME_WINDOW_LABELS)
        mod.TIME_WINDOW_LABELS["trailing_1y"] = "the period; price is high and likely to"
        try:
            with self.assertRaises(ValueError):
                build_risk_profile_claim(
                    "SPY",
                    "trailing_1y",
                    {
                        "realized_volatility": 0.1,
                        "max_drawdown": -0.2,
                        "conditional_var": -0.03,
                        "average_volume": 1_000_000.0,
                    },
                )
        finally:
            mod.TIME_WINDOW_LABELS.clear()
            mod.TIME_WINDOW_LABELS.update(original)

    # --- redline probes (gate): no optimizer / proposal / endpoint -------------------
    def test_module_references_no_optimizer_or_proposal_surface_identifiers(self) -> None:
        # AST identifier scan (not a raw grep): docstrings/comments that *describe* the
        # boundary must not trip the probe; only real code identifiers count.
        tree = ast.parse(_MODULE_PATH.read_text(encoding="utf-8"))
        identifiers: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Name):
                identifiers.add(node.id)
            elif isinstance(node, ast.Attribute):
                identifiers.add(node.attr)
            elif isinstance(node, (ast.ImportFrom, ast.Import)):
                identifiers.update(alias.name for alias in node.names)
        for banned in ("optimize_riskfolio_allocation", "Proposal", "APIRouter", "FastAPI"):
            self.assertNotIn(banned, identifiers, f"RE2 must not reference {banned}")

    # --- provided item still satisfies the RE1 contract ------------------------------
    def test_emitted_item_is_a_valid_research_evidence(self) -> None:
        provider = self._provider({"SPY": _ohlcv(120)})
        item = provider.provide(_request()).items[0]
        self.assertIsInstance(item, ResearchEvidence)
        # Re-validate by round-tripping through the model.
        ResearchEvidence(**item.model_dump())


if __name__ == "__main__":
    unittest.main()
