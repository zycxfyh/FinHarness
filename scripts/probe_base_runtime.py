#!/usr/bin/env python3
"""Probe that base runtime has core imports and no optional dependency imports.

Run in an environment with only base dependencies installed.
"""

from __future__ import annotations

import importlib
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


def _check_import(module: str) -> tuple[bool, str | None]:
    try:
        importlib.import_module(module)
        return True, None
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"


def main() -> int:
    errors: list[str] = []

    # Required base imports
    required = [
        "fastapi",
        "keyring",
        "opentelemetry.sdk.trace",
        "opentelemetry.trace",
        "pandas",
        "pydantic_settings",
        "sqlmodel",
        "structlog",
        "uvicorn",
        "finharness.project_paths",
        "finharness.statecore.store",
        "finharness.api.app",
    ]
    for module in required:
        available, detail = _check_import(module)
        if not available:
            errors.append(f"MISSING base import: {module} ({detail})")

    # Forbidden optional imports
    for module in sorted(FORBIDDEN):
        available, _detail = _check_import(module)
        if available:
            errors.append(f"FORBIDDEN optional import leaked: {module}")

    if not errors:
        from finharness.api.app import app

        paths = set(app.openapi()["paths"])
        for required_path in ("/health", "/execution/orders"):
            if required_path not in paths:
                errors.append(f"MISSING base API route: {required_path}")
        if "/data/catalog" in paths or app.state.data_surface_available:
            errors.append("FORBIDDEN optional data surface active in base-only runtime")

    if errors:
        for err in errors:
            print(f"FAIL: {err}", file=sys.stderr)
        return FAIL

    print("PASS: base FinHarness runtime imports and core routes work without optional groups")
    return PASS


if __name__ == "__main__":
    sys.exit(main())
