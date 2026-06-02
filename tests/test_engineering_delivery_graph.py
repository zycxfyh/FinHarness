from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from finharness.engineering_delivery_graph import (
    engineering_delivery_graph,
    run_engineering_delivery_graph,
)


class EngineeringDeliveryGraphTest(unittest.TestCase):
    def test_graph_compiles(self) -> None:
        self.assertIsNotNone(engineering_delivery_graph)

    def test_graph_writes_pass_receipt_and_review(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = run_engineering_delivery_graph(
                goal="Engineering Delivery Graph MVP",
                source_ref="unit-test",
                proposal_ref="docs/proposals/2026-06-02-engineering-delivery-graph-mvp.md",
                module_refs=["docs/modules/engineering-delivery.md"],
                change_type="new_workflow",
                scope="Implement first delivery governance graph.",
                non_goals=["authorize financial execution"],
                success_criteria=["receipt produced", "tests passed"],
                planned_files=["src/finharness/engineering_delivery_graph.py"],
                changed_files=["src/finharness/engineering_delivery_graph.py"],
                docs_updated=[
                    "docs/modules/engineering-delivery.md",
                    "docs/proposals/2026-06-02-engineering-delivery-graph-mvp.md",
                ],
                checks=[{"name": "unit", "status": "passed", "detail": "ok"}],
                root=root,
            )

            final = result["final"]
            self.assertEqual(final["workflow"], "langgraph_engineering_delivery_v1")
            self.assertEqual(final["status"], "pass")
            self.assertTrue(final["quality_ok"])
            self.assertFalse(final["execution_allowed"])
            self.assertEqual(final["remaining_debt"], [])

            receipt_path = Path(final["receipt_ref"])
            review_path = Path(final["review_ref"])
            self.assertTrue(receipt_path.exists())
            self.assertTrue(review_path.exists())

            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            self.assertEqual(receipt["status"], "pass")
            self.assertEqual(receipt["snapshot"]["change_type"], "new_workflow")
            self.assertEqual(receipt["snapshot"]["checks"][0]["status"], "passed")

    def test_graph_fails_when_required_evidence_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = run_engineering_delivery_graph(
                goal="Missing evidence delivery",
                source_ref="unit-test",
                change_type="new_workflow",
                scope="Try a substantial workflow without proposal or checks.",
                non_goals=["authorize financial execution"],
                changed_files=[],
                docs_updated=[],
                checks=[],
                root=root,
            )

            final = result["final"]
            self.assertEqual(final["status"], "failed")
            self.assertFalse(final["quality_ok"])
            self.assertIn("proposal_ref", final["remaining_debt"])
            self.assertIn("changed_files", final["remaining_debt"])
            self.assertIn("docs_updated", final["remaining_debt"])
            self.assertIn("passing_checks", final["remaining_debt"])
            self.assertTrue(Path(final["receipt_ref"]).exists())
            self.assertTrue(Path(final["review_ref"]).exists())


if __name__ == "__main__":
    unittest.main()
