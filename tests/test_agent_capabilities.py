from __future__ import annotations

import unittest

from pydantic import ValidationError

from finharness.agent_capabilities import (
    CAPITAL_CONTEXT_TOOL_NAMES,
    CURRENT_AGENT_TOOL_NAMES,
    DEFAULT_AGENT_PROFILE,
    DRAFT_PROPOSAL_TOOL_NAMES,
    REVIEW_NOTE_TOOL_NAMES,
    AgentCapability,
    AgentCapabilityProfile,
    get_agent_profile,
    list_agent_profiles,
    profile_allows_capability,
    tool_names_for_profile,
)

MUTATING_AGENT_TOOL_NAMES = {
    "create_governed_proposal",
    "revise_governed_proposal_scaffold",
    "create_governed_attestation",
    "approve_proposal",
    "reject_proposal",
    "create_action_intent",
    "execute_order",
    "transfer_funds",
}


class AgentCapabilitiesTest(unittest.TestCase):
    def test_default_profile_exists_and_is_read_only(self) -> None:
        profile = get_agent_profile()

        self.assertEqual(profile.name, "default")
        self.assertFalse(profile.execution_allowed)
        self.assertEqual(
            profile.capabilities,
            (AgentCapability.CAPITAL_READ, AgentCapability.CAPITAL_EXPLAIN),
        )
        self.assertIn("Not execution authorization.", profile.non_claims)

    def test_default_profile_includes_read_only_context_tools(self) -> None:
        names = set(tool_names_for_profile("default"))

        self.assertTrue(set(CAPITAL_CONTEXT_TOOL_NAMES).issubset(names))

    def test_no_profile_exposes_mutating_agent_tools(self) -> None:
        for profile in list_agent_profiles():
            with self.subTest(profile=profile.name):
                self.assertTrue(MUTATING_AGENT_TOOL_NAMES.isdisjoint(profile.tool_names))

    def test_capital_execute_is_not_enabled_by_current_profiles(self) -> None:
        for profile in list_agent_profiles():
            with self.subTest(profile=profile.name):
                self.assertNotIn(AgentCapability.CAPITAL_EXECUTE, profile.capabilities)
                self.assertNotIn(
                    AgentCapability.CAPITAL_EXECUTE,
                    profile.planned_capabilities,
                )
                self.assertFalse(
                    profile_allows_capability(
                        profile.name,
                        AgentCapability.CAPITAL_EXECUTE,
                    )
                )

    def test_review_draft_profile_allows_proposal_drafts_only(self) -> None:
        review_profile = get_agent_profile("review-draft")
        self.assertIn(AgentCapability.CAPITAL_PROPOSE, review_profile.capabilities)
        self.assertNotIn(AgentCapability.CAPITAL_REVIEW_NOTE, review_profile.capabilities)
        self.assertTrue(
            profile_allows_capability(
                "review-draft",
                AgentCapability.CAPITAL_PROPOSE,
            )
        )
        self.assertFalse(
            profile_allows_capability(
                "review-draft",
                AgentCapability.CAPITAL_REVIEW_NOTE,
            )
        )
        self.assertTrue(set(DRAFT_PROPOSAL_TOOL_NAMES).issubset(review_profile.tool_names))
        self.assertTrue(set(DRAFT_PROPOSAL_TOOL_NAMES).isdisjoint(DEFAULT_AGENT_PROFILE.tool_names))

    def test_review_note_profile_allows_review_note_drafts_only(self) -> None:
        profile = get_agent_profile("review-note")

        self.assertIn(AgentCapability.CAPITAL_REVIEW_NOTE, profile.capabilities)
        self.assertNotIn(AgentCapability.CAPITAL_PROPOSE, profile.capabilities)
        self.assertTrue(
            profile_allows_capability(
                "review-note",
                AgentCapability.CAPITAL_REVIEW_NOTE,
            )
        )
        self.assertFalse(
            profile_allows_capability(
                "review-note",
                AgentCapability.CAPITAL_PROPOSE,
            )
        )
        self.assertTrue(set(REVIEW_NOTE_TOOL_NAMES).issubset(profile.tool_names))
        self.assertTrue(set(REVIEW_NOTE_TOOL_NAMES).isdisjoint(DEFAULT_AGENT_PROFILE.tool_names))
        self.assertTrue(set(REVIEW_NOTE_TOOL_NAMES).isdisjoint(tool_names_for_profile("review-draft")))

    def test_simulation_capability_is_planned_not_active(self) -> None:
        simulation_profile = get_agent_profile("simulation")
        self.assertNotIn(AgentCapability.CAPITAL_SIMULATE, simulation_profile.capabilities)
        self.assertIn(
            AgentCapability.CAPITAL_SIMULATE,
            simulation_profile.planned_capabilities,
        )
        self.assertFalse(
            profile_allows_capability(
                "simulation",
                AgentCapability.CAPITAL_SIMULATE,
            )
        )

    def test_execution_allowed_is_always_false(self) -> None:
        for profile in list_agent_profiles():
            with self.subTest(profile=profile.name):
                self.assertFalse(profile.execution_allowed)

        with self.assertRaises(ValidationError):
            AgentCapabilityProfile(
                name="bad",
                description="Bad profile.",
                capabilities=(AgentCapability.CAPITAL_READ,),
                tool_names=(),
                execution_allowed=True,
            )

    def test_unknown_profile_raises_clear_error(self) -> None:
        with self.assertRaisesRegex(ValueError, "unknown agent capability profile"):
            get_agent_profile("missing")

    def test_default_tool_names_are_stable_and_ordered(self) -> None:
        self.assertEqual(tool_names_for_profile("default"), CURRENT_AGENT_TOOL_NAMES)
        self.assertEqual(DEFAULT_AGENT_PROFILE.tool_names, CURRENT_AGENT_TOOL_NAMES)


if __name__ == "__main__":
    unittest.main()
