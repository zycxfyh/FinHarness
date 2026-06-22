"""Small hypothesis utility helpers."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from finharness.hypotheses._constants import RECOMMENDATION_PATTERNS, VALIDATED_PATTERNS
from finharness.hypotheses.models import HypothesisRecord


def now_utc() -> str:
    return datetime.now(UTC).isoformat()


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str)
        + "\n",
        encoding="utf-8",
    )


def normalize_symbol(symbol: str) -> str:
    return symbol.strip().upper()


def find_blocked_language(value: str) -> list[str]:
    lower = value.lower()
    hits: list[str] = []
    for pattern in [*RECOMMENDATION_PATTERNS, *VALIDATED_PATTERNS]:
        if re.search(pattern, lower):
            hits.append(pattern)
    return hits


def record_text_for_guard(record: HypothesisRecord) -> str:
    validation_text = [
        f"{check.description} {check.expected_support} {check.expected_disconfirm}"
        for check in record.validation_plan
    ]
    return "\n".join(
        [
            record.mechanism,
            record.hypothesis,
            *record.expected_observations,
            *record.disconfirming_observations,
            *record.assumptions,
            *validation_text,
        ]
    )
