"""Verify the canonical uv-managed FinHarness development environment."""

from __future__ import annotations

import importlib
import importlib.metadata
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_PACKAGE_ROOT = (ROOT / "src" / "finharness").resolve()
EXPECTED_VENV = (ROOT / ".venv").resolve()


def build_report() -> dict[str, object]:
    """Return machine-readable environment facts and fail-closed findings."""
    findings: list[str] = []
    python_path = os.environ.get("PYTHONPATH")
    if python_path:
        findings.append("PYTHONPATH must be unset; use the editable project installation")

    module = importlib.import_module("finharness")
    module_file = Path(module.__file__ or "").resolve()
    if module_file.parent != EXPECTED_PACKAGE_ROOT:
        findings.append(
            f"finharness resolves outside this worktree: {module_file}"
        )

    environment = Path(sys.prefix).resolve()
    if environment != EXPECTED_VENV:
        findings.append(f"Python environment is not this worktree's .venv: {environment}")

    if sys.version_info[:2] != (3, 12):
        findings.append(f"Python 3.12 is required, found {sys.version.split()[0]}")

    return {
        "ok": not findings,
        "python": sys.version.split()[0],
        "environment": str(environment),
        "distribution_version": importlib.metadata.version("finharness"),
        "module_file": str(module_file),
        "pythonpath": python_path,
        "findings": findings,
    }


def main() -> int:
    report = build_report()
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
