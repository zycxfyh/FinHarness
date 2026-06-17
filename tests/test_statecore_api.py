from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from finharness.api.app import create_app
from finharness.statecore.models import (
    Account,
    Attestation,
    Position,
    Proposal,
    ReceiptIndex,
    Snapshot,
)
from finharness.statecore.store import StateCoreStoreError, init_state_core, read_all, write_records


class StateCoreApiTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.db_path = self.root / "state-core.sqlite"
        self.receipt_root = self.root / "receipts" / "state-core"
        self.engine = init_state_core(self.db_path)
        self._seed_state()
        self.client = TestClient(
            create_app(
                state_core_engine=self.engine,
                receipt_root=str(self.receipt_root),
            )
        )
        self.addCleanup(self.client.close)
        self.addCleanup(self.engine.dispose)
        self.addCleanup(self.tmp.cleanup)

    def _seed_state(self) -> None:
        account = Account(
            account_id="acct_api",
            kind="broker",
            venue="alpaca-paper",
            display_name="API Account",
            source_refs=["data/receipts/before.json"],
        )
        before = Snapshot(
            snapshot_id="snap_before",
            kind="portfolio",
            as_of_utc="2026-06-17T09:00:00+00:00",
            payload={"source": "broker_read"},
            source_refs=["data/receipts/before.json"],
        )
        after = Snapshot(
            snapshot_id="snap_after",
            kind="portfolio",
            as_of_utc="2026-06-17T10:00:00+00:00",
            payload={"source": "broker_read"},
            source_refs=["data/receipts/after.json"],
        )
        receipt = ReceiptIndex(
            receipt_id="receipt_after",
            kind="broker_read",
            path="data/receipts/after.json",
            created_at_utc="2026-06-17T10:00:00+00:00",
            source_refs=["data/receipts/after.json"],
        )
        positions = [
            Position(
                position_id="pos_before_spy",
                snapshot_id=before.snapshot_id,
                account_id=account.account_id,
                symbol="SPY",
                quantity=1.0,
                market_value=100.0,
                source_refs=["data/receipts/before.json"],
            ),
            Position(
                position_id="pos_after_spy",
                snapshot_id=after.snapshot_id,
                account_id=account.account_id,
                symbol="SPY",
                quantity=1.5,
                market_value=155.0,
                source_refs=["data/receipts/after.json"],
            ),
            Position(
                position_id="pos_after_aapl",
                snapshot_id=after.snapshot_id,
                account_id=account.account_id,
                symbol="AAPL",
                quantity=4.0,
                market_value=80.0,
                source_refs=["data/receipts/after.json"],
            ),
        ]
        write_records([account, before, after, receipt, *positions], engine=self.engine)

    def test_read_only_state_endpoints_return_pydantic_state_models(self) -> None:
        accounts = self.client.get("/state/accounts")
        positions = self.client.get("/state/positions", params={"snapshot_id": "snap_after"})
        snapshots = self.client.get("/snapshots", params={"kind": "portfolio"})
        receipt = self.client.get("/receipts/receipt_after")

        self.assertEqual(accounts.status_code, 200)
        self.assertEqual(accounts.json()[0]["account_id"], "acct_api")

        self.assertEqual(positions.status_code, 200)
        self.assertEqual([row["symbol"] for row in positions.json()], ["AAPL", "SPY"])

        self.assertEqual(snapshots.status_code, 200)
        self.assertEqual(
            [row["snapshot_id"] for row in snapshots.json()],
            ["snap_before", "snap_after"],
        )

        self.assertEqual(receipt.status_code, 200)
        self.assertEqual(receipt.json()["path"], "data/receipts/after.json")

    def test_diff_endpoint_returns_descriptive_diff_only(self) -> None:
        response = self.client.get(
            "/diff",
            params={
                "before_snapshot_id": "snap_before",
                "after_snapshot_id": "snap_after",
            },
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertFalse(body["execution_allowed"])
        self.assertEqual(body["total_market_value_before"], 100.0)
        self.assertEqual(body["total_market_value_after"], 235.0)
        self.assertEqual(body["total_market_value_delta"], 135.0)
        self.assertEqual([row["symbol"] for row in body["added"]], ["AAPL"])
        self.assertEqual([row["symbol"] for row in body["changed"]], ["SPY"])
        self.assertIn("Descriptive state diff only.", body["non_claims"])

    def test_missing_read_targets_return_not_found(self) -> None:
        receipt = self.client.get("/receipts/not_here")
        diff = self.client.get(
            "/diff",
            params={
                "before_snapshot_id": "snap_before",
                "after_snapshot_id": "snap_missing",
            },
        )

        self.assertEqual(receipt.status_code, 404)
        self.assertEqual(diff.status_code, 404)

    def test_openapi_exists_and_exposes_only_read_methods(self) -> None:
        response = self.client.get("/openapi.json")

        self.assertEqual(response.status_code, 200)
        schema = response.json()
        paths = schema["paths"]
        allowed_methods = {
            "/state/accounts": {"get"},
            "/state/positions": {"get"},
            "/snapshots": {"get"},
            "/diff": {"get"},
            "/receipts/{receipt_id}": {"get"},
            "/proposals": {"post"},
            "/proposals/{proposal_id}/attest": {"post"},
        }
        self.assertEqual(set(paths), set(allowed_methods))
        for path, methods in paths.items():
            self.assertEqual(set(methods), allowed_methods[path])
        for path in paths:
            for forbidden in ("authorize", "execute", "live", "order", "transfer"):
                self.assertNotIn(forbidden, path)

        schemas = schema["components"]["schemas"]
        for model_name in (
            "Account",
            "Attestation",
            "Position",
            "Proposal",
            "ReceiptIndex",
            "Snapshot",
        ):
            self.assertIn(model_name, schemas)

    def test_create_proposal_writes_db_receipt_and_index_without_authority(self) -> None:
        response = self.client.post(
            "/proposals",
            json={
                "kind": "rebalance_review",
                "claim": "Review concentration before any human decision.",
                "evidence": {"snapshot_id": "snap_after"},
                "assumptions": {"operator_review": "required"},
                "limitations": {"data_scope": "sample"},
                "non_claims": ["No profitability claim."],
                "source_refs": ["data/receipts/after.json"],
            },
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertFalse(body["execution_allowed"])
        self.assertFalse(body["proposal"]["execution_allowed"])
        self.assertIn("Not execution authorization.", body["proposal"]["non_claims"])

        proposals = read_all(Proposal, engine=self.engine)
        receipts = read_all(ReceiptIndex, engine=self.engine)
        self.assertEqual(len(proposals), 1)
        self.assertFalse(proposals[0].execution_allowed)
        self.assertEqual(proposals[0].receipt_ref, body["receipt_ref"])
        self.assertEqual(len(receipts), 2)
        proposal_receipt = next(
            receipt for receipt in receipts if receipt.kind == "state_core_proposal"
        )
        self.assertEqual(proposal_receipt.path, body["receipt_ref"])

        receipt_path = Path(body["receipt_ref"])
        self.assertTrue(receipt_path.exists())
        payload = json.loads(receipt_path.read_text(encoding="utf-8"))
        self.assertEqual(payload["kind"], "state_core_proposal")
        self.assertFalse(payload["governance"]["execution_allowed"])
        self.assertTrue(payload["governance"]["human_review_required"])
        self.assertTrue(payload["governance"]["not_execution_authorization"])

    def test_proposal_request_cannot_smuggle_execution_authority(self) -> None:
        response = self.client.post(
            "/proposals",
            json={
                "kind": "rebalance_review",
                "claim": "Review concentration.",
                "execution_allowed": True,
            },
        )

        self.assertEqual(response.status_code, 422)
        self.assertEqual(read_all(Proposal, engine=self.engine), [])

    def test_attestation_requires_reason_and_approval_is_not_execution_auth(self) -> None:
        created = self.client.post(
            "/proposals",
            json={
                "kind": "rebalance_review",
                "claim": "Review concentration before any human decision.",
                "source_refs": ["data/receipts/after.json"],
            },
        )
        proposal_id = created.json()["proposal"]["proposal_id"]

        rejected = self.client.post(
            f"/proposals/{proposal_id}/attest",
            json={
                "decision": "approved",
                "attester": "Jane Control",
                "reason": "   ",
            },
        )
        self.assertEqual(rejected.status_code, 422)
        self.assertEqual(read_all(Attestation, engine=self.engine), [])

        position_count = len(read_all(Position, engine=self.engine))
        approved = self.client.post(
            f"/proposals/{proposal_id}/attest",
            json={
                "decision": "approved",
                "attester": "Jane Control",
                "reason": "I reviewed the evidence; this records review only.",
            },
        )

        self.assertEqual(approved.status_code, 200)
        body = approved.json()
        self.assertFalse(body["execution_allowed"])
        self.assertTrue(body["approved_is_not_execution_authorization"])
        self.assertFalse(body["proposal"]["execution_allowed"])
        self.assertEqual(body["attestation"]["decision"], "approved")
        self.assertEqual(len(read_all(Position, engine=self.engine)), position_count)

        proposals = read_all(Proposal, engine=self.engine)
        attestations = read_all(Attestation, engine=self.engine)
        self.assertEqual(len(proposals), 1)
        self.assertEqual(len(attestations), 1)
        self.assertFalse(proposals[0].execution_allowed)
        self.assertIn(proposals[0].receipt_ref, attestations[0].source_refs)

        receipt_path = Path(body["receipt_ref"])
        self.assertTrue(receipt_path.exists())
        payload = json.loads(receipt_path.read_text(encoding="utf-8"))
        self.assertEqual(payload["kind"], "state_core_attestation")
        self.assertFalse(payload["governance"]["execution_allowed"])
        self.assertTrue(payload["governance"]["approved_is_not_execution_authorization"])

    def test_proposal_db_failure_cleans_orphan_receipt_best_effort(self) -> None:
        with patch(
            "finharness.api.routes_proposals.write_records",
            side_effect=StateCoreStoreError("forced db failure"),
        ):
            response = self.client.post(
                "/proposals",
                json={
                    "kind": "rebalance_review",
                    "claim": "Review concentration before any human decision.",
                },
            )

        self.assertEqual(response.status_code, 500)
        self.assertEqual(read_all(Proposal, engine=self.engine), [])
        self.assertEqual(list((self.receipt_root / "proposals").glob("*.json")), [])

    def test_attestation_db_failure_cleans_new_receipt_but_keeps_proposal_receipt(self) -> None:
        created = self.client.post(
            "/proposals",
            json={
                "kind": "rebalance_review",
                "claim": "Review concentration before any human decision.",
            },
        )
        proposal_receipt_ref = Path(created.json()["receipt_ref"])
        proposal_id = created.json()["proposal"]["proposal_id"]

        with patch(
            "finharness.api.routes_proposals.write_records",
            side_effect=StateCoreStoreError("forced db failure"),
        ):
            response = self.client.post(
                f"/proposals/{proposal_id}/attest",
                json={
                    "decision": "approved",
                    "attester": "Jane Control",
                    "reason": "Review-only approval.",
                },
            )

        self.assertEqual(response.status_code, 500)
        self.assertTrue(proposal_receipt_ref.exists())
        self.assertEqual(read_all(Attestation, engine=self.engine), [])
        self.assertEqual(list((self.receipt_root / "attestations").glob("*.json")), [])


if __name__ == "__main__":
    unittest.main()
