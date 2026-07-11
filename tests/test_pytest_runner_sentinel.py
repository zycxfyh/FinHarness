# finharness-test-runner: pytest
"""Positive/negative sentinel for pytest runner.

Passes under normal conditions.
Fails when FINHARNESS_FAIL_PYTEST_SENTINEL=1.
"""

from __future__ import annotations

import os

import pytest


def test_pytest_runner_sentinel() -> None:
    if os.environ.get("FINHARNESS_FAIL_PYTEST_SENTINEL") == "1":
        pytest.fail(
            "pytest sentinel triggered: "
            "FINHARNESS_FAIL_PYTEST_SENTINEL=1"
        )
