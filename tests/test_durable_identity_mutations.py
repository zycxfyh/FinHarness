from __future__ import annotations

import json
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlmodel import Session, select

from finharness.api.app import create_app
from finharness.identity import (
    IDEMPOTENCY_HEADER,
    IDEMPOTENT_REPLAY_HEADER,
    IDENTITY_RECEIPT_HEADER,
    OperatorContext,
    PrincipalIdentity,
    TestIdentityProvider,
    reconcile_identity_mutation_as_applied,
)
from finharness.statecore.models import Proposal
from finharness.statecore.receipt_io import atomic_write_json, durable_atomic_write_json
from finharness.statecore.store import init_state_core
from tests._scaffold import VALID_SCAFFOLD


def _context() -> OperatorContext:
    return OperatorContext(
        principal=PrincipalIdentity(principal_id="principal:alice", provider_id="test"),
        authentication_method="test_bearer",
        authenticated_at_utc=datetime.now(UTC).isoformat(),
    )


class DurableIdentityMutationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.engine = init_state_core(self.root / "state.sqlite")
        self.addCleanup(self.engine.dispose)
        self.app = create_app(
            state_core_engine=self.engine,
            receipt_root=str(self.root / "receipts"),
            identity_provider=TestIdentityProvider({"alice": _context()}),
        )
        self.body = {
            "kind": "allocation",
            "claim": "A keyed mutation is applied at most once.",
            "decision_scaffold": VALID_SCAFFOLD,
            "source_refs": ["test:durable-identity"],
        }
        self.headers = {
            "Authorization": "Bearer alice",
            IDEMPOTENCY_HEADER: "proposal-attempt-0001",
        }

    def _proposal_count(self) -> int:
        with Session(self.engine) as session:
            return len(session.exec(select(Proposal)).all())

    def test_durable_write_fsyncs_file_and_directory_but_atomic_write_does_not(self) -> None:
        with patch("finharness.statecore.receipt_io.os.fsync") as fsync:
            atomic_write_json(self.root / "replace-only.json", {"state": "complete"})
            self.assertEqual(fsync.call_count, 0)
            durable_atomic_write_json(self.root / "power-loss-durable.json", {"state": "complete"})
            self.assertGreaterEqual(fsync.call_count, 2)

    def test_completed_key_replays_response_without_duplicate_effect(self) -> None:
        with TestClient(self.app) as client:
            first = client.post("/proposals", headers=self.headers, json=self.body)
            second = client.post("/proposals", headers=self.headers, json=self.body)

        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(second.status_code, 200, second.text)
        self.assertEqual(second.json(), first.json())
        self.assertEqual(second.headers[IDEMPOTENT_REPLAY_HEADER], "true")
        self.assertEqual(
            second.headers[IDENTITY_RECEIPT_HEADER],
            first.headers[IDENTITY_RECEIPT_HEADER],
        )
        self.assertEqual(self._proposal_count(), 1)
        receipt_path = (
            self.root / "receipts" / "identity" / f"{first.headers[IDENTITY_RECEIPT_HEADER]}.json"
        )
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        self.assertEqual(receipt["state"], "committed")
        self.assertEqual(receipt["durability"], "power_loss_durable")

    def test_key_reuse_with_different_body_fails_before_route(self) -> None:
        changed = self.body | {"claim": "Different request under the same key."}
        with TestClient(self.app) as client:
            first = client.post("/proposals", headers=self.headers, json=self.body)
            conflict = client.post("/proposals", headers=self.headers, json=changed)

        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(conflict.status_code, 409, conflict.text)
        self.assertEqual(
            conflict.json()["detail"]["code"],
            "idempotency_key_reused_for_different_request",
        )
        self.assertEqual(self._proposal_count(), 1)

    def test_tampered_completed_receipt_fails_closed_before_route(self) -> None:
        with TestClient(self.app) as client:
            first = client.post("/proposals", headers=self.headers, json=self.body)
        receipt_path = (
            self.root / "receipts" / "identity" / f"{first.headers[IDENTITY_RECEIPT_HEADER]}.json"
        )
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        receipt["response"]["status_code"] = 201
        receipt_path.write_text(json.dumps(receipt), encoding="utf-8")

        with TestClient(self.app) as client:
            retry = client.post("/proposals", headers=self.headers, json=self.body)

        self.assertEqual(retry.status_code, 409, retry.text)
        self.assertEqual(retry.json()["detail"]["code"], "invalid_idempotency_contract")
        self.assertEqual(self._proposal_count(), 1)

    def test_failure_before_domain_call_has_no_effect(self) -> None:
        with (
            patch(
                "finharness.api.app.begin_identity_mutation",
                side_effect=OSError("simulated pre-commit durability failure"),
            ),
            TestClient(self.app, raise_server_exceptions=False) as client,
        ):
            response = client.post("/proposals", headers=self.headers, json=self.body)

        self.assertEqual(response.status_code, 500)
        self.assertEqual(self._proposal_count(), 0)

    def test_failure_after_domain_commit_blocks_retry_until_reconciled(self) -> None:
        with TestClient(self.app, raise_server_exceptions=False) as client:
            with patch(
                "finharness.api.app.complete_identity_mutation",
                side_effect=OSError("simulated post-commit receipt failure"),
            ):
                lost_response = client.post("/proposals", headers=self.headers, json=self.body)
            retry = client.post("/proposals", headers=self.headers, json=self.body)

        self.assertEqual(lost_response.status_code, 500)
        self.assertEqual(retry.status_code, 409, retry.text)
        self.assertEqual(retry.json()["detail"]["code"], "mutation_outcome_ambiguous")
        self.assertEqual(self._proposal_count(), 1)
        receipt_id = retry.headers[IDENTITY_RECEIPT_HEADER]
        receipt_path = self.root / "receipts" / "identity" / f"{receipt_id}.json"
        self.assertEqual(json.loads(receipt_path.read_text(encoding="utf-8"))["state"], "pending")

        reconciled_body = json.dumps(
            {"reconciled": True, "execution_allowed": False}, separators=(",", ":")
        ).encode()
        reconcile_identity_mutation_as_applied(
            receipt_path,
            reconciled_by="operator:alice",
            reason="Verified the proposal row and domain receipt after response loss.",
            status_code=200,
            response_body=reconciled_body,
        )
        with TestClient(self.app) as client:
            replay = client.post("/proposals", headers=self.headers, json=self.body)
        self.assertEqual(replay.status_code, 200)
        self.assertEqual(replay.json(), {"reconciled": True, "execution_allowed": False})
        self.assertEqual(replay.headers[IDEMPOTENT_REPLAY_HEADER], "true")
        self.assertEqual(self._proposal_count(), 1)


if __name__ == "__main__":
    unittest.main()
