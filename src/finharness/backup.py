"""Capacity-gated, verifiable local backups for State Core evidence."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import tarfile
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path, PurePosixPath
from typing import Any

from finharness.config import load_settings
from finharness.statecore.receipt_io import atomic_write_json, resolve_under

BACKUP_SCHEMA_VERSION = "finharness.backup.v2"
LEGAL_HOLD_MARKER = ".legal-hold"


class BackupError(RuntimeError):
    """Base class for predictable backup-policy failures."""


class BackupCapacityError(BackupError):
    """Raised before backup artifacts are written when capacity is insufficient."""


class BackupVerificationError(BackupError):
    """Raised when a backup is incomplete, corrupt, or unsafe to restore."""


@dataclass(frozen=True)
class BackupPolicy:
    """Operator-controlled capacity and retention boundaries."""

    min_free_bytes: int = 512 * 1024 * 1024
    retention_count: int = 7
    retention_days: int = 30

    def __post_init__(self) -> None:
        if self.min_free_bytes < 0:
            raise ValueError("min_free_bytes must be non-negative")
        if self.retention_count < 1:
            raise ValueError("retention_count must be at least 1")
        if self.retention_days < 1:
            raise ValueError("retention_days must be at least 1")


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _backup_id(now: datetime) -> str:
    return now.astimezone(UTC).strftime("%Y%m%dT%H%M%S.%fZ")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _receipt_files(receipt_root: Path) -> list[Path]:
    if not receipt_root.is_dir():
        raise FileNotFoundError(f"receipt root missing: {receipt_root}")
    paths = sorted(receipt_root.rglob("*"))
    symlinks = [path for path in paths if path.is_symlink()]
    if symlinks:
        raise BackupError(f"receipt tree contains unsupported symlink: {symlinks[0]}")
    return [path for path in paths if path.is_file()]


def _estimated_required_bytes(source_db: Path, receipt_files: list[Path]) -> int:
    if not source_db.is_file():
        raise FileNotFoundError(f"state-core sqlite file missing: {source_db}")
    return source_db.stat().st_size + sum(path.stat().st_size for path in receipt_files)


def _require_capacity(root: Path, *, required_bytes: int, reserve_bytes: int) -> int:
    root.mkdir(parents=True, exist_ok=True)
    free_bytes = shutil.disk_usage(root).free
    threshold = required_bytes + reserve_bytes
    if free_bytes < threshold:
        raise BackupCapacityError(
            "backup capacity policy not met: "
            f"free_bytes={free_bytes}, required_bytes={required_bytes}, "
            f"reserve_bytes={reserve_bytes}, threshold_bytes={threshold}"
        )
    return free_bytes


def _vacuum_into(source_db: Path, target_db: Path) -> None:
    target_db.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(f"file:{source_db}?mode=ro", uri=True) as connection:
        connection.execute("VACUUM main INTO ?", (str(target_db),))


def _tar_receipts(files: list[Path], receipt_root: Path, target_tar: Path) -> int:
    target_tar.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(target_tar, "w:gz") as archive:
        for path in files:
            archive.add(path, arcname=Path("receipts") / path.relative_to(receipt_root))
    return len(files)


def _artifact(path: Path, *, relative_path: str, file_count: int | None = None) -> dict[str, Any]:
    result: dict[str, Any] = {
        "path": relative_path,
        "size_bytes": path.stat().st_size,
        "sha256": _sha256(path),
    }
    if file_count is not None:
        result["file_count"] = file_count
    return result


def create_backup(
    *,
    db_path: str | Path | None = None,
    receipt_root: str | Path | None = None,
    backup_root: str | Path | None = None,
    policy: BackupPolicy | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Create and atomically publish a capacity-gated, self-verifying backup."""
    settings = load_settings()
    source_db = Path(db_path or settings.state_core_db_path)
    source_receipts = Path(receipt_root or settings.receipt_root)
    root = Path(backup_root or settings.backup_root)
    active_policy = policy or BackupPolicy(
        min_free_bytes=settings.backup_min_free_bytes,
        retention_count=settings.backup_retention_count,
        retention_days=settings.backup_retention_days,
    )
    generated_at = (now or _utc_now()).astimezone(UTC)
    backup_id = _backup_id(generated_at)
    final_dir = resolve_under(root, backup_id)
    staging_dir = resolve_under(root, f".incomplete-{backup_id}-{os.getpid()}")
    if final_dir.exists() or staging_dir.exists():
        raise BackupError(f"backup destination already exists: {final_dir}")

    files = _receipt_files(source_receipts)
    required_bytes = _estimated_required_bytes(source_db, files)
    free_bytes = _require_capacity(
        root,
        required_bytes=required_bytes,
        reserve_bytes=active_policy.min_free_bytes,
    )
    db_snapshot = staging_dir / "state-core.sqlite"
    receipts_archive = staging_dir / "receipts.tar.gz"
    manifest_path = staging_dir / "manifest.json"
    try:
        staging_dir.mkdir()
        _vacuum_into(source_db, db_snapshot)
        receipt_file_count = _tar_receipts(files, source_receipts, receipts_archive)
        manifest: dict[str, Any] = {
            "schema_version": BACKUP_SCHEMA_VERSION,
            "backup_id": backup_id,
            "generated_at_utc": generated_at.isoformat(),
            "source": {
                "state_core_db_path": str(source_db),
                "receipt_root": str(source_receipts),
            },
            "capacity": {
                "free_bytes_at_preflight": free_bytes,
                "estimated_required_bytes": required_bytes,
                "minimum_free_reserve_bytes": active_policy.min_free_bytes,
            },
            "artifacts": {
                "state_core": _artifact(db_snapshot, relative_path="state-core.sqlite"),
                "receipts": _artifact(
                    receipts_archive,
                    relative_path="receipts.tar.gz",
                    file_count=receipt_file_count,
                ),
            },
            # Compatibility fields point at the final, atomically published paths.
            "state_core_db_snapshot": str(final_dir / "state-core.sqlite"),
            "receipts_archive": str(final_dir / "receipts.tar.gz"),
            "receipt_file_count": receipt_file_count,
            "execution_allowed": False,
            "release_authorization": False,
        }
        atomic_write_json(manifest_path, manifest)
        verify_backup(staging_dir)
        staging_dir.replace(final_dir)
    except Exception:
        shutil.rmtree(staging_dir, ignore_errors=True)
        raise
    return manifest | {"manifest_ref": str(final_dir / "manifest.json")}


def _safe_artifact_path(backup_dir: Path, artifact: dict[str, Any]) -> Path:
    relative = artifact.get("path")
    if not isinstance(relative, str) or not relative or Path(relative).is_absolute():
        raise BackupVerificationError("manifest artifact path must be a non-empty relative path")
    try:
        return resolve_under(backup_dir, relative)
    except ValueError as exc:
        raise BackupVerificationError(f"unsafe artifact path: {relative}") from exc


def _verify_artifact(backup_dir: Path, name: str, artifact: dict[str, Any]) -> Path:
    path = _safe_artifact_path(backup_dir, artifact)
    if not path.is_file():
        raise BackupVerificationError(f"incomplete backup: {name} artifact missing")
    expected_size = artifact.get("size_bytes")
    expected_hash = artifact.get("sha256")
    if not isinstance(expected_size, int) or path.stat().st_size != expected_size:
        raise BackupVerificationError(f"corrupt backup: {name} size mismatch")
    if not isinstance(expected_hash, str) or _sha256(path) != expected_hash:
        raise BackupVerificationError(f"corrupt backup: {name} sha256 mismatch")
    return path


def _verify_sqlite(path: Path) -> None:
    try:
        with sqlite3.connect(f"file:{path}?mode=ro&immutable=1", uri=True) as connection:
            result = connection.execute("PRAGMA quick_check").fetchone()
    except sqlite3.Error as exc:
        raise BackupVerificationError(f"corrupt backup: sqlite open/check failed: {exc}") from exc
    if result != ("ok",):
        raise BackupVerificationError(f"corrupt backup: sqlite quick_check returned {result!r}")


def _verify_receipt_archive(path: Path, expected_count: int) -> None:
    count = 0
    try:
        with tarfile.open(path, "r:gz") as archive:
            for member in archive:
                parts = PurePosixPath(member.name).parts
                if (
                    member.name.startswith("/")
                    or not parts
                    or parts[0] != "receipts"
                    or ".." in parts
                    or member.issym()
                    or member.islnk()
                    or not (member.isfile() or member.isdir())
                ):
                    raise BackupVerificationError(f"unsafe receipt archive member: {member.name}")
                if member.isfile():
                    extracted = archive.extractfile(member)
                    if extracted is None:
                        raise BackupVerificationError(
                            f"incomplete receipt archive member: {member.name}"
                        )
                    while extracted.read(1024 * 1024):
                        pass
                    count += 1
    except (tarfile.TarError, OSError, EOFError) as exc:
        raise BackupVerificationError(f"corrupt backup: receipt archive failed: {exc}") from exc
    if count != expected_count:
        raise BackupVerificationError(
            f"incomplete backup: receipt file count mismatch ({count} != {expected_count})"
        )


def verify_backup(backup: str | Path) -> dict[str, Any]:
    """Verify manifest bindings plus SQLite and receipt-archive restore readability."""
    supplied = Path(backup)
    manifest_path = supplied if supplied.name == "manifest.json" else supplied / "manifest.json"
    backup_dir = manifest_path.parent.resolve()
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BackupVerificationError(f"incomplete backup: manifest unreadable: {exc}") from exc
    if manifest.get("schema_version") != BACKUP_SCHEMA_VERSION:
        raise BackupVerificationError("unsupported or missing backup schema version")
    backup_id = manifest.get("backup_id")
    generated_at_raw = manifest.get("generated_at_utc")
    try:
        generated_at = datetime.fromisoformat(generated_at_raw)
    except (TypeError, ValueError) as exc:
        raise BackupVerificationError("invalid generated_at_utc") from exc
    if generated_at.tzinfo is None or backup_id != _backup_id(generated_at):
        raise BackupVerificationError("backup_id does not bind generated_at_utc")
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, dict):
        raise BackupVerificationError("incomplete backup: artifacts manifest missing")
    state_core = artifacts.get("state_core")
    receipts = artifacts.get("receipts")
    if not isinstance(state_core, dict) or not isinstance(receipts, dict):
        raise BackupVerificationError("incomplete backup: required artifacts missing")
    db_path = _verify_artifact(backup_dir, "state_core", state_core)
    archive_path = _verify_artifact(backup_dir, "receipts", receipts)
    expected_count = receipts.get("file_count")
    if not isinstance(expected_count, int) or expected_count < 0:
        raise BackupVerificationError("invalid receipt file count")
    _verify_sqlite(db_path)
    _verify_receipt_archive(archive_path, expected_count)
    return {
        "ok": True,
        "backup_id": backup_id,
        "manifest_ref": str(manifest_path),
        "verified_artifacts": ["state_core", "receipts"],
        "execution_allowed": False,
    }


def _valid_backup_records(root: Path) -> tuple[list[tuple[datetime, Path]], list[str]]:
    valid: list[tuple[datetime, Path]] = []
    skipped: list[str] = []
    if not root.exists():
        return valid, skipped
    for path in sorted(root.iterdir()):
        if not path.is_dir() or path.is_symlink() or path.name.startswith(".incomplete-"):
            continue
        try:
            verify_backup(path)
            payload = json.loads((path / "manifest.json").read_text(encoding="utf-8"))
            generated_at = datetime.fromisoformat(payload["generated_at_utc"])
            if generated_at.tzinfo is None:
                raise ValueError("generated_at_utc lacks timezone")
            valid.append((generated_at.astimezone(UTC), path))
        except (BackupVerificationError, KeyError, TypeError, ValueError, OSError):
            skipped.append(path.name)
    valid.sort(key=lambda item: item[0], reverse=True)
    return valid, skipped


def prune_backups(
    backup_root: str | Path,
    *,
    policy: BackupPolicy,
    dry_run: bool = True,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Apply retention only to verified backups, conservatively and dry-run by default."""
    root = Path(backup_root).resolve()
    valid, skipped = _valid_backup_records(root)
    current = (now or _utc_now()).astimezone(UTC)
    cutoff = current - timedelta(days=policy.retention_days)
    protected = {path for _, path in valid[: policy.retention_count]}
    if valid:
        protected.add(valid[0][1])
    held = {path for _, path in valid if (path / LEGAL_HOLD_MARKER).is_file()}
    candidates = [
        path
        for generated_at, path in valid
        if path not in protected and path not in held and generated_at < cutoff
    ]
    deleted: list[str] = []
    if not dry_run:
        for path in candidates:
            safe_path = resolve_under(root, path.name)
            if safe_path == root or safe_path.is_symlink():
                raise BackupError(f"refusing unsafe prune target: {safe_path}")
            shutil.rmtree(safe_path)
            deleted.append(path.name)
    return {
        "ok": True,
        "dry_run": dry_run,
        "candidates": [path.name for path in candidates],
        "deleted": deleted,
        "held": sorted(path.name for path in held),
        "skipped_invalid": sorted(skipped),
        "newest_valid": valid[0][1].name if valid else None,
        "execution_allowed": False,
    }
