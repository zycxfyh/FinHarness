#!/usr/bin/env python3
"""Probe that base runtime has core imports and no optional dependency imports.

Run in an environment with only base dependencies installed.
"""

from __future__ import annotations

import sys

PASS = 0
FAIL = 1

FORBIDDEN = {
    "langgraph",
    "agents",
    "backtrader",
    "quantstats",
    "riskfolio",
    "scipy",
    "vectorbt",
    "yfinance",
    "pandera",
    "nautilus_trader",
    "deepeval",
    "beancount",
    "beanquery",
    "openai",
}


def _check_import(module: str) -> bool:
    try:
        __import__(module)
        return True
    except ImportError:
        return False


def main() -> int:
    errors: list[str] = []

    # Required base imports
    required = [
        ("fastapi", "FastAPI"),
        ("sqlmodel", "SQLModel"),
        ("structlog", "structlog"),
        ("pandas", "pandas"),
        ("uvicorn", "uvicorn"),
        ("keyring", "keyring"),
    ]
    for module, _name in required:
        if not _check_import(module):
            errors.append(f"MISSING base import: {module}")

    # Forbidden optional imports
    for module in sorted(FORBIDDEN):
        if _check_import(module):
            errors.append(f"FORBIDDEN optional import leaked: {module}")

    if errors:
        for err in errors:
            print(f"FAIL: {err}", file=sys.stderr)
        return FAIL

    print("PASS: base runtime probe — all core imports available, no optional leaks")
    return PASS


if __name__ == "__main__":
    sys.exit(main())
