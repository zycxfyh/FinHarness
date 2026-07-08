"""Execution receipts — durable evidence for the execution lifecycle.

Every execution service writes a receipt. These are positive execution
receipts: order_draft.created, order.submitted, report.recorded — not
"not_live_order" or "execution_allowed_false" protection receipts.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from finharness.statecore.receipt_io import atomic_write_json, resolve_under

# ── Receipt kinds ───────────────────────────────────────────────────────────

EXECUTION_RECEIPT_KINDS: tuple[str, ...] = (
    "execution.order_draft.created",
    "execution.pretrade_check.recorded",
    "execution.approval.recorded",
    "execution.order.staged",
    "execution.order.submit_attempted",
    "execution.order.submitted",
    "execution.report.recorded",
    "execution.position_delta.recorded",
    "execution.reconciliation.recorded",
)

DEFAULT_EXECUTION_RECEIPT_ROOT = "data/receipts/execution"


# ── Helpers ─────────────────────────────────────────────────────────────────


def _stamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def _now_utc() -> str:
    return datetime.now(UTC).isoformat()


def _safe_id(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in {"_", "-"} else "_" for ch in value)


def _execution_receipt_id(kind: str, artifact_id: str) -> str:
    """Generate a stable receipt id for an execution artifact."""
    stamp = _stamp()
    short = artifact_id.replace("-", "")[:8] if artifact_id else uuid4().hex[:8]
    return f"exec_{kind.split('.')[-1]}_{stamp}_{short}"


# ── Receipt writers ─────────────────────────────────────────────────────────


def write_execution_receipt(
    *,
    receipt_root: str | Path,
    kind: str,
    artifact_id: str,
    payload: dict[str, Any],
    refs: list[str] | None = None,
) -> tuple[str, str]:
    """Write an execution receipt and return (receipt_id, receipt_path)."""
    resolved_root = Path(receipt_root)
    receipt_id = _execution_receipt_id(kind, artifact_id)
    filename = f"{receipt_id}.json"

    receipt_payload: dict[str, Any] = {
        "receipt_id": receipt_id,
        "kind": kind,
        "artifact_id": artifact_id,
        "created_at_utc": _now_utc(),
        "refs": refs or [],
        "payload": payload,
    }

    target = resolve_under(resolved_root, "receipts", filename)
    atomic_write_json(target, receipt_payload)

    return receipt_id, str(target)
