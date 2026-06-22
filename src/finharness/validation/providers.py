"""Validation draft and backtest evidence providers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from finharness.hypotheses import HypothesisRecord, HypothesisSnapshot
from finharness.research_rigor import (
    ResearchRung,
    deflated_sharpe_ratio,
    sharpe_variance,
    time_train_test_split,
)
from finharness.validation._constants import BACKTEST_LIMITATIONS, ValidationResult
from finharness.validation.backtest import (
    _nan_if_none,
    backtest_metrics,
    backtest_window,
    map_backtest_result,
    oos_metrics,
    walk_forward_metrics,
)
from finharness.validation.models import (
    BacktestEvidence,
    ValidationJob,
)
from finharness.vectorbt_runner import (
    VECTORBT_BACKEND,
    run_vectorbt_ma_oos,
    run_vectorbt_ma_walk_forward,
    run_vectorbt_moving_average_research,
)


class NullValidationDraftProvider:
    """Default provider: deterministic validation, no LLM call."""

    provider_name = "none"

    def assess(self, hypothesis: HypothesisRecord) -> dict[str, Any]:
        return {}


class HermesValidationDraftProvider:
    """Reserved adapter boundary for /root/projects/hermes-agent."""

    provider_name = "hermes-agent"

    def __init__(self, *, hermes_root: str | Path = "/root/projects/hermes-agent") -> None:
        self.hermes_root = Path(hermes_root)

    def assess(self, hypothesis: HypothesisRecord) -> dict[str, Any]:
        return {
            "provider": self.provider_name,
            "enabled": False,
            "hermes_root": str(self.hermes_root),
            "note": "LLM validation interface reserved; deterministic checks used in MVP.",
            "hypothesis_id": hypothesis.hypothesis_id,
        }

class NullBacktestEvidenceProvider:
    """Default provider: no backtest is run in deterministic offline validation."""

    provider_name = "none"

    def assess(
        self,
        *,
        job: ValidationJob,
        hypothesis: HypothesisRecord,
        snapshot: HypothesisSnapshot,
    ) -> BacktestEvidence:
        return BacktestEvidence(
            method=VECTORBT_BACKEND,
            window="not_available",
            metrics=backtest_metrics(
                fast=None,
                slow=None,
                initial_cash=None,
                fees=None,
                slippage=None,
                start_value=None,
                end_value=None,
                total_return=None,
                trade_count=0,
                provider=self.provider_name,
                reason="no backtest provider configured",
                rung="not_run",
                trial_count=0,
            ),
            result="not_testable",
            supports_hypothesis=False,
            disconfirms_hypothesis=False,
            limitations=[
                *BACKTEST_LIMITATIONS,
                "No backtest provider was configured for this validation run.",
            ],
        )


class VectorbtBacktestEvidenceProvider:
    """vectorbt-backed validation evidence adapter.

    The provider owns only research evidence shaping. It does not create
    proposals, orders, position sizing, or execution permission.
    """

    provider_name = "vectorbt"

    def __init__(
        self,
        *,
        history_by_symbol: dict[str, Any],
        fast: int = 20,
        slow: int = 50,
        initial_cash: float = 10_000.0,
        fees: float = 0.0,
        slippage: float = 0.0,
        rung: ResearchRung = "out_of_sample",
        train_frac: float = 0.7,
        n_folds: int = 4,
        configs: list[dict[str, Any]] | None = None,
    ) -> None:
        self.history_by_symbol = {
            symbol.upper(): history for symbol, history in history_by_symbol.items()
        }
        self.fast = fast
        self.slow = slow
        self.initial_cash = initial_cash
        self.fees = fees
        self.slippage = slippage
        self.rung = rung
        self.train_frac = train_frac
        self.n_folds = n_folds
        self.configs = configs or []

    def assess(
        self,
        *,
        job: ValidationJob,
        hypothesis: HypothesisRecord,
        snapshot: HypothesisSnapshot,
    ) -> BacktestEvidence:
        history = self.history_by_symbol.get(hypothesis.symbol.upper())
        if history is None:
            return self._not_testable(
                window="not_available",
                reason=f"no history configured for {hypothesis.symbol.upper()}",
            )

        window = backtest_window(history)
        effective_rung: ResearchRung = (
            "trial_discounted" if len(self.configs) > 1 else self.rung
        )
        try:
            if effective_rung == "in_sample":
                return self._assess_in_sample(history=history, window=window)
            if effective_rung == "walk_forward":
                return self._assess_walk_forward(history=history, window=window)
            if effective_rung == "trial_discounted":
                return self._assess_trial_recorded_psr(history=history, window=window)
            return self._assess_oos(history=history, window=window)
        except Exception as exc:  # vectorbt screens degrade to evidence, not workflow failure.
            return self._not_testable(window=window, reason=str(exc))

    def _assess_in_sample(self, *, history: Any, window: str) -> BacktestEvidence:
        summary = run_vectorbt_moving_average_research(
            history,
            fast=self.fast,
            slow=self.slow,
            initial_cash=self.initial_cash,
            fees=self.fees,
            slippage=self.slippage,
        )
        metrics = backtest_metrics(
            fast=self.fast,
            slow=self.slow,
            initial_cash=self.initial_cash,
            fees=self.fees,
            slippage=self.slippage,
            start_value=summary.start_value,
            end_value=summary.end_value,
            total_return=summary.total_return,
            trade_count=summary.trade_count,
            provider=self.provider_name,
            strategy=summary.strategy,
            rung="in_sample",
            trial_count=1,
            return_sample_count=summary.return_sample_count,
            observed_sharpe=summary.observed_sharpe,
            return_skew=summary.return_skew,
            return_kurtosis=summary.return_kurtosis,
            psr_gt_zero=summary.psr_gt_zero,
        )
        result = map_backtest_result(
            rung="in_sample",
            trade_count=summary.trade_count,
            total_return=summary.total_return,
        )
        return self._evidence(
            window=window,
            metrics=metrics,
            result=result,
            limitations=[
                *BACKTEST_LIMITATIONS,
                "Research rung: in_sample. Single in-sample evidence is capped at "
                "inconclusive and cannot support a hypothesis.",
            ],
        )

    def _assess_oos(self, *, history: Any, window: str) -> BacktestEvidence:
        summary = run_vectorbt_ma_oos(
            history,
            fast=self.fast,
            slow=self.slow,
            train_frac=self.train_frac,
            initial_cash=self.initial_cash,
            fees=self.fees,
            slippage=self.slippage,
        )
        metrics = backtest_metrics(
            fast=self.fast,
            slow=self.slow,
            initial_cash=self.initial_cash,
            fees=self.fees,
            slippage=self.slippage,
            start_value=None,
            end_value=None,
            total_return=summary.test_return,
            trade_count=summary.test_trade_count,
            provider=self.provider_name,
            strategy=summary.strategy,
            rung="out_of_sample",
            trial_count=1,
            oos=oos_metrics(summary),
        )
        result = map_backtest_result(
            rung="out_of_sample",
            trade_count=summary.test_trade_count,
            oos_test_return=summary.test_return,
            oos_test_consistent=summary.test_consistent,
            oos_test_trade_count=summary.test_trade_count,
        )
        return self._evidence(
            window=window,
            metrics=metrics,
            result=result,
            limitations=[
                *BACKTEST_LIMITATIONS,
                "Research rung: out_of_sample. Support requires the held-out test "
                "segment to clear the bar; no multiple-testing correction.",
            ],
        )

    def _assess_walk_forward(self, *, history: Any, window: str) -> BacktestEvidence:
        summary = run_vectorbt_ma_walk_forward(
            history,
            fast=self.fast,
            slow=self.slow,
            n_folds=self.n_folds,
            initial_cash=self.initial_cash,
            fees=self.fees,
            slippage=self.slippage,
        )
        trade_count = sum(fold.test_trade_count for fold in summary.folds)
        metrics = backtest_metrics(
            fast=self.fast,
            slow=self.slow,
            initial_cash=self.initial_cash,
            fees=self.fees,
            slippage=self.slippage,
            start_value=None,
            end_value=None,
            total_return=summary.mean_test_return,
            trade_count=trade_count,
            provider=self.provider_name,
            strategy=summary.strategy,
            rung="walk_forward",
            trial_count=1,
            walk_forward=walk_forward_metrics(summary),
        )
        result = map_backtest_result(
            rung="walk_forward",
            trade_count=trade_count,
            walk_forward_frac_folds_positive=summary.frac_folds_positive,
            walk_forward_mean_test_return=summary.mean_test_return,
        )
        return self._evidence(
            window=window,
            metrics=metrics,
            result=result,
            limitations=[
                *BACKTEST_LIMITATIONS,
                "Research rung: walk_forward. Support requires forward test-fold "
                "consistency; no multiple-testing correction.",
            ],
        )

    def _assess_trial_recorded_psr(self, *, history: Any, window: str) -> BacktestEvidence:
        selected, train_sharpes = self._select_config_on_train(history)
        fast = selected["fast"]
        slow = selected["slow"]
        summary = run_vectorbt_ma_oos(
            history,
            fast=fast,
            slow=slow,
            train_frac=self.train_frac,
            initial_cash=self.initial_cash,
            fees=self.fees,
            slippage=self.slippage,
        )
        trial_count = max(1, len(self.configs))
        # Deflate the selected strategy's out-of-sample Sharpe by the expected
        # maximum Sharpe of the trials. PSR-against-zero ignores how many configs
        # were tried; DSR is the selection-bias-adjusted statistic.
        trial_sharpe_var = sharpe_variance(train_sharpes)
        dsr = deflated_sharpe_ratio(
            observed_sharpe=_nan_if_none(summary.test_observed_sharpe),
            n_samples=summary.test_return_sample_count,
            skew=_nan_if_none(summary.test_return_skew),
            kurtosis=_nan_if_none(summary.test_return_kurtosis),
            trial_sharpe_variance=trial_sharpe_var,
            n_trials=trial_count,
        )
        metrics = backtest_metrics(
            fast=fast,
            slow=slow,
            initial_cash=self.initial_cash,
            fees=self.fees,
            slippage=self.slippage,
            start_value=None,
            end_value=None,
            total_return=summary.test_return,
            trade_count=summary.test_trade_count,
            provider=self.provider_name,
            strategy=summary.strategy,
            rung="trial_discounted",
            trial_count=trial_count,
            oos=oos_metrics(summary),
            discount={
                "method": "deflated_sharpe",
                "deflated_sharpe": dsr,
                "psr_gt_zero": summary.test_psr_gt_zero,
                "trial_sharpe_variance": trial_sharpe_var,
                "selection_bias_adjusted": True,
                "note": "Selected OOS Sharpe deflated by the expected max Sharpe of "
                f"{trial_count} trials (Bailey & Lopez de Prado, 2014).",
            },
            selected_config=selected,
        )
        result = map_backtest_result(
            rung="trial_discounted",
            trade_count=summary.test_trade_count,
            oos_test_return=summary.test_return,
            trial_psr_gt_zero=dsr,
            trial_discount_method="deflated_sharpe",
        )
        return self._evidence(
            window=window,
            metrics=metrics,
            result=result,
            limitations=[
                *BACKTEST_LIMITATIONS,
                "Research rung: trial_discounted. The selected multi-config OOS "
                "Sharpe is deflated by the expected maximum Sharpe of the trials "
                "(Deflated Sharpe Ratio); support requires the DSR to clear the bar.",
            ],
        )

    def _select_config_on_train(
        self, history: Any
    ) -> tuple[dict[str, Any], list[float]]:
        """Select the best config on the train segment only and return it with the
        train Sharpe of every config tried (the raw material for DSR deflation)."""
        configs = self.configs or [{"fast": self.fast, "slow": self.slow}]
        max_slow = max(int(config.get("slow", self.slow)) for config in configs)
        train_slice, _ = time_train_test_split(
            len(history),
            train_frac=self.train_frac,
            min_train=max_slow + 1,
            min_test=max_slow + 1,
        )
        train_history = history.iloc[train_slice].copy()
        scored: list[dict[str, Any]] = []
        train_sharpes: list[float] = []
        for config in configs:
            fast = int(config.get("fast", self.fast))
            slow = int(config.get("slow", self.slow))
            summary = run_vectorbt_moving_average_research(
                train_history,
                fast=fast,
                slow=slow,
                initial_cash=self.initial_cash,
                fees=self.fees,
                slippage=self.slippage,
            )
            if summary.observed_sharpe is not None:
                train_sharpes.append(summary.observed_sharpe)
            scored.append(
                {
                    "fast": fast,
                    "slow": slow,
                    "train_return": summary.total_return,
                    "train_trade_count": summary.trade_count,
                }
            )
        if not scored:
            raise ValueError("no valid trial configs")
        return max(scored, key=lambda item: item["train_return"]), train_sharpes

    def _evidence(
        self,
        *,
        window: str,
        metrics: dict[str, Any],
        result: ValidationResult,
        limitations: list[str],
    ) -> BacktestEvidence:
        return BacktestEvidence(
            method=VECTORBT_BACKEND,
            window=window,
            metrics=metrics,
            result=result,
            supports_hypothesis=result == "supported",
            disconfirms_hypothesis=result == "weakened",
            limitations=limitations,
        )

    def _not_testable(self, *, window: str, reason: str) -> BacktestEvidence:
        return BacktestEvidence(
            method=VECTORBT_BACKEND,
            window=window,
            metrics=backtest_metrics(
                fast=self.fast,
                slow=self.slow,
                initial_cash=self.initial_cash,
                fees=self.fees,
                slippage=self.slippage,
                start_value=None,
                end_value=None,
                total_return=None,
                trade_count=0,
                provider=self.provider_name,
                reason=reason,
                rung=self.rung,
                trial_count=max(1, len(self.configs)),
            ),
            result="not_testable",
            supports_hypothesis=False,
            disconfirms_hypothesis=False,
            limitations=[*BACKTEST_LIMITATIONS, reason],
        )
