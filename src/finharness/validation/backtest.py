"""Backtest evidence mapping for validation."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import pandas as pd

from finharness.hypotheses import HypothesisRecord, HypothesisSnapshot
from finharness.validation._constants import BACKTEST_LIMITATIONS, ValidationResult
from finharness.validation._util import now_utc
from finharness.validation.models import (
    BacktestEvidence,
    BacktestEvidenceProvider,
    ValidationCheckResult,
    ValidationJob,
)
from finharness.vectorbt_runner import (
    VECTORBT_BACKEND,
    VectorbtOosResearchSummary,
    VectorbtWalkForwardResearchSummary,
)


def backtest_input_refs(snapshot: HypothesisSnapshot) -> list[str]:
    return [
        *snapshot.lineage.market_snapshot_refs,
        *snapshot.lineage.indicator_snapshot_refs,
    ]


def backtest_metrics(
    *,
    fast: int | None,
    slow: int | None,
    initial_cash: float | None,
    fees: float | None,
    slippage: float | None,
    start_value: float | None,
    end_value: float | None,
    total_return: float | None,
    trade_count: int,
    provider: str,
    reason: str | None = None,
    strategy: str | None = None,
    rung: str | None = None,
    trial_count: int | None = None,
    return_sample_count: int | None = None,
    observed_sharpe: float | None = None,
    return_skew: float | None = None,
    return_kurtosis: float | None = None,
    psr_gt_zero: float | None = None,
    oos: dict[str, Any] | None = None,
    walk_forward: dict[str, Any] | None = None,
    discount: dict[str, Any] | None = None,
    selected_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    metrics: dict[str, Any] = {
        "fast": fast,
        "slow": slow,
        "initial_cash": initial_cash,
        "fees": fees,
        "slippage": slippage,
        "start_value": start_value,
        "end_value": end_value,
        "total_return": total_return,
        "trade_count": trade_count,
        "provider": provider,
    }
    metrics.update(
        {
            key: value
            for key, value in {
                "trial_count": trial_count,
                "return_sample_count": return_sample_count,
                "observed_sharpe": observed_sharpe,
                "return_skew": return_skew,
                "return_kurtosis": return_kurtosis,
                "psr_gt_zero": psr_gt_zero,
            }.items()
            if value is not None
        }
    )
    metrics.update(
        {
            key: value
            for key, value in {
                "reason": reason,
                "strategy": strategy,
                "rung": rung,
                "oos": oos,
                "walk_forward": walk_forward,
                "discount": discount,
                "selected_config": selected_config,
            }.items()
            if value
        }
    )
    return metrics


def oos_metrics(summary: VectorbtOosResearchSummary) -> dict[str, Any]:
    return {
        "train_return": summary.train_return,
        "test_return": summary.test_return,
        "test_trade_count": summary.test_trade_count,
        "test_consistent": summary.test_consistent,
        "test_return_sample_count": summary.test_return_sample_count,
        "test_observed_sharpe": summary.test_observed_sharpe,
        "test_return_skew": summary.test_return_skew,
        "test_return_kurtosis": summary.test_return_kurtosis,
        "test_psr_gt_zero": summary.test_psr_gt_zero,
        "train_rows": summary.train_rows,
        "test_rows": summary.test_rows,
    }


def walk_forward_metrics(summary: VectorbtWalkForwardResearchSummary) -> dict[str, Any]:
    return {
        "fold_count": summary.fold_count,
        "frac_folds_positive": summary.frac_folds_positive,
        "mean_test_return": summary.mean_test_return,
        "mean_test_sharpe": summary.mean_test_sharpe,
        "folds": [
            {
                "fold_index": fold.fold_index,
                "train_rows": fold.train_rows,
                "test_rows": fold.test_rows,
                "test_return": fold.test_return,
                "test_trade_count": fold.test_trade_count,
                "test_observed_sharpe": fold.test_observed_sharpe,
                "test_psr_gt_zero": fold.test_psr_gt_zero,
            }
            for fold in summary.folds
        ],
    }


def backtest_window(history: Any) -> str:
    if isinstance(history, pd.DataFrame) and not history.empty and "date" in history.columns:
        dates = pd.to_datetime(history["date"], errors="coerce", utc=True).dropna()
        if not dates.empty:
            return f"{dates.min().date().isoformat()} to {dates.max().date().isoformat()}"
    try:
        return f"{len(history)} rows"
    except TypeError:
        return "unknown_window"


def _nan_if_none(value: float | None) -> float:
    return float("nan") if value is None else float(value)


# A "supported" verdict needs enough trades to be more than luck. Below this the
# result is too thin to support a hypothesis — it is capped at "inconclusive"
# (insufficient evidence), never "supported". A 1-trade backtest is not support.
MIN_SUPPORTED_TRADES = 5


def map_in_sample_backtest_result(total_return: float | None) -> ValidationResult:
    if total_return is not None and total_return <= -0.02:
        return "weakened"
    return "inconclusive"


def map_oos_backtest_result(
    *,
    trade_count: int,
    oos_test_return: float | None,
    oos_test_consistent: bool,
    oos_test_trade_count: int | None,
) -> ValidationResult:
    if oos_test_trade_count is not None and oos_test_trade_count <= 0:
        return "not_testable"
    if oos_test_return is not None and oos_test_return <= -0.02:
        return "weakened"
    if (
        oos_test_return is not None
        and oos_test_return >= 0.02
        and oos_test_consistent
        and trade_count >= MIN_SUPPORTED_TRADES
    ):
        return "supported"
    return "inconclusive"


def map_walk_forward_backtest_result(
    *,
    trade_count: int,
    walk_forward_frac_folds_positive: float | None,
    walk_forward_mean_test_return: float | None,
) -> ValidationResult:
    if (
        walk_forward_frac_folds_positive is not None
        and walk_forward_mean_test_return is not None
        and walk_forward_frac_folds_positive >= 0.6
        and walk_forward_mean_test_return >= 0.0
        and trade_count >= MIN_SUPPORTED_TRADES
    ):
        return "supported"
    if walk_forward_frac_folds_positive is not None and walk_forward_frac_folds_positive <= 0.4:
        return "weakened"
    return "inconclusive"


def map_trial_discounted_backtest_result(
    *,
    trade_count: int,
    oos_test_return: float | None,
    trial_psr_gt_zero: float | None,
    trial_discount_method: str | None,
) -> ValidationResult:
    if oos_test_return is not None and oos_test_return <= -0.02:
        return "weakened"
    if (
        trial_discount_method == "deflated_sharpe"
        and trial_psr_gt_zero is not None
        and trial_psr_gt_zero >= 0.95
        and trade_count >= MIN_SUPPORTED_TRADES
    ):
        return "supported"
    return "inconclusive"


def map_backtest_result(
    *,
    rung: str,
    trade_count: int,
    total_return: float | None = None,
    oos_test_return: float | None = None,
    oos_test_consistent: bool = False,
    oos_test_trade_count: int | None = None,
    walk_forward_frac_folds_positive: float | None = None,
    walk_forward_mean_test_return: float | None = None,
    trial_psr_gt_zero: float | None = None,
    trial_discount_method: str | None = None,
) -> ValidationResult:
    if trade_count == 0:
        return "not_testable"
    if rung == "in_sample":
        return map_in_sample_backtest_result(total_return)
    if rung == "out_of_sample":
        return map_oos_backtest_result(
            trade_count=trade_count,
            oos_test_return=oos_test_return,
            oos_test_consistent=oos_test_consistent,
            oos_test_trade_count=oos_test_trade_count,
        )
    if rung == "walk_forward":
        return map_walk_forward_backtest_result(
            trade_count=trade_count,
            walk_forward_frac_folds_positive=walk_forward_frac_folds_positive,
            walk_forward_mean_test_return=walk_forward_mean_test_return,
        )
    if rung == "trial_discounted":
        return map_trial_discounted_backtest_result(
            trade_count=trade_count,
            oos_test_return=oos_test_return,
            trial_psr_gt_zero=trial_psr_gt_zero,
            trial_discount_method=trial_discount_method,
        )
    return "inconclusive"


def backtest_result_respects_rung(result: ValidationCheckResult) -> bool:
    if result.check_type != "backtest" or result.result != "supported":
        return True

    metrics = result.metrics
    rung = metrics.get("rung")
    if rung == "in_sample":
        return False
    if rung == "out_of_sample":
        oos = metrics.get("oos") or {}
        return (
            (oos.get("test_trade_count") or 0) > 0
            and (oos.get("test_return") or 0.0) >= 0.02
            and bool(oos.get("test_consistent"))
        )
    if rung == "walk_forward":
        walk_forward = metrics.get("walk_forward") or {}
        return (
            (metrics.get("trade_count") or 0) > 0
            and (walk_forward.get("frac_folds_positive") or 0.0) >= 0.6
            and (walk_forward.get("mean_test_return") or 0.0) >= 0.0
        )
    if rung == "trial_discounted":
        discount = metrics.get("discount") or {}
        return (
            discount.get("method") == "deflated_sharpe"
            and bool(discount.get("selection_bias_adjusted"))
            and (discount.get("psr_gt_zero") or 0.0) >= 0.95
        )
    return False


def backtest_evidence_result(
    *,
    job: ValidationJob,
    hypothesis: HypothesisRecord,
    snapshot: HypothesisSnapshot,
    provider: BacktestEvidenceProvider,
) -> ValidationCheckResult:
    try:
        evidence = provider.assess(job=job, hypothesis=hypothesis, snapshot=snapshot)
    except Exception as exc:  # provider failures become not-testable evidence.
        evidence = BacktestEvidence(
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
                provider=getattr(provider, "provider_name", "unknown"),
                reason=str(exc),
                rung="provider_error",
                trial_count=0,
            ),
            result="not_testable",
            supports_hypothesis=False,
            disconfirms_hypothesis=False,
            limitations=[*BACKTEST_LIMITATIONS, str(exc)],
        )

    return ValidationCheckResult(
        check_id=f"valchk_{uuid4().hex[:12]}",
        validation_job_id=job.validation_job_id,
        hypothesis_id=hypothesis.hypothesis_id,
        check_type="backtest",
        input_refs=backtest_input_refs(snapshot),
        method=evidence.method,
        window=evidence.window,
        metrics=evidence.metrics,
        result=evidence.result,
        supports_hypothesis=evidence.supports_hypothesis,
        disconfirms_hypothesis=evidence.disconfirms_hypothesis,
        confidence="low",
        limitations=evidence.limitations,
        created_at_utc=now_utc(),
    )
