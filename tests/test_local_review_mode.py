from __future__ import annotations

import argparse
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient
from scripts.serve_local_cockpit import build_app

from finharness.statecore.proposals import create_governed_proposal

SCAFFOLD = {
    "decision_intent": "Review the local proposal",
    "thesis": "The evidence merits human review",
    "do_nothing_case": "No governed decision is recorded",
    "risk_if_wrong": "The review conclusion may be wrong",
}


class LocalReviewModeTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.db = self.root / "state.sqlite"
        self.receipts = self.root / "receipts"

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _args(self, mode: str, *, receipts: Path | None = None) -> argparse.Namespace:
        return argparse.Namespace(
            mode=mode,
            host="127.0.0.1",
            port=8765,
            state_db=self.db,
            receipt_root=receipts or self.receipts,
            operator_id="test-human",
        )

    def _seed(self, app, proposal_id: str) -> None:
        create_governed_proposal(
            proposal_id=proposal_id,
            kind="local_review",
            claim=f"Review {proposal_id}",
            evidence={"fixture": True},
            source_refs=["fixture://local-review"],
            decision_scaffold=SCAFFOLD,
            engine=app.state.state_core_engine,
            receipt_root=self.receipts,
        )

    def _attest(self, client: TestClient, proposal_id: str, decision: str):
        version = client.get(f"/proposals/{proposal_id}/revisions").json()["revisions"][0]
        return client.post(
            f"/proposals/{proposal_id}/attest",
            json={
                "decision": decision,
                "reason": f"Browser-equivalent {decision} review",
                "expected_proposal_version_id": version["receipt_id"],
                "expected_proposal_receipt_ref": version["receipt_ref"],
            },
        )

    def test_confirm_reject_and_defer_persist_across_restart(self) -> None:
        app = build_app(self._args("review"))
        for proposal_id in ("confirm", "reject", "defer"):
            self._seed(app, proposal_id)
        with TestClient(app) as client:
            self.assertEqual(self._attest(client, "confirm", "approved").status_code, 200)
            self.assertEqual(self._attest(client, "reject", "rejected").status_code, 200)
            self.assertEqual(self._attest(client, "defer", "deferred").status_code, 200)
        app.state.state_core_engine.dispose()

        restarted = build_app(self._args("review"))
        with TestClient(restarted) as client:
            expected = {
                "confirm": ("approved", False),
                "reject": ("rejected", False),
                "defer": ("deferred", True),
            }
            for proposal_id, (decision, open_for_review) in expected.items():
                detail = client.get(f"/proposals/{proposal_id}").json()
                self.assertEqual(detail["attestations"][0]["decision"], decision)
                self.assertFalse(detail["attestations"][0]["stale"])
                self.assertIsNotNone(detail["attestations"][0]["bound_proposal_version_id"])
                self.assertEqual(detail["open_for_review"], open_for_review)
            self.assertEqual(client.get("/dashboard/summary").json()["open_proposal_count"], 1)
            queue = client.get("/review/queue", params={"include_closed": True}).json()
            deferred = next(
                item for item in queue["items"] if item["proposal_id"] == "defer"
            )
            self.assertNotEqual(deferred["status"], "reviewed")

    def test_revision_marks_prior_decision_stale_and_rejects_stale_submit(self) -> None:
        app = build_app(self._args("review"))
        self._seed(app, "revision")
        with TestClient(app) as client:
            before = client.get("/proposals/revision/revisions").json()["revisions"][0]
            response = self._attest(client, "revision", "approved")
            self.assertEqual(response.status_code, 200)
            revised = client.patch(
                "/proposals/revision/decision-scaffold",
                json={
                    "reason": "Add current counter evidence",
                    "decision_scaffold": {"counter_evidence": "A falsifier appeared"},
                    "expected_proposal_version_id": before["receipt_id"],
                    "expected_proposal_receipt_ref": before["receipt_ref"],
                },
            )
            self.assertEqual(revised.status_code, 200)
            detail = client.get("/proposals/revision").json()
            self.assertTrue(detail["attestations"][0]["stale"])
            self.assertTrue(detail["open_for_review"])

            stale = client.post(
                "/proposals/revision/attest",
                json={
                    "decision": "rejected",
                    "reason": "This tab is stale",
                    "expected_proposal_version_id": before["receipt_id"],
                    "expected_proposal_receipt_ref": before["receipt_ref"],
                },
            )
            self.assertEqual(stale.status_code, 409)
            self.assertEqual(
                stale.json()["detail"]["code"],
                "proposal_version_conflict",
            )

    def test_read_only_mode_denies_write_and_persistence_failure_is_structured(self) -> None:
        writable = build_app(self._args("review"))
        self._seed(writable, "denied")
        writable.state.state_core_engine.dispose()
        read_only = build_app(self._args("read-only"))
        with TestClient(read_only) as client:
            version = client.get("/proposals/denied/revisions").json()["revisions"][0]
            denied = client.post(
                "/proposals/denied/attest",
                json={
                    "decision": "approved",
                    "reason": "Must be denied",
                    "expected_proposal_version_id": version["receipt_id"],
                    "expected_proposal_receipt_ref": version["receipt_ref"],
                },
            )
            self.assertEqual(denied.status_code, 403)
            self.assertEqual(denied.json()["detail"]["code"], "write_capability_required")
        read_only.state.state_core_engine.dispose()

        bad_root = self.root / "not-a-directory"
        bad_root.write_text("blocked", encoding="utf-8")
        failing = build_app(self._args("review", receipts=bad_root))
        with TestClient(failing, raise_server_exceptions=False) as client:
            failed = client.post(
                "/proposals",
                json={
                    "kind": "local_review",
                    "claim": "Persistence must fail visibly",
                    "source_refs": ["fixture://failure"],
                    "decision_scaffold": SCAFFOLD,
                },
            )
            self.assertEqual(failed.status_code, 503)
            self.assertEqual(failed.json()["detail"]["code"], "local_persistence_failure")

    def test_review_mode_rejects_non_loopback_binding(self) -> None:
        args = self._args("review")
        args.host = "0.0.0.0"  # noqa: S104 - negative test proves this binding is rejected
        with self.assertRaisesRegex(SystemExit, "loopback"):
            build_app(args)


if __name__ == "__main__":
    unittest.main()
