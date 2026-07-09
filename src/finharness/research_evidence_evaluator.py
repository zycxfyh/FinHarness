"""Research evidence quality evaluator v0.

Agentic-space dimension: Evaluation Space.
Operating surface: Track E — Evaluator / Simulation.

First domain evaluator beyond lexical plan checking. Evaluates the
quality structure of research evidence, not its investment correctness.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from finharness.evaluation_report import (
    EvaluationFinding,
    EvaluationReport,
    build_evaluation_report,
)

NON_CLAIMS: tuple[str, ...] = (
    "Research evidence quality evaluation checks structure, not correctness.",
    "Does not judge investment merit.",
    "Not execution authorization.",
    "Not investment advice.",
)


class ResearchEvidenceItem(BaseModel):
    """One evidence item to evaluate."""

    model_config = ConfigDict(frozen=True)

    ref: str
    claim: str | None = None
    source_type: str | None = None
    provider: str | None = None
    recency: str | None = None
    evidence_refs: list[str] | None = None


def evaluate_research_evidence_quality(
    *,
    evidence_items: list[ResearchEvidenceItem],
    source_refs: list[str] | None = None,
) -> EvaluationReport:
    """Evaluate the structural quality of research evidence items.

    Checks:
    - source_type present and classified
    - provider/origin present
    - recency stated
    - claim linked to evidence_ref
    - external_provider evidence not auto-trusted
    - unsupported claims flagged
    """
    findings: list[EvaluationFinding] = []
    blocked = False
    warned = False

    for item in evidence_items:
        # Source type must be present
        if not item.source_type:
            findings.append(EvaluationFinding(
                code="evidence_source_type_missing",
                severity="block",
                message=f"Evidence item '{item.ref}' has no source_type",
                recovery_hint="Classify the source: market_data, capital_context, local_eval, etc.",
                source_refs=[item.ref],
            ))
            blocked = True
            continue

        # Provider/origin should be present
        if not item.provider:
            findings.append(EvaluationFinding(
                code="evidence_provider_missing",
                severity="warn",
                message=f"Evidence item '{item.ref}' has no provider/origin",
                recovery_hint="Record the data provider or origin of this evidence",
                source_refs=[item.ref],
            ))
            warned = True

        # Recency should be stated
        if not item.recency:
            findings.append(EvaluationFinding(
                code="evidence_recency_missing",
                severity="warn",
                message=f"Evidence item '{item.ref}' has no recency information",
                recovery_hint="Record when this evidence was observed or retrieved",
                source_refs=[item.ref],
            ))
            warned = True

        # Claim linked to evidence ref
        if item.claim and not item.evidence_refs:
            findings.append(EvaluationFinding(
                code="unsupported_claim",
                severity="warn",
                message=f"Claim on '{item.ref}' has no evidence_refs backing",
                recovery_hint=(
                    "Link the claim to specific evidence references"
                ),
                source_refs=[item.ref],
            ))
            warned = True

        # External provider evidence not auto-trusted
        if item.source_type == "external_provider":
            findings.append(EvaluationFinding(
                code="external_provider_not_auto_trusted",
                severity="warn",
                message=(
                    f"Evidence item '{item.ref}' from external provider — "
                    "requires additional verification"
                ),
                recovery_hint=(
                    "Cross-reference with internal data or human review"
                ),
                source_refs=[item.ref],
            ))
            warned = True

    status: str = "block" if blocked else "warn" if warned else "pass"

    return build_evaluation_report(
        evaluator_id="research_evidence_quality",
        subject_type="research_evidence",
        subject_id="evidence_batch",
        status=status,
        findings=findings,
        source_refs=source_refs or [item.ref for item in evidence_items],
    )
