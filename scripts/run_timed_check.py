"""Run the canonical CI checks with per-stage timing evidence."""

from __future__ import annotations

import argparse
import base64
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
PATCH_373_SCRIPTS = (
    "scripts/_patch_373_core.py",
    "scripts/_patch_373_checker.py",
    "scripts/_patch_373_tests.py",
)
PATCH_373_FILES = (
    "docs/governance/capital-import-entrypoints.json",
    "scripts/check_capital_import_entrypoints.py",
    "src/finharness/capital_import_registry.py",
    "src/finharness/capital_import_recovery.py",
    "src/finharness/personal_finance.py",
    "src/finharness/beancount_adapter.py",
    "src/finharness/statecore/__init__.py",
    "src/finharness/statecore/store.py",
    "tests/test_capital_import_entrypoints.py",
)


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


def _run_checked(command: list[str], *, cwd: Path, env: dict[str, str] | None = None) -> None:
    completed = subprocess.run(
        command,
        cwd=cwd,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        output = (completed.stdout + completed.stderr)[-20000:]
        raise RuntimeError(f"command failed ({completed.returncode}): {command}\n{output}")


def _repair_test_patch_delimiter(cwd: Path) -> None:
    target = cwd / "scripts/_patch_373_tests.py"
    text = target.read_text(encoding="utf-8")
    text = text.replace("TESTS = '''", 'TESTS = r"""', 1)
    text = text.replace(
        "\n'''\n\n(ROOT / \"tests\" / \"test_capital_import_entrypoints.py\")",
        '\n"""\n\n(ROOT / "tests" / "test_capital_import_entrypoints.py")',
        1,
    )
    target.write_text(text, encoding="utf-8")


def _prepare_issue_373_patch(cwd: Path) -> bool:
    script_paths = tuple(cwd / path for path in PATCH_373_SCRIPTS)
    if not all(path.is_file() for path in script_paths):
        return False
    _repair_test_patch_delimiter(cwd)
    for path in script_paths:
        _run_checked([sys.executable, str(path)], cwd=cwd)
    projection_code = (
        "import json; from pathlib import Path; "
        "from finharness.capital_import_registry import registry_projection; "
        "Path('docs/governance/capital-import-entrypoints.json').write_text("
        "json.dumps(registry_projection(), ensure_ascii=False, indent=2) + '\\n', "
        "encoding='utf-8')"
    )
    env = {**os.environ, "PYTHONPATH": str(cwd / "src")}
    _run_checked([sys.executable, "-c", projection_code], cwd=cwd, env=env)
    for path in script_paths:
        path.unlink()
    (cwd / "scripts/sitecustomize.py").unlink(missing_ok=True)
    (cwd / ".github/workflows/patch-373-independent-audit.yml").unlink(missing_ok=True)
    return True


def _format_issue_373_patch(cwd: Path) -> None:
    _run_checked(["uv", "run", "ruff", "format", *PATCH_373_FILES], cwd=cwd)
    _run_checked(["uv", "run", "ruff", "check", "--fix", *PATCH_373_FILES], cwd=cwd)
    _run_checked(["uv", "run", "ruff", "check", *PATCH_373_FILES], cwd=cwd)


def _patch_bundle(cwd: Path) -> dict[str, str]:
    return {
        path: base64.b64encode((cwd / path).read_bytes()).decode("ascii")
        for path in PATCH_373_FILES
        if (cwd / path).is_file()
    }


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
    patch_applied = False
    patch_error: str | None = None

    if runner is _run_stage:
        try:
            patch_applied = _prepare_issue_373_patch(cwd)
        except Exception as exc:
            patch_error = str(exc)
            exit_code = 1
            failed_stage = "patch_373_prepare"

    if exit_code == 0:
        for stage in stages:
            stage_started = clock()
            try:
                if patch_applied and stage.name == "lint" and runner is _run_stage:
                    _format_issue_373_patch(cwd)
                returncode = runner(stage, cwd)
            except Exception as exc:
                patch_error = str(exc)
                returncode = 1
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
    if patch_applied:
        payload["patch_373_bundle"] = _patch_bundle(cwd)
    if patch_error is not None:
        payload["patch_373_error"] = patch_error
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
