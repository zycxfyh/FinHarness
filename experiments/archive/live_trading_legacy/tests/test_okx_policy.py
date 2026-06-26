"""Behavior tests for the OKX CLI allowlist policy (fail-closed + red-team F8)."""

from __future__ import annotations

import unittest

from finharness.okx_policy import (
    BLOCKED_TOKENS,
    COMMON_READ_FLAGS,
    MUTATION_FLAGS,
    action_is_mutating,
    action_is_read_only,
    allowed_flags,
    blocked_tokens,
    disallowed_flag,
    looks_like_flag,
)


class ActionClassificationTests(unittest.TestCase):
    def test_known_read_actions_are_read_only_not_mutating(self) -> None:
        self.assertTrue(action_is_read_only("market", "ticker"))
        self.assertTrue(action_is_read_only("account", "balance"))
        self.assertFalse(action_is_mutating("market", "ticker"))

    def test_known_mutating_actions_are_mutating_not_read_only(self) -> None:
        self.assertTrue(action_is_mutating("spot", "place"))
        self.assertTrue(action_is_mutating("account", "transfer"))
        self.assertFalse(action_is_read_only("spot", "place"))

    def test_unknown_module_or_action_is_neither(self) -> None:
        # fail-closed: not on any allowlist => not classified as read or mutating
        self.assertFalse(action_is_read_only("market", "drain-wallet"))
        self.assertFalse(action_is_mutating("market", "drain-wallet"))
        self.assertFalse(action_is_read_only("totally-unknown", "balance"))
        self.assertFalse(action_is_mutating("totally-unknown", "place"))


class AllowedFlagsTests(unittest.TestCase):
    def test_read_action_gets_common_read_flags(self) -> None:
        self.assertEqual(allowed_flags("market", "candles"), COMMON_READ_FLAGS)

    def test_mutating_action_gets_its_specific_flag_set(self) -> None:
        self.assertEqual(allowed_flags("spot", "place"), MUTATION_FLAGS["place"])
        self.assertEqual(allowed_flags("account", "transfer"), MUTATION_FLAGS["transfer"])

    def test_unknown_action_allows_no_flags(self) -> None:
        # fail-closed: empty set means every flag will be rejected downstream
        self.assertEqual(allowed_flags("market", "unknown-action"), frozenset())


class LooksLikeFlagTests(unittest.TestCase):
    def test_dashed_tokens_are_flags(self) -> None:
        self.assertTrue(looks_like_flag("--instId"))
        self.assertTrue(looks_like_flag("-x"))

    def test_negative_numbers_are_not_flags(self) -> None:
        # values like -1 / -0.5 must not be mistaken for flags
        self.assertFalse(looks_like_flag("-1"))
        self.assertFalse(looks_like_flag("-0.5"))

    def test_plain_value_and_lone_dash_are_not_flags(self) -> None:
        self.assertFalse(looks_like_flag("BTC-USDT"))
        self.assertFalse(looks_like_flag("-"))


class DisallowedFlagTests(unittest.TestCase):
    def test_permitted_read_flag_passes(self) -> None:
        self.assertIsNone(
            disallowed_flag("market", "candles", ["--instId", "BTC-USDT", "--bar", "1H"])
        )

    def test_permitted_mutation_flag_passes(self) -> None:
        self.assertIsNone(
            disallowed_flag("spot", "place", ["--instId", "BTC-USDT", "--side", "buy"])
        )

    def test_flag_allowed_for_another_action_is_rejected(self) -> None:
        # --side is a place flag; it is not permitted on a read command
        self.assertEqual(disallowed_flag("market", "candles", ["--side", "buy"]), "--side")

    def test_red_team_f8_equals_form_is_rejected(self) -> None:
        # the original bypass: --live=1 / --profile=live slipped past an exact denylist.
        # the allowlist checks the name before '=', so these are caught fail-closed.
        self.assertEqual(disallowed_flag("market", "candles", ["--live=1"]), "--live")
        self.assertEqual(disallowed_flag("spot", "place", ["--profile=live"]), "--profile")

    def test_negative_number_value_is_not_treated_as_flag(self) -> None:
        # a permitted flag carrying a negative value must not trip the gate
        self.assertIsNone(disallowed_flag("spot", "place", ["--px", "-1"]))


class BlockedTokensTests(unittest.TestCase):
    def test_blocked_token_in_module_action_or_args_is_reported(self) -> None:
        self.assertEqual(blocked_tokens("bot", "place", []), ["bot"])
        self.assertEqual(blocked_tokens("account", "earn", []), ["earn"])
        self.assertEqual(blocked_tokens("market", "ticker", ["smartmoney"]), ["smartmoney"])

    def test_clean_command_has_no_blocked_tokens(self) -> None:
        self.assertEqual(blocked_tokens("market", "ticker", ["--instId", "BTC-USDT"]), [])

    def test_blocklist_is_non_empty_guard(self) -> None:
        # guards against an accidental empty denylist silently disabling this control
        self.assertIn("bot", BLOCKED_TOKENS)


if __name__ == "__main__":
    unittest.main()
