"""PlanDraft semantic evaluator v0.

Agentic-space dimension: Evaluation Space.

Deterministic evaluator for PlanDraftReceipt artifacts.
Checks structural completeness, stop conditions, option set linkage,
and rejects action/execution language. No Execution Kernel dependency.

Produces an EvaluationReport with pass/warn/block status.
"""

from __future__ import annotations

import re
from typing import Literal

from finharness.deliberation_receipts import PlanDraftReceipt
from finharness.evaluation_report import (
    EvaluationFinding,
    EvaluationReport,
    build_evaluation_report,
)

BLOCKED_ACTION_TOKENS: frozenset[str] = frozenset(
    {
        "execute",
        "execution",
        "order",
        "submit",
        "transfer",
        "broker",
        "trade",
        "deploy",
        "dispatch",
    }
)

NON_ACTION_PHRASE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\btrade[- ]off analysis\b", re.IGNORECASE),
    re.compile(r"\brisk[- ]return trade[- ]offs?\b", re.IGNORECASE),
    re.compile(r"\bportfolio trade[- ]offs?\b", re.IGNORECASE),
)


def _strip_non_action_phrases(step: str) -> str:
    """Remove known non-action phrases before tokenization."""
    out = step
    for pattern in NON_ACTION_PHRASE_PATTERNS:
        out = pattern.sub(" ", out)
    return out


def _tokenize_step(step: str) -> list[str]:
    """Tokenize a plan step using regex word boundaries.

    Uses re.findall with [a-zA-Z_]+ to split on word boundaries
    including punctuation (execute., submit:, broker,).
    """
    cleaned = _strip_non_action_phrases(step)
    return re.findall(r"[a-zA-Z_]+", cleaned.lower())


def evaluate_plan_draft_receipt(
    *,
    plan_draft: PlanDraftReceipt,
    source_refs: list[str] | None = None,
) -> tuple[Literal['pass', 'warn', 'block'], list[EvaluationFinding]]:
    """Evaluate a PlanDraftReceipt for structural semantic quality.

    Returns (status, findings).
    status: "pass" if all checks pass, "warn" if issues exist but don't block,
    "block" if plan contains execution language or has no steps.

    Does NOT connect to Execution Kernel, broker, or StateCore.
    """
    findings: list[EvaluationFinding] = []
    refs = source_refs or []

    # Block-level checks
    if not plan_draft.steps:
        findings.append(
            EvaluationFinding(
                code="plan_no_steps",
                severity="block",
                message="Plan has no steps",
                recovery_hint="Add at least one step to the plan",
                source_refs=refs,
            )
        )

    action_tokens_found: list[str] = []
    for step in plan_draft.steps:
        tokens = _tokenize_step(step)
        for tok in tokens:
            if tok in BLOCKED_ACTION_TOKENS and tok not in action_tokens_found:
                action_tokens_found.append(tok)
    if action_tokens_found:
        findings.append(
            EvaluationFinding(
                code="plan_action_language",
                severity="block",
                message=f"Plan steps contain action/execution tokens: "
                f"{', '.join(action_tokens_found)}",
                recovery_hint="Replace action verbs with preparation/analysis steps",
                source_refs=refs,
            )
        )

    # Warn-level checks
    if not plan_draft.source_refs:
        findings.append(
            EvaluationFinding(
                code="plan_no_source_refs",
                severity="warn",
                message="Plan has no source refs",
                recovery_hint="Add context/source references to ground the plan",
                source_refs=refs,
            )
        )

    if not plan_draft.stop_conditions:
        findings.append(
            EvaluationFinding(
                code="plan_no_stop_conditions",
                severity="warn",
                message="Plan has no stop conditions",
                recovery_hint="Add conditions that define when to stop or escalate",
                source_refs=refs,
            )
        )

    if not plan_draft.related_option_set_id:
        findings.append(
            EvaluationFinding(
                code="plan_no_option_set_link",
                severity="warn",
                message="Plan is not linked to an OptionSet",
                recovery_hint="Link plan to an OptionSet via related_option_set_id",
                source_refs=refs,
            )
        )

    if not plan_draft.required_evaluations:
        findings.append(
            EvaluationFinding(
                code="plan_no_required_evaluations",
                severity="warn",
                message="Plan has no required evaluations",
                recovery_hint="Add required evaluations (e.g., ips_check, risk_check)",
                source_refs=refs,
            )
        )

    # Determine overall status
    blocks = [f for f in findings if f.severity == "block"]
    warns = [f for f in findings if f.severity == "warn"]

    if blocks:
        return "block", findings
    if warns:
        return "warn", findings
    return "pass", findings


def evaluate_plan_draft_to_report(
    *,
    plan_draft: PlanDraftReceipt,
    source_refs: list[str] | None = None,
    receipt_refs: list[str] | None = None,
) -> EvaluationReport:
    """Evaluate a PlanDraft and return a full EvaluationReport.

    Convenience wrapper: runs evaluate_plan_draft_receipt() and wraps
    the result in an EvaluationReport with deterministic hash.
    """
    status, findings = evaluate_plan_draft_receipt(
        plan_draft=plan_draft,
        source_refs=source_refs,
    )
    return build_evaluation_report(
        evaluator_id="plan_draft_evaluator",
        subject_type="plan_draft",
        subject_id=plan_draft.plan_id,
        status=status,
        findings=findings,
        source_refs=source_refs or [],
        receipt_refs=receipt_refs or [],
    )
