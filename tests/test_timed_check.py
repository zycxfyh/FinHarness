from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import yaml
from scripts.run_timed_check import (
    CHECK_STAGES,
    TIMING_SCHEMA,
    CheckStage,
    render_step_summary,
    run_timed_check,
)


class _Clock:
    def __init__(self, values: list[float]) -> None:
        self._values = iter(values)

    def __call__(self) -> float:
        return next(self._values)


class TimedCheckTest(unittest.TestCase):
    def test_stage_inventory_expands_the_existing_ci_layers(self) -> None:
        root = Path(__file__).resolve().parents[1]
        taskfile = yaml.safe_load((root / "Taskfile.yml").read_text(encoding="utf-8"))
        tasks = taskfile["tasks"]

        def leaf_tasks(task_name: str) -> list[str]:
            task = tasks[task_name]
            commands = task.get("cmds", [])
            if any(
                not isinstance(command, dict) or "task" not in command
                for command in commands
            ):
                return [task_name]
            refs = [str(name) for name in task.get("deps", [])]
            refs.extend(
                str(command["task"])
                for command in commands
                if isinstance(command, dict) and "task" in command
            )
            if not refs:
                return [task_name]
            return [leaf for ref in refs for leaf in leaf_tasks(ref)]

        self.assertEqual([stage.task for stage in CHECK_STAGES], leaf_tasks("check:ci"))

    def test_success_writes_timing_logs_and_summary(self) -> None:
        stages = (CheckStage("first", "lint"), CheckStage("second", "typecheck"))
        calls: list[str] = []

        def runner(stage: CheckStage, _cwd: Path, log_path: Path) -> int:
            calls.append(stage.task)
            log_path.write_text(f"{stage.name} output\n", encoding="utf-8")
            return 0

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "timing.json"
            summary = root / "summary.md"
            payload, returncode = run_timed_check(
                stages=stages,
                cwd=root,
                output_path=output,
                summary_path=summary,
                runner=runner,
                clock=_Clock([0.0, 1.0, 2.5, 3.0, 5.0, 6.0]),
            )

            persisted = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(returncode, 0)
            self.assertEqual(calls, ["lint", "typecheck"])
            self.assertEqual(persisted["schema"], TIMING_SCHEMA)
            self.assertEqual(persisted["status"], "passed")
            self.assertEqual(persisted["stage_count"], 2)
            self.assertEqual(persisted["stages"][0]["duration_seconds"], 1.5)
            self.assertTrue(Path(persisted["stages"][0]["log_path"]).is_file())
            self.assertEqual(payload["total_duration_seconds"], 6.0)
            summary_text = summary.read_text(encoding="utf-8")
            self.assertIn("| first | `lint` | passed | 1.500 |", summary_text)
            self.assertIn("01-first.log", summary_text)

    def test_failure_preserves_exit_code_and_excerpt(self) -> None:
        stages = (
            CheckStage("first", "lint"),
            CheckStage("broken", "typecheck"),
            CheckStage("never", "test:compile"),
        )
        calls: list[str] = []

        def runner(stage: CheckStage, _cwd: Path, log_path: Path) -> int:
            calls.append(stage.task)
            log_path.write_text(
                "ordinary output\nspecific failure detail\n",
                encoding="utf-8",
            )
            return 7 if stage.name == "broken" else 0

        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "timing.json"
            payload, returncode = run_timed_check(
                stages=stages,
                output_path=output,
                runner=runner,
                clock=_Clock([0.0, 1.0, 2.0, 3.0, 5.0, 6.0]),
            )

            self.assertEqual(returncode, 7)
            self.assertEqual(calls, ["lint", "typecheck"])
            self.assertEqual(payload["status"], "failed")
            self.assertEqual(payload["failed_stage"], "broken")
            self.assertEqual(payload["stage_count"], 2)
            self.assertIn("specific failure detail", payload["failure_excerpt"])
            persisted = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(persisted["returncode"], 7)
            summary = render_step_summary(payload)
            self.assertIn("Stopped after failed stage", summary)
            self.assertIn("specific failure detail", summary)


if __name__ == "__main__":
    unittest.main()
