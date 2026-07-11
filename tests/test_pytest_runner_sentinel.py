# finharness-test-runner: pytest
"""Positive/negative sentinel for pytest runner.

Passes under normal conditions.
Fails when FINHARNESS_FAIL_PYTEST_SENTINEL=1.
"""

from __future__ import annotations

import os

import pytest


def test_sentinel_passes_in_normal_environment() -> None:
    """The sentinel must pass when the environment variable is not set."""
    assert "FINHARNESS_FAIL_PYTEST_SENTINEL" not in os.environ


def test_sentinel_fails_when_env_var_set() -> None:
    """The sentinel must fail when FINHARNESS_FAIL_PYTEST_SENTINEL=1."""
    if os.environ.get("FINHARNESS_FAIL_PYTEST_SENTINEL") == "1":
        pytest.fail("pytest sentinel triggered: FINHARNESS_FAIL_PYTEST_SENTINEL=1")
    # Otherwise, nothing to assert — the test passes.
