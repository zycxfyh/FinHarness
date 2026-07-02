"""Preflight-bound ActionIntentSimulationReport writes."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from sqlalchemy import Engine
from sqlmodel import Session

from finharness.action_intent_preflight import (
    ActionIntentPreflightReport,
    preflight_action_intent,
)
from finharness.statecore.action_intents import _dedupe_text, forbidden_action_intent_marker
from finharness.statecore.models import (
    ACTION_INTENT_SIMULATION_SCENARIO_MODES,
    ActionIntent,
    ActionIntentSimulationReport,
    ReceiptIndex,
)
from finharness.statecore.proposals import (
    _display_path,
    _now_utc,
    _receipt_index,
    _revision_stamp,
    _safe_id,
)
from finharness.statecore.receipt_io import (
    atomic_write_json,
    remove_file_best_effort,
    resolve_under,
)
from finharness.statecore.store import StateCoreStoreError, write_records

ActionIntentSimulationScenarioMode = Literal[
    "descriptive_v0",
    "risk_posture_v0",
    "exposure_context_v0",
]

ACTION_INTENT_SIMULATION_NON_CLAIMS: tuple[str, ...] = (
    "ActionIntentSimulationReport is a preflight-bound descriptive report.",
    "ActionIntentSimulationReport is not an order ticket.",
    "ActionIntentSimulationReport is not broker execution.",
    "ActionIntentSimulationReport is not approval, attestation, or execution authorization.",
    "ActionIntentSimulationReport does not size a trade or choose an execution venue.",
)


class ActionIntentSimulationValidationError(ValueError):
    """Raised when a simulation report would cross its descriptive boundary."""


class ActionIntentSimulationStaleError(ValueError):
    """Raised when caller freshness evidence no longer matches current state."""


class ActionIntentSimulationPreflightBlockedError(ValueError):
    """Raised when current action preflight blocks downstream simulation."""

    def __init__(self, message: str, *, codes: list[str]) -> None:
        super().__init__(message)
        self.codes = codes


@dataclass(frozen=True)
class GovernedActionIntentSimulationWrite:
    simulation_report: ActionIntentSimulationReport
    receipt_ref: str
    execution_allowed: bool = False
    authority_transition: bool = False


def create_governed_action_intent_simulation_report(
    *,
    action_intent_id: str,
    expected_action_intent_receipt_ref: str,
    expected_action_preflight_report_hash: str,
    simulation_reason: str,
    explicit_preflight_acknowledgement: bool = False,
    acknowledged_preflight_warning_codes: list[str] | None = None,
    scenario_mode: ActionIntentSimulationScenarioMode = "descriptive_v0",
    assumptions: dict[str, Any] | None = None,
    source_refs: list[str] | None = None,
    engine: Engine,
    receipt_root: str | Path,
) -> GovernedActionIntentSimulationWrite:
    """Persist a qualitative simulation report bound to current preflight evidence."""

    if scenario_mode not in ACTION_INTENT_SIMULATION_SCENARIO_MODES:
        raise ActionIntentSimulationValidationError(f"unknown scenario mode: {scenario_mode}")
    if not simulation_reason.strip():
        raise ActionIntentSimulationValidationError("simulation report requires a reason")
    marker = forbidden_action_intent_marker(assumptions or {})
    if marker is not None:
        raise ActionIntentSimulationValidationError(
            f"assumptions cannot carry order/broker/authority field {marker!r}"
        )

    with Session(engine) as session:
        action_intent = session.get(ActionIntent, action_intent_id)
    if action_intent is None:
        raise KeyError(action_intent_id)
    expected_receipt = expected_action_intent_receipt_ref.strip()
    if action_intent.receipt_ref != expected_receipt:
        raise ActionIntentSimulationStaleError(
            "action intent receipt ref does not match expected_action_intent_receipt_ref"
        )

    preflight = preflight_action_intent(action_intent_id, engine=engine)
    if preflight is None:
        raise KeyError(action_intent_id)
    if preflight.report_hash != expected_action_preflight_report_hash.strip():
        raise ActionIntentSimulationStaleError(
            "action preflight report hash does not match current preflight"
        )
    _require_preflight_allows_simulation(
        preflight=preflight,
        explicit_preflight_acknowledgement=explicit_preflight_acknowledgement,
        acknowledged_warning_codes=acknowledged_preflight_warning_codes or [],
    )

    created_at = _now_utc()
    simulation_report_id = _safe_id(f"action_sim_{_revision_stamp()}_{uuid4().hex[:8]}")
    receipt_id = f"receipt_{simulation_report_id}"
    receipt_path = resolve_under(
        receipt_root,
        "action-intent-simulation-reports",
        f"{receipt_id}.json",
    )
    receipt_ref = _display_path(receipt_path)
    final_source_refs = _dedupe_text(
        [
            *action_intent.source_refs,
            *(source_refs or []),
        ]
    )
    final_receipt_refs = _dedupe_text(
        [
            *action_intent.receipt_refs,
            *([action_intent.receipt_ref] if action_intent.receipt_ref else []),
            *(
                [preflight.current_proposal_receipt_ref]
                if preflight.current_proposal_receipt_ref
                else []
            ),
            preflight.report_hash,
            receipt_ref,
        ]
    )
    status = "incomplete" if preflight.status == "warn" else "complete"
    simulation_report = ActionIntentSimulationReport(
        simulation_report_id=simulation_report_id,
        action_intent_id=action_intent.action_intent_id,
        proposal_id=action_intent.proposal_id,
        source_action_intent_receipt_ref=action_intent.receipt_ref or "",
        source_action_preflight_report_hash=preflight.report_hash,
        source_action_preflight_status=preflight.status,
        source_action_preflight_finding_codes=[finding.code for finding in preflight.findings],
        acknowledged_preflight_warning_codes=_dedupe_text(
            acknowledged_preflight_warning_codes or []
        ),
        scenario_mode=scenario_mode,
        simulation_status=status,
        risk_posture=preflight.risk_posture,
        risk_direction=preflight.impact_summary.risk_direction,
        affected_scope=dict(preflight.impact_summary.affected_scope),
        current_state_refs=list(preflight.impact_summary.known_state_refs),
        missing_data=list(preflight.impact_summary.missing_data),
        assumptions=dict(assumptions or {}),
        qualitative_impact=_qualitative_impact(
            action_intent=action_intent,
            preflight=preflight,
            simulation_reason=simulation_reason,
        ),
        numeric_impact=_numeric_impact(preflight),
        next_actions=_next_actions(preflight),
        source_refs=final_source_refs,
        receipt_refs=final_receipt_refs,
        non_claims=list(ACTION_INTENT_SIMULATION_NON_CLAIMS),
        receipt_ref=receipt_ref,
        execution_allowed=False,
        authority_transition=False,
        created_at_utc=created_at,
        as_of_utc=created_at,
    )
    atomic_write_json(
        receipt_path,
        _receipt_payload(simulation_report=simulation_report, preflight=preflight),
    )
    receipt_index: ReceiptIndex = _receipt_index(
        receipt_id=receipt_id,
        kind="state_core_action_intent_simulation_report",
        path=receipt_path,
        created_at_utc=created_at,
        refs=_dedupe_text(
            [
                simulation_report.simulation_report_id,
                action_intent.action_intent_id,
                action_intent.proposal_id,
                action_intent.receipt_ref or "",
                preflight.report_hash,
                *simulation_report.source_refs,
            ]
        ),
    )
    try:
        write_records([simulation_report, receipt_index], engine=engine)
    except StateCoreStoreError:
        remove_file_best_effort(receipt_path)
        raise
    return GovernedActionIntentSimulationWrite(
        simulation_report=simulation_report,
        receipt_ref=receipt_ref,
        execution_allowed=False,
        authority_transition=False,
    )


def _require_preflight_allows_simulation(
    *,
    preflight: ActionIntentPreflightReport,
    explicit_preflight_acknowledgement: bool,
    acknowledged_warning_codes: list[str],
) -> None:
    if preflight.status == "block":
        raise ActionIntentSimulationPreflightBlockedError(
            "action preflight blocks simulation report creation",
            codes=[finding.code for finding in preflight.findings if finding.blocks_progression],
        )
    warning_codes = set(_warning_codes(preflight))
    if not warning_codes:
        return
    acknowledged = set(_dedupe_text(acknowledged_warning_codes))
    if not explicit_preflight_acknowledgement:
        raise ActionIntentSimulationValidationError(
            "preflight warnings require explicit_preflight_acknowledgement=true"
        )
    missing = sorted(warning_codes - acknowledged)
    if missing:
        raise ActionIntentSimulationValidationError(
            "preflight warnings are not fully acknowledged: " + ", ".join(missing)
        )


def _warning_codes(preflight: ActionIntentPreflightReport) -> list[str]:
    return _dedupe_text(
        [finding.code for finding in preflight.findings if finding.severity == "warning"]
    )


def _qualitative_impact(
    *,
    action_intent: ActionIntent,
    preflight: ActionIntentPreflightReport,
    simulation_reason: str,
) -> dict[str, Any]:
    action_type = action_intent.action_type
    if action_type == "reduce_exposure":
        posture_note = "May reduce concentration risk if a future governed workflow approves it."
    elif action_type == "increase_exposure":
        posture_note = "May increase portfolio exposure and should remain simulation-first."
    elif action_type == "request_more_evidence":
        posture_note = "Requests evidence only and does not imply capital movement."
    else:
        posture_note = "Describes potential workflow impact without creating an execution plan."
    return {
        "summary": posture_note,
        "simulation_reason": simulation_reason.strip(),
        "risk_posture": preflight.risk_posture,
        "risk_direction": preflight.impact_summary.risk_direction,
        "preflight_status": preflight.status,
        "finding_codes": [finding.code for finding in preflight.findings],
        "boundary": "descriptive_no_execution",
    }


def _numeric_impact(preflight: ActionIntentPreflightReport) -> dict[str, Any]:
    return {
        "estimate_available": False,
        "portfolio_delta_available": False,
        "sizing_unavailable_reason": (
            "Simulation report v0 is qualitative and does not size capital actions."
        ),
        "known_state_ref_count": len(preflight.impact_summary.known_state_refs),
        "missing_data_count": len(preflight.impact_summary.missing_data),
    }


def _next_actions(preflight: ActionIntentPreflightReport) -> list[str]:
    if preflight.status == "warn":
        return [
            "Attach acknowledged preflight warning context to any future candidate.",
            "Resolve missing data before treating the report as complete.",
        ]
    return [
        "Use this simulation report receipt as evidence for the next governed review step.",
        "Do not create execution artifacts without a separate authority contract.",
    ]


def _receipt_payload(
    *,
    simulation_report: ActionIntentSimulationReport,
    preflight: ActionIntentPreflightReport,
) -> dict[str, Any]:
    return {
        "receipt_id": f"receipt_{simulation_report.simulation_report_id}",
        "kind": "state_core_action_intent_simulation_report",
        "created_at_utc": simulation_report.created_at_utc,
        "action_intent_id": simulation_report.action_intent_id,
        "proposal_id": simulation_report.proposal_id,
        "source_action_intent_receipt_ref": (
            simulation_report.source_action_intent_receipt_ref
        ),
        "source_action_preflight_report_hash": (
            simulation_report.source_action_preflight_report_hash
        ),
        "source_action_preflight_status": simulation_report.source_action_preflight_status,
        "source_action_preflight_finding_codes": (
            simulation_report.source_action_preflight_finding_codes
        ),
        "simulation_report": simulation_report.model_dump(mode="json"),
        "preflight_snapshot": {
            "status": preflight.status,
            "report_hash": preflight.report_hash,
            "finding_codes": [finding.code for finding in preflight.findings],
            "impact_summary": preflight.impact_summary.__dict__,
        },
        "governance": {
            "execution_allowed": False,
            "authority_transition": False,
            "preflight_bound": True,
            "not_order_ticket": True,
            "not_execution_authorization": True,
            "not_investment_advice": True,
            "non_claims": list(ACTION_INTENT_SIMULATION_NON_CLAIMS),
        },
    }
