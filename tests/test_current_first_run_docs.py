from __future__ import annotations

import re
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
FIRST_RUN_DOCS = (
    Path("README.md"),
    Path("docs/README.md"),
    Path("docs/how-to/README.md"),
    Path("docs/tutorials/golden-path.md"),
    Path("docs/reference/commands.md"),
)


def _read(path: Path) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


class CurrentFirstRunDocumentationTest(unittest.TestCase):
    def test_task_modes_and_documented_boundaries_match(self) -> None:
        taskfile = yaml.safe_load(_read(Path("Taskfile.yml")))
        tasks = taskfile["tasks"]
        api_command = "\n".join(tasks["api:serve"]["cmds"])
        review_command = "\n".join(tasks["cockpit:review"]["cmds"])

        self.assertIn("--mode read-only", api_command)
        self.assertIn("--mode review", review_command)

        commands = _read(Path("docs/reference/commands.md"))
        tutorial = _read(Path("docs/tutorials/golden-path.md"))
        self.assertIn("`task api:serve`", commands)
        self.assertIn("read-only", commands.lower())
        self.assertIn("fails closed for writes", commands.lower())
        self.assertIn("`task cockpit:review`", commands)
        self.assertIn("governed human review writes", commands.lower())
        self.assertIn("task cockpit:review -- --state-db", tutorial)

    def test_synthetic_demo_is_not_claimed_as_canonical_product_journey(self) -> None:
        tutorial = _read(Path("docs/tutorials/golden-path.md")).lower()
        self.assertIn("isolated synthetic proposal/review/receipt replay demo", tutorial)
        self.assertIn("does not prove canonical capital import", tutorial)
        self.assertIn("capital-truth readiness", tutorial)
        self.assertIn("daily brief", tutorial)
        self.assertIn("does not expose its temporary state core", tutorial)

        for path in FIRST_RUN_DOCS:
            text = _read(path).lower()
            self.assertNotIn("first safe end-to-end", text, path.as_posix())
            self.assertNotIn("safe end-to-end flow", text, path.as_posix())

    def test_demo_and_persistent_cockpit_are_explicitly_separate(self) -> None:
        tutorial = _read(Path("docs/tutorials/golden-path.md"))
        self.assertIn("task decisions:golden-path", tutorial)
        self.assertIn("does not open the demo's temporary workspace", tutorial)
        self.assertIn("task api:serve -- --state-db", tutorial)
        self.assertIn("task cockpit:review -- --state-db", tutorial)
        self.assertGreaterEqual(tutorial.count("$STATE_DB"), 4)
        self.assertGreaterEqual(tutorial.count("$RECEIPT_ROOT"), 4)

    def test_current_first_run_docs_have_no_maintainer_absolute_paths(self) -> None:
        forbidden = re.compile(r"(?:/root/projects/|/home/[^/\s]+/[^\s`)]*)")
        for path in FIRST_RUN_DOCS:
            self.assertIsNone(forbidden.search(_read(path)), path.as_posix())

    def test_api_serve_is_never_described_as_write_capable(self) -> None:
        tutorial = _read(Path("docs/tutorials/golden-path.md")).lower()
        commands = _read(Path("docs/reference/commands.md")).lower()
        self.assertNotIn("may let a named human attest", tutorial)
        self.assertIn("every write fails closed", tutorial)
        self.assertIn("all writes fail closed", commands)


if __name__ == "__main__":
    unittest.main()
