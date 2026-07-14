from __future__ import annotations

import json
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path

from fastapi.testclient import TestClient

from finharness.api.app import create_app
from finharness.api.routes_proposals import (
    identity_mutation_source_ref,
)
from finharness.identity import (
    IDEMPOTENCY_HEADER,
    IDENTITY_RECEIPT_HEADER,
    OperatorContext,
    PrincipalIdentity,
    TestIdentityProvider,
)
from finharness.project_paths import ROOT
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


if __name__ == "__main__":
    unittest.main()
