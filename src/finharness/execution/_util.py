"""Small execution helpers shared by implementation modules."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from finharness.execution._constants import ExecutionEventType, ExecutionStatus
from finharness.execution.models import ExecutionEvent


def now_utc() -> str:
    return datetime.now(UTC).isoformat()


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str)
        + "\n",
        encoding="utf-8",
    )


def event(
    *,
    event_type: ExecutionEventType,
    status: ExecutionStatus,
    raw_status: str,
    order_request_id: str | None = None,
    quantity: int = 0,
    filled_quantity: int = 0,
    average_price: float | None = None,
    raw_event: dict[str, Any] | None = None,
) -> ExecutionEvent:
    return ExecutionEvent(
        event_id=f"exevt_{uuid4().hex[:12]}",
        order_request_id=order_request_id,
        event_type=event_type,
        status=status,
        quantity=quantity,
        filled_quantity=filled_quantity,
        average_price=average_price,
        raw_status=raw_status,
        raw_event=raw_event or {},
        created_at_utc=now_utc(),
    )
