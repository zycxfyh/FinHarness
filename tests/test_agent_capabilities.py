from __future__ import annotations

import unittest

from pydantic import ValidationError

from finharness.agent_capabilities import (
    CAPITAL_CONTEXT_TOOL_NAMES,
    CURRENT_AGENT_TOOL_NAMES,
    DEFAULT_AGENT_PROFILE,
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
                self.assertFalse(
                    profile_allows_capability(
                        profile.name,
                        AgentCapability.CAPITAL_EXECUTE,
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
