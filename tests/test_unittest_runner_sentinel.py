"""Positive/negative sentinel for unittest runner.

Passes under normal conditions.
Fails when FINHARNESS_FAIL_UNITTEST_SENTINEL=1.
"""

from __future__ import annotations

import os
import unittest


class TestUnittestRunnerSentinel(unittest.TestCase):
    def test_sentinel_passes_in_normal_environment(self) -> None:
        """The sentinel must pass when the environment variable is not set."""
        self.assertNotIn("FINHARNESS_FAIL_UNITTEST_SENTINEL", os.environ)

    def test_sentinel_fails_when_env_var_set(self) -> None:
        """The sentinel must fail when FINHARNESS_FAIL_UNITTEST_SENTINEL=1."""
        if os.environ.get("FINHARNESS_FAIL_UNITTEST_SENTINEL") == "1":
            self.fail("unittest sentinel triggered: FINHARNESS_FAIL_UNITTEST_SENTINEL=1")
        # Otherwise, nothing to assert — the test passes.
