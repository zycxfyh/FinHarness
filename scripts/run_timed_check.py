"""Run canonical CI checks with per-stage timing and diagnostic evidence."""

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
FAILURE_EXCERPT_LINES = 30


@dataclass(frozen=True)
class CheckStage:
    name: str
    task: str


CHECK_STAGES: tuple[CheckStage, ...] = (
    CheckStage("setup", "setup"),
    CheckStage("lint", "lint"),
    CheckStage("typecheck", "typecheck"),
    CheckStage("python_compile", "test:compile"),
    CheckStage("python_unittest", "test:unittest"),
    CheckStage("python_pytest", "test:pytest"),
    CheckStage("rust_runtime", "test:runtime"),
    CheckStage("base_dependency_profile", "deps:probe-base"),
    CheckStage("frontend", "test:frontend"),
    CheckStage("architecture", "architecture:check"),
    CheckStage("rules", "rules:audit"),
)

StageRunner = Callable[[CheckStage, Path, Path], int]
Clock = Callable[[], float]


def _run_stage(stage: CheckStage, cwd: Path, log_path: Path) -> int:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("w", encoding="utf-8") as log:
        process = subprocess.Popen(
            ["task", stage.task],
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )
        if process.stdout is None:
            raise RuntimeError(f"failed to capture output for {stage.task}")
        for line in process.stdout:
            print(line, end="")
            log.write(line)
        return process.wait()


def _failure_excerpt(log_path: Path, limit: int = FAILURE_EXCERPT_LINES) -> list[str]:
    if not log_path.is_file():
        return []
    lines = [
        line.rstrip()
        for line in log_path.read_text(encoding="utf-8", errors="replace").splitlines()
        if line.strip()
    ]
    return lines[-limit:]


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
        "## FinHarness check evidence",
        "",
        f"Overall status: **{payload['status']}**  ",
        f"Total duration: **{payload['total_duration_seconds']:.3f}s**",
        "",
        "| Stage | Task | Status | Seconds | Log |",
        "| --- | --- | --- | ---: | --- |",
    ]
    for stage in payload["stages"]:
        lines.append(
            f"| {stage['name']} | `{stage['task']}` | {stage['status']} | "
            f"{stage['duration_seconds']:.3f} | `{stage['log_path']}` |"
        )
    if failed_stage := payload.get("failed_stage"):
        lines.extend(("", f"Stopped after failed stage: `{failed_stage}`."))
        excerpt = payload.get("failure_excerpt") or []
        if excerpt:
            lines.extend(
                (
                    "",
                    "### Failure excerpt",
                    "",
                    "```text",
                    *excerpt,
                    "```",
                )
            )
    return "\n".join(lines) + "\n"


def run_timed_check(
    *,
    stages: Sequence[CheckStage] = CHECK_STAGES,
    cwd: Path = ROOT,
    output_path: Path = DEFAULT_OUTPUT,
    log_dir: Path | None = None,
    summary_path: Path | None = None,
    runner: StageRunner = _run_stage,
    clock: Clock = time.perf_counter,
) -> tuple[dict[str, Any], int]:
    started_at = datetime.now(UTC).isoformat()
    suite_started = clock()
    results: list[dict[str, Any]] = []
    exit_code = 0
    failed_stage: str | None = None
    failure_excerpt: list[str] = []
    resolved_log_dir = log_dir or output_path.parent / "check-logs"
    resolved_log_dir.mkdir(parents=True, exist_ok=True)

    for index, stage in enumerate(stages, start=1):
        log_path = resolved_log_dir / f"{index:02d}-{stage.name}.log"
        log_path.touch()
        stage_started = clock()
        returncode = runner(stage, cwd, log_path)
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
                "log_path": log_path.as_posix(),
            }
        )
        if returncode != 0:
            exit_code = returncode
            failed_stage = stage.name
            failure_excerpt = _failure_excerpt(log_path)
            break

    payload: dict[str, Any] = {
        "schema": TIMING_SCHEMA,
        "started_at_utc": started_at,
        "status": "passed" if exit_code == 0 else "failed",
        "returncode": exit_code,
        "failed_stage": failed_stage,
        "failure_excerpt": failure_excerpt,
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
    parser.add_argument("--log-dir", type=Path)
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
        log_dir=args.log_dir,
        summary_path=args.summary,
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
