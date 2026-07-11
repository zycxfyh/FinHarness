"""Human review workspace projection v0.1.

Agentic-space dimension: All Spaces / Human Collaboration.
Operating surface: Track F — Work Surface.

v0.1 (PR #216): Can hydrate findings, data_gaps, and evaluation status
from receipts instead of requiring caller-supplied values.
"""

from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

from pydantic import BaseModel, ConfigDict

from finharness.agent_cognition_flow import AgentCognitionFlowResult
from finharness.statecore.receipt_io import atomic_write_json, resolve_under


class EvaluationFindingSummary(BaseModel):
    """Lightweight summary of an evaluation finding."""

    model_config = ConfigDict(frozen=True)

    code: str
    severity: str
    message: str


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
    open_findings: list[str] = []
    data_gaps: list[str] = []
    suggested_playbooks: list[str] = []
    receipt_refs: list[str] = []
    evaluation_status: str | None = None
    authority_eligibility: str | None = None
    evaluation_findings: list[EvaluationFindingSummary] = []
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


def _read_receipt_json(root: Path, ref: str | None) -> dict | None:
    """Read a receipt JSON file. Returns None if missing or invalid."""
    if not ref:
        return None
    # Strip fragment (e.g. #sha256:...) from ref
    clean_ref = ref.split("#")[0]
    path = root / clean_ref
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _hydrate_evaluation(
    eval_ref: str, root: Path,
) -> tuple[str | None, list[str], list[EvaluationFindingSummary]]:
    """Hydrate evaluation status and findings from eval report."""
    payload = _read_receipt_json(root, eval_ref)
    if payload is None:
        return None, [], []
    status = str(payload.get("status", "")) or None
    findings_list: list[EvaluationFindingSummary] = []
    open_f: list[str] = []
    raw = payload.get("findings", [])
    if isinstance(raw, list):
        for f in raw:
            if isinstance(f, dict):
                code = str(f.get("code", ""))
                severity = str(f.get("severity", "warn"))
                message = str(f.get("message", ""))
                findings_list.append(
                    EvaluationFindingSummary(code=code, severity=severity, message=message)
                )
                if severity in ("block", "warn"):
                    open_f.append(f"{code}: {message}")
    return status, open_f, findings_list


def _hydrate_data_gaps(run_ref: str, root: Path) -> list[str]:
    """Hydrate data_gaps from agent run receipt."""
    payload = _read_receipt_json(root, run_ref)
    if payload is None:
        return []
    raw = payload.get("data_gaps", [])
    if isinstance(raw, list):
        return [str(g) for g in raw]
    return []


def build_review_workspace_projection_from_receipts(
    *,
    flow_result: AgentCognitionFlowResult,
    receipt_root: str | Path,
    subject_type: str = "plan_draft",
    subject_id: str = "",
) -> ReviewWorkspaceProjection:
    """Build a hydrated review workspace by reading receipts.

    Reads evaluation reports, agent run receipts, and authority
    transitions from disk to populate findings, data_gaps, and
    evaluation status — no need for the caller to supply them.
    """
    root = Path(receipt_root)

    # Hydrate from evaluation report
    evaluation_status, open_findings, eval_findings = _hydrate_evaluation(
        flow_result.evaluation_report_ref or "", root,
    )

    # Hydrate from agent run receipt
    data_gaps = _hydrate_data_gaps(
        flow_result.agent_run_receipt_ref or "", root,
    )

    # Hydrate from authority transition
    authority_eligibility: str | None = None
    payload = _read_receipt_json(root, flow_result.authority_transition_ref)
    if payload is not None:
        authority_eligibility = str(payload.get("eligibility", "")) or None

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
        open_findings=open_findings,
        data_gaps=data_gaps,
        suggested_playbooks=[],
        receipt_refs=receipt_refs,
        evaluation_status=evaluation_status,
        authority_eligibility=authority_eligibility,
        evaluation_findings=eval_findings,
    )


def write_review_workspace_projection(
    projection: ReviewWorkspaceProjection,
    *,
    receipt_root: str | Path,
) -> str:
    """Persist a hydrated workspace and return a root-relative reference."""

    relative = Path("review-workspaces") / f"{projection.workspace_id}.json"
    atomic_write_json(
        resolve_under(receipt_root, relative),
        projection.model_dump(mode="json"),
    )
    return relative.as_posix()
