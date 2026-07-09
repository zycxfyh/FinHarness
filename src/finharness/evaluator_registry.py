"""Evaluator registry v0 — deterministic evaluator discovery.

Agentic-space dimension: Evaluation Space.
Operating surface: Track E — Evaluator / Simulation.

Registry for deterministic evaluators. No LLM evaluators. No plugin system.
First pass: plan_draft_evaluator only.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

NON_CLAIMS: tuple[str, ...] = (
    "Evaluator registry records evaluator metadata, not execution authority.",
    "Not investment advice.",
)


class EvaluatorSpec(BaseModel):
    """Deterministic evaluator registration entry."""

    model_config = ConfigDict(frozen=True)

    evaluator_id: str
    subject_type: str
    description: str
    input_kind: str
    output_kind: str = "EvaluationReport"
    deterministic: bool = True
    execution_allowed: bool = False
    authority_transition: bool = False


# ── registry ────────────────────────────────────────────────────────

_DETERMINISTIC_EVALUATORS: dict[str, EvaluatorSpec] = {
    "plan_draft_evaluator": EvaluatorSpec(
        evaluator_id="plan_draft_evaluator",
        subject_type="PlanDraft",
        description=(
            "Checks plan completeness, stop conditions, option set linkage, "
            "and rejects action/execution language"
        ),
        input_kind="plan_draft",
    ),
    "research_evidence_quality": EvaluatorSpec(
        evaluator_id="research_evidence_quality",
        subject_type="research_evidence",
        description=(
            "Checks evidence source type, provider, recency, "
            "and claim support"
        ),
        input_kind="research_evidence_items",
    ),
}


def list_evaluators() -> list[EvaluatorSpec]:
    """Return all registered deterministic evaluators."""
    return list(_DETERMINISTIC_EVALUATORS.values())


def get_evaluator(evaluator_id: str) -> EvaluatorSpec | None:
    """Get a single evaluator spec by id, or None."""
    return _DETERMINISTIC_EVALUATORS.get(evaluator_id)


def evaluator_ids() -> list[str]:
    """Return sorted evaluator IDs."""
    return sorted(_DETERMINISTIC_EVALUATORS)


def evaluators_for_subject(subject_type: str) -> list[EvaluatorSpec]:
    """Return evaluators applicable to a given subject type."""
    return [
        e for e in _DETERMINISTIC_EVALUATORS.values()
        if e.subject_type == subject_type
    ]
