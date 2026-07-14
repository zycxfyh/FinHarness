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
from finharness.statecore.proposals import proposal_content_hash
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

    def test_scaffold_reconciliation_selects_exact_revision_after_later_revision(
        self,
    ) -> None:
        """Reconciliation must use exact revision_context binding, not inherited source_refs.

        When mutation A creates Revision A (counter_evidence), then a separate
        Revision B (alternatives) inherits A's source_refs, the scaffold resolver
        must NOT treat both ReceiptIndex entries as exact evidence. It must locate
        Revision A via its exact revision_context.identity_mutation_receipt_id and
        reconstruct the canonical response from A's immutable receipt snapshot.
        """
        with TestClient(
            self.app,
            raise_server_exceptions=False,
        ) as client:
            # -- 7.1 Create base Proposal (unkeyed) --
            proposal = self._create_unkeyed_proposal(client)
            proposal_id = proposal["proposal_id"]
            initial_receipt_ref = proposal["receipt_ref"]

            endpoint = f"/proposals/{proposal_id}/decision-scaffold"

            # -- 7.2 Keyed Revision A with simulated terminal loss --
            key_a = "recover-scaffold-before-later-revision-0001"
            body_a = {
                "attester": "operator:alice",
                "reason": "Revision A: counter_evidence",
                "decision_scaffold": {
                    "counter_evidence": "Reconciliation recovery counter-evidence."
                },
                "source_refs": ["test:scaffold-exact-revision-a"],
            }

            receipt_id_a, receipt_path_a = self._lose_terminal_write(
                client,
                method="PATCH",
                endpoint=endpoint,
                key=key_a,
                body=body_a,
            )

            mutation_ref_a = identity_mutation_source_ref(receipt_id_a)

            with Session(self.engine) as session:
                current = session.get(Proposal, proposal_id)
                indexes = list(
                    session.exec(
                        select(ReceiptIndex).where(ReceiptIndex.kind == "state_core_proposal")
                    ).all()
                )

            self.assertIsNotNone(current)
            assert current is not None

            # After A's domain write, exactly one ReceiptIndex binds mutation_ref.
            bound_a = [index for index in indexes if mutation_ref_a in list(index.refs or [])]
            self.assertEqual(len(bound_a), 1)
            revision_a_receipt_ref = bound_a[0].path
            self.assertEqual(current.receipt_ref, revision_a_receipt_ref)
            self.assertNotEqual(current.receipt_ref, initial_receipt_ref)

            # Read Revision A's receipt to capture its changed fields and
            # previous_receipt_ref for later assertions.
            revision_a_path = self._resolve_receipt_path(revision_a_receipt_ref)
            revision_a_receipt = json.loads(revision_a_path.read_text(encoding="utf-8"))
            revision_a_context = revision_a_receipt.get("revision_context", {})
            self.assertEqual(
                revision_a_context.get("identity_mutation_receipt_id"),
                receipt_id_a,
            )
            revision_a_previous_ref = revision_a_context.get("previous_receipt_ref")
            revision_a_changed_fields = revision_a_context.get("changed_scaffold_fields", [])
            self.assertIn("counter_evidence", revision_a_changed_fields)

            # -- 7.3 Create legitimate later Revision B (different field, no key) --
            body_b = {
                "attester": "operator:alice",
                "reason": "Revision B: alternatives",
                "decision_scaffold": {"alternatives": "Later revision alternatives."},
                "source_refs": ["test:scaffold-exact-revision-b"],
            }

            rev_b_response = client.patch(
                endpoint,
                headers={"Authorization": "Bearer alice"},
                json=body_b,
            )

            self.assertEqual(
                rev_b_response.status_code,
                200,
                rev_b_response.text,
            )
            rev_b_body = rev_b_response.json()
            revision_b_receipt_ref = rev_b_body["receipt_ref"]
            self.assertNotEqual(revision_b_receipt_ref, revision_a_receipt_ref)

            with Session(self.engine) as session:
                current_b = session.get(Proposal, proposal_id)
                indexes_b = list(
                    session.exec(
                        select(ReceiptIndex).where(ReceiptIndex.kind == "state_core_proposal")
                    ).all()
                )

            self.assertIsNotNone(current_b)
            assert current_b is not None
            self.assertEqual(current_b.receipt_ref, revision_b_receipt_ref)

            # -- 7.4 Prove mutation_ref is inherited by Revision B --
            candidates_after_b = [
                index for index in indexes_b if mutation_ref_a in list(index.refs or [])
            ]
            self.assertGreaterEqual(
                len(candidates_after_b),
                2,
                "At least Revision A and Revision B ReceiptIndex "
                "rows must contain the mutation_ref via inherited "
                "source_refs; otherwise this test does not reproduce "
                "the inherited-ref ambiguity defect.",
            )

            # -- 7.5 Execute typed reconciliation --
            reconciled = reconcile_identity_mutation_from_domain_truth(
                receipt_path_a,
                engine=self.engine,
                receipt_root=(self.root / "receipts"),
                reconciled_by="operator:alice",
                reason=(
                    "Verified exact scaffold revision from immutable receipt "
                    "after a later revision inherited the mutation ref."
                ),
            )

            self.assertEqual(
                reconciled["state"],
                "reconciled_applied",
            )
            self.assertEqual(
                reconciled["reconciliation"]["resolver_id"],
                "finharness.api.proposal_scaffold_revision.v1",
            )
            self.assertEqual(
                reconciled["reconciliation"]["response_source"],
                "canonical_route_reconstruction",
            )
            domain_effect = reconciled["reconciliation"]["domain_effect"]
            self.assertEqual(
                domain_effect["receipt_ref"],
                revision_a_receipt_ref,
            )
            self.assertEqual(
                domain_effect["previous_receipt_ref"],
                revision_a_previous_ref,
            )
            self.assertFalse(domain_effect["execution_allowed"])

            # -- 7.6 Same-key replay returns Revision A history --
            replay = client.request(
                "PATCH",
                endpoint,
                headers=self._headers(key_a),
                json=body_a,
            )

            self.assertEqual(replay.status_code, 200, replay.text)
            self.assertEqual(
                replay.headers[IDEMPOTENT_REPLAY_HEADER],
                "true",
            )
            self.assertEqual(
                replay.headers[IDENTITY_RECEIPT_HEADER],
                receipt_id_a,
            )

            replay_body = replay.json()
            self.assertEqual(
                replay_body["receipt_ref"],
                revision_a_receipt_ref,
            )
            self.assertEqual(
                replay_body["previous_receipt_ref"],
                revision_a_previous_ref,
            )
            self.assertIn(
                "counter_evidence",
                replay_body["changed_scaffold_fields"],
            )
            self.assertEqual(
                replay_body["proposal"]["receipt_ref"],
                revision_a_receipt_ref,
            )
            # Replay response must NOT return Revision B's current state.
            self.assertNotEqual(
                replay_body["proposal"]["receipt_ref"],
                revision_b_receipt_ref,
            )

            # -- 7.7 Current domain state is not rolled back --
            with Session(self.engine) as session:
                final_proposal = session.get(Proposal, proposal_id)

            self.assertIsNotNone(final_proposal)
            assert final_proposal is not None
            self.assertEqual(
                final_proposal.receipt_ref,
                revision_b_receipt_ref,
            )

            # -- 7.8 No extra domain effects --
            with Session(self.engine) as session:
                final_indexes = list(
                    session.exec(
                        select(ReceiptIndex).where(ReceiptIndex.kind == "state_core_proposal")
                    ).all()
                )

            # Exactly two Proposal ReceiptIndex entries:
            # the initial creation + Revision B. Reconciliation
            # must NOT create Revision C or a new ReceiptIndex.
            # Note: the initial proposal create generates one ReceiptIndex,
            # Revision A (keyed) generates one, Revision B (non-keyed)
            # generates one. That makes three total.  But
            # ReceiptIndex is created at proposal creation time too.
            # Actually, both Revision A and B each produce one index,
            # and the unkeyed proposal create also produces one.
            # Total >= 3 is normal. The key assertion is that
            # reconciliation does NOT add a new one.
            exact_a_matches = [
                index for index in final_indexes if revision_a_receipt_ref in (index.path or "")
            ]
            self.assertEqual(
                len(exact_a_matches),
                1,
                "Revision A receipt must still be referenced exactly once.",
            )
            exact_b_matches = [
                index for index in final_indexes if revision_b_receipt_ref in (index.path or "")
            ]
            self.assertEqual(
                len(exact_b_matches),
                1,
                "Revision B receipt must still be referenced exactly once.",
            )

    def test_multiple_exact_scaffold_revision_bindings_fail_closed(
        self,
    ) -> None:
        """Reconciliation must fail closed when two receipts claim the SAME
        exact identity_mutation_receipt_id.

        Unlike inherited source_refs — where a later revision happens to carry
        an older mutation_ref — this test constructs genuine exact-effect
        ambiguity: two distinct proposal receipts whose revision_context both
        claim the target receipt_id with matching full binding.
        """
        with TestClient(
            self.app,
            raise_server_exceptions=False,
        ) as client:
            proposal = self._create_unkeyed_proposal(client)
            proposal_id = proposal["proposal_id"]
            endpoint = f"/proposals/{proposal_id}/decision-scaffold"

            # -- Keyed Revision A with terminal loss --
            key_a = "exact-ambiguity-scaffold-0001"
            body_a = {
                "attester": "operator:alice",
                "reason": "Ambiguity: counter_evidence",
                "decision_scaffold": {"counter_evidence": "Ambiguity counter-evidence."},
                "source_refs": ["test:exact-ambiguity-a"],
            }

            receipt_id_a, receipt_path_a = self._lose_terminal_write(
                client,
                method="PATCH",
                endpoint=endpoint,
                key=key_a,
                body=body_a,
            )

            # Read Revision A's domain receipt to get its revision_context.
            with Session(self.engine) as session:
                indexes = list(
                    session.exec(
                        select(ReceiptIndex).where(ReceiptIndex.kind == "state_core_proposal")
                    ).all()
                )

            mutation_ref_a = identity_mutation_source_ref(receipt_id_a)
            bound = [index for index in indexes if mutation_ref_a in list(index.refs or [])]
            self.assertEqual(len(bound), 1)
            revision_a_ref = bound[0].path

            revision_a_path = self._resolve_receipt_path(revision_a_ref)
            revision_a_receipt = json.loads(revision_a_path.read_text(encoding="utf-8"))
            revision_a_context = revision_a_receipt.get("revision_context", {})

            # Verify Revision A has the correct exact binding.
            self.assertEqual(
                revision_a_context.get("identity_mutation_receipt_id"),
                receipt_id_a,
            )

            # -- Clone Revision A's receipt to create a second receipt that
            #    also claims the same exact identity_mutation_receipt_id --
            #    This simulates a genuine exact-effect ambiguity where two
            #    immutable receipts both claim the same mutation.

            # Find the next available receipt ref path.
            revision_a_dir = revision_a_path.parent
            duplicate_receipt_ref = str(revision_a_dir / "proposal_duplicate_ambiguity.json")

            # Write a distinct proposal snapshot that shares the same
            # exact identity_mutation_receipt_id binding.
            duplicate_proposal_snapshot = dict(revision_a_receipt["proposal"])
            if duplicate_proposal_snapshot.get("claim"):
                duplicate_proposal_snapshot["claim"] = (
                    "AMBIGUITY DUPLICATE: " + duplicate_proposal_snapshot["claim"]
                )

            # Use the canonical domain hash so verification passes.
            duplicate_proposal_snapshot["receipt_ref"] = duplicate_receipt_ref
            dup_proposal = Proposal.model_validate(duplicate_proposal_snapshot)
            duplicate_content_hash = proposal_content_hash(dup_proposal)

            duplicate_receipt = {
                "kind": "state_core_proposal",
                "proposal": duplicate_proposal_snapshot,
                "content_hash": duplicate_content_hash,
                "revision_context": {
                    **revision_a_context,
                    "changed_scaffold_fields": [
                        "counter_evidence",
                        "thesis",
                    ],
                },
                "supersedes": revision_a_context.get("previous_receipt_ref"),
            }

            duplicate_path = self._resolve_receipt_path(duplicate_receipt_ref)
            duplicate_path.write_text(
                json.dumps(duplicate_receipt, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )

            # Register the duplicate in ReceiptIndex.
            with Session(self.engine) as session:
                dup_index = ReceiptIndex(
                    receipt_id="receipt:duplicate-ambiguity-0001",
                    refs=[mutation_ref_a],
                    kind="state_core_proposal",
                    path=duplicate_receipt_ref,
                )
                session.add(dup_index)
                session.commit()

                # Confirm both receipts now claim the same mutation.
                post_indexes = list(
                    session.exec(
                        select(ReceiptIndex).where(ReceiptIndex.kind == "state_core_proposal")
                    ).all()
                )

            exact_candidates = [
                index for index in post_indexes if mutation_ref_a in list(index.refs or [])
            ]
            self.assertGreaterEqual(
                len(exact_candidates),
                2,
                "Both the original and duplicate receipts must "
                "reference mutation_ref_a for the test to be valid.",
            )

            # Both receipts claim receipt_id_a in their exact binding.
            self._assert_reconciliation_fails_closed(
                receipt_path_a,
                message_pattern=("multiple scaffold revisions are bound to one mutation receipt"),
            )

            # Clean up: remove the duplicate ReceiptIndex so it does not
            # contaminate later tests.
            with Session(self.engine) as session:
                dup_row = session.exec(
                    select(ReceiptIndex).where(ReceiptIndex.path == duplicate_receipt_ref)
                ).first()
                if dup_row is not None:
                    session.delete(dup_row)
                    session.commit()

            # Remove the duplicate receipt file.
            if duplicate_path.is_file():
                duplicate_path.unlink()

    def test_scaffold_reconciliation_rejects_unreadable_candidate_alongside_exact_match(
        self,
    ) -> None:
        """Reconciliation must fail closed when one of several candidates is unreadable.

        If Candidate A is the exact match and Candidate B is unreadable/corrupt,
        the system cannot prove that B is merely an inherited reference — it could
        be a second domain effect, a tampered receipt, or corrupted duplicate
        evidence. The only safe disposition is to keep the mutation pending.
        """
        with TestClient(
            self.app,
            raise_server_exceptions=False,
        ) as client:
            # -- Base Proposal --
            proposal = self._create_unkeyed_proposal(client)
            proposal_id = proposal["proposal_id"]
            endpoint = f"/proposals/{proposal_id}/decision-scaffold"

            # -- Keyed Revision A with terminal loss --
            key_a = "corrupt-candidate-revision-a-0001"
            body_a = {
                "attester": "operator:alice",
                "reason": "Revision A: counter_evidence",
                "decision_scaffold": {
                    "counter_evidence": "Corrupt-candidate test counter-evidence."
                },
                "source_refs": ["test:corrupt-candidate-a"],
            }

            receipt_id_a, receipt_path_a = self._lose_terminal_write(
                client,
                method="PATCH",
                endpoint=endpoint,
                key=key_a,
                body=body_a,
            )

            mutation_ref_a = identity_mutation_source_ref(receipt_id_a)

            # -- Later unkeyed Revision B that inherits A's mutation_ref --
            body_b = {
                "attester": "operator:alice",
                "reason": "Revision B: alternatives",
                "decision_scaffold": {"alternatives": "Later revision alternatives."},
                "source_refs": ["test:corrupt-candidate-b"],
            }

            rev_b_response = client.patch(
                endpoint,
                headers={"Authorization": "Bearer alice"},
                json=body_b,
            )

            self.assertEqual(rev_b_response.status_code, 200, rev_b_response.text)
            rev_b_body = rev_b_response.json()
            revision_b_receipt_ref = rev_b_body["receipt_ref"]

            # -- Prove candidates >= 2 --
            with Session(self.engine) as session:
                indexes = list(
                    session.exec(
                        select(ReceiptIndex).where(ReceiptIndex.kind == "state_core_proposal")
                    ).all()
                )

            candidates = [index for index in indexes if mutation_ref_a in list(index.refs or [])]
            self.assertGreaterEqual(
                len(candidates),
                2,
                "Need at least 2 candidates to reproduce the defect.",
            )

            # -- Corrupt Revision B receipt (delete it) --
            revision_b_path = self._resolve_receipt_path(revision_b_receipt_ref)
            self.assertTrue(revision_b_path.is_file())
            revision_b_path.unlink()
            self.assertFalse(revision_b_path.exists())

            # -- Reconciliation must fail closed, not silently skip B --
            before = receipt_path_a.read_bytes()

            with self.assertRaisesRegex(
                IdentityMutationError,
                "domain receipt is missing or unreadable",
            ):
                reconcile_identity_mutation_from_domain_truth(
                    receipt_path_a,
                    engine=self.engine,
                    receipt_root=(self.root / "receipts"),
                    reconciled_by="operator:alice",
                    reason="Must fail because one candidate is unreadable.",
                )

            # Identity receipt bytes unchanged
            after = receipt_path_a.read_bytes()
            self.assertEqual(after, before)

            # State remains pending
            pending = json.loads(after)
            self.assertEqual(pending["state"], "pending")
            self.assertNotIn("reconciliation", pending)
            self.assertNotIn("response", pending)

            # Current Proposal remains Revision B
            with Session(self.engine) as session:
                final_proposal = session.get(Proposal, proposal_id)

            self.assertIsNotNone(final_proposal)
            assert final_proposal is not None
            self.assertEqual(
                final_proposal.receipt_ref,
                revision_b_receipt_ref,
            )

    def test_scaffold_reconciliation_rejects_snapshot_without_mutation_ref(
        self,
    ) -> None:
        """Reconciliation must fail closed when index claims a binding the snapshot denies.

        ReceiptIndex.refs is a lookup surface; the immutable proposal snapshot is
        the authoritative source of truth. If ReceiptIndex claims mutation_ref is
        present but the proposal's source_refs do not contain it, the evidence
        sources contradict and the system must refuse to reconcile.
        """
        with TestClient(
            self.app,
            raise_server_exceptions=False,
        ) as client:
            proposal = self._create_unkeyed_proposal(client)
            proposal_id = proposal["proposal_id"]
            endpoint = f"/proposals/{proposal_id}/decision-scaffold"

            key_a = "snapshot-without-mutation-ref-0001"
            body_a = {
                "attester": "operator:alice",
                "reason": "Revision for snapshot binding test",
                "decision_scaffold": {
                    "counter_evidence": "Snapshot binding test counter-evidence."
                },
                "source_refs": ["test:snapshot-binding"],
            }

            receipt_id_a, receipt_path_a = self._lose_terminal_write(
                client,
                method="PATCH",
                endpoint=endpoint,
                key=key_a,
                body=body_a,
            )

            mutation_ref_a = identity_mutation_source_ref(receipt_id_a)

            with Session(self.engine) as session:
                indexes = list(
                    session.exec(
                        select(ReceiptIndex).where(ReceiptIndex.kind == "state_core_proposal")
                    ).all()
                )

            bound = [index for index in indexes if mutation_ref_a in list(index.refs or [])]
            self.assertEqual(len(bound), 1)
            revision_a_ref = bound[0].path

            # -- Corrupt the proposal snapshot: remove mutation_ref from source_refs,
            #    but keep revision_context intact and recompute content_hash --
            revision_a_path = self._resolve_receipt_path(revision_a_ref)
            receipt = json.loads(revision_a_path.read_text(encoding="utf-8"))

            snapshot = receipt["proposal"]
            original_source_refs = list(snapshot.get("source_refs", []))
            self.assertIn(mutation_ref_a, original_source_refs)

            # Remove mutation_ref but keep other refs
            snapshot["source_refs"] = [ref for ref in original_source_refs if ref != mutation_ref_a]

            # Recompute content_hash so receipt is internally self-consistent
            dup_proposal = Proposal.model_validate(snapshot)
            receipt["content_hash"] = proposal_content_hash(dup_proposal)

            revision_a_path.write_text(
                json.dumps(receipt, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )

            # -- Reconciliation must fail closed: index vs snapshot contradiction --
            before = receipt_path_a.read_bytes()

            with self.assertRaisesRegex(
                IdentityMutationError,
                "scaffold candidate index claims mutation ref",
            ):
                reconcile_identity_mutation_from_domain_truth(
                    receipt_path_a,
                    engine=self.engine,
                    receipt_root=(self.root / "receipts"),
                    reconciled_by="operator:alice",
                    reason="Must fail because index and snapshot disagree.",
                )

            after = receipt_path_a.read_bytes()
            self.assertEqual(after, before)

            pending = json.loads(after)
            self.assertEqual(pending["state"], "pending")
            self.assertNotIn("reconciliation", pending)
            self.assertNotIn("response", pending)

    def test_scaffold_reconciliation_rejects_relabelled_duplicate_candidate(
        self,
    ) -> None:
        """A duplicate effect receipt relabelled as a foreign mutation must fail closed.

        Changing identity_mutation_receipt_id on a duplicate receipt to a
        different value must not allow the system to silently skip it as a
        "verified foreign candidate".  The system cannot prove the candidate
        genuinely belongs to a valid other mutation without verifying the
        foreign identity receipt exists and is internally consistent.
        """
        with TestClient(
            self.app,
            raise_server_exceptions=False,
        ) as client:
            proposal = self._create_unkeyed_proposal(client)
            proposal_id = proposal["proposal_id"]
            endpoint = f"/proposals/{proposal_id}/decision-scaffold"

            key_a = "relabel-duplicate-revision-0001"
            body_a = {
                "attester": "operator:alice",
                "reason": "Revision for relabel test",
                "decision_scaffold": {"counter_evidence": "Relabel bypass test counter-evidence."},
                "source_refs": ["test:relabel-duplicate"],
            }

            receipt_id_a, receipt_path_a = self._lose_terminal_write(
                client,
                method="PATCH",
                endpoint=endpoint,
                key=key_a,
                body=body_a,
            )

            mutation_ref_a = identity_mutation_source_ref(receipt_id_a)

            with Session(self.engine) as session:
                indexes = list(
                    session.exec(
                        select(ReceiptIndex).where(ReceiptIndex.kind == "state_core_proposal")
                    ).all()
                )

            bound = [index for index in indexes if mutation_ref_a in list(index.refs or [])]
            self.assertEqual(len(bound), 1)
            revision_a_ref = bound[0].path

            # Clone Revision A's receipt with a relabelled claim_id.
            revision_a_path = self._resolve_receipt_path(revision_a_ref)
            receipt = json.loads(revision_a_path.read_text(encoding="utf-8"))

            fake_claim_id = "identity_mutation_fake_relabelled_bad"
            context = receipt["revision_context"]
            context["identity_mutation_receipt_id"] = fake_claim_id

            # Write the duplicate receipt to a new path so it can be
            # registered alongside the original.
            dup_receipt_ref = str(revision_a_path.parent / "proposal_relabelled_duplicate.json")
            # Patch receipt_ref in proposal snapshot for hash consistency.
            receipt["proposal"]["receipt_ref"] = dup_receipt_ref
            dup_proposal = Proposal.model_validate(receipt["proposal"])
            receipt["content_hash"] = proposal_content_hash(dup_proposal)

            dup_path = self._resolve_receipt_path(dup_receipt_ref)
            dup_path.write_text(
                json.dumps(receipt, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )

            with Session(self.engine) as session:
                dup_index = ReceiptIndex(
                    receipt_id="receipt:relabel-duplicate-0001",
                    refs=[mutation_ref_a],
                    kind="state_core_proposal",
                    path=dup_receipt_ref,
                )
                session.add(dup_index)
                session.commit()

            before = receipt_path_a.read_bytes()

            with self.assertRaisesRegex(
                IdentityMutationError,
                "scaffold candidate claims foreign receipt_id",
            ):
                reconcile_identity_mutation_from_domain_truth(
                    receipt_path_a,
                    engine=self.engine,
                    receipt_root=(self.root / "receipts"),
                    reconciled_by="operator:alice",
                    reason="Relabelled duplicate must fail closed.",
                )

            after = receipt_path_a.read_bytes()
            self.assertEqual(after, before)

            pending = json.loads(after)
            self.assertEqual(pending["state"], "pending")

            # Clean up.
            with Session(self.engine) as session:
                dup_row = session.exec(
                    select(ReceiptIndex).where(ReceiptIndex.path == dup_receipt_ref)
                ).first()
                if dup_row is not None:
                    session.delete(dup_row)
                    session.commit()
            if dup_path.is_file():
                dup_path.unlink()

    def test_scaffold_reconciliation_rejects_schema_only_partial_binding(
        self,
    ) -> None:
        """An unkeyed revision with residual schema field must fail closed.

        _MUTATION_BINDING_FIELDS currently omits 'schema' and 'effect_kind'.
        A receipt that carries 'schema' without identity_mutation_receipt_id
        is a partial binding and must block reconciliation.
        """
        with TestClient(
            self.app,
            raise_server_exceptions=False,
        ) as client:
            proposal = self._create_unkeyed_proposal(client)
            proposal_id = proposal["proposal_id"]
            endpoint = f"/proposals/{proposal_id}/decision-scaffold"

            # Keyed Revision A with terminal loss.
            key_a = "partial-schema-binding-0001"
            body_a = {
                "attester": "operator:alice",
                "reason": "Revision A for partial-binding test",
                "decision_scaffold": {"counter_evidence": "Partial binding test counter-evidence."},
                "source_refs": ["test:partial-binding"],
            }

            _, receipt_path_a = self._lose_terminal_write(
                client,
                method="PATCH",
                endpoint=endpoint,
                key=key_a,
                body=body_a,
            )

            # Keyed Revision B — normally, with a different key.
            key_b = "partial-binding-revision-b-0001"
            body_b = {
                "attester": "operator:alice",
                "reason": "Revision B: alternatives",
                "decision_scaffold": {"alternatives": "Later revision alternatives."},
                "source_refs": ["test:partial-binding-b"],
            }

            rev_b_response = client.patch(
                endpoint,
                headers=self._headers(key_b),
                json=body_b,
            )
            self.assertEqual(rev_b_response.status_code, 200, rev_b_response.text)
            rev_b_body = rev_b_response.json()
            revision_b_receipt_ref = rev_b_body["receipt_ref"]

            # Corrupt Revision B's context: remove identity_mutation_receipt_id
            # but keep 'schema'.
            revision_b_path = self._resolve_receipt_path(revision_b_receipt_ref)
            b_receipt = json.loads(revision_b_path.read_text(encoding="utf-8"))
            b_context = b_receipt["revision_context"]
            b_context.pop("identity_mutation_receipt_id", None)
            b_context["schema"] = "finharness.api_domain_mutation_binding.v1"

            revision_b_path.write_text(
                json.dumps(b_receipt, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )

            before = receipt_path_a.read_bytes()

            with self.assertRaisesRegex(
                IdentityMutationError,
                "partial mutation-binding",
            ):
                reconcile_identity_mutation_from_domain_truth(
                    receipt_path_a,
                    engine=self.engine,
                    receipt_root=(self.root / "receipts"),
                    reconciled_by="operator:alice",
                    reason="Schema-only partial binding must fail closed.",
                )

            after = receipt_path_a.read_bytes()
            self.assertEqual(after, before)

            pending = json.loads(after)
            self.assertEqual(pending["state"], "pending")
            self.assertNotIn("reconciliation", pending)
            self.assertNotIn("response", pending)


if __name__ == "__main__":
    unittest.main()
