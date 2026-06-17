from __future__ import annotations

import json
import sqlite3
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.backup import create_backup

from finharness.config import FinHarnessConfigError, FinHarnessSettings
from finharness.runtime_log import configure_logging, get_logger
from finharness.statecore.models import Account
from finharness.statecore.receipt_io import atomic_write_json
from finharness.statecore.store import init_state_core, write_records


class StateCoreSupportTest(unittest.TestCase):
    def test_settings_reads_broker_key_from_keyring_only(self) -> None:
        settings = FinHarnessSettings(
            broker_keyring_service="svc",
            broker_keyring_username="user",
        )

        with patch("finharness.config.keyring.get_password", return_value="secret") as get:
            self.assertEqual(settings.get_broker_key(), "secret")

        get.assert_called_once_with("svc", "user")
        self.assertNotIn("secret", json.dumps(settings.model_dump(), default=str))

    def test_keyring_failure_is_explicit(self) -> None:
        settings = FinHarnessSettings(
            broker_keyring_service="svc",
            broker_keyring_username="user",
        )

        with (
            patch("finharness.config.keyring.get_password", side_effect=RuntimeError("nope")),
            self.assertRaises(FinHarnessConfigError),
        ):
            settings.get_broker_key()

    def test_runtime_log_configures_structlog(self) -> None:
        configure_logging()
        logger = get_logger("finharness.tests")
        self.assertTrue(hasattr(logger, "info"))

    def test_atomic_write_json_leaves_complete_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "receipt.json"

            atomic_write_json(path, {"kind": "first", "execution_allowed": False})
            atomic_write_json(path, {"kind": "second", "execution_allowed": False})

            self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["kind"], "second")
            self.assertEqual(list(Path(tmp).glob("*.tmp")), [])

    def test_backup_creates_sqlite_snapshot_receipts_archive_and_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            db_path = root / "state-core.sqlite"
            receipt_root = root / "receipts"
            backup_root = root / "backups"
            receipt_root.mkdir()
            (receipt_root / "sample.json").write_text(
                json.dumps({"receipt_id": "sample", "kind": "test"}),
                encoding="utf-8",
            )
            engine = init_state_core(db_path)
            self.addCleanup(engine.dispose)
            write_records(
                [
                    Account(
                        account_id="acct_backup",
                        kind="broker",
                        venue="manual",
                        display_name="Backup Account",
                    )
                ],
                engine=engine,
            )

            manifest = create_backup(
                db_path=db_path,
                receipt_root=receipt_root,
                backup_root=backup_root,
            )

            manifest_path = Path(manifest["manifest_ref"])
            db_snapshot = Path(manifest["state_core_db_snapshot"])
            receipts_archive = Path(manifest["receipts_archive"])
            self.assertTrue(manifest_path.exists())
            self.assertTrue(db_snapshot.exists())
            self.assertTrue(receipts_archive.exists())
            self.assertEqual(manifest["receipt_file_count"], 1)
            self.assertFalse(manifest["execution_allowed"])

            with sqlite3.connect(db_snapshot) as connection:
                count = connection.execute("select count(*) from accounts").fetchone()[0]
            self.assertEqual(count, 1)
            with tarfile.open(receipts_archive, "r:gz") as archive:
                self.assertIn("receipts/sample.json", archive.getnames())


if __name__ == "__main__":
    unittest.main()
