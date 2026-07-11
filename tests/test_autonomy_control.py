"""Behavioral contracts for the Agent-native autonomy control plane."""

from __future__ import annotations

import unittest

from pydantic import ValidationError

from finharness.autonomy_control import (
    AdmissionDisposition,
    AgentActionClass,
    AgentActionRequest,
    AgentAutonomyLevel,
    AutonomyFindingCode,
    AutonomyMandate,
    AutonomyRuntimeState,
    HumanControlMode,
    WorldFidelityLevel,
    action_requirements,
    evaluate_autonomy_admission,
    human_control_mode,
    legacy_autonomy_level,
)


class AutonomyControlPlaneTest(unittest.TestCase):
    def _request(
        self,
        *,
        action_class: AgentActionClass = AgentActionClass.GATHER_EVIDENCE,
        autonomy: AgentAutonomyLevel = AgentAutonomyLevel.AUT1_TOOL_REVIEWER,
        external_effect: bool = False,
        tool_name: str | None = "get_capital_context_projection",
    ) -> AgentActionRequest:
        return AgentActionRequest(
            action_id="action_1",
            work_id="work_1",
            agent_id="agent:capital",
            objective="protect the capital objective",
            action_class=action_class,
            requested_autonomy=autonomy,
            external_effect=external_effect,
            tool_name=tool_name,
            arguments={"scope": "portfolio"},
        )

    def _runtime(
        self,
        *,
        world: WorldFidelityLevel = WorldFidelityLevel.W0_CAPITAL_FACTS,
        ceiling: AgentAutonomyLevel = AgentAutonomyLevel.AUT1_TOOL_REVIEWER,
    ) -> AutonomyRuntimeState:
        return AutonomyRuntimeState(
            world_fidelity=world,
            runtime_autonomy_ceiling=ceiling,
            world_state_ref="capital-state:1",
            now_utc="2026-07-11T00:00:00+00:00",
        )

    def _mandate(
        self,
        *,
        autonomy: AgentAutonomyLevel,
        actions: tuple[AgentActionClass, ...],
        tools: tuple[str, ...] = ("get_capital_context_projection",),
        status: str = "active",
        kill_switch_engaged: bool = False,
        expires_at_utc: str | None = "2027-01-01T00:00:00+00:00",
    ) -> AutonomyMandate:
        return AutonomyMandate(
            mandate_id="mandate_1",
            principal_id="human:owner",
            agent_id="agent:capital",
            status=status,
            granted_autonomy=autonomy,
            allowed_action_classes=actions,
            allowed_tools=tools,
            kill_switch_engaged=kill_switch_engaged,
            expires_at_utc=expires_at_utc,
        )

    def test_action_requirements_encode_world_and_autonomy_ladder(self) -> None:
        self.assertEqual(
            action_requirements(AgentActionClass.MAKE_PLANNING_DECISION),
            (
                WorldFidelityLevel.W2_SCENARIO_WORLD,
                AgentAutonomyLevel.AUT3_DELEGATED_REVIEW,
            ),
        )
        self.assertEqual(
            action_requirements(AgentActionClass.TAKE_REAL_ACTION),
            (
                WorldFidelityLevel.W4_LEARNING_POLICY,
                AgentAutonomyLevel.AUT5_REAL_OPERATOR,
            ),
        )

    def test_human_control_mode_graduates_with_autonomy(self) -> None:
        self.assertEqual(
            human_control_mode(AgentAutonomyLevel.AUT2_DURABLE_LOOP),
            HumanControlMode.IN_THE_LOOP,
        )
        self.assertEqual(
            human_control_mode(AgentAutonomyLevel.AUT4_PAPER_MANAGER),
            HumanControlMode.ON_THE_LOOP,
        )
        self.assertEqual(
            human_control_mode(AgentAutonomyLevel.AUT6_CONTINUOUS_AGENT),
            HumanControlMode.OVER_THE_LOOP,
        )

    def test_read_and_evidence_can_be_effective_without_delegated_mandate(self) -> None:
        report = evaluate_autonomy_admission(
            request=self._request(),
            runtime=self._runtime(),
            mandate=None,
        )

        self.assertEqual(report.disposition, AdmissionDisposition.EFFECTIVE)
        self.assertTrue(report.effective)
        self.assertFalse(report.effect_admitted)
        self.assertFalse(report.external_effect_admitted)
        self.assertFalse(report.execution_allowed)
        self.assertFalse(report.authority_transition)

    def test_review_packet_without_mandate_remains_candidate(self) -> None:
        request = self._request(
            action_class=AgentActionClass.PREPARE_REVIEW_PACKET,
            autonomy=AgentAutonomyLevel.AUT2_DURABLE_LOOP,
        )
        report = evaluate_autonomy_admission(
            request=request,
            runtime=self._runtime(
                world=WorldFidelityLevel.W1_VERSIONED_DECISIONS,
                ceiling=AgentAutonomyLevel.AUT2_DURABLE_LOOP,
            ),
            mandate=None,
        )

        self.assertEqual(report.disposition, AdmissionDisposition.CANDIDATE)
        self.assertFalse(report.effective)
        self.assertEqual(report.findings[0].code, AutonomyFindingCode.MANDATE_REQUIRED)

    def test_world_fidelity_blocks_premature_planning_decision(self) -> None:
        request = self._request(
            action_class=AgentActionClass.MAKE_PLANNING_DECISION,
            autonomy=AgentAutonomyLevel.AUT3_DELEGATED_REVIEW,
        )
        report = evaluate_autonomy_admission(
            request=request,
            runtime=self._runtime(
                world=WorldFidelityLevel.W1_VERSIONED_DECISIONS,
                ceiling=AgentAutonomyLevel.AUT3_DELEGATED_REVIEW,
            ),
            mandate=None,
        )

        self.assertEqual(report.disposition, AdmissionDisposition.BLOCKED)
        self.assertIn(
            AutonomyFindingCode.WORLD_FIDELITY_INSUFFICIENT,
            {finding.code for finding in report.findings},
        )

    def test_runtime_ceiling_blocks_unimplemented_autonomy(self) -> None:
        request = self._request(
            action_class=AgentActionClass.PREPARE_REVIEW_PACKET,
            autonomy=AgentAutonomyLevel.AUT2_DURABLE_LOOP,
        )
        report = evaluate_autonomy_admission(
            request=request,
            runtime=self._runtime(
                world=WorldFidelityLevel.W1_VERSIONED_DECISIONS,
                ceiling=AgentAutonomyLevel.AUT1_TOOL_REVIEWER,
            ),
            mandate=None,
        )

        self.assertEqual(report.disposition, AdmissionDisposition.BLOCKED)
        self.assertIn(
            AutonomyFindingCode.AUTONOMY_EXCEEDS_RUNTIME,
            {finding.code for finding in report.findings},
        )

    def test_mandate_contained_planning_decision_becomes_effective(self) -> None:
        request = self._request(
            action_class=AgentActionClass.MAKE_PLANNING_DECISION,
            autonomy=AgentAutonomyLevel.AUT3_DELEGATED_REVIEW,
            tool_name="compare_scenarios",
        )
        mandate = self._mandate(
            autonomy=AgentAutonomyLevel.AUT3_DELEGATED_REVIEW,
            actions=(AgentActionClass.MAKE_PLANNING_DECISION,),
            tools=("compare_scenarios",),
        )
        report = evaluate_autonomy_admission(
            request=request,
            runtime=self._runtime(
                world=WorldFidelityLevel.W2_SCENARIO_WORLD,
                ceiling=AgentAutonomyLevel.AUT3_DELEGATED_REVIEW,
            ),
            mandate=mandate,
        )

        self.assertEqual(report.disposition, AdmissionDisposition.EFFECTIVE)
        self.assertTrue(report.effective)
        self.assertEqual(report.mandate_id, "mandate_1")
        self.assertEqual(report.human_control_mode, HumanControlMode.IN_OR_ON_THE_LOOP)
        self.assertFalse(report.effect_admitted)

    def test_action_outside_mandate_remains_candidate(self) -> None:
        request = self._request(
            action_class=AgentActionClass.MAKE_PLANNING_DECISION,
            autonomy=AgentAutonomyLevel.AUT3_DELEGATED_REVIEW,
            tool_name="compare_scenarios",
        )
        mandate = self._mandate(
            autonomy=AgentAutonomyLevel.AUT3_DELEGATED_REVIEW,
            actions=(AgentActionClass.PREPARE_REVIEW_PACKET,),
            tools=("compare_scenarios",),
        )
        report = evaluate_autonomy_admission(
            request=request,
            runtime=self._runtime(
                world=WorldFidelityLevel.W2_SCENARIO_WORLD,
                ceiling=AgentAutonomyLevel.AUT3_DELEGATED_REVIEW,
            ),
            mandate=mandate,
        )

        self.assertEqual(report.disposition, AdmissionDisposition.CANDIDATE)
        self.assertFalse(report.effective)
        self.assertIn(
            AutonomyFindingCode.ACTION_OUTSIDE_MANDATE,
            {finding.code for finding in report.findings},
        )

    def test_kill_switch_and_expiry_block_effective_action(self) -> None:
        request = self._request(
            action_class=AgentActionClass.TAKE_PAPER_ACTION,
            autonomy=AgentAutonomyLevel.AUT4_PAPER_MANAGER,
            tool_name="submit_paper_order",
        )
        runtime = self._runtime(
            world=WorldFidelityLevel.W3_OUTCOME_RECONCILIATION,
            ceiling=AgentAutonomyLevel.AUT4_PAPER_MANAGER,
        )
        killed = evaluate_autonomy_admission(
            request=request,
            runtime=runtime,
            mandate=self._mandate(
                autonomy=AgentAutonomyLevel.AUT4_PAPER_MANAGER,
                actions=(AgentActionClass.TAKE_PAPER_ACTION,),
                tools=("submit_paper_order",),
                kill_switch_engaged=True,
            ),
        )
        expired = evaluate_autonomy_admission(
            request=request,
            runtime=runtime,
            mandate=self._mandate(
                autonomy=AgentAutonomyLevel.AUT4_PAPER_MANAGER,
                actions=(AgentActionClass.TAKE_PAPER_ACTION,),
                tools=("submit_paper_order",),
                expires_at_utc="2026-07-10T00:00:00+00:00",
            ),
        )

        self.assertEqual(killed.disposition, AdmissionDisposition.BLOCKED)
        self.assertEqual(expired.disposition, AdmissionDisposition.BLOCKED)
        self.assertIn(
            AutonomyFindingCode.KILL_SWITCH_ENGAGED,
            {finding.code for finding in killed.findings},
        )
        self.assertIn(
            AutonomyFindingCode.MANDATE_EXPIRED,
            {finding.code for finding in expired.findings},
        )

    def test_paper_action_is_effect_admitted_but_not_external(self) -> None:
        request = self._request(
            action_class=AgentActionClass.TAKE_PAPER_ACTION,
            autonomy=AgentAutonomyLevel.AUT4_PAPER_MANAGER,
            tool_name="submit_paper_order",
        )
        report = evaluate_autonomy_admission(
            request=request,
            runtime=self._runtime(
                world=WorldFidelityLevel.W3_OUTCOME_RECONCILIATION,
                ceiling=AgentAutonomyLevel.AUT4_PAPER_MANAGER,
            ),
            mandate=self._mandate(
                autonomy=AgentAutonomyLevel.AUT4_PAPER_MANAGER,
                actions=(AgentActionClass.TAKE_PAPER_ACTION,),
                tools=("submit_paper_order",),
            ),
        )

        self.assertTrue(report.effect_admitted)
        self.assertFalse(report.external_effect_admitted)
        self.assertFalse(report.execution_allowed)

    def test_real_action_can_be_admitted_without_becoming_execution_receipt(self) -> None:
        request = self._request(
            action_class=AgentActionClass.TAKE_REAL_ACTION,
            autonomy=AgentAutonomyLevel.AUT5_REAL_OPERATOR,
            external_effect=True,
            tool_name="submit_bounded_real_order",
        )
        report = evaluate_autonomy_admission(
            request=request,
            runtime=self._runtime(
                world=WorldFidelityLevel.W4_LEARNING_POLICY,
                ceiling=AgentAutonomyLevel.AUT5_REAL_OPERATOR,
            ),
            mandate=self._mandate(
                autonomy=AgentAutonomyLevel.AUT5_REAL_OPERATOR,
                actions=(AgentActionClass.TAKE_REAL_ACTION,),
                tools=("submit_bounded_real_order",),
            ),
        )

        self.assertEqual(report.disposition, AdmissionDisposition.EFFECTIVE)
        self.assertTrue(report.effect_admitted)
        self.assertTrue(report.external_effect_admitted)
        self.assertFalse(report.execution_allowed)
        self.assertFalse(report.authority_transition)

    def test_constitutional_change_always_escalates_to_human(self) -> None:
        request = self._request(
            action_class=AgentActionClass.CHANGE_CAPITAL_CONSTITUTION,
            autonomy=AgentAutonomyLevel.AUT6_CONTINUOUS_AGENT,
            tool_name=None,
        )
        report = evaluate_autonomy_admission(
            request=request,
            runtime=self._runtime(
                world=WorldFidelityLevel.W4_LEARNING_POLICY,
                ceiling=AgentAutonomyLevel.AUT6_CONTINUOUS_AGENT,
            ),
            mandate=self._mandate(
                autonomy=AgentAutonomyLevel.AUT6_CONTINUOUS_AGENT,
                actions=(AgentActionClass.CHANGE_CAPITAL_CONSTITUTION,),
                tools=(),
            ),
        )

        self.assertEqual(report.disposition, AdmissionDisposition.ESCALATE)
        self.assertFalse(report.effective)
        self.assertEqual(
            report.findings[0].code,
            AutonomyFindingCode.CONSTITUTIONAL_CHANGE_REQUIRES_HUMAN,
        )

    def test_real_action_shape_requires_external_effect(self) -> None:
        with self.assertRaises(ValidationError):
            self._request(
                action_class=AgentActionClass.TAKE_REAL_ACTION,
                autonomy=AgentAutonomyLevel.AUT5_REAL_OPERATOR,
                external_effect=False,
            )

    def test_legacy_mandate_levels_map_without_reinterpreting_storage(self) -> None:
        self.assertEqual(
            legacy_autonomy_level("L0_read_only"),
            AgentAutonomyLevel.AUT0_CONTEXT_ASSISTANT,
        )
        self.assertEqual(
            legacy_autonomy_level("L3_bounded_delegation_candidate"),
            AgentAutonomyLevel.AUT3_DELEGATED_REVIEW,
        )
        with self.assertRaises(ValueError):
            legacy_autonomy_level("L9_unknown")


if __name__ == "__main__":
    unittest.main()
