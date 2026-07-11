"""StateCore integration for the Agent-native autonomy control plane."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from sqlmodel import Session

from finharness.autonomy_control import (
    AdmissionDisposition,
    AgentActionClass,
    AgentActionRequest,
    AgentAutonomyLevel,
    AutonomyFindingCode,
    AutonomyRuntimeState,
    WorldFidelityLevel,
    evaluate_autonomy_admission,
)
from finharness.statecore.agent_authority_grants import record_agent_authority_grant
from finharness.statecore.autonomy_adapter import resolve_runtime_autonomy_mandate
from finharness.statecore.capital_mandates import record_capital_mandate
from finharness.statecore.models import AgentAuthorityGrant
from finharness.statecore.store import init_state_core


class AutonomyStateCoreAdapterTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.engine = init_state_core(self.root / "state-core.sqlite")
        self.addCleanup(self.engine.dispose)
        self.addCleanup(self.tmp.cleanup)

    def _record_grant(self) -> str:
        mandate = record_capital_mandate(
            capital_mandate_id="mandate_aut3",
            profile_snapshot={"profile": "balanced"},
            investment_objectives={"primary": "capital_preservation"},
            risk_profile={"max_drawdown_pct": 0.10},
            allowed_asset_classes=["cash", "equity"],
            restricted_asset_classes=["crypto_leverage"],
            allowed_action_types=["rebalance", "raise_cash"],
            restricted_action_types=["open_margin"],
            autonomy_level="L3_bounded_delegation_candidate",
            limit_book={"max_notional_usd": 1000},
            kill_switch_rules=[{"rule": "owner_revokes", "engaged": False}],
            human_attester="owner@example.com",
            human_reason="Delegate bounded planning decisions to the capital agent.",
            explicit_confirmation=True,
            engine=self.engine,
            receipt_root=self.root / "receipts",
        )
        grant = record_agent_authority_grant(
            agent_authority_grant_id="grant_aut3",
            capital_mandate_id=mandate.capital_mandate_id,
            agent_id="agent:capital",
            agent_profile_name="review-note",
            grant_scope={
                "allowed_asset_classes": ["cash"],
                "allowed_action_types": ["rebalance"],
                "autonomy_level": "L3_bounded_delegation_candidate",
            },
            issued_by="owner@example.com",
            issued_reason="Allow mandate-contained planning review.",
            engine=self.engine,
            receipt_root=self.root / "receipts",
        )
        return grant.agent_authority_grant_id

    def test_resolves_legacy_state_into_aut3_runtime_mandate(self) -> None:
        grant_id = self._record_grant()

        resolution = resolve_runtime_autonomy_mandate(
            grant_id,
            engine=self.engine,
            now_utc="2026-07-11T00:00:00+00:00",
        )

        self.assertTrue(resolution.resolved)
        assert resolution.mandate is not None
        self.assertEqual(
            resolution.mandate.granted_autonomy,
            AgentAutonomyLevel.AUT3_DELEGATED_REVIEW,
        )
        self.assertEqual(resolution.mandate.authority_grant_id, grant_id)
        self.assertIn(
            AgentActionClass.MAKE_PLANNING_DECISION,
            resolution.mandate.allowed_action_classes,
        )
        self.assertEqual(resolution.mandate.allowed_financial_action_types, ("rebalance",))
        self.assertEqual(resolution.mandate.allowed_asset_classes, ("cash",))
        self.assertIn("get_capital_context_projection", resolution.mandate.allowed_tools)

    def test_resolved_mandate_drives_financial_scope_admission(self) -> None:
        grant_id = self._record_grant()
        resolution = resolve_runtime_autonomy_mandate(grant_id, engine=self.engine)
        assert resolution.mandate is not None
        runtime = AutonomyRuntimeState(
            world_fidelity=WorldFidelityLevel.W2_SCENARIO_WORLD,
            runtime_autonomy_ceiling=AgentAutonomyLevel.AUT3_DELEGATED_REVIEW,
            now_utc="2026-07-11T00:00:00+00:00",
        )
        base = {
            "work_id": "work_scope",
            "agent_id": "agent:capital",
            "objective": "decide a bounded rebalance",
            "action_class": AgentActionClass.MAKE_PLANNING_DECISION,
            "requested_autonomy": AgentAutonomyLevel.AUT3_DELEGATED_REVIEW,
            "tool_name": "get_capital_context_projection",
        }
        admitted = evaluate_autonomy_admission(
            request=AgentActionRequest(
                **base,
                target_scope={"action_type": "rebalance", "asset_class": "cash"},
            ),
            runtime=runtime,
            mandate=resolution.mandate,
        )
        outside_scope = evaluate_autonomy_admission(
            request=AgentActionRequest(
                **base,
                target_scope={"action_type": "open_margin", "asset_class": "crypto"},
            ),
            runtime=runtime,
            mandate=resolution.mandate,
        )

        self.assertEqual(admitted.disposition, AdmissionDisposition.EFFECTIVE)
        self.assertEqual(outside_scope.disposition, AdmissionDisposition.CANDIDATE)
        codes = {finding.code for finding in outside_scope.findings}
        self.assertIn(AutonomyFindingCode.FINANCIAL_ACTION_OUTSIDE_MANDATE, codes)
        self.assertIn(AutonomyFindingCode.ASSET_CLASS_OUTSIDE_MANDATE, codes)

    def test_dynamic_grant_revocation_prevents_runtime_resolution(self) -> None:
        grant_id = self._record_grant()
        with Session(self.engine) as session:
            grant = session.get(AgentAuthorityGrant, grant_id)
            assert grant is not None
            grant.status = "revoked"
            session.add(grant)
            session.commit()

        resolution = resolve_runtime_autonomy_mandate(grant_id, engine=self.engine)

        self.assertFalse(resolution.resolved)
        self.assertIsNone(resolution.mandate)
        self.assertIn("grant_not_active", resolution.deny_reasons)

    def test_missing_grant_fails_closed(self) -> None:
        resolution = resolve_runtime_autonomy_mandate("missing", engine=self.engine)

        self.assertFalse(resolution.resolved)
        self.assertEqual(resolution.deny_reasons, ("grant_not_found",))


if __name__ == "__main__":
    unittest.main()
