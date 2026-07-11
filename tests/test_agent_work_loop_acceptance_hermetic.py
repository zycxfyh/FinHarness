"""Hermeticity contract: Agent Work Loop acceptance must not depend on external StateCore."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from scripts.run_agent_work_loop_acceptance import collect_acceptance_checks

from finharness.config import load_settings
from finharness.statecore.store import STATE_CORE_DB_ENV_VAR

EXPECTED_ALL_CHECKS: set[str] = {
    "all_stop_paths_reduced", "context_snapshot_frozen", "evaluation_report_linked",
    "execution_boundary_closed", "final_agent_run_receipt_linked", "max_steps_effective",
    "max_tool_calls_effective", "observation_driven_decision",
    "playbook_requirements_enforced", "real_tool_arguments",
    "result_searchable_by_work_id", "review_workspace_hydrated",
    "tool_result_refs_are_artifacts", "unavailable_tool_stop", "work_result_persisted",
}

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "data" / "state" / "state-core" / "state-core.sqlite"
DEFAULT_WAL = DEFAULT_DB.with_suffix(".sqlite-wal")
DEFAULT_SHM = DEFAULT_DB.with_suffix(".sqlite-shm")


class _EnvGuard:
    def __init__(self, key: str) -> None:
        self._key = key
        self._prev = os.environ.get(key)

    def __enter__(self) -> _EnvGuard:
        return self

    def __exit__(self, *_: object) -> None:
        load_settings.cache_clear()
        if self._prev is None:
            os.environ.pop(self._key, None)
        else:
            os.environ[self._key] = self._prev


class AgentWorkLoopAcceptanceHermeticTest(unittest.TestCase):

    def test_all_15_checks_pass_with_nonexistent_external_path(self) -> None:
        with _EnvGuard(STATE_CORE_DB_ENV_VAR), tempfile.TemporaryDirectory() as tmp:
            external_path = Path(tmp) / "missing" / "state-core.sqlite"
            os.environ[STATE_CORE_DB_ENV_VAR] = str(external_path)
            load_settings.cache_clear()
            checks = collect_acceptance_checks()
            failed = {c.check_id for c in checks if not c.passed}
            self.assertEqual(failed, set())
            self.assertFalse(external_path.exists())

    def test_env_var_restored_after_call(self) -> None:
        with _EnvGuard(STATE_CORE_DB_ENV_VAR), tempfile.TemporaryDirectory() as tmp:
            restore_path = str(Path(tmp) / "restore-test.sqlite")
            os.environ[STATE_CORE_DB_ENV_VAR] = restore_path
            load_settings.cache_clear()
            collect_acceptance_checks()
            self.assertEqual(os.environ.get(STATE_CORE_DB_ENV_VAR), restore_path)

    def test_env_var_restored_when_not_set(self) -> None:
        with _EnvGuard(STATE_CORE_DB_ENV_VAR):
            if STATE_CORE_DB_ENV_VAR in os.environ:
                os.environ.pop(STATE_CORE_DB_ENV_VAR, None)
            load_settings.cache_clear()
            collect_acceptance_checks()
            self.assertNotIn(STATE_CORE_DB_ENV_VAR, os.environ)

    def test_all_15_check_ids_are_stable(self) -> None:
        checks = collect_acceptance_checks()
        actual = {c.check_id for c in checks}
        self.assertEqual(actual, EXPECTED_ALL_CHECKS)
        self.assertEqual(len(checks), 15)

    def test_does_not_create_or_modify_default_db(self) -> None:
        existed_before = DEFAULT_DB.is_file()
        metadata_before = (
            (DEFAULT_DB.stat().st_size, DEFAULT_DB.stat().st_mtime_ns)
            if existed_before else None
        )
        wal_before = DEFAULT_WAL.exists()
        shm_before = DEFAULT_SHM.exists()
        checks = collect_acceptance_checks()
        self.assertEqual({c.check_id for c in checks if not c.passed}, set())
        if existed_before:
            self.assertTrue(DEFAULT_DB.is_file())
            self.assertEqual(metadata_before,
                             (DEFAULT_DB.stat().st_size, DEFAULT_DB.stat().st_mtime_ns))
        else:
            self.assertFalse(DEFAULT_DB.exists())
        if not wal_before:
            self.assertFalse(DEFAULT_WAL.exists())
        if not shm_before:
            self.assertFalse(DEFAULT_SHM.exists())
