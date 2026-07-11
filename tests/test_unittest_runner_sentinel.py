"""Positive/negative sentinel for unittest runner.

Passes under normal conditions.
Fails when FINHARNESS_FAIL_UNITTEST_SENTINEL=1.
"""

from __future__ import annotations

import os
import unittest


class TestUnittestRunnerSentinel(unittest.TestCase):
    def test_unittest_runner_sentinel(self) -> None:
        if os.environ.get("FINHARNESS_FAIL_UNITTEST_SENTINEL") == "1":
            self.fail(
                "unittest sentinel triggered: "
                "FINHARNESS_FAIL_UNITTEST_SENTINEL=1"
            )
