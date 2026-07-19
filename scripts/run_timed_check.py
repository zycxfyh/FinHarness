"""Run the canonical CI checks with per-stage timing evidence."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

TIMING_SCHEMA = "finharness.check_timing.v1"
DEFAULT_OUTPUT = Path(".artifacts/check-timing.json")
ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class CheckStage:
    name: str
    task: str


# These are existing authoritative Taskfile executors, expanded only far enough
# to make setup and the three Python test layers independently observable.
CHECK_STAGES: tuple[CheckStage, ...] = (
    CheckStage("setup", "setup"),
    CheckStage("lint", "lint"),
    CheckStage("typecheck", "typecheck"),
    CheckStage("python_compile", "test:compile"),
    CheckStage("python_unittest", "test:unittest"),
    CheckStage("python_pytest", "test:pytest"),
    CheckStage("base_dependency_profile", "deps:probe-base"),
    CheckStage("integration", "test:integration"),
    CheckStage("frontend", "test:frontend"),
    CheckStage("governance", "governance:inventory"),
    CheckStage("architecture", "architecture:check"),
    CheckStage("rules", "rules:audit"),
)

StageRunner = Callable[[CheckStage, Path], int]
Clock = Callable[[], float]


def _run_stage(stage: CheckStage, cwd: Path) -> int:
    completed = subprocess.run(
        ["task", stage.task],
        cwd=cwd,
        check=False,
    )
    return completed.returncode


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path: Path | None = None
    try:
        with NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temp_path = Path(handle.name)
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
        temp_path.replace(path)
    except Exception:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
        raise


def render_step_summary(payload: dict[str, Any]) -> str:
    lines = [
        "## FinHarness check timing",
        "",
        f"Overall status: **{payload['status']}**  ",
        f"Total duration: **{payload['total_duration_seconds']:.3f}s**",
        "",
        "| Stage | Task | Status | Seconds |",
        "| --- | --- | --- | ---: |",
    ]
    for stage in payload["stages"]:
        lines.append(
            f"| {stage['name']} | `{stage['task']}` | {stage['status']} | "
            f"{stage['duration_seconds']:.3f} |"
        )
    if failed_stage := payload.get("failed_stage"):
        lines.extend(("", f"Stopped after failed stage: `{failed_stage}`."))
    return "\n".join(lines) + "\n"


def run_timed_check(
    *,
    stages: Sequence[CheckStage] = CHECK_STAGES,
    cwd: Path = ROOT,
    output_path: Path = DEFAULT_OUTPUT,
    summary_path: Path | None = None,
    runner: StageRunner = _run_stage,
    clock: Clock = time.perf_counter,
) -> tuple[dict[str, Any], int]:
    started_at = datetime.now(UTC).isoformat()
    suite_started = clock()
    results: list[dict[str, Any]] = []
    exit_code = 0
    failed_stage: str | None = None

    for stage in stages:
        stage_started = clock()
        returncode = runner(stage, cwd)
        duration = round(clock() - stage_started, 3)
        status = "passed" if returncode == 0 else "failed"
        results.append(
            {
                "name": stage.name,
                "task": stage.task,
                "command": ["task", stage.task],
                "status": status,
                "returncode": returncode,
                "duration_seconds": duration,
            }
        )
        if returncode != 0:
            exit_code = returncode
            failed_stage = stage.name
            break

    payload: dict[str, Any] = {
        "schema": TIMING_SCHEMA,
        "started_at_utc": started_at,
        "status": "passed" if exit_code == 0 else "failed",
        "returncode": exit_code,
        "failed_stage": failed_stage,
        "total_duration_seconds": round(clock() - suite_started, 3),
        "stage_count": len(results),
        "stages": results,
    }
    _atomic_write_json(output_path, payload)
    if summary_path is not None:
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        with summary_path.open("a", encoding="utf-8") as handle:
            handle.write(render_step_summary(payload))
    return payload, exit_code


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--summary",
        type=Path,
        default=Path(os.environ["GITHUB_STEP_SUMMARY"])
        if os.environ.get("GITHUB_STEP_SUMMARY")
        else None,
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    payload, exit_code = run_timed_check(
        output_path=args.output,
        summary_path=args.summary,
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
