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
from finharness.deliberation_receipts import (
    OptionDraft,
    write_option_set_receipt,
    write_plan_draft_receipt,
)
from finharness.evaluation_report import (
    EvaluationFinding,
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
    eval_status: str = "warn",
    eval_findings: list[EvaluationFinding] | None = None,
) -> AgentCognitionFlowResult:
    """Run a deterministic agent cognition flow.

    Steps:
    1. write_option_set_receipt — deliberated options
    2. write_plan_draft_receipt — chosen plan
    3. build + write_evaluation_report — evaluates the plan
    4. record_authority_transition — if human confirmation present
    5. write_agent_run_receipt — traces the entire run

    eval_status controls the evaluation result: "pass", "warn" (default), or "block".
    eval_findings overrides the default finding; if omitted, a default
    "plan evaluation — human review required" finding is generated.

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

    # 3. Evaluation — uses real plan draft evaluator
    eval_report = evaluate_plan_draft_to_report(
        plan_draft=plan_draft,
        source_refs=source_refs,
    )
    if eval_findings is not None:
        # Custom findings override evaluator output
        eval_report = eval_report.model_copy(update={"findings": list(eval_findings)})
    if eval_status in ("pass", "warn", "block"):
        eval_report = eval_report.model_copy(update={"status": eval_status})
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
