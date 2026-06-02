from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from finharness.cognitive_graph import cognitive_graph, run_cognitive_project_flow


class CognitiveGraphTest(unittest.TestCase):
    def test_graph_compiles(self) -> None:
        self.assertIsNotNone(cognitive_graph)

    def test_graph_writes_cognitive_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = run_cognitive_project_flow(
                topic="Events layer MVP",
                raw_thought="Use the cognitive flow before building the events layer.",
                layer="events",
                source="unit-test",
                root=root,
            )

            final = result["final"]
            self.assertEqual(final["workflow"], "langgraph_cognitive_engineering_v1")
            self.assertIn("events-layer-mvp", final["proposal_path"])

            for key in [
                "idea_path",
                "note_path",
                "proposal_path",
                "review_path",
                "lesson_path",
                "receipt_path",
            ]:
                self.assertTrue(Path(final[key]).exists(), key)

            receipt = json.loads(Path(final["receipt_path"]).read_text(encoding="utf-8"))
            self.assertEqual(receipt["workflow"], "langgraph_cognitive_engineering_v1")
            self.assertEqual(receipt["layer"], "events")
            self.assertEqual(receipt["artifacts"]["proposal"], final["proposal_path"])


if __name__ == "__main__":
    unittest.main()
