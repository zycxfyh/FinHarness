# finharness-test-runner: pytest
from __future__ import annotations

import json
import os
from pathlib import Path

from finharness.agent_work_loop import (
    AgentWorkDecision,
    AgentWorkDecisionState,
    AgentWorkRequest,
    AgentWorkToolRequest,
    freeze_work_context,
    run_agent_work_loop,
    run_bounded_tool_dispatch_loop,
    run_cognition_flow_from_work_result,
)
from finharness.config import load_settings
from finharness.context_trust import trust_for_system_computed
from finharness.statecore.store import STATE_CORE_DB_ENV_VAR, init_state_core

WORLD_ID = "capital_world_0123456789abcdef01234567"
BASIS = "0" * 64
SOURCE = "dataset://scf/household/1"


def _envelope() -> dict[str, object]:
    payload = {
        "name": "capital_summary",
        "available": True,
        "summary": {
            "world_id": WORLD_ID,
            "basis_digest": BASIS,
            "world_status": "admitted",
            "selected_batch_ids": ["batch_1"],
            "trust": trust_for_system_computed(source_refs=[SOURCE]).model_dump(),
            "capital_truth": {
                "status": "admitted",
                "blockers": [],
                "asset_valuation_admitted": True,
                "net_worth_admitted": True,
            },
            "total_assets": "391960",
            "total_liabilities": "191000",
            "net_worth": "200960",
            "concentration_flagged": False,
        },
        "source_refs": [SOURCE],
        "context_pack_refs": ["context_pack://capital_summary"],
        "data_gaps": [],
        "execution_allowed": False,
    }
    return {
        "tool_name": "get_capital_summary_context",
        "toolset": "capital_context",
        "ok": True,
        "observation_payload": payload,
        "observation_sha256": "1" * 64,
        "world_id": WORLD_ID,
        "basis_digest": BASIS,
        "world_status": "admitted",
        "trust": payload["summary"]["trust"],
        "capital_truth": payload["summary"]["capital_truth"],
        "source_refs": [SOURCE],
        "artifact_refs": [],
        "receipt_refs": [],
        "context_refs": ["context_pack://capital_summary"],
        "data_gaps": [],
        "side_effect": "read",
        "output_kind": "context",
        "truncated": False,
        "artifact_ref": "agent-tool-results/step-1.json",
        "execution_allowed": False,
        "authority_transition": False,
    }


def test_semantic_cognition_persists_audit_and_non_generic_plan(tmp_path: Path) -> None:
    request = AgentWorkRequest(
        goal="Audit the current Capital World",
        profile_name="default",
        objective="Separate facts, inferences, and unsupported claims",
        work_type="evidence_triage",
        receipt_root=str(tmp_path),
    )
    snapshot = freeze_work_context(
        work_id=request.work_id,
        profile_name=request.profile_name,
    )
    flow = run_cognition_flow_from_work_result(
        request=request,
        context_snapshot=snapshot,
        tool_envelopes=[_envelope()],
        receipt_root=tmp_path,
    )
    assert flow["audit_disposition"] == "complete"
    audit_ref = str(flow["capital_world_audit_ref"])
    plan_ref = str(flow["plan_draft_ref"])
    audit = json.loads((tmp_path / audit_ref).read_text())
    plan = json.loads((tmp_path / plan_ref).read_text())
    assert audit["world_id"] == WORLD_ID
    assert audit["observed"]
    assert plan["stop_conditions"]
    assert plan["required_evaluations"]
    assert all("Review results from" not in step for step in plan["steps"])
    assert plan["execution_allowed"] is False


def test_repeated_identical_dispatch_stops_before_third_call(tmp_path: Path) -> None:
    db = tmp_path / "state.sqlite"
    engine = init_state_core(db)
    engine.dispose()
    previous = os.environ.get(STATE_CORE_DB_ENV_VAR)
    os.environ[STATE_CORE_DB_ENV_VAR] = str(db)
    load_settings.cache_clear()
    try:
        request = AgentWorkRequest(
            goal="Detect no progress",
            profile_name="default",
            objective="Bound repeated reads",
            work_type="evidence_triage",
            receipt_root=str(tmp_path / "receipts"),
            max_steps=8,
            max_tool_calls=8,
        )
        snapshot = freeze_work_context(
            work_id=request.work_id,
            profile_name=request.profile_name,
        )

        def repeated_port(_state: AgentWorkDecisionState) -> AgentWorkDecision:
            return AgentWorkDecision(
                action="dispatch",
                tool_request=AgentWorkToolRequest(
                    tool_name="get_capital_context_projection",
                    arguments={"open_proposals_limit": 1},
                ),
            )

        envelopes, stop_reason, gaps = run_bounded_tool_dispatch_loop(
            request=request,
            context_snapshot=snapshot,
            decision_port=repeated_port,
        )
        assert len(envelopes) == 2
        assert stop_reason == "no_progress_detected"
        assert any("no_progress_detected" in gap for gap in gaps)
    finally:
        if previous is None:
            os.environ.pop(STATE_CORE_DB_ENV_VAR, None)
        else:
            os.environ[STATE_CORE_DB_ENV_VAR] = previous
        load_settings.cache_clear()


def test_blocked_capital_world_reduces_to_semantic_stop(tmp_path: Path) -> None:
    db = tmp_path / "state.sqlite"
    engine = init_state_core(db)
    engine.dispose()
    previous = os.environ.get(STATE_CORE_DB_ENV_VAR)
    os.environ[STATE_CORE_DB_ENV_VAR] = str(db)
    load_settings.cache_clear()
    try:
        result = run_agent_work_loop(
            request=AgentWorkRequest(
                goal="Audit blocked Capital World",
                profile_name="default",
                objective="Stop on incomplete Capital Truth",
                work_type="evidence_triage",
                receipt_root=str(tmp_path / "agent-receipts"),
                tool_requests=[AgentWorkToolRequest(
                    tool_name="get_capital_context_projection",
                    arguments={"open_proposals_limit": 1},
                )],
            )
        )
        assert result.outcome == "stopped"
        assert result.stop_reason == "semantic_stop"
        assert result.audit_disposition == "stopped"
        assert result.capital_world_audit_ref
        audit = json.loads(
            (tmp_path / "agent-receipts" / result.capital_world_audit_ref).read_text()
        )
        assert audit["world_status"] != "admitted"
        assert audit["unsupported"]
        assert audit["execution_allowed"] is False
    finally:
        if previous is None:
            os.environ.pop(STATE_CORE_DB_ENV_VAR, None)
        else:
            os.environ[STATE_CORE_DB_ENV_VAR] = previous
        load_settings.cache_clear()
