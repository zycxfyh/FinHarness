"""Runtime configuration for the FinHarness local services."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import keyring
from pydantic_settings import BaseSettings, SettingsConfigDict

from finharness.project_paths import ROOT
from finharness.statecore.receipt_index import DEFAULT_RECEIPT_ROOT
from finharness.statecore.store import DEFAULT_STATE_CORE_DB_PATH


class FinHarnessConfigError(RuntimeError):
    """Raised when runtime configuration cannot be loaded safely."""


class FinHarnessSettings(BaseSettings):
    """Settings read from environment, with broker secrets held in keyring."""

    model_config = SettingsConfigDict(env_prefix="FINHARNESS_", extra="ignore")

    state_core_db_path: Path = DEFAULT_STATE_CORE_DB_PATH
    receipt_root: Path = DEFAULT_RECEIPT_ROOT
    backup_root: Path = ROOT / "data" / "backups" / "state-core"
    backup_min_free_bytes: int = 512 * 1024 * 1024
    backup_retention_count: int = 7
    backup_retention_days: int = 30
    broker_keyring_service: str = "finharness.broker"
    broker_keyring_username: str = "default"
    log_json: bool = True

    def get_broker_key(self) -> str | None:
        """Read the broker key from the OS keyring; never from repo files."""
        try:
            return keyring.get_password(
                self.broker_keyring_service,
                self.broker_keyring_username,
            )
        except Exception as exc:
            raise FinHarnessConfigError(f"broker keyring lookup failed: {exc}") from exc


@lru_cache(maxsize=1)
def load_settings() -> FinHarnessSettings:
    return FinHarnessSettings()
