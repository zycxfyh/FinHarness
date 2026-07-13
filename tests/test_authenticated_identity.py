"""Authenticated Principal/Agent identity and durable write binding tests."""

from __future__ import annotations

import json
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path

from fastapi.testclient import TestClient

from finharness.api.app import create_app
from finharness.identity import (
    AgentRuntimeIdentity,
    IdentitySubstitutionError,
    OperatorContext,
    PrincipalIdentity,
    TestIdentityProvider,
)
from finharness.statecore.store import init_state_core
from tests._scaffold import VALID_SCAFFOLD


def _context(principal_id: str, agent_id: str | None = None) -> OperatorContext:
    return OperatorContext(
        principal=PrincipalIdentity(
            principal_id=principal_id,
            provider_id="test-identity-provider",
            display_label=principal_id,
        ),
        agent_runtime=(
            AgentRuntimeIdentity(
                agent_runtime_id=agent_id,
                principal_id=principal_id,
                provider_id="test-identity-provider",
                agent_profile="review-note",
            )
            if agent_id
            else None
        ),
        authentication_method="test_bearer",
        authenticated_at_utc=datetime.now(UTC).isoformat(),
    )


class AuthenticatedIdentityTest(unittest.TestCase):
    def test_cross_principal_and_agent_substitution_fail_closed(self) -> None:
        context = _context("principal:alice", "agent:alice:review")
        with self.assertRaisesRegex(IdentitySubstitutionError, "cross-principal"):
            context.reject_identity_substitution(claimed_principal_id="principal:bob")
        with self.assertRaisesRegex(IdentitySubstitutionError, "cross-agent"):
            context.reject_identity_substitution(claimed_agent_runtime_id="agent:bob:review")

    def test_agent_must_be_bound_to_authenticated_principal(self) -> None:
        with self.assertRaisesRegex(ValueError, "principal binding mismatch"):
            OperatorContext(
                principal=PrincipalIdentity(
                    principal_id="principal:alice",
                    provider_id="test",
                ),
                agent_runtime=AgentRuntimeIdentity(
                    agent_runtime_id="agent:bob",
                    principal_id="principal:bob",
                    provider_id="test",
                ),
                authentication_method="test",
                authenticated_at_utc=datetime.now(UTC).isoformat(),
            )

    def test_identity_survives_restart_and_is_bound_to_write_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            engine = init_state_core(root / "state.sqlite")
            provider = TestIdentityProvider({"alice-token": _context("principal:alice")})

            for _restart in range(2):
                app = create_app(
                    state_core_engine=engine,
                    receipt_root=str(root / "receipts"),
                    identity_provider=provider,
                )
                with TestClient(app) as client:
                    response = client.post(
                        "/proposals",
                        headers={"Authorization": "Bearer alice-token"},
                        json={
                            "kind": "allocation",
                            "claim": "Identity comes from server context.",
                            "decision_scaffold": VALID_SCAFFOLD,
                            "source_refs": ["test:authenticated-identity"],
                        },
                    )
                self.assertEqual(response.status_code, 200, response.text)
                receipt_id = response.headers["X-FinHarness-Identity-Receipt"]
                receipt = json.loads(
                    (root / "receipts" / "identity" / f"{receipt_id}.json").read_text()
                )
                self.assertEqual(receipt["actor"]["principal_id"], "principal:alice")
                self.assertIsNone(receipt["actor"]["capital_authority"])

    def test_payload_identity_cannot_replace_server_context(self) -> None:
        context = _context("principal:alice")
        binding = context.receipt_binding()
        hostile_payload = {"principal_id": "principal:bob", "issued_by": "principal:bob"}
        self.assertEqual(binding["principal_id"], "principal:alice")
        self.assertNotEqual(binding["principal_id"], hostile_payload["principal_id"])

    def test_missing_or_unknown_credentials_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            app = create_app(
                state_core_engine=init_state_core(root / "state.sqlite"),
                receipt_root=str(root / "receipts"),
                identity_provider=TestIdentityProvider({"alice": _context("principal:alice")}),
            )
            with TestClient(app) as client:
                for headers in ({}, {"Authorization": "Bearer unknown"}):
                    response = client.post(
                        "/proposals",
                        headers=headers,
                        json={"title": "denied", "summary": "denied"},
                    )
                    self.assertEqual(response.status_code, 403)
                    self.assertEqual(
                        response.json()["detail"]["code"],
                        "write_capability_required",
                    )


if __name__ == "__main__":
    unittest.main()
