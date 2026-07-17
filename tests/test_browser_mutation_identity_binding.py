"""Authenticated browser mutation binding and pre-body admission tests."""

from __future__ import annotations

import json
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path

from fastapi.testclient import TestClient

from finharness.api.app import create_app
from finharness.identity import (
    BROWSER_MUTATION_BINDING_HEADER,
    IDEMPOTENCY_HEADER,
    AgentRuntimeIdentity,
    AuthorityAdministrationAssertion,
    BrowserMutationBindingError,
    OperatorContext,
    PrincipalIdentity,
    TestIdentityProvider,
    browser_mutation_identity_binding,
)
from finharness.statecore.store import init_state_core
from tests._scaffold import VALID_SCAFFOLD


def _context(
    principal_id: str = "principal:alice",
    *,
    epoch_id: str | None = "alice-session-1",
    agent_runtime_id: str | None = None,
    display_label: str | None = "Alice",
    expired: bool = False,
    authority: bool = False,
) -> OperatorContext:
    authenticated_at = datetime(2026, 1, 1, tzinfo=UTC)
    expires_at = (
        datetime(2026, 1, 2, tzinfo=UTC)
        if expired
        else datetime(2099, 1, 1, tzinfo=UTC)
    )
    return OperatorContext(
        principal=PrincipalIdentity(
            principal_id=principal_id,
            provider_id="test-browser-provider",
            principal_kind="human",
            display_label=display_label,
        ),
        agent_runtime=(
            AgentRuntimeIdentity(
                agent_runtime_id=agent_runtime_id,
                principal_id=principal_id,
                provider_id="test-browser-provider",
            )
            if agent_runtime_id
            else None
        ),
        authority_administration=(
            AuthorityAdministrationAssertion(
                assertion_id="assertion:test",
                principal_id=principal_id,
                provider_id="test-browser-provider",
                capability="authority_administrator",
                policy_version="test-policy-v1",
                authentication_assurance="elevated",
                issued_at_utc="2026-01-01T00:00:00+00:00",
                expires_at_utc="2099-01-01T00:00:00+00:00",
            )
            if authority
            else None
        ),
        authentication_method="test_bearer",
        authenticated_at_utc=authenticated_at.isoformat(),
        authentication_epoch_id=epoch_id,
        authentication_expires_at_utc=(
            expires_at.isoformat() if epoch_id is not None else None
        ),
    )


class BrowserMutationIdentityModelTest(unittest.TestCase):
    def test_binding_identity_changes_only_with_canonical_authentication_identity(
        self,
    ) -> None:
        alice = browser_mutation_identity_binding(_context())
        same = browser_mutation_identity_binding(_context(display_label="Renamed Alice"))
        with_authority = browser_mutation_identity_binding(_context(authority=True))
        bob = browser_mutation_identity_binding(_context("principal:bob"))
        rotated = browser_mutation_identity_binding(
            _context(epoch_id="alice-session-2")
        )
        agent = browser_mutation_identity_binding(
            _context(agent_runtime_id="agent:alice:review")
        )

        self.assertEqual(alice.binding_id, same.binding_id)
        self.assertEqual(alice.binding_id, with_authority.binding_id)
        self.assertNotEqual(alice.binding_id, bob.binding_id)
        self.assertNotEqual(alice.binding_id, rotated.binding_id)
        self.assertNotEqual(alice.binding_id, agent.binding_id)

    def test_epoch_fields_are_paired_and_utc(self) -> None:
        payload = _context().model_dump()
        payload["authentication_expires_at_utc"] = None
        with self.assertRaisesRegex(ValueError, "present together"):
            OperatorContext.model_validate(payload)

        payload = _context().model_dump()
        payload["authentication_expires_at_utc"] = "2099-01-01T00:00:00"
        with self.assertRaisesRegex(ValueError, "must be UTC"):
            OperatorContext.model_validate(payload)

    def test_missing_and_expired_epoch_cannot_create_binding(self) -> None:
        with self.assertRaisesRegex(
            BrowserMutationBindingError,
            "browser_mutation_binding_unavailable",
        ):
            browser_mutation_identity_binding(_context(epoch_id=None))
        empty_method = _context().model_copy(
            update={"authentication_method": ""}
        )
        with self.assertRaisesRegex(
            BrowserMutationBindingError,
            "browser_mutation_binding_unavailable",
        ):
            browser_mutation_identity_binding(empty_method)
        with self.assertRaisesRegex(
            BrowserMutationBindingError,
            "browser_mutation_binding_expired",
        ):
            browser_mutation_identity_binding(_context(expired=True))

    def test_binding_never_serializes_raw_credentials_or_authority(self) -> None:
        serialized = browser_mutation_identity_binding(
            _context(authority=True)
        ).model_dump_json(by_alias=True)
        self.assertNotIn("Bearer", serialized)
        self.assertNotIn("cookie", serialized.lower())
        self.assertNotIn("authority_administrator", serialized)
        self.assertIn('"capital_authority":null', serialized)
        self.assertIn('"execution_allowed":false', serialized)


class BrowserMutationIdentityApiTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.engine = init_state_core(self.root / "state.sqlite")
        self.addCleanup(self.engine.dispose)
        self.identities = {
            "alice": _context(),
            "alice-2": _context(epoch_id="alice-session-2"),
            "bob": _context("principal:bob", epoch_id="bob-session-1"),
            "expired": _context(expired=True),
            "unbound": _context(epoch_id=None),
        }
        self.app = create_app(
            state_core_engine=self.engine,
            receipt_root=str(self.root / "receipts"),
            identity_provider=TestIdentityProvider(self.identities),
        )

    def _identity_receipts(self) -> list[Path]:
        return sorted((self.root / "receipts" / "identity").glob("*.json"))

    def _binding(self, token: str) -> str:
        return browser_mutation_identity_binding(
            self.identities[token]
        ).binding_id

    def test_endpoint_returns_closed_no_store_non_authority_binding(self) -> None:
        with TestClient(self.app) as client:
            response = client.get(
                "/identity/browser-mutation-binding",
                headers={"Authorization": "Bearer alice"},
            )

        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(
            set(body),
            {
                "schema",
                "binding_id",
                "principal_id",
                "identity_provider_id",
                "principal_kind",
                "agent_runtime_id",
                "authentication_method",
                "authentication_epoch_id",
                "authentication_expires_at_utc",
                "server_time_utc",
                "capital_authority",
                "execution_allowed",
            },
        )
        self.assertEqual(
            response.headers[BROWSER_MUTATION_BINDING_HEADER],
            body["binding_id"],
        )
        self.assertEqual(response.headers["cache-control"], "no-store")
        self.assertEqual(response.headers["pragma"], "no-cache")
        self.assertEqual(response.headers["vary"], "Authorization, Cookie")
        self.assertIsNone(body["capital_authority"])
        self.assertFalse(body["execution_allowed"])

    def test_missing_and_expired_epoch_return_typed_denials(self) -> None:
        with TestClient(self.app) as client:
            for token, code in (
                ("unbound", "browser_mutation_binding_unavailable"),
                ("expired", "browser_mutation_binding_expired"),
            ):
                response = client.get(
                    "/identity/browser-mutation-binding",
                    headers={"Authorization": f"Bearer {token}"},
                )
                self.assertEqual(response.status_code, 403, response.text)
                self.assertEqual(response.json()["detail"]["code"], code)

    def test_matching_header_allows_keyed_write_and_echoes_binding(self) -> None:
        binding_id = self._binding("alice")
        body = {
            "kind": "allocation",
            "claim": "Browser binding is transport identity only.",
            "decision_scaffold": VALID_SCAFFOLD,
            "source_refs": ["test:#388"],
        }
        with TestClient(self.app) as client:
            response = client.post(
                "/proposals",
                headers={
                    "Authorization": "Bearer alice",
                    IDEMPOTENCY_HEADER: "browser-binding-0001",
                    BROWSER_MUTATION_BINDING_HEADER: binding_id,
                },
                json=body,
            )

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(
            response.headers[BROWSER_MUTATION_BINDING_HEADER],
            binding_id,
        )
        receipt = json.loads(
            self._identity_receipts()[0].read_text(encoding="utf-8")
        )
        self.assertEqual(receipt["actor"]["principal_id"], "principal:alice")
        self.assertNotIn("authentication_epoch_id", receipt["actor"])

    def test_payload_actor_cannot_replace_transport_binding(self) -> None:
        binding_id = self._binding("alice")
        with TestClient(self.app) as client:
            response = client.post(
                "/proposals",
                headers={
                    "Authorization": "Bearer alice",
                    IDEMPOTENCY_HEADER: "browser-forged-actor-0001",
                    BROWSER_MUTATION_BINDING_HEADER: binding_id,
                },
                json={
                    "kind": "allocation",
                    "claim": "Payload identity cannot become authentication.",
                    "decision_scaffold": VALID_SCAFFOLD,
                    "source_refs": ["test:#388:forged-actor"],
                    "actor": "principal:bob",
                },
            )

        self.assertEqual(response.status_code, 422, response.text)
        self.assertEqual(
            response.headers[BROWSER_MUTATION_BINDING_HEADER],
            binding_id,
        )
        receipt = json.loads(
            self._identity_receipts()[0].read_text(encoding="utf-8")
        )
        self.assertEqual(receipt["actor"]["principal_id"], "principal:alice")

    def test_cross_principal_epoch_and_malformed_headers_fail_before_body_receipt(
        self,
    ) -> None:
        cases = (
            (
                "bob",
                self._binding("alice"),
                "browser_mutation_binding_mismatch",
            ),
            (
                "alice-2",
                self._binding("alice"),
                "browser_mutation_binding_mismatch",
            ),
            (
                "alice",
                "not-a-binding",
                "browser_mutation_binding_invalid",
            ),
        )
        for index, (token, binding_id, code) in enumerate(cases):
            consumed = 0

            def chunks():
                nonlocal consumed
                consumed += 1
                yield b'{"actor":"principal:alice"}'

            with TestClient(self.app) as client:
                response = client.post(
                    "/proposals",
                    headers={
                        "Authorization": f"Bearer {token}",
                        IDEMPOTENCY_HEADER: f"browser-denied-{index:04d}",
                        BROWSER_MUTATION_BINDING_HEADER: binding_id,
                    },
                    content=chunks(),
                )

            self.assertEqual(response.status_code, 409, response.text)
            self.assertEqual(response.json()["detail"]["code"], code)
            self.assertEqual(consumed, 0)
            self.assertEqual(self._identity_receipts(), [])

    def test_expired_current_epoch_fails_before_body_and_receipt(self) -> None:
        consumed = 0

        def chunks():
            nonlocal consumed
            consumed += 1
            yield b"{}"

        with TestClient(self.app) as client:
            response = client.post(
                "/proposals",
                headers={
                    "Authorization": "Bearer expired",
                    IDEMPOTENCY_HEADER: "browser-expired-0001",
                    BROWSER_MUTATION_BINDING_HEADER: "a" * 64,
                },
                content=chunks(),
            )

        self.assertEqual(response.status_code, 403, response.text)
        self.assertEqual(
            response.json()["detail"]["code"],
            "browser_mutation_binding_expired",
        )
        self.assertEqual(consumed, 0)
        self.assertEqual(self._identity_receipts(), [])


if __name__ == "__main__":
    unittest.main()
