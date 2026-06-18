"""Fifth-layer falsifiable hypothesis governance package.

The package preserves the original ``finharness.hypotheses`` interface while
keeping implementation concerns in smaller modules.
"""

from __future__ import annotations

from finharness.hypotheses._constants import (
    ALLOWED_DRAFT_CHECK_TYPES,
    HERMES_DRAFT_PROMPT_VERSION,
    HERMES_DRAFT_ROOT,
    HYPOTHESIS_NORMALIZED_ROOT,
    HYPOTHESIS_RECEIPT_ROOT,
    RECOMMENDATION_PATTERNS,
    VALIDATED_PATTERNS,
    ConfidencePrior,
    HypothesisStatus,
)
from finharness.hypotheses._util import (
    find_blocked_language,
    normalize_symbol,
    now_utc,
    record_text_for_guard,
    write_json,
)
from finharness.hypotheses.bundle import (
    build_hypothesis_bundle_from_interpretation_snapshot,
    hypothesis_storage_roots,
    persist_hypothesis_bundle,
)
from finharness.hypotheses.formulation import (
    assumptions_for_record,
    build_validation_plan,
    disconfirming_observations,
    expected_observations,
    formulate_hypothesis_record,
    select_hypothesis_candidates,
)
from finharness.hypotheses.models import (
    HypothesisBundle,
    HypothesisLineage,
    HypothesisQuality,
    HypothesisReceipt,
    HypothesisRecord,
    HypothesisSnapshot,
    HypothesisSourceSpec,
    ValidationCheck,
)
from finharness.hypotheses.providers import (
    HermesHypothesisDraftProvider,
    HypothesisDraftProvider,
    NullHypothesisDraftProvider,
    build_hermes_hypothesis_prompt,
    hypothesis_draft_root,
    sanitize_hermes_draft,
)
from finharness.hypotheses.quality import (
    build_hypothesis_quality,
    missing_hypothesis_fields,
    snapshot_review_questions,
    validation_handoff,
)

__all__ = [
    "ALLOWED_DRAFT_CHECK_TYPES",
    "HERMES_DRAFT_PROMPT_VERSION",
    "HERMES_DRAFT_ROOT",
    "HYPOTHESIS_NORMALIZED_ROOT",
    "HYPOTHESIS_RECEIPT_ROOT",
    "RECOMMENDATION_PATTERNS",
    "VALIDATED_PATTERNS",
    "ConfidencePrior",
    "HermesHypothesisDraftProvider",
    "HypothesisBundle",
    "HypothesisDraftProvider",
    "HypothesisLineage",
    "HypothesisQuality",
    "HypothesisReceipt",
    "HypothesisRecord",
    "HypothesisSnapshot",
    "HypothesisSourceSpec",
    "HypothesisStatus",
    "NullHypothesisDraftProvider",
    "ValidationCheck",
    "assumptions_for_record",
    "build_hermes_hypothesis_prompt",
    "build_hypothesis_bundle_from_interpretation_snapshot",
    "build_hypothesis_quality",
    "build_validation_plan",
    "disconfirming_observations",
    "expected_observations",
    "find_blocked_language",
    "formulate_hypothesis_record",
    "hypothesis_draft_root",
    "hypothesis_storage_roots",
    "missing_hypothesis_fields",
    "normalize_symbol",
    "now_utc",
    "persist_hypothesis_bundle",
    "record_text_for_guard",
    "sanitize_hermes_draft",
    "select_hypothesis_candidates",
    "snapshot_review_questions",
    "validation_handoff",
    "write_json",
]
