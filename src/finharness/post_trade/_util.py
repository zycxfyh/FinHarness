"""Small post-trade utility helpers."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from finharness.post_trade._constants import PostTradeExceptionSeverity
from finharness.post_trade.models import PostTradeException


def now_utc() -> str:
    return datetime.now(UTC).isoformat()


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str)
        + "\n",
        encoding="utf-8",
    )


def exception(
    *,
    exception_type: str,
    severity: PostTradeExceptionSeverity,
    reason: str,
    evidence_refs: list[str] | None = None,
) -> PostTradeException:
    return PostTradeException(
        exception_id=f"ptexc_{uuid4().hex[:12]}",
        exception_type=exception_type,
        severity=severity,
        reason=reason,
        evidence_refs=evidence_refs or [],
        created_at_utc=now_utc(),
    )
