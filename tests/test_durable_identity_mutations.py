from __future__ import annotations

import json
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from threading import Barrier
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlmodel import Session, select

from finharness.api.app import create_app
from finharness.identity import (
    IDEMPOTENCY_HEADER,
    IDEMPOTENT_REPLAY_HEADER,
    IDENTITY_RECEIPT_HEADER,
    IdentityMutationError,
    OperatorContext,
    PrincipalIdentity,
    TestIdentityProvider,
    begin_identity_mutation,
    complete_identity_mutation,
    reconcile_identity_mutation_as_applied,
    request_body_sha256,
)
from finharness.statecore.models import Proposal
from finharness.statecore.receipt_io import (
    atomic_write_json,
    durable_atomic_write_json,
    durable_compare_and_swap_json,
)
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

    def _pending_claim(self, idempotency_key: str):
        body = json.dumps(
            self.body,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return begin_identity_mutation(
            self.root / "receipts" / "identity",
            context=_context(),
            method="POST",
            path="/proposals",
            request_target="/proposals",
            semantic_headers={"content-type": "application/json"},
            trace_id="trace:cas-test",
            idempotency_key=idempotency_key,
            body_sha256=request_body_sha256(body),
        )

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

    def test_key_reuse_with_different_query_fails_before_route(self) -> None:
        with TestClient(self.app) as client:
            first = client.post(
                "/proposals?mode=first",
                headers=self.headers,
                json=self.body,
            )
            conflict = client.post(
                "/proposals?mode=second",
                headers=self.headers,
                json=self.body,
            )

        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(conflict.status_code, 409, conflict.text)
        self.assertEqual(
            conflict.json()["detail"]["code"],
            "idempotency_key_reused_for_different_request",
        )
        self.assertEqual(self._proposal_count(), 1)

    def test_key_reuse_with_different_content_type_fails_before_route(self) -> None:
        body = json.dumps(self.body, separators=(",", ":")).encode()
        first_headers = self.headers | {"content-type": "application/json"}
        changed_headers = self.headers | {"content-type": "application/vnd.finharness+json"}

        with TestClient(self.app) as client:
            first = client.post(
                "/proposals",
                headers=first_headers,
                content=body,
            )
            conflict = client.post(
                "/proposals",
                headers=changed_headers,
                content=body,
            )

        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(conflict.status_code, 409, conflict.text)
        self.assertEqual(
            conflict.json()["detail"]["code"],
            "idempotency_key_reused_for_different_request",
        )
        self.assertEqual(self._proposal_count(), 1)

    def test_oversized_keyed_request_is_rejected_before_route(self) -> None:
        def body_chunks():
            yield b'{"padding":"'
            yield b"x" * 128
            yield b'"}'

        headers = self.headers | {"content-type": "application/json"}
        with (
            patch("finharness.api.app._MAX_IDEMPOTENT_REQUEST_BYTES", 32),
            TestClient(self.app) as client,
        ):
            response = client.post(
                "/proposals",
                headers=headers,
                content=body_chunks(),
            )

        self.assertEqual(response.status_code, 413, response.text)
        self.assertEqual(
            response.json()["detail"]["code"],
            "idempotent_request_too_large",
        )
        self.assertEqual(response.json()["detail"]["limit_bytes"], 32)
        self.assertEqual(self._proposal_count(), 0)
        self.assertNotIn(IDENTITY_RECEIPT_HEADER, response.headers)

    def test_oversized_response_leaves_pending_and_blocks_retry(self) -> None:
        with TestClient(self.app) as client:
            with patch(
                "finharness.api.app._MAX_IDEMPOTENT_RESPONSE_BYTES",
                1,
            ):
                response = client.post(
                    "/proposals",
                    headers=self.headers,
                    json=self.body,
                )
            retry = client.post(
                "/proposals",
                headers=self.headers,
                json=self.body,
            )

        self.assertEqual(response.status_code, 503, response.text)
        self.assertEqual(
            response.json()["detail"]["code"],
            "idempotent_response_too_large",
        )
        self.assertEqual(response.json()["detail"]["limit_bytes"], 1)
        self.assertEqual(self._proposal_count(), 1)

        receipt_id = response.headers[IDENTITY_RECEIPT_HEADER]
        receipt_path = self.root / "receipts" / "identity" / f"{receipt_id}.json"
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        self.assertEqual(receipt["state"], "pending")

        self.assertEqual(retry.status_code, 409, retry.text)
        self.assertEqual(
            retry.json()["detail"]["code"],
            "mutation_outcome_ambiguous",
        )
        self.assertEqual(
            retry.headers[IDENTITY_RECEIPT_HEADER],
            receipt_id,
        )
        self.assertEqual(self._proposal_count(), 1)

    def test_compare_and_swap_allows_exactly_one_terminal_writer(self) -> None:
        path = self.root / "receipt-cas.json"
        pending = {
            "state": "pending",
            "content_sha256": "pending-version",
        }
        durable_atomic_write_json(path, pending)
        barrier = Barrier(2)

        def transition(state: str) -> bool:
            barrier.wait()
            return durable_compare_and_swap_json(
                path,
                expected_content_sha256="pending-version",
                expected_state="pending",
                payload={
                    "state": state,
                    "content_sha256": f"{state}-version",
                },
            )

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(
                executor.map(
                    transition,
                    ["committed", "reconciled_applied"],
                )
            )

        self.assertEqual(sorted(results), [False, True])
        terminal = json.loads(path.read_text(encoding="utf-8"))
        self.assertIn(
            terminal["state"],
            {"committed", "reconciled_applied"},
        )

    def test_stale_reconciliation_cannot_overwrite_committed_receipt(self) -> None:
        claim = self._pending_claim("stale-reconcile-0001")
        completed = complete_identity_mutation(
            claim,
            trace_id="trace:complete",
            status_code=200,
            response_body=b'{"ok":true}',
            content_type="application/json",
        )

        with (
            patch(
                "finharness.identity._load_identity_mutation_receipt",
                return_value=claim.payload,
            ),
            self.assertRaisesRegex(
                IdentityMutationError,
                "changed before terminal transition",
            ),
        ):
            reconcile_identity_mutation_as_applied(
                claim.receipt_path,
                reconciled_by="operator:alice",
                reason="Stale operator view must not replace committed truth.",
                status_code=200,
                response_body=b'{"incorrect":"replacement"}',
            )

        persisted = json.loads(claim.receipt_path.read_text(encoding="utf-8"))
        self.assertEqual(persisted["state"], "committed")
        self.assertEqual(
            persisted["content_sha256"],
            completed["content_sha256"],
        )
        self.assertEqual(
            persisted["previous_content_sha256"],
            claim.payload["content_sha256"],
        )

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

    def test_invalid_identity_contract_hides_internal_details(self) -> None:
        secret_path = "/root/private/identity/secret-receipt.json"
        internal_error = f"existing mutation receipt is unreadable: {secret_path}"
        with (
            patch(
                "finharness.api.app.begin_identity_mutation",
                side_effect=IdentityMutationError(internal_error),
            ),
            patch("finharness.api.app.logger.warning") as warning,
            TestClient(self.app) as client,
        ):
            response = client.post(
                "/proposals",
                headers=self.headers,
                json=self.body,
            )

        self.assertEqual(response.status_code, 409, response.text)
        detail = response.json()["detail"]
        self.assertEqual(detail["code"], "invalid_idempotency_contract")
        self.assertEqual(
            detail["message"],
            "The mutation identity receipt could not be validated.",
        )
        self.assertEqual(
            detail["trace_id"],
            response.headers["x-finharness-trace-id"],
        )
        self.assertNotIn(secret_path, response.text)
        self.assertNotIn(internal_error, response.text)

        warning.assert_called_once()
        log_fields = warning.call_args.kwargs
        self.assertEqual(log_fields["trace_id"], detail["trace_id"])
        self.assertEqual(log_fields["error_type"], "IdentityMutationError")
        self.assertEqual(log_fields["error_message"], internal_error)

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
