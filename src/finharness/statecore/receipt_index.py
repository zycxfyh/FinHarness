"""Read-only receipt-file indexing for the state core."""

from __future__ import annotations

import json
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import Engine

from finharness.market_data import ROOT
from finharness.statecore.models import ReceiptIndex
from finharness.statecore.store import StateCoreStoreError, upsert_records

DEFAULT_RECEIPT_ROOT = ROOT / "data" / "receipts"
RECEIPT_REF_KEYS = {
    "receipt_id",
    "receipt_ref",
    "receipt_refs",
    "input_execution_receipt_ref",
    "input_receipt_ref",
    "source_receipt_ref",
}


def _display_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(ROOT).as_posix()
    except ValueError:
        return str(resolved)


def _safe_id(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in {"_", "-", "."} else "_" for ch in value)


def _fallback_receipt_id(path: Path, receipt_root: Path) -> str:
    try:
        rel = path.resolve().relative_to(receipt_root.resolve())
        stem = rel.with_suffix("").as_posix()
    except ValueError:
        stem = path.stem
    return _safe_id(stem.replace("/", "__"))


def _load_json(path: Path) -> Any:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise StateCoreStoreError(f"receipt file unreadable: {path}: {exc}") from exc
    return payload


def _created_at_from_path(path: Path) -> str:
    try:
        return datetime.fromtimestamp(path.stat().st_mtime, tz=UTC).isoformat()
    except OSError:
        return datetime.now(UTC).isoformat()


def _unreadable_json_record(path: Path, receipt_root: Path) -> ReceiptIndex:
    return ReceiptIndex(
        receipt_id=_fallback_receipt_id(path, receipt_root),
        kind="unreadable_json",
        path=_display_path(path),
        created_at_utc=_created_at_from_path(path),
        refs=[],
        source_refs=[_display_path(path)],
    )


def _created_at(payload: dict[str, Any], path: Path) -> str:
    for key in ("created_at_utc", "timestamp_utc", "generated_at"):
        value = payload.get(key)
        if value:
            return str(value)
    snapshot = payload.get("snapshot")
    if isinstance(snapshot, dict) and snapshot.get("as_of_utc"):
        return str(snapshot["as_of_utc"])
    return _created_at_from_path(path)


def _kind(payload: dict[str, Any]) -> str:
    for key in ("kind", "workflow"):
        value = payload.get(key)
        if value:
            return str(value)
    snapshot = payload.get("snapshot")
    if isinstance(snapshot, dict):
        workflow = snapshot.get("workflow")
        if workflow:
            return str(workflow)
    return "unknown"


def _collect_receipt_refs(value: Any, *, key: str | None = None) -> list[str]:
    refs: list[str] = []
    if isinstance(value, dict):
        for child_key, child_value in value.items():
            refs.extend(_collect_receipt_refs(child_value, key=str(child_key)))
    elif isinstance(value, list):
        for item in value:
            refs.extend(_collect_receipt_refs(item, key=key))
    elif isinstance(value, str):
        looks_like_ref = (
            key in RECEIPT_REF_KEYS
            or value.startswith("receipt_")
            or "data/receipts/" in value
        )
        if looks_like_ref:
            refs.append(value)
    return refs


def receipt_index_record_from_path(
    path: str | Path,
    *,
    receipt_root: str | Path = DEFAULT_RECEIPT_ROOT,
    strict: bool = True,
) -> ReceiptIndex:
    target = Path(path)
    root = Path(receipt_root)
    try:
        payload = _load_json(target)
    except StateCoreStoreError:
        if strict:
            raise
        return _unreadable_json_record(target, root)
    if not isinstance(payload, dict):
        json_kind = type(payload).__name__
        return ReceiptIndex(
            receipt_id=_fallback_receipt_id(target, root),
            kind=f"raw_json_{json_kind}",
            path=_display_path(target),
            created_at_utc=_created_at_from_path(target),
            refs=[],
            source_refs=[_display_path(target)],
        )
    receipt_id = str(payload.get("receipt_id") or _fallback_receipt_id(target, root))
    refs = sorted(set(ref for ref in _collect_receipt_refs(payload) if ref != receipt_id))
    return ReceiptIndex(
        receipt_id=receipt_id,
        kind=_kind(payload),
        path=_display_path(target),
        created_at_utc=_created_at(payload, target),
        refs=refs,
        source_refs=[_display_path(target)],
    )


def iter_receipt_json_files(receipt_root: str | Path = DEFAULT_RECEIPT_ROOT) -> Iterable[Path]:
    root = Path(receipt_root)
    if not root.exists():
        raise StateCoreStoreError(f"receipt root missing: {root}")
    return sorted(path for path in root.rglob("*.json") if path.is_file())


def build_receipt_index_records(
    receipt_root: str | Path = DEFAULT_RECEIPT_ROOT,
) -> list[ReceiptIndex]:
    return [
        receipt_index_record_from_path(path, receipt_root=receipt_root, strict=False)
        for path in iter_receipt_json_files(receipt_root)
    ]


def index_receipts(
    *,
    receipt_root: str | Path = DEFAULT_RECEIPT_ROOT,
    engine: Engine,
) -> list[ReceiptIndex]:
    records = build_receipt_index_records(receipt_root)
    return list(upsert_records(records, engine=engine))
