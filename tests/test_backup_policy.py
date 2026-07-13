from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from finharness.backup import (
    LEGAL_HOLD_MARKER,
    BackupCapacityError,
    BackupError,
    BackupPolicy,
    BackupVerificationError,
    create_backup,
    prune_backups,
    verify_backup,
)


class BackupPolicyTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.db_path = self.root / "state-core.sqlite"
        self.receipt_root = self.root / "receipts"
        self.backup_root = self.root / "backups"
        self.receipt_root.mkdir()
        (self.receipt_root / "receipt.json").write_text(
            json.dumps({"receipt_id": "test"}), encoding="utf-8"
        )
        with sqlite3.connect(self.db_path) as connection:
            connection.execute("create table evidence (id integer primary key, value text)")
            connection.execute("insert into evidence(value) values ('bound')")
        self.policy = BackupPolicy(
            min_free_bytes=0,
            retention_count=2,
            retention_days=30,
        )

    def create(self, now: datetime | None = None) -> dict[str, object]:
        return create_backup(
            db_path=self.db_path,
            receipt_root=self.receipt_root,
            backup_root=self.backup_root,
            policy=self.policy,
            now=now,
        )

    def test_manifest_binds_both_artifacts_and_verifies_restore_readability(self) -> None:
        manifest = self.create()
        manifest_path = Path(str(manifest["manifest_ref"]))
        stored = json.loads(manifest_path.read_text(encoding="utf-8"))

        self.assertEqual(stored["schema_version"], "finharness.backup.v2")
        for artifact in stored["artifacts"].values():
            self.assertEqual(len(artifact["sha256"]), 64)
            self.assertGreater(artifact["size_bytes"], 0)
        result = verify_backup(manifest_path.parent)
        self.assertTrue(result["ok"])
        self.assertEqual(result["verified_artifacts"], ["state_core", "receipts"])

    def test_capacity_refusal_happens_before_backup_artifacts_are_written(self) -> None:
        with (
            patch(
                "finharness.backup.shutil.disk_usage",
                return_value=SimpleNamespace(total=100, used=99, free=1),
            ),
            self.assertRaisesRegex(BackupCapacityError, "capacity policy not met"),
        ):
            create_backup(
                db_path=self.db_path,
                receipt_root=self.receipt_root,
                backup_root=self.backup_root,
                policy=BackupPolicy(min_free_bytes=100, retention_count=1, retention_days=1),
            )

        self.assertEqual(list(self.backup_root.iterdir()), [])

    def test_verification_detects_corrupt_bound_artifact(self) -> None:
        manifest = self.create()
        archive = Path(str(manifest["receipts_archive"]))
        archive.write_bytes(archive.read_bytes() + b"corrupt")

        with self.assertRaisesRegex(BackupVerificationError, "size mismatch"):
            verify_backup(Path(str(manifest["manifest_ref"])).parent)

    def test_verification_detects_incomplete_backup(self) -> None:
        manifest = self.create()
        Path(str(manifest["state_core_db_snapshot"])).unlink()

        with self.assertRaisesRegex(BackupVerificationError, "artifact missing"):
            verify_backup(Path(str(manifest["manifest_ref"])).parent)

    def test_verification_rejects_manifest_path_escape(self) -> None:
        manifest = self.create()
        manifest_path = Path(str(manifest["manifest_ref"]))
        stored = json.loads(manifest_path.read_text(encoding="utf-8"))
        stored["artifacts"]["state_core"]["path"] = "../state-core.sqlite"
        manifest_path.write_text(json.dumps(stored), encoding="utf-8")

        with self.assertRaisesRegex(BackupVerificationError, "unsafe artifact path"):
            verify_backup(manifest_path)

    def test_verification_rejects_unbound_retention_timestamp(self) -> None:
        manifest = self.create()
        manifest_path = Path(str(manifest["manifest_ref"]))
        stored = json.loads(manifest_path.read_text(encoding="utf-8"))
        stored["generated_at_utc"] = "2000-01-01T00:00:00+00:00"
        manifest_path.write_text(json.dumps(stored), encoding="utf-8")

        with self.assertRaisesRegex(BackupVerificationError, "does not bind"):
            verify_backup(manifest_path)

    def test_backup_rejects_receipt_symlink(self) -> None:
        outside = self.root / "outside.json"
        outside.write_text("secret", encoding="utf-8")
        (self.receipt_root / "linked.json").symlink_to(outside)

        with self.assertRaisesRegex(BackupError, "symlink"):
            self.create()

    def test_retention_is_dry_run_and_preserves_newest_held_and_recent(self) -> None:
        now = datetime(2026, 7, 13, tzinfo=UTC)
        oldest = self.create(now - timedelta(days=90))
        held = self.create(now - timedelta(days=60))
        recent = self.create(now - timedelta(days=5))
        newest = self.create(now)
        held_dir = Path(str(held["manifest_ref"])).parent
        (held_dir / LEGAL_HOLD_MARKER).touch()

        preview = prune_backups(self.backup_root, policy=self.policy, dry_run=True, now=now)
        oldest_dir = Path(str(oldest["manifest_ref"])).parent
        self.assertEqual(preview["candidates"], [oldest_dir.name])
        self.assertTrue(oldest_dir.exists())
        self.assertIn(held_dir.name, preview["held"])

        applied = prune_backups(self.backup_root, policy=self.policy, dry_run=False, now=now)
        self.assertEqual(applied["deleted"], [oldest_dir.name])
        self.assertFalse(oldest_dir.exists())
        self.assertTrue(held_dir.exists())
        self.assertTrue(Path(str(recent["manifest_ref"])).parent.exists())
        self.assertTrue(Path(str(newest["manifest_ref"])).parent.exists())

    def test_retention_skips_invalid_directories(self) -> None:
        valid = self.create(datetime(2026, 7, 13, tzinfo=UTC))
        invalid = self.backup_root / "operator-notes"
        invalid.mkdir()

        result = prune_backups(
            self.backup_root,
            policy=BackupPolicy(min_free_bytes=0, retention_count=1, retention_days=1),
            dry_run=False,
            now=datetime(2026, 9, 1, tzinfo=UTC),
        )

        self.assertEqual(result["newest_valid"], Path(str(valid["manifest_ref"])).parent.name)
        self.assertEqual(result["skipped_invalid"], ["operator-notes"])
        self.assertTrue(invalid.exists())


if __name__ == "__main__":
    unittest.main()
