"""Agent Cognition Flow v0 — deterministic cognition chain.

Agentic-space dimension: Trace / Deliberation / Evaluation / Authority.

The first end-to-end flow proof for Agent Cognition Runtime v0.
Serializes Wave 0 primitives into a deterministic, receipt-backed,
non-executing cognition chain:

  goal → option set → plan draft → evaluation → authority → agent run receipt

No LLM. No broker. No StateCore table. No Execution Kernel.
"""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from pydantic import BaseModel, ConfigDict

from finharness.agent_run_receipts import (
    AgentToolCallSummary,
    write_agent_run_receipt,
)
from finharness.authority_eligibility_policy import eligibility_from_evaluation_status
from finharness.authority_transition import (
    record_authority_transition,
)
from finharness.context_trust import ContextTrust
from finharness.context_use_policy import (
    ContextRequiredUse,
    validate_context_refs_for_use,
)
from finharness.deliberation_receipts import (
    OptionDraft,
    write_option_set_receipt,
    write_plan_draft_receipt,
)
from finharness.evaluation_report import (
    EvaluationFinding,
    EvaluationReport,
    write_evaluation_report,
)
from finharness.plan_draft_evaluator import evaluate_plan_draft_to_report

NON_CLAIMS: tuple[str, ...] = (
    "AgentCognitionFlow is a deterministic cognition trace, not an execution pipeline.",
    "No orders are created. No broker is contacted. No StateCore is written.",
    "execution_allowed=False throughout the entire chain.",
    "Not investment advice.",
)


class AgentCognitionFlowResult(BaseModel):
    """Result of one agent cognition flow run."""

    model_config = ConfigDict(frozen=True)

    flow_id: str
    goal: str
    option_set_ref: str
    plan_draft_ref: str
    evaluation_report_ref: str
    authority_transition_ref: str | None = None
    agent_run_receipt_ref: str
    execution_allowed: bool = False


def _new_id() -> str:
    return f"acf_{uuid4().hex[:12]}"


def run_agent_cognition_flow(
    *,
    goal: str,
    profile_name: str,
    objective: str,
    option_claims: list[str],
    plan_steps: list[str],
    receipt_root: str | Path,
    context_refs: list[str] | None = None,
    source_refs: list[str] | None = None,
    human_attester: str | None = None,
    human_reason: str | None = None,
    explicit_confirmation: bool = False,
    context_trust_by_ref: dict[str, ContextTrust] | None = None,
    required_context_use: ContextRequiredUse = "use_as_evidence",
    evaluator_override: EvaluationReport | None = None,
    allow_evaluation_override: bool = False,
) -> AgentCognitionFlowResult:
    """Run a deterministic agent cognition flow.

    Steps:
    1. write_option_set_receipt — deliberated options
    2. write_plan_draft_receipt — chosen plan
    3. build + write_evaluation_report — evaluates the plan
    4. record_authority_transition — if human confirmation present
    5. write_agent_run_receipt — traces the entire run

    By default, the real plan_draft_evaluator runs. For testing only,
    pass evaluator_override with allow_evaluation_override=True to
    substitute a pre-built EvaluationReport. This gate prevents
    accidental bypass of the semantic evaluator.

    Returns AgentCognitionFlowResult with all artifact refs.
    execution_allowed is False throughout.
    """
    flow_id = _new_id()
    root = Path(receipt_root)

    # 1. OptionSet
    options = [
        OptionDraft(
            option_id=f"opt_{i + 1}",
            claim=claim,
        )
        for i, claim in enumerate(option_claims)
    ]
    option_set = write_option_set_receipt(
        objective=objective,
        options=options,
        receipt_root=root,
        source_refs=source_refs,
    )
    option_set_ref = f"deliberation/{option_set.receipt_id}.json"

    # 2. PlanDraft
    plan_draft = write_plan_draft_receipt(
        objective=objective,
        steps=plan_steps,
        receipt_root=root,
        related_option_set_id=option_set.option_set_id,
        source_refs=source_refs,
        receipt_refs=[option_set_ref],
    )
    plan_draft_ref = f"deliberation/{plan_draft.receipt_id}.json"

    # 2.5 Context validation — enforce allowed uses if trust metadata provided
    context_findings: list[EvaluationFinding] = []

    if source_refs:
        if context_trust_by_ref is None:
            context_findings.append(
                EvaluationFinding(
                    code="context_trust_metadata_missing",
                    severity="warn",
                    message=(
                        "Context refs were supplied without ContextTrust metadata"
                    ),
                    recovery_hint=(
                        "Provide context_trust_by_ref so source refs can be "
                        "validated for intended use"
                    ),
                    source_refs=list(source_refs),
                )
            )
        else:
            validation = validate_context_refs_for_use(
                refs=list(source_refs),
                trust_by_ref=context_trust_by_ref,
                required_use=required_context_use,
            )
            for ref, reason in zip(
                validation.blocked_refs, validation.blocked_reasons, strict=False
            ):
                context_findings.append(
                    EvaluationFinding(
                        code="context_use_not_allowed",
                        severity="block",
                        message=reason,
                        recovery_hint=(
                            f"Use a context ref whose allowed_uses "
                            f"includes {required_context_use}"
                        ),
                        source_refs=[ref],
                    )
                )

    # 3. Evaluation — uses real plan draft evaluator
    if evaluator_override is not None:
        if not allow_evaluation_override:
            raise ValueError(
                "evaluator_override requires allow_evaluation_override=True"
            )
        eval_report = evaluator_override
    else:
        eval_report = evaluate_plan_draft_to_report(
            plan_draft=plan_draft,
            source_refs=source_refs,
        )

    # Merge context validation findings into evaluation report
    if context_findings:
        merged_findings = [*eval_report.findings, *context_findings]
        merged_status = (
            "block"
            if any(f.severity == "block" for f in merged_findings)
            else "warn"
            if any(f.severity == "warn" for f in merged_findings)
            else eval_report.status
        )
        eval_report = eval_report.model_copy(
            update={
                "findings": merged_findings,
                "status": merged_status,
            }
        )

    eval_ref = write_evaluation_report(
        report=eval_report,
        receipt_root=root,
    )

    # 4. Authority transition (optional)
    authority_ref: str | None = None
    tool_calls = [
        AgentToolCallSummary(
            tool_name="write_option_set_receipt",
            side_effect="append_only_review_write",
            ok=True,
            receipt_refs=[option_set_ref],
        ),
        AgentToolCallSummary(
            tool_name="write_plan_draft_receipt",
            side_effect="append_only_review_write",
            ok=True,
            receipt_refs=[plan_draft_ref],
        ),
        AgentToolCallSummary(
            tool_name="build_evaluation_report",
            side_effect="read",
            ok=True,
            evidence_refs=[eval_ref],
        ),
    ]

    if human_attester and human_reason and explicit_confirmation:
        eligibility = eligibility_from_evaluation_status(eval_report.status)
        to_state_map = {"eligible": "eligible", "deferred": "deferred", "not_eligible": "blocked"}
        at_record = record_authority_transition(
            subject_type="plan_draft",
            subject_id=plan_draft.plan_id,
            from_state="drafted",
            to_state=to_state_map[eligibility],
            eligibility=eligibility,
            evaluation_report_refs=[eval_ref],
            human_attester=human_attester,
            human_reason=human_reason,
            explicit_confirmation=True,
            receipt_root=root,
            supporting_receipt_refs=[option_set_ref, plan_draft_ref],
        )
        authority_ref = f"authority-transitions/{at_record.transition_id}.json"
        tool_calls.append(
            AgentToolCallSummary(
                tool_name="record_authority_transition",
                side_effect="append_only_review_write",
                ok=True,
                receipt_refs=[authority_ref],
                evidence_refs=[eval_ref],
            ),
        )

    # 5. AgentRunReceipt
    all_refs = [option_set_ref, plan_draft_ref, eval_ref]
    if authority_ref:
        all_refs.append(authority_ref)
    run_receipt = write_agent_run_receipt(
        goal=goal,
        profile_name=profile_name,
        tool_calls=tool_calls,
        outcome="succeeded" if authority_ref else "partial",
        stop_reason="flow_complete" if authority_ref else "awaiting_human_confirmation",
        receipt_root=root,
        context_refs=context_refs or [],
        artifact_refs=all_refs,
        evidence_refs=[eval_ref],
        data_gaps=(
            []
            if authority_ref
            else ["Human confirmation not provided — authority transition skipped"]
        ),
    )
    run_ref = f"agent-runs/{run_receipt.receipt_id}.json"

    return AgentCognitionFlowResult(
        flow_id=flow_id,
        goal=goal,
        option_set_ref=option_set_ref,
        plan_draft_ref=plan_draft_ref,
        evaluation_report_ref=eval_ref,
        authority_transition_ref=authority_ref,
        agent_run_receipt_ref=run_ref,
    )
