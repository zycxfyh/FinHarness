"""Record local red-team tool readiness without installing dependencies."""

from __future__ import annotations

import argparse
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from finharness.hardening import build_red_team_tool_readiness_report

ROOT = Path(__file__).resolve().parents[1]


def run_command(command: list[str]) -> dict[str, Any]:
    completed = subprocess.run(
        command,
        cwd=ROOT,
        check=False,
        text=True,
        capture_output=True,
    )
    return {
        "command": command,
        "returncode": completed.returncode,
        "stdout": completed.stdout.strip(),
        "stderr": completed.stderr.strip(),
    }


def probe_promptfoo() -> dict[str, Any]:
    version = run_command(["pnpm", "exec", "promptfoo", "--version"])
    return {
        "id": "promptfoo",
        "status": "active_smoke" if version["returncode"] == 0 else "missing",
        "available": version["returncode"] == 0,
        "required_for_current_gate": True,
        "version": version["stdout"].splitlines()[-1] if version["stdout"] else "",
    }


def probe_promptfoo_redteam() -> dict[str, Any]:
    help_result = run_command(["pnpm", "exec", "promptfoo", "redteam", "--help"])
    available = help_result["returncode"] == 0 and "Usage: promptfoo redteam" in (
        help_result["stdout"] + help_result["stderr"]
    )
    return {
        "id": "promptfoo_redteam_cli",
        "status": "available_unconfigured" if available else "missing",
        "available": available,
        "required_for_current_gate": False,
        "version": "",
    }


def probe_python_import(module_name: str, tool_id: str) -> dict[str, Any]:
    result = run_command(
        [
            "uv",
            "run",
            "python",
            "-c",
            f"import {module_name}; print({module_name!r})",
        ]
    )
    return {
        "id": tool_id,
        "status": "available_unconfigured" if result["returncode"] == 0 else "planned_missing",
        "available": result["returncode"] == 0,
        "required_for_current_gate": False,
        "version": "",
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "data" / "redteam" / "exports" / "tool-readiness.json",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    tools = [
        probe_promptfoo(),
        probe_promptfoo_redteam(),
        probe_python_import("pyrit", "pyrit"),
        probe_python_import("garak", "garak"),
    ]
    report = build_red_team_tool_readiness_report(tools)
    report["generated_at"] = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report["summary"]["required_available"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
