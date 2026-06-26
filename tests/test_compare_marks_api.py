from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from finharness.api.app import create_app
from finharness.statecore.store import init_state_core
from tests._scaffold import VALID_SCAFFOLD
from tests.asgi_test_client import AsgiTestClient


class CompareMarksApiTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.receipt_root = self.root / "receipts" / "state-core"
        self.engine = init_state_core(self.root / "state-core.sqlite")
        self.app = create_app(
            state_core_engine=self.engine, receipt_root=str(self.receipt_root)
        )
        self.client = AsgiTestClient(self.app)
        self.addCleanup(self.client.close)
        self.addCleanup(self.engine.dispose)
        self.addCleanup(self.tmp.cleanup)

    def _proposal(self, claim: str) -> str:
        resp = self.client.post(
            "/proposals",
            json={
                "kind": "rebalance_review",
                "claim": claim,
                "evidence": {},
                "decision_scaffold": VALID_SCAFFOLD,
            },
        )
        return resp.json()["proposal"]["proposal_id"]

    def _compare_mark(self, proposal_id: str, compare_with: str) -> None:
        resp = self.client.post(
            f"/proposals/{proposal_id}/review-events",
            json={
                "kind": "compare_mark",
                "attester": "operator",
                "reason": "compare these",
                "compare_with": compare_with,
            },
        )
        self.assertEqual(resp.status_code, 200)

    def test_empty(self) -> None:
        body = self.client.get("/review/compare-marks").json()
        self.assertEqual(body["pairs"], [])
        self.assertFalse(body["execution_allowed"])

    def test_marked_pair_is_listed_read_only(self) -> None:
        a = self._proposal("candidate A")
        b = self._proposal("candidate B")
        self._compare_mark(a, b)
        body = self.client.get("/review/compare-marks").json()
        self.assertEqual(len(body["pairs"]), 1)
        pair = body["pairs"][0]
        self.assertEqual({pair["proposal_id"], pair["compare_with"]}, {a, b})
        self.assertTrue(pair["proposal_exists"] and pair["compare_with_exists"])
        self.assertIsNone(pair["missing_side"])
        self.assertFalse(body["execution_allowed"])
        self.assertTrue(any("not a recommendation" in nc for nc in body["non_claims"]))


if __name__ == "__main__":
    unittest.main()
