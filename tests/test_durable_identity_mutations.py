from __future__ import annotations

import inspect
import json
import multiprocessing
import tempfile
import time
import unittest
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from threading import Barrier
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlmodel import Session, select

from finharness.api.app import create_app
from finharness.api.routes_proposals import (
    ProposalCreateResponse,
    proposal_id_for_identity_mutation,
    reconcile_proposal_create_identity_mutation,
)
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
    record_verified_identity_mutation_reconciliation,
    request_body_sha256,
)
from finharness.project_paths import ROOT
from finharness.statecore.models import Proposal
from finharness.statecore.receipt_io import (
    atomic_write_json,
    durable_atomic_write_json,
    durable_compare_and_swap_json,
)
from finharness.statecore.store import init_state_core
from tests._scaffold import VALID_SCAFFOLD


def _cross_process_terminal_transition(
    path: str,
    state: str,
    ready_path: str,
    start_path: str,
) -> bool:
    """Wait for a file barrier, then attempt one terminal CAS."""

    Path(ready_path).write_text("ready", encoding="utf-8")
    start = Path(start_path)
    deadline = time.monotonic() + 10

    while not start.exists():
        if time.monotonic() >= deadline:
            raise TimeoutError("cross-process CAS start barrier timed out")
        time.sleep(0.01)

    return durable_compare_and_swap_json(
        path,
        expected_content_sha256="pending-version",
        expected_state="pending",
        payload={
            "state": state,
            "content_sha256": f"{state}-version",
        },
    )


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

    def _ambiguous_applied_mutation(
        self,
        idempotency_key: str,
    ) -> tuple[dict[str, str], Path, Proposal, Path]:
        """Create a domain effect whose terminal identity receipt was lost."""

        headers = self.headers | {
            IDEMPOTENCY_HEADER: idempotency_key,
        }
        with TestClient(
            self.app,
            raise_server_exceptions=False,
        ) as client:
            with patch(
                "finharness.api.app.complete_identity_mutation",
                side_effect=OSError("simulated post-commit receipt failure"),
            ):
                lost_response = client.post(
                    "/proposals",
                    headers=headers,
                    json=self.body,
                )

            retry = client.post(
                "/proposals",
                headers=headers,
                json=self.body,
            )

        self.assertEqual(lost_response.status_code, 500)
        self.assertEqual(retry.status_code, 409, retry.text)
        self.assertEqual(
            retry.json()["detail"]["code"],
            "mutation_outcome_ambiguous",
        )

        receipt_id = retry.headers[IDENTITY_RECEIPT_HEADER]
        receipt_path = self.root / "receipts" / "identity" / f"{receipt_id}.json"
        proposal_id = proposal_id_for_identity_mutation(receipt_id)

        with Session(self.engine) as session:
            proposal = session.get(Proposal, proposal_id)

        if proposal is None:
            self.fail("ambiguous mutation must have one persisted proposal effect")
        if not proposal.receipt_ref:
            self.fail("ambiguous proposal effect must have a domain receipt")

        domain_receipt_path = Path(proposal.receipt_ref)
        if not domain_receipt_path.is_absolute():
            domain_receipt_path = ROOT / domain_receipt_path

        self.assertTrue(domain_receipt_path.is_file())
        self.assertEqual(
            json.loads(receipt_path.read_text(encoding="utf-8"))["state"],
            "pending",
        )
        return (
            headers,
            receipt_path,
            proposal,
            domain_receipt_path,
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

    def test_committed_replay_survives_app_and_database_restart(self) -> None:
        headers = self.headers | {
            IDEMPOTENCY_HEADER: "restart-committed-0001",
        }

        with TestClient(self.app) as client:
            first = client.post(
                "/proposals",
                headers=headers,
                json=self.body,
            )

        self.assertEqual(first.status_code, 200, first.text)
        first_body = first.json()
        first_receipt_id = first.headers[IDENTITY_RECEIPT_HEADER]

        self.engine.dispose()

        restarted_engine = init_state_core(self.root / "state.sqlite")
        self.addCleanup(restarted_engine.dispose)
        restarted_app = create_app(
            state_core_engine=restarted_engine,
            receipt_root=str(self.root / "receipts"),
            identity_provider=TestIdentityProvider({"alice": _context()}),
        )

        with TestClient(restarted_app) as client:
            replay = client.post(
                "/proposals",
                headers=headers,
                json=self.body,
            )

        self.assertEqual(replay.status_code, 200, replay.text)
        self.assertEqual(replay.json(), first_body)
        self.assertEqual(
            replay.headers[IDEMPOTENT_REPLAY_HEADER],
            "true",
        )
        self.assertEqual(
            replay.headers[IDENTITY_RECEIPT_HEADER],
            first_receipt_id,
        )

        with Session(restarted_engine) as session:
            proposals = session.exec(select(Proposal)).all()
        self.assertEqual(len(proposals), 1)

    def test_ambiguous_effect_survives_restart_and_never_duplicates(self) -> None:
        headers, receipt_path, _proposal, _domain_path = self._ambiguous_applied_mutation(
            "restart-ambiguous-0001"
        )

        self.engine.dispose()

        restarted_engine = init_state_core(self.root / "state.sqlite")
        self.addCleanup(restarted_engine.dispose)
        restarted_app = create_app(
            state_core_engine=restarted_engine,
            receipt_root=str(self.root / "receipts"),
            identity_provider=TestIdentityProvider({"alice": _context()}),
        )

        with TestClient(restarted_app) as client:
            blocked_retry = client.post(
                "/proposals",
                headers=headers,
                json=self.body,
            )

        self.assertEqual(
            blocked_retry.status_code,
            409,
            blocked_retry.text,
        )
        self.assertEqual(
            blocked_retry.json()["detail"]["code"],
            "mutation_outcome_ambiguous",
        )

        with Session(restarted_engine) as session:
            proposals = session.exec(select(Proposal)).all()
        self.assertEqual(len(proposals), 1)

        reconciled = reconcile_proposal_create_identity_mutation(
            receipt_path,
            engine=restarted_engine,
            receipt_root=self.root / "receipts",
            reconciled_by="operator:alice",
            reason=(
                "Verified the persisted proposal after a full application and database restart."
            ),
        )
        self.assertEqual(
            reconciled["state"],
            "reconciled_applied",
        )

        restarted_engine.dispose()

        second_engine = init_state_core(self.root / "state.sqlite")
        self.addCleanup(second_engine.dispose)
        second_app = create_app(
            state_core_engine=second_engine,
            receipt_root=str(self.root / "receipts"),
            identity_provider=TestIdentityProvider({"alice": _context()}),
        )

        with TestClient(second_app) as client:
            replay = client.post(
                "/proposals",
                headers=headers,
                json=self.body,
            )

        self.assertEqual(replay.status_code, 200, replay.text)
        self.assertEqual(
            replay.headers[IDEMPOTENT_REPLAY_HEADER],
            "true",
        )

        with Session(second_engine) as session:
            proposals = session.exec(select(Proposal)).all()
        self.assertEqual(len(proposals), 1)

    def test_cross_process_terminal_race_has_exactly_one_winner(self) -> None:
        path = self.root / "cross-process-receipt.json"
        durable_atomic_write_json(
            path,
            {
                "state": "pending",
                "content_sha256": "pending-version",
            },
        )

        ready_a = self.root / "worker-a.ready"
        ready_b = self.root / "worker-b.ready"
        start_path = self.root / "workers.start"

        with ProcessPoolExecutor(
            max_workers=2,
            mp_context=multiprocessing.get_context("spawn"),
        ) as executor:
            first = executor.submit(
                _cross_process_terminal_transition,
                str(path),
                "committed",
                str(ready_a),
                str(start_path),
            )
            second = executor.submit(
                _cross_process_terminal_transition,
                str(path),
                "reconciled_applied",
                str(ready_b),
                str(start_path),
            )

            deadline = time.monotonic() + 10
            while not (ready_a.exists() and ready_b.exists()):
                if time.monotonic() >= deadline:
                    self.fail("cross-process CAS workers did not reach barrier")
                time.sleep(0.01)

            start_path.write_text(
                "start",
                encoding="utf-8",
            )
            results = [
                first.result(timeout=10),
                second.result(timeout=10),
            ]

        self.assertEqual(sorted(results), [False, True])
        terminal = json.loads(path.read_text(encoding="utf-8"))
        self.assertIn(
            terminal["state"],
            {"committed", "reconciled_applied"},
        )

    def test_false_reconciliation_evidence_matrix_fails_closed(self) -> None:
        scenarios = (
            (
                "missing_domain_receipt",
                "proposal domain receipt is unreadable",
            ),
            (
                "malformed_domain_receipt",
                "proposal domain receipt is unreadable",
            ),
            (
                "proposal_payload_mismatch",
                "proposal row and domain receipt do not match",
            ),
            (
                "proposal_content_hash_mismatch",
                "proposal domain receipt content hash does not match",
            ),
            (
                "mutation_receipt_id_mismatch",
                "proposal domain receipt mutation binding does not match",
            ),
            (
                "request_body_hash_mismatch",
                "proposal domain receipt mutation binding does not match",
            ),
            (
                "missing_mutation_source_ref",
                "proposal effect is not bound to the mutation receipt",
            ),
            (
                "domain_receipt_outside_root",
                "proposal receipt is outside the configured receipt root",
            ),
        )

        for index, (scenario, expected_error) in enumerate(
            scenarios,
            start=1,
        ):
            with self.subTest(scenario=scenario):
                (
                    _headers,
                    receipt_path,
                    proposal,
                    domain_receipt_path,
                ) = self._ambiguous_applied_mutation(f"false-evidence-{index:04d}")

                if scenario == "missing_domain_receipt":
                    domain_receipt_path.unlink()

                elif scenario == "malformed_domain_receipt":
                    domain_receipt_path.write_text(
                        "{bad json",
                        encoding="utf-8",
                    )

                elif scenario in {
                    "proposal_payload_mismatch",
                    "proposal_content_hash_mismatch",
                    "mutation_receipt_id_mismatch",
                    "request_body_hash_mismatch",
                }:
                    domain_receipt = json.loads(domain_receipt_path.read_text(encoding="utf-8"))

                    if scenario == "proposal_payload_mismatch":
                        domain_receipt["proposal"]["claim"] = "tampered proposal claim"
                    elif scenario == "proposal_content_hash_mismatch":
                        domain_receipt["content_hash"] = "0" * 64
                    elif scenario == "mutation_receipt_id_mismatch":
                        domain_receipt["revision_context"]["identity_mutation_receipt_id"] = (
                            "identity_mutation_wrong"
                        )
                    else:
                        domain_receipt["revision_context"][
                            "identity_mutation_request_body_sha256"
                        ] = "0" * 64

                    durable_atomic_write_json(
                        domain_receipt_path,
                        domain_receipt,
                    )

                elif scenario == "missing_mutation_source_ref":
                    with Session(self.engine) as session:
                        row = session.get(
                            Proposal,
                            proposal.proposal_id,
                        )
                        if row is None:
                            self.fail("proposal disappeared before tamper")
                        row.source_refs = [
                            ref
                            for ref in row.source_refs
                            if not ref.startswith("identity-mutation:")
                        ]
                        session.add(row)
                        session.commit()

                elif scenario == "domain_receipt_outside_root":
                    with Session(self.engine) as session:
                        row = session.get(
                            Proposal,
                            proposal.proposal_id,
                        )
                        if row is None:
                            self.fail("proposal disappeared before tamper")
                        row.receipt_ref = str(self.root / "outside-receipts" / "proposal.json")
                        session.add(row)
                        session.commit()

                with self.assertRaisesRegex(
                    IdentityMutationError,
                    expected_error,
                ):
                    reconcile_proposal_create_identity_mutation(
                        receipt_path,
                        engine=self.engine,
                        receipt_root=self.root / "receipts",
                        reconciled_by="operator:alice",
                        reason=("False or incomplete evidence must not create replay truth."),
                    )

                persisted = json.loads(receipt_path.read_text(encoding="utf-8"))
                self.assertEqual(
                    persisted["state"],
                    "pending",
                )

    def test_unsupported_route_cannot_be_reconciled_as_proposal(self) -> None:
        body = json.dumps(
            {"unsupported": True},
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        claim = begin_identity_mutation(
            self.root / "receipts" / "identity",
            context=_context(),
            method="POST",
            path="/unsupported",
            request_target="/unsupported",
            semantic_headers={
                "content-type": "application/json",
            },
            trace_id="trace:unsupported-route",
            idempotency_key="unsupported-route-0001",
            body_sha256=request_body_sha256(body),
        )

        with self.assertRaisesRegex(
            IdentityMutationError,
            "no typed reconciliation resolver",
        ):
            reconcile_proposal_create_identity_mutation(
                claim.receipt_path,
                engine=self.engine,
                receipt_root=self.root / "receipts",
                reconciled_by="operator:alice",
                reason="Unsupported routes must remain pending.",
            )

        persisted = json.loads(claim.receipt_path.read_text(encoding="utf-8"))
        self.assertEqual(persisted["state"], "pending")

    def test_terminal_receipt_cannot_be_reconciled_again(self) -> None:
        headers = self.headers | {
            IDEMPOTENCY_HEADER: "terminal-reconcile-0001",
        }
        with TestClient(self.app) as client:
            response = client.post(
                "/proposals",
                headers=headers,
                json=self.body,
            )

        self.assertEqual(response.status_code, 200, response.text)
        receipt_path = (
            self.root
            / "receipts"
            / "identity"
            / (response.headers[IDENTITY_RECEIPT_HEADER] + ".json")
        )

        with self.assertRaisesRegex(
            IdentityMutationError,
            "only a pending mutation can be reconciled",
        ):
            reconcile_proposal_create_identity_mutation(
                receipt_path,
                engine=self.engine,
                receipt_root=self.root / "receipts",
                reconciled_by="operator:alice",
                reason="Terminal receipts are immutable.",
            )

        persisted = json.loads(receipt_path.read_text(encoding="utf-8"))
        self.assertEqual(persisted["state"], "committed")

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

        with self.assertRaisesRegex(
            IdentityMutationError,
            "changed before terminal transition",
        ):
            record_verified_identity_mutation_reconciliation(
                claim.receipt_path,
                expected_payload=claim.payload,
                reconciled_by="operator:alice",
                reason=("Stale operator view must not replace committed truth."),
                resolver_id="test.stale-reconciliation.v1",
                evidence_refs=["test:stale-domain-evidence"],
                domain_effect={
                    "kind": "test_effect",
                    "canonical_resource": "/test/effect",
                },
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

    def test_typed_reconciliation_accepts_no_operator_response(self) -> None:
        parameters = inspect.signature(reconcile_proposal_create_identity_mutation).parameters
        self.assertNotIn("response_body", parameters)
        self.assertNotIn("response_file", parameters)
        self.assertNotIn("status_code", parameters)
        self.assertNotIn("content_type", parameters)

    def test_reconciliation_without_verified_effect_stays_pending(self) -> None:
        claim = self._pending_claim("missing-effect-0001")

        with self.assertRaisesRegex(
            IdentityMutationError,
            "verified proposal effect not found",
        ):
            reconcile_proposal_create_identity_mutation(
                claim.receipt_path,
                engine=self.engine,
                receipt_root=self.root / "receipts",
                reconciled_by="operator:alice",
                reason="No matching domain effect exists.",
            )

        persisted = json.loads(claim.receipt_path.read_text(encoding="utf-8"))
        self.assertEqual(persisted["state"], "pending")

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
        with TestClient(
            self.app,
            raise_server_exceptions=False,
        ) as client:
            with patch(
                "finharness.api.app.complete_identity_mutation",
                side_effect=OSError("simulated post-commit receipt failure"),
            ):
                lost_response = client.post(
                    "/proposals",
                    headers=self.headers,
                    json=self.body,
                )
            retry = client.post(
                "/proposals",
                headers=self.headers,
                json=self.body,
            )

        self.assertEqual(lost_response.status_code, 500)
        self.assertEqual(retry.status_code, 409, retry.text)
        self.assertEqual(
            retry.json()["detail"]["code"],
            "mutation_outcome_ambiguous",
        )
        self.assertEqual(self._proposal_count(), 1)

        receipt_id = retry.headers[IDENTITY_RECEIPT_HEADER]
        receipt_path = self.root / "receipts" / "identity" / f"{receipt_id}.json"
        self.assertEqual(
            json.loads(receipt_path.read_text(encoding="utf-8"))["state"],
            "pending",
        )

        reconciled = reconcile_proposal_create_identity_mutation(
            receipt_path,
            engine=self.engine,
            receipt_root=self.root / "receipts",
            reconciled_by="operator:alice",
            reason=("Verified the bound Proposal row and domain receipt after response loss."),
        )
        self.assertEqual(
            reconciled["state"],
            "reconciled_applied",
        )
        self.assertEqual(
            reconciled["reconciliation"]["resolver_id"],
            "finharness.api.proposal_create.v1",
        )
        self.assertEqual(
            reconciled["reconciliation"]["response_source"],
            "canonical_route_reconstruction",
        )

        with TestClient(self.app) as client:
            replay = client.post(
                "/proposals",
                headers=self.headers,
                json=self.body,
            )

        self.assertEqual(replay.status_code, 200, replay.text)
        replay_model = ProposalCreateResponse.model_validate(replay.json())
        self.assertFalse(replay_model.execution_allowed)
        self.assertEqual(
            replay_model.receipt_ref,
            replay_model.proposal.receipt_ref,
        )
        self.assertIn(
            f"identity-mutation:{receipt_id}",
            replay_model.proposal.source_refs,
        )
        self.assertEqual(
            replay.headers[IDEMPOTENT_REPLAY_HEADER],
            "true",
        )
        self.assertEqual(self._proposal_count(), 1)


if __name__ == "__main__":
    unittest.main()
