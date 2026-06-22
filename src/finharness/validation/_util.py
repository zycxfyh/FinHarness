"""Small validation helpers shared by implementation modules."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from finharness.validation._constants import BLOCKED_VALIDATION_LANGUAGE
from finharness.validation.models import ValidationCheckResult


def now_utc() -> str:
    return datetime.now(UTC).isoformat()


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str)
        + "\n",
        encoding="utf-8",
    )


def find_blocked_language(value: str) -> list[str]:
    lower = value.lower()
    hits: list[str] = []
    for pattern in BLOCKED_VALIDATION_LANGUAGE:
        if re.search(pattern, lower):
            hits.append(pattern)
    return hits


def result_text_for_guard(result: ValidationCheckResult) -> str:
    return "\n".join(
        [
            result.method,
            result.window,
            str(result.metrics),
            *result.limitations,
        ]
    )
