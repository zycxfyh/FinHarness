"""Redaction helpers for OKX CLI output and errors."""

from __future__ import annotations

import re
from typing import Any

# Output keys that must never be surfaced raw (red-team F9).
SENSITIVE_KEYS = frozenset(
    {
        "apikey",
        "secretkey",
        "passphrase",
        "secret",
        "key",
        "privatekey",
        "sign",
        "token",
        "uid",
        "mainuid",
        "ip",
        "label",
    }
)
REDACTED = "***REDACTED***"


def redact_okx_output(obj: Any) -> Any:
    """Recursively mask sensitive fields in an okx response (red-team F9)."""
    if isinstance(obj, dict):
        return {
            key: (REDACTED if key.lower() in SENSITIVE_KEYS else redact_okx_output(value))
            for key, value in obj.items()
        }
    if isinstance(obj, list):
        return [redact_okx_output(item) for item in obj]
    return obj


def redact_text(text: str) -> str:
    """Mask key/secret-looking assignments in free text such as stderr."""
    pattern = re.compile(
        r"(?i)(api[_-]?key|secret[_-]?key|passphrase|secret|private[_-]?key|sign|token)"
        r"(\"?\s*[:=]\s*\"?)([^\",}\s]+)"
    )
    return pattern.sub(lambda m: f"{m.group(1)}{m.group(2)}{REDACTED}", text)
