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
from finharness.api.routes_proposals import (
    identity_mutation_source_ref,
    reconcile_identity_mutation_from_domain_truth,
)
from finharness.identity import (
    IDEMPOTENCY_HEADER,
    IDEMPOTENT_REPLAY_HEADER,
    IDENTITY_RECEIPT_HEADER,
    IdentityMutationError,
    OperatorContext,
    PrincipalIdentity,
    TestIdentityProvider,
)
from finharness.project_paths import ROOT
from finharness.statecore.models import (
    Attestation,
    Proposal,
    ReceiptIndex,
    ReviewEvent,
)
from finharness.statecore.store import init_state_core
from tests._scaffold import VALID_SCAFFOLD


def _context() -> OperatorContext:
    return OperatorContext(
        principal=PrincipalIdentity(
            principal_id="principal:alice",
            provider_id="test",
        ),
        authentication_method="test_bearer",
        authenticated_at_utc=datetime.now(UTC).isoformat(),
    )


class IdentityMutationDomainBindingTest(unittest.TestCase):
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

        self.proposal_body = {
            "kind": "allocation",
            "claim": ("Cockpit effects bind to their identity mutation receipt."),
            "decision_scaffold": VALID_SCAFFOLD,
            "source_refs": ["test:domain-mutation-binding"],
        }

    def _headers(
        self,
        idempotency_key: str,
    ) -> dict[str, str]:
        return {
            "Authorization": "Bearer alice",
            IDEMPOTENCY_HEADER: idempotency_key,
        }

    def _read_receipt_ref(
        self,
        receipt_ref: str,
    ) -> dict:
        path = Path(receipt_ref)

        if not path.is_absolute():
            path = ROOT / path

        self.assertTrue(
            path.is_file(),
            f"receipt must exist: {path}",
        )

        return json.loads(path.read_text(encoding="utf-8"))

    def _read_identity_receipt(
        self,
        receipt_id: str,
    ) -> dict:
        path = self.root / "receipts" / "identity" / f"{receipt_id}.json"

        self.assertTrue(path.is_file())

        return json.loads(path.read_text(encoding="utf-8"))

    def _create_proposal(
        self,
        client: TestClient,
        *,
        key: str,
    ) -> dict:
        response = client.post(
            "/proposals",
            headers=self._headers(key),
            json=self.proposal_body,
        )

        self.assertEqual(
            response.status_code,
            200,
            response.text,
        )

        return response.json()["proposal"]

    def _assert_binding(
        self,
        *,
        identity_receipt_id: str,
        context: dict,
        effect_kind: str,
        method: str,
        path: str,
    ) -> None:
        identity_receipt = self._read_identity_receipt(identity_receipt_id)
        request_binding = identity_receipt["request"]

        self.assertEqual(
            context["schema"],
            ("finharness.api_domain_mutation_binding.v1"),
        )
        self.assertEqual(
            context["effect_kind"],
            effect_kind,
        )
        self.assertEqual(
            context["identity_mutation_receipt_id"],
            identity_receipt_id,
        )
        self.assertEqual(
            context["identity_mutation_request_body_sha256"],
            request_binding["body_sha256"],
        )
        self.assertEqual(
            context["identity_mutation_request_target"],
            request_binding["target"],
        )
        self.assertEqual(
            context["identity_mutation_method"],
            method,
        )
        self.assertEqual(
            context["identity_mutation_path"],
            path,
        )
        self.assertFalse(context["execution_allowed"])

    def test_attestation_receipt_binds_identity_mutation(
        self,
    ) -> None:
        with TestClient(self.app) as client:
            proposal = self._create_proposal(
                client,
                key="binding-proposal-attest-0001",
            )
            endpoint = f"/proposals/{proposal['proposal_id']}/attest"
            response = client.post(
                endpoint,
                headers=self._headers("binding-attestation-0001"),
                json={
                    "decision": "rejected",
                    "attester": "operator:alice",
                    "reason": ("Explicitly bind this review decision to its mutation."),
                    "source_refs": ["test:attestation-binding"],
                },
            )

        self.assertEqual(
            response.status_code,
            200,
            response.text,
        )

        identity_id = response.headers[IDENTITY_RECEIPT_HEADER]
        mutation_ref = identity_mutation_source_ref(identity_id)
        body = response.json()

        self.assertIn(
            mutation_ref,
            body["attestation"]["source_refs"],
        )

        receipt = self._read_receipt_ref(body["receipt_ref"])

        self._assert_binding(
            identity_receipt_id=identity_id,
            context=receipt["mutation_context"],
            effect_kind="api_attestation_create",
            method="POST",
            path=endpoint,
        )

    def test_scaffold_revision_binds_identity_mutation(
        self,
    ) -> None:
        with TestClient(self.app) as client:
            proposal = self._create_proposal(
                client,
                key="binding-proposal-scaffold-0001",
            )
            endpoint = f"/proposals/{proposal['proposal_id']}/decision-scaffold"
            response = client.patch(
                endpoint,
                headers=self._headers("binding-scaffold-0001"),
                json={
                    "attester": "operator:alice",
                    "reason": ("Record an exact mutation-bound scaffold revision."),
                    "decision_scaffold": {
                        "counter_evidence": ("A distinct binding-test counter-evidence condition.")
                    },
                    "source_refs": ["test:scaffold-binding"],
                },
            )

        self.assertEqual(
            response.status_code,
            200,
            response.text,
        )

        identity_id = response.headers[IDENTITY_RECEIPT_HEADER]
        mutation_ref = identity_mutation_source_ref(identity_id)
        body = response.json()

        self.assertIn(
            mutation_ref,
            body["proposal"]["source_refs"],
        )

        receipt = self._read_receipt_ref(body["receipt_ref"])

        self._assert_binding(
            identity_receipt_id=identity_id,
            context=receipt["revision_context"],
            effect_kind=("api_proposal_decision_scaffold_revision"),
            method="PATCH",
            path=endpoint,
        )

    def test_review_event_receipt_binds_identity_mutation(
        self,
    ) -> None:
        with TestClient(self.app) as client:
            proposal = self._create_proposal(
                client,
                key="binding-proposal-review-0001",
            )
            endpoint = f"/proposals/{proposal['proposal_id']}/review-events"
            response = client.post(
                endpoint,
                headers=self._headers("binding-review-event-0001"),
                json={
                    "kind": "annotation",
                    "attester": "operator:alice",
                    "reason": ("Record a mutation-bound review annotation."),
                    "text": ("This effect must be recoverable from domain truth."),
                    "source_refs": ["test:review-event-binding"],
                },
            )

        self.assertEqual(
            response.status_code,
            200,
            response.text,
        )

        identity_id = response.headers[IDENTITY_RECEIPT_HEADER]
        mutation_ref = identity_mutation_source_ref(identity_id)
        body = response.json()

        self.assertIn(
            mutation_ref,
            body["review_event"]["source_refs"],
        )

        receipt = self._read_receipt_ref(body["receipt_ref"])

        self._assert_binding(
            identity_receipt_id=identity_id,
            context=receipt["mutation_context"],
            effect_kind="api_review_event_create",
            method="POST",
            path=endpoint,
        )

    def _create_unkeyed_proposal(
        self,
        client: TestClient,
    ) -> dict:
        response = client.post(
            "/proposals",
            headers={
                "Authorization": "Bearer alice",
            },
            json=self.proposal_body,
        )

        self.assertEqual(
            response.status_code,
            200,
            response.text,
        )

        return response.json()["proposal"]

    def _identity_receipt_path(
        self,
        receipt_id: str,
    ) -> Path:
        return self.root / "receipts" / "identity" / f"{receipt_id}.json"

    def _lose_terminal_write(
        self,
        client: TestClient,
        *,
        method: str,
        endpoint: str,
        key: str,
        body: dict,
    ) -> tuple[str, Path]:
        headers = self._headers(key)

        with patch(
            "finharness.api.app.complete_identity_mutation",
            side_effect=OSError("simulated post-domain terminal receipt failure"),
        ):
            lost = client.request(
                method,
                endpoint,
                headers=headers,
                json=body,
            )

        self.assertEqual(
            lost.status_code,
            500,
            lost.text,
        )

        blocked = client.request(
            method,
            endpoint,
            headers=headers,
            json=body,
        )

        self.assertEqual(
            blocked.status_code,
            409,
            blocked.text,
        )
        self.assertEqual(
            blocked.json()["detail"]["code"],
            "mutation_outcome_ambiguous",
        )

        receipt_id = blocked.headers[IDENTITY_RECEIPT_HEADER]
        receipt_path = self._identity_receipt_path(receipt_id)

        self.assertTrue(receipt_path.is_file())

        pending = json.loads(receipt_path.read_text(encoding="utf-8"))
        self.assertEqual(
            pending["state"],
            "pending",
        )

        return receipt_id, receipt_path

    def _reconcile_and_replay(
        self,
        client: TestClient,
        *,
        receipt_id: str,
        receipt_path: Path,
        resolver_id: str,
        method: str,
        endpoint: str,
        key: str,
        body: dict,
    ) -> tuple[dict, dict]:
        reconciled = reconcile_identity_mutation_from_domain_truth(
            receipt_path,
            engine=self.engine,
            receipt_root=(self.root / "receipts"),
            reconciled_by="operator:alice",
            reason=(
                "Verified the exact persisted "
                "domain effect and its bound "
                "receipt after terminal loss."
            ),
        )

        self.assertEqual(
            reconciled["state"],
            "reconciled_applied",
        )
        self.assertEqual(
            reconciled["reconciliation"]["resolver_id"],
            resolver_id,
        )
        self.assertEqual(
            reconciled["reconciliation"]["response_source"],
            "canonical_route_reconstruction",
        )
        self.assertFalse(reconciled["reconciliation"]["domain_effect"]["execution_allowed"])

        replay = client.request(
            method,
            endpoint,
            headers=self._headers(key),
            json=body,
        )

        self.assertEqual(
            replay.status_code,
            200,
            replay.text,
        )
        self.assertEqual(
            replay.headers[IDEMPOTENT_REPLAY_HEADER],
            "true",
        )
        self.assertEqual(
            replay.headers[IDENTITY_RECEIPT_HEADER],
            receipt_id,
        )

        persisted = json.loads(receipt_path.read_text(encoding="utf-8"))
        self.assertEqual(
            persisted["state"],
            "reconciled_applied",
        )

        return reconciled, replay.json()

    def test_attestation_recovers_from_lost_terminal_write(
        self,
    ) -> None:
        with TestClient(
            self.app,
            raise_server_exceptions=False,
        ) as client:
            proposal = self._create_unkeyed_proposal(client)
            proposal_id = proposal["proposal_id"]
            endpoint = f"/proposals/{proposal_id}/attest"
            key = "recover-attestation-terminal-0001"
            body = {
                "decision": "rejected",
                "attester": "operator:alice",
                "reason": ("Reject while proving typed mutation recovery."),
                "source_refs": ["test:attestation-recovery"],
            }

            receipt_id, receipt_path = self._lose_terminal_write(
                client,
                method="POST",
                endpoint=endpoint,
                key=key,
                body=body,
            )

            mutation_ref = identity_mutation_source_ref(receipt_id)

            with Session(self.engine) as session:
                effects = list(
                    session.exec(
                        select(Attestation).where(Attestation.proposal_id == proposal_id)
                    ).all()
                )

            self.assertEqual(
                len(effects),
                1,
            )
            effect = effects[0]
            self.assertIn(
                mutation_ref,
                effect.source_refs,
            )

            reconciled, replay = self._reconcile_and_replay(
                client,
                receipt_id=receipt_id,
                receipt_path=receipt_path,
                resolver_id=("finharness.api.attestation_create.v1"),
                method="POST",
                endpoint=endpoint,
                key=key,
                body=body,
            )

            self.assertEqual(
                replay["attestation"]["attestation_id"],
                effect.attestation_id,
            )
            self.assertEqual(
                replay["proposal"]["proposal_id"],
                proposal_id,
            )
            self.assertEqual(
                reconciled["reconciliation"]["domain_effect"]["attestation_id"],
                effect.attestation_id,
            )

            with Session(self.engine) as session:
                final_effects = list(
                    session.exec(
                        select(Attestation).where(Attestation.proposal_id == proposal_id)
                    ).all()
                )

            self.assertEqual(
                len(final_effects),
                1,
            )

    def test_scaffold_revision_recovers_from_lost_terminal_write(
        self,
    ) -> None:
        with TestClient(
            self.app,
            raise_server_exceptions=False,
        ) as client:
            proposal = self._create_unkeyed_proposal(client)
            proposal_id = proposal["proposal_id"]
            previous_receipt_ref = proposal["receipt_ref"]
            endpoint = f"/proposals/{proposal_id}/decision-scaffold"
            key = "recover-scaffold-terminal-0001"
            body = {
                "attester": "operator:alice",
                "reason": ("Revise while proving exact historical receipt recovery."),
                "decision_scaffold": {
                    "counter_evidence": ("A recovery-specific counter-evidence condition.")
                },
                "source_refs": ["test:scaffold-recovery"],
            }

            receipt_id, receipt_path = self._lose_terminal_write(
                client,
                method="PATCH",
                endpoint=endpoint,
                key=key,
                body=body,
            )

            mutation_ref = identity_mutation_source_ref(receipt_id)

            with Session(self.engine) as session:
                current = session.get(
                    Proposal,
                    proposal_id,
                )
                indexes = list(
                    session.exec(
                        select(ReceiptIndex).where(ReceiptIndex.kind == "state_core_proposal")
                    ).all()
                )

            self.assertIsNotNone(current)
            assert current is not None

            bound_revisions = [index for index in indexes if mutation_ref in list(index.refs or [])]

            self.assertEqual(
                len(bound_revisions),
                1,
            )
            domain_receipt_ref = bound_revisions[0].path
            self.assertEqual(
                current.receipt_ref,
                domain_receipt_ref,
            )
            self.assertNotEqual(
                current.receipt_ref,
                previous_receipt_ref,
            )

            reconciled, replay = self._reconcile_and_replay(
                client,
                receipt_id=receipt_id,
                receipt_path=receipt_path,
                resolver_id=("finharness.api.proposal_scaffold_revision.v1"),
                method="PATCH",
                endpoint=endpoint,
                key=key,
                body=body,
            )

            self.assertEqual(
                replay["proposal"]["proposal_id"],
                proposal_id,
            )
            self.assertEqual(
                replay["receipt_ref"],
                domain_receipt_ref,
            )
            self.assertEqual(
                replay["previous_receipt_ref"],
                previous_receipt_ref,
            )
            self.assertIn(
                "counter_evidence",
                replay["changed_scaffold_fields"],
            )
            self.assertEqual(
                reconciled["reconciliation"]["domain_effect"]["receipt_ref"],
                domain_receipt_ref,
            )

            with Session(self.engine) as session:
                final_indexes = list(
                    session.exec(
                        select(ReceiptIndex).where(ReceiptIndex.kind == "state_core_proposal")
                    ).all()
                )

            final_bound = [
                index for index in final_indexes if mutation_ref in list(index.refs or [])
            ]

            self.assertEqual(
                len(final_bound),
                1,
            )

    def test_review_event_recovers_from_lost_terminal_write(
        self,
    ) -> None:
        with TestClient(
            self.app,
            raise_server_exceptions=False,
        ) as client:
            proposal = self._create_unkeyed_proposal(client)
            proposal_id = proposal["proposal_id"]
            endpoint = f"/proposals/{proposal_id}/review-events"
            key = "recover-review-event-terminal-0001"
            body = {
                "kind": "annotation",
                "attester": "operator:alice",
                "reason": ("Annotate while proving typed review-event recovery."),
                "text": ("This event must exist exactly once after replay."),
                "source_refs": ["test:review-event-recovery"],
            }

            receipt_id, receipt_path = self._lose_terminal_write(
                client,
                method="POST",
                endpoint=endpoint,
                key=key,
                body=body,
            )

            mutation_ref = identity_mutation_source_ref(receipt_id)

            with Session(self.engine) as session:
                effects = list(
                    session.exec(
                        select(ReviewEvent).where(ReviewEvent.proposal_id == proposal_id)
                    ).all()
                )

            self.assertEqual(
                len(effects),
                1,
            )
            effect = effects[0]
            self.assertIn(
                mutation_ref,
                effect.source_refs,
            )

            reconciled, replay = self._reconcile_and_replay(
                client,
                receipt_id=receipt_id,
                receipt_path=receipt_path,
                resolver_id=("finharness.api.review_event_create.v1"),
                method="POST",
                endpoint=endpoint,
                key=key,
                body=body,
            )

            self.assertEqual(
                replay["review_event"]["review_event_id"],
                effect.review_event_id,
            )
            self.assertEqual(
                replay["review_event"]["content_hash"],
                effect.content_hash,
            )
            self.assertEqual(
                reconciled["reconciliation"]["domain_effect"]["review_event_id"],
                effect.review_event_id,
            )

            with Session(self.engine) as session:
                final_effects = list(
                    session.exec(
                        select(ReviewEvent).where(ReviewEvent.proposal_id == proposal_id)
                    ).all()
                )

            self.assertEqual(
                len(final_effects),
                1,
            )

    def _resolve_receipt_path(
        self,
        receipt_ref: str,
    ) -> Path:
        path = Path(receipt_ref)

        if not path.is_absolute():
            path = ROOT / path

        return path

    def _assert_reconciliation_fails_closed(
        self,
        receipt_path: Path,
        *,
        message_pattern: str,
    ) -> None:
        before = receipt_path.read_bytes()
        before_payload = json.loads(before)

        self.assertEqual(
            before_payload["state"],
            "pending",
        )

        with self.assertRaisesRegex(
            IdentityMutationError,
            message_pattern,
        ):
            reconcile_identity_mutation_from_domain_truth(
                receipt_path,
                engine=self.engine,
                receipt_root=(self.root / "receipts"),
                reconciled_by="operator:alice",
                reason=(
                    "This reconciliation must remain "
                    "pending because its domain evidence "
                    "is not uniquely verifiable."
                ),
            )

        after = receipt_path.read_bytes()

        # Failed verification must not rewrite timestamps,
        # hashes, state or any other receipt evidence.
        self.assertEqual(after, before)

        after_payload = json.loads(after)
        self.assertEqual(
            after_payload["state"],
            "pending",
        )
        self.assertNotIn(
            "reconciliation",
            after_payload,
        )
        self.assertNotIn(
            "response",
            after_payload,
        )

    def test_tampered_attestation_binding_fails_closed(
        self,
    ) -> None:
        with TestClient(
            self.app,
            raise_server_exceptions=False,
        ) as client:
            proposal = self._create_unkeyed_proposal(client)
            proposal_id = proposal["proposal_id"]
            endpoint = f"/proposals/{proposal_id}/attest"
            body = {
                "decision": "rejected",
                "attester": "operator:alice",
                "reason": ("Create an attestation whose binding will be tested."),
                "source_refs": ["test:tampered-attestation-binding"],
            }

            receipt_id, identity_path = self._lose_terminal_write(
                client,
                method="POST",
                endpoint=endpoint,
                key=("tamper-attestation-binding-0001"),
                body=body,
            )

        mutation_ref = identity_mutation_source_ref(receipt_id)

        with Session(self.engine) as session:
            effects = list(
                session.exec(
                    select(Attestation).where(Attestation.proposal_id == proposal_id)
                ).all()
            )

        self.assertEqual(len(effects), 1)
        effect = effects[0]
        self.assertIn(
            mutation_ref,
            effect.source_refs,
        )

        receipt_refs = [
            ref
            for ref in effect.source_refs
            if isinstance(ref, str) and "attestations" in Path(ref).parts
        ]
        self.assertEqual(
            len(receipt_refs),
            1,
        )

        domain_path = self._resolve_receipt_path(receipt_refs[0])
        domain_receipt = json.loads(domain_path.read_text(encoding="utf-8"))

        context = domain_receipt.get("mutation_context")
        self.assertIsInstance(context, dict)
        assert isinstance(context, dict)

        # Preserve the domain row and response-shaped data,
        # but corrupt the cryptographic request binding.
        context["identity_mutation_request_body_sha256"] = "0" * 64

        domain_path.write_text(
            json.dumps(
                domain_receipt,
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

        self._assert_reconciliation_fails_closed(
            identity_path,
            message_pattern=("domain receipt mutation binding does not match"),
        )

        with Session(self.engine) as session:
            final_effects = list(
                session.exec(
                    select(Attestation).where(Attestation.proposal_id == proposal_id)
                ).all()
            )

        self.assertEqual(
            len(final_effects),
            1,
        )

    def test_multiple_review_events_for_one_mutation_fail_closed(
        self,
    ) -> None:
        with TestClient(
            self.app,
            raise_server_exceptions=False,
        ) as client:
            proposal = self._create_unkeyed_proposal(client)
            proposal_id = proposal["proposal_id"]
            endpoint = f"/proposals/{proposal_id}/review-events"
            body = {
                "kind": "annotation",
                "attester": "operator:alice",
                "reason": ("Create one legitimate mutation-bound review event."),
                "text": ("The resolver must reject ambiguous duplicate effects."),
                "source_refs": ["test:multiple-review-effects"],
            }

            receipt_id, identity_path = self._lose_terminal_write(
                client,
                method="POST",
                endpoint=endpoint,
                key=("multiple-review-effects-0001"),
                body=body,
            )

        mutation_ref = identity_mutation_source_ref(receipt_id)

        with Session(self.engine) as session:
            effects = list(
                session.exec(
                    select(ReviewEvent).where(ReviewEvent.proposal_id == proposal_id)
                ).all()
            )

        self.assertEqual(len(effects), 1)
        original = effects[0]
        self.assertIn(
            mutation_ref,
            original.source_refs,
        )

        # Inject corrupt StateCore evidence directly. This is
        # not a second API call; it proves the resolver refuses
        # to guess when domain truth is non-unique.
        duplicate_payload = original.model_dump(mode="python")
        duplicate_payload["review_event_id"] = f"{original.review_event_id}_duplicate"
        duplicate = ReviewEvent(**duplicate_payload)

        with Session(self.engine) as session:
            session.add(duplicate)
            session.commit()

        with Session(self.engine) as session:
            corrupted_effects = list(
                session.exec(
                    select(ReviewEvent).where(ReviewEvent.proposal_id == proposal_id)
                ).all()
            )

        self.assertEqual(
            len(corrupted_effects),
            2,
        )
        self.assertTrue(all(mutation_ref in event.source_refs for event in corrupted_effects))

        self._assert_reconciliation_fails_closed(
            identity_path,
            message_pattern=("multiple review event effects are bound to one mutation receipt"),
        )

    def test_missing_scaffold_revision_receipt_fails_closed(
        self,
    ) -> None:
        with TestClient(
            self.app,
            raise_server_exceptions=False,
        ) as client:
            proposal = self._create_unkeyed_proposal(client)
            proposal_id = proposal["proposal_id"]
            endpoint = f"/proposals/{proposal_id}/decision-scaffold"
            body = {
                "attester": "operator:alice",
                "reason": ("Create a mutation-bound historical revision."),
                "decision_scaffold": {
                    "counter_evidence": (
                        "A negative recovery fixture with missing receipt evidence."
                    )
                },
                "source_refs": ["test:missing-scaffold-receipt"],
            }

            receipt_id, identity_path = self._lose_terminal_write(
                client,
                method="PATCH",
                endpoint=endpoint,
                key=("missing-scaffold-receipt-0001"),
                body=body,
            )

        mutation_ref = identity_mutation_source_ref(receipt_id)

        with Session(self.engine) as session:
            proposal_row = session.get(
                Proposal,
                proposal_id,
            )
            indexes = list(
                session.exec(
                    select(ReceiptIndex).where(ReceiptIndex.kind == "state_core_proposal")
                ).all()
            )

        self.assertIsNotNone(proposal_row)
        assert proposal_row is not None

        bound_indexes = [index for index in indexes if mutation_ref in list(index.refs or [])]

        self.assertEqual(
            len(bound_indexes),
            1,
        )

        exact_revision_ref = bound_indexes[0].path
        self.assertEqual(
            proposal_row.receipt_ref,
            exact_revision_ref,
        )

        exact_revision_path = self._resolve_receipt_path(exact_revision_ref)
        self.assertTrue(exact_revision_path.is_file())

        # Keep the current Proposal row and ReceiptIndex but
        # remove the immutable receipt that proves the exact
        # historical effect. The resolver must not synthesize
        # an answer from mutable current state.
        exact_revision_path.unlink()

        self.assertFalse(exact_revision_path.exists())

        self._assert_reconciliation_fails_closed(
            identity_path,
            message_pattern=("domain receipt is missing or unreadable"),
        )

        with Session(self.engine) as session:
            final_proposal = session.get(
                Proposal,
                proposal_id,
            )
            final_indexes = list(
                session.exec(
                    select(ReceiptIndex).where(ReceiptIndex.kind == "state_core_proposal")
                ).all()
            )

        self.assertIsNotNone(final_proposal)
        assert final_proposal is not None
        self.assertEqual(
            final_proposal.receipt_ref,
            exact_revision_ref,
        )

        final_bound_indexes = [
            index for index in final_indexes if mutation_ref in list(index.refs or [])
        ]
        self.assertEqual(
            len(final_bound_indexes),
            1,
        )


if __name__ == "__main__":
    unittest.main()
