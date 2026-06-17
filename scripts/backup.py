"""Create a local state-core backup without relying on git."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import tarfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from finharness.config import load_settings
from finharness.statecore.receipt_io import atomic_write_json


def _stamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def _vacuum_into(source_db: Path, target_db: Path) -> None:
    if not source_db.exists():
        raise FileNotFoundError(f"state-core sqlite file missing: {source_db}")
    target_db.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(f"file:{source_db}?mode=ro", uri=True) as connection:
        connection.execute("VACUUM main INTO ?", (str(target_db),))


def _tar_receipts(receipt_root: Path, target_tar: Path) -> int:
    if not receipt_root.exists():
        raise FileNotFoundError(f"receipt root missing: {receipt_root}")
    target_tar.parent.mkdir(parents=True, exist_ok=True)
    files = sorted(path for path in receipt_root.rglob("*") if path.is_file())
    with tarfile.open(target_tar, "w:gz") as archive:
        for path in files:
            archive.add(path, arcname=Path("receipts") / path.relative_to(receipt_root))
    return len(files)


def create_backup(
    *,
    db_path: str | Path | None = None,
    receipt_root: str | Path | None = None,
    backup_root: str | Path | None = None,
) -> dict[str, Any]:
    settings = load_settings()
    source_db = Path(db_path or settings.state_core_db_path)
    source_receipts = Path(receipt_root or settings.receipt_root)
    root = Path(backup_root or settings.backup_root)
    stamp = _stamp()
    backup_dir = root / stamp
    db_snapshot = backup_dir / "state-core.sqlite"
    receipts_archive = backup_dir / "receipts.tar.gz"
    manifest_path = backup_dir / "manifest.json"

    _vacuum_into(source_db, db_snapshot)
    receipt_file_count = _tar_receipts(source_receipts, receipts_archive)
    manifest = {
        "schema_version": "finharness.backup.v1",
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "state_core_db_path": str(source_db),
        "state_core_db_snapshot": str(db_snapshot),
        "receipt_root": str(source_receipts),
        "receipts_archive": str(receipts_archive),
        "receipt_file_count": receipt_file_count,
        "execution_allowed": False,
        "release_authorization": False,
    }
    atomic_write_json(manifest_path, manifest)
    return manifest | {"manifest_ref": str(manifest_path)}


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Back up state-core DB and receipts.")
    parser.add_argument("--db-path")
    parser.add_argument("--receipt-root")
    parser.add_argument("--backup-root")
    ns = parser.parse_args(argv)
    try:
        manifest = create_backup(
            db_path=ns.db_path,
            receipt_root=ns.receipt_root,
            backup_root=ns.backup_root,
        )
    except Exception as exc:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": str(exc),
                    "execution_allowed": False,
                },
                ensure_ascii=False,
            )
        )
        return 1
    print(json.dumps({"ok": True, **manifest}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
