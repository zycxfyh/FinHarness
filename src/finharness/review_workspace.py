"""Human review workspace projection v0.

Agentic-space dimension: All Spaces / Human Collaboration.
Operating surface: Track F — Work Surface.

Produces a lightweight read model from cognition flow results so a
human reviewer can see the current state of a review subject.
"""

from __future__ import annotations

from uuid import uuid4

from pydantic import BaseModel, ConfigDict

from finharness.agent_cognition_flow import AgentCognitionFlowResult


class ReviewWorkspaceProjection(BaseModel):
    """Human-facing projection of a review subject's current state."""

    model_config = ConfigDict(frozen=True)

    workspace_id: str
    subject_type: str
    subject_id: str
    goal: str
    latest_plan_ref: str | None = None
    latest_evaluation_ref: str | None = None
    authority_transition_ref: str | None = None
    open_findings: list[str]
    data_gaps: list[str]
    suggested_playbooks: list[str]
    receipt_refs: list[str]
    execution_allowed: bool = False
    authority_transition: bool = False


def build_review_workspace_projection(
    *,
    flow_result: AgentCognitionFlowResult,
    subject_type: str = "plan_draft",
    subject_id: str = "",
    open_findings: list[str] | None = None,
    data_gaps: list[str] | None = None,
    suggested_playbooks: list[str] | None = None,
) -> ReviewWorkspaceProjection:
    """Build a review workspace projection from a cognition flow result.

    Aggregates the flow's artifact refs into a single read model
    suitable for a human reviewer or cockpit surface.
    """
    receipt_refs = [
        ref for ref in [
            flow_result.option_set_ref,
            flow_result.plan_draft_ref,
            flow_result.evaluation_report_ref,
            flow_result.agent_run_receipt_ref,
        ] if ref
    ]

    workspace_id = f"rwp_{uuid4().hex[:12]}"

    return ReviewWorkspaceProjection(
        workspace_id=workspace_id,
        subject_type=subject_type,
        subject_id=subject_id or flow_result.goal[:40],
        goal=flow_result.goal,
        latest_plan_ref=flow_result.plan_draft_ref,
        latest_evaluation_ref=flow_result.evaluation_report_ref,
        authority_transition_ref=flow_result.authority_transition_ref,
        open_findings=open_findings or [],
        data_gaps=data_gaps or [],
        suggested_playbooks=suggested_playbooks or [],
        receipt_refs=receipt_refs,
    )
