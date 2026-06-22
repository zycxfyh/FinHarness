"""Sixth-layer validation governance package.

The package preserves the original ``finharness.validation`` interface while
keeping implementation concerns in smaller modules.
"""

from __future__ import annotations

from finharness.validation._constants import (
    BACKTEST_LIMITATIONS,
    BLOCKED_VALIDATION_LANGUAGE,
    VALIDATION_NORMALIZED_ROOT,
    VALIDATION_RECEIPT_ROOT,
    ValidationCheckType,
    ValidationResult,
)
from finharness.validation._util import (
    find_blocked_language,
    now_utc,
    result_text_for_guard,
    write_json,
)
from finharness.validation.backtest import (
    MIN_SUPPORTED_TRADES,
    backtest_evidence_result,
    backtest_input_refs,
    backtest_metrics,
    backtest_result_respects_rung,
    backtest_window,
    map_backtest_result,
    map_in_sample_backtest_result,
    map_oos_backtest_result,
    map_trial_discounted_backtest_result,
    map_walk_forward_backtest_result,
    oos_metrics,
    walk_forward_metrics,
)
from finharness.validation.bundle import (
    build_validation_bundle_from_hypothesis_snapshot,
    build_validation_quality,
    persist_validation_bundle,
    proposal_handoff,
    snapshot_review_questions,
)
from finharness.validation.checks import (
    benchmark_context_result,
    build_validation_results,
    create_validation_jobs,
    disconfirmation_results,
    event_reaction_result,
    limitations_result,
    mechanism_result,
    source_validity_result,
)
from finharness.validation.models import (
    BacktestEvidence,
    BacktestEvidenceProvider,
    ValidationBundle,
    ValidationCheckResult,
    ValidationDraftProvider,
    ValidationJob,
    ValidationLineage,
    ValidationQuality,
    ValidationReceipt,
    ValidationSnapshot,
    ValidationSourceSpec,
)
from finharness.validation.providers import (
    HermesValidationDraftProvider,
    NullBacktestEvidenceProvider,
    NullValidationDraftProvider,
    VectorbtBacktestEvidenceProvider,
)
from finharness.validation_metrics import assess_realized_move, load_cached_close_series

__all__ = [
    "BACKTEST_LIMITATIONS",
    "BLOCKED_VALIDATION_LANGUAGE",
    "MIN_SUPPORTED_TRADES",
    "VALIDATION_NORMALIZED_ROOT",
    "VALIDATION_RECEIPT_ROOT",
    "BacktestEvidence",
    "BacktestEvidenceProvider",
    "HermesValidationDraftProvider",
    "NullBacktestEvidenceProvider",
    "NullValidationDraftProvider",
    "ValidationBundle",
    "ValidationCheckResult",
    "ValidationCheckType",
    "ValidationDraftProvider",
    "ValidationJob",
    "ValidationLineage",
    "ValidationQuality",
    "ValidationReceipt",
    "ValidationResult",
    "ValidationSnapshot",
    "ValidationSourceSpec",
    "VectorbtBacktestEvidenceProvider",
    "assess_realized_move",
    "backtest_evidence_result",
    "backtest_input_refs",
    "backtest_metrics",
    "backtest_result_respects_rung",
    "backtest_window",
    "benchmark_context_result",
    "build_validation_bundle_from_hypothesis_snapshot",
    "build_validation_quality",
    "build_validation_results",
    "create_validation_jobs",
    "disconfirmation_results",
    "event_reaction_result",
    "find_blocked_language",
    "limitations_result",
    "load_cached_close_series",
    "map_backtest_result",
    "map_in_sample_backtest_result",
    "map_oos_backtest_result",
    "map_trial_discounted_backtest_result",
    "map_walk_forward_backtest_result",
    "mechanism_result",
    "now_utc",
    "oos_metrics",
    "persist_validation_bundle",
    "proposal_handoff",
    "result_text_for_guard",
    "snapshot_review_questions",
    "source_validity_result",
    "walk_forward_metrics",
    "write_json",
]
