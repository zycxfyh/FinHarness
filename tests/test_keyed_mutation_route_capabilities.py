from __future__ import annotations

import copy
import json
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from fastapi import Request
from fastapi.testclient import TestClient

from finharness.api.app import create_app
from finharness.api.keyed_mutation_capabilities import (
    KeyedMutationCapabilityError,
    KeyedMutationRouteCapabilityRegistry,
    audit_keyed_mutation_route_capabilities,
    load_keyed_mutation_route_capabilities,
)
from finharness.api.routes_proposals import (
    identity_mutation_reconciliation_dispatcher_contracts,
    reconcile_identity_mutation_from_domain_truth,
)
from finharness.identity import (
    IDEMPOTENCY_HEADER,
    IDENTITY_RECEIPT_HEADER,
    IdentityMutationError,
    OperatorContext,
    PrincipalIdentity,
    TestIdentityProvider,
    begin_identity_mutation,
)
from finharness.statecore.receipt_io import canonical_json_sha256
from finharness.statecore.store import init_state_core
from tests._scaffold import VALID_SCAFFOLD


def _operator() -> OperatorContext:
    return OperatorContext(
        principal=PrincipalIdentity(
            principal_id="principal:route-capability",
            provider_id="test",
            principal_kind="human",
        ),
        authentication_method="test_bearer",
        authenticated_at_utc=datetime.now(UTC).isoformat(),
    )


def _swap_attestation_and_review_event_resolvers(
    registry: KeyedMutationRouteCapabilityRegistry,
) -> KeyedMutationRouteCapabilityRegistry:
    attestation_resolver = "finharness.api.attestation_create.v1"
    review_event_resolver = "finharness.api.review_event_create.v1"
    capabilities = tuple(
        capability.model_copy(
            update={
                "resolver_id": (
                    review_event_resolver
                    if capability.resolver_id == attestation_resolver
                    else attestation_resolver
                )
            }
        )
        if capability.resolver_id in {attestation_resolver, review_event_resolver}
        else capability
        for capability in registry.capabilities
    )
    return registry.model_copy(update={"capabilities": capabilities})


class KeyedMutationRouteCapabilityAdmissionTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.engine = init_state_core(self.root / "state.sqlite")
        self.addCleanup(self.engine.dispose)
        self.app = create_app(
            state_core_engine=self.engine,
            receipt_root=str(self.root / "receipts"),
            identity_provider=TestIdentityProvider({"operator": _operator()}),
        )
        self.headers = {
            "Authorization": "Bearer operator",
            IDEMPOTENCY_HEADER: "route-capability-0001",
        }

    def _identity_receipts(self) -> list[Path]:
        return sorted((self.root / "receipts" / "identity").glob("*.json"))

    def test_synthetic_unregistered_route_fails_before_handler_and_receipt(self) -> None:
        handler_calls = 0

        @self.app.post("/synthetic-unregistered")
        async def synthetic_unregistered(_request: Request) -> dict[str, bool]:
            nonlocal handler_calls
            handler_calls += 1
            return {"executed": True}

        with TestClient(self.app) as client:
            response = client.post(
                "/synthetic-unregistered",
                headers=self.headers,
                content=b'{"candidate":"must-not-run"}',
            )

        self.assertEqual(response.status_code, 409, response.text)
        self.assertEqual(
            response.json()["detail"]["code"],
            "keyed_mutation_route_unregistered",
        )
        self.assertEqual(handler_calls, 0)
        self.assertEqual(self._identity_receipts(), [])

    def test_real_prohibited_route_fails_without_receipt(self) -> None:
        with TestClient(self.app) as client:
            response = client.post(
                "/ips/draft",
                headers=self.headers,
                content=b'{"caller_capability_id":"typed_domain_reconciliation"}',
            )

        self.assertEqual(response.status_code, 409, response.text)
        self.assertEqual(
            response.json()["detail"]["code"],
            "keyed_mutation_prohibited",
        )
        self.assertEqual(self._identity_receipts(), [])

    def test_nonexistent_or_wrong_method_preserves_router_result_without_receipt(
        self,
    ) -> None:
        with TestClient(self.app) as client:
            missing = client.post(
                "/route-does-not-exist",
                headers=self.headers,
                content=b"{}",
            )
            wrong_method = client.request(
                "DELETE",
                "/proposals",
                headers=self.headers,
                content=b"{}",
            )

        self.assertEqual(missing.status_code, 404, missing.text)
        self.assertEqual(wrong_method.status_code, 405, wrong_method.text)
        self.assertEqual(self._identity_receipts(), [])

    def test_prohibited_large_stream_is_rejected_before_body_consumption(self) -> None:
        consumed = 0

        def chunks():
            nonlocal consumed
            for _ in range(4):
                consumed += 1
                yield b"x" * 1_048_576

        with TestClient(self.app) as client:
            response = client.post(
                "/ips/draft",
                headers=self.headers,
                content=chunks(),
            )

        self.assertEqual(response.status_code, 409, response.text)
        self.assertEqual(response.json()["detail"]["code"], "keyed_mutation_prohibited")
        self.assertEqual(consumed, 0)
        self.assertEqual(self._identity_receipts(), [])

    def test_swapped_registry_mapping_fails_before_body_handler_and_receipt(
        self,
    ) -> None:
        self.app.state.keyed_mutation_route_capabilities = (
            _swap_attestation_and_review_event_resolvers(
                self.app.state.keyed_mutation_route_capabilities
            )
        )
        consumed = 0

        def chunks():
            nonlocal consumed
            consumed += 1
            yield b'{"decision":"approved","reason":"must not run"}'

        with TestClient(self.app) as client:
            response = client.post(
                "/proposals/not-created/attest",
                headers=self.headers,
                content=chunks(),
            )

        self.assertEqual(response.status_code, 409, response.text)
        self.assertEqual(
            response.json()["detail"]["code"],
            "keyed_mutation_capability_invalid",
        )
        self.assertEqual(consumed, 0)
        self.assertEqual(self._identity_receipts(), [])

    def test_new_proposal_receipt_binds_v2_route_capability(self) -> None:
        body = {
            "kind": "allocation",
            "claim": "The route capability is bound before the pending receipt.",
            "decision_scaffold": VALID_SCAFFOLD,
            "source_refs": ["test:#387"],
        }
        with TestClient(self.app) as client:
            response = client.post("/proposals", headers=self.headers, json=body)

        self.assertEqual(response.status_code, 200, response.text)
        receipt_path = (
            self.root
            / "receipts"
            / "identity"
            / f"{response.headers[IDENTITY_RECEIPT_HEADER]}.json"
        )
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        self.assertEqual(
            receipt["schema"],
            "finharness.api_mutation_identity_receipt.v2",
        )
        self.assertEqual(
            receipt["route_capability"]["canonical_path_template"],
            "/proposals",
        )
        self.assertEqual(
            receipt["route_capability"]["resolver_id"],
            "finharness.api.proposal_create.v1",
        )

    def test_same_key_cannot_cross_route_capability_version_drift(self) -> None:
        body = {
            "kind": "allocation",
            "claim": "The same key cannot silently cross a capability change.",
            "decision_scaffold": VALID_SCAFFOLD,
            "source_refs": ["test:#387:capability-drift"],
        }
        with TestClient(self.app) as client:
            first = client.post("/proposals", headers=self.headers, json=body)
            self.assertEqual(first.status_code, 200, first.text)

            registry = self.app.state.keyed_mutation_route_capabilities
            capabilities = tuple(
                capability.model_copy(
                    update={
                        "max_response_bytes": capability.max_response_bytes + 1,
                    }
                )
                if capability.canonical_path_template == "/proposals"
                and capability.method == "POST"
                else capability
                for capability in registry.capabilities
            )
            self.app.state.keyed_mutation_route_capabilities = registry.model_copy(
                update={"capabilities": capabilities}
            )
            replay = client.post("/proposals", headers=self.headers, json=body)

        self.assertEqual(replay.status_code, 409, replay.text)
        self.assertEqual(
            replay.json()["detail"]["code"],
            "idempotency_key_reused_for_different_request",
        )
        self.assertEqual(len(self._identity_receipts()), 1)

    def test_recomputed_tampered_capability_still_fails_registry_admission(
        self,
    ) -> None:
        body = {
            "kind": "allocation",
            "claim": "Capability tampering cannot select another resolver.",
            "decision_scaffold": VALID_SCAFFOLD,
            "source_refs": ["test:#387:capability-tamper"],
        }
        with (
            patch(
                "finharness.api.app.complete_identity_mutation",
                side_effect=OSError("simulated terminal receipt loss"),
            ),
            TestClient(self.app, raise_server_exceptions=False) as client,
        ):
            response = client.post("/proposals", headers=self.headers, json=body)
        self.assertEqual(response.status_code, 500)
        receipt_path = self._identity_receipts()[0]
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        capability = receipt["route_capability"]
        capability["resolver_id"] = "finharness.api.path_guessing_fallback.v1"
        capability["capability_sha256"] = canonical_json_sha256(
            {
                key: value
                for key, value in capability.items()
                if key != "capability_sha256"
            }
        )
        receipt["content_sha256"] = canonical_json_sha256(
            {
                key: value
                for key, value in receipt.items()
                if key != "content_sha256"
            }
        )
        receipt_path.write_text(json.dumps(receipt), encoding="utf-8")

        with self.assertRaisesRegex(
            IdentityMutationError,
            "does not match the canonical registry",
        ):
            reconcile_identity_mutation_from_domain_truth(
                receipt_path,
                engine=self.engine,
                receipt_root=self.root / "receipts",
                reconciled_by="operator:route-capability",
                reason="Attempt to prove a recomputed capability cannot redirect dispatch.",
            )

    def test_canonical_registry_swap_still_fails_executable_dispatch_contract(
        self,
    ) -> None:
        with TestClient(self.app) as client:
            proposal_response = client.post(
                "/proposals",
                headers={"Authorization": "Bearer operator"},
                json={
                    "kind": "allocation",
                    "claim": "A canonical registry swap cannot redirect recovery.",
                    "decision_scaffold": VALID_SCAFFOLD,
                    "source_refs": ["test:#387:canonical-registry-swap"],
                },
            )
        self.assertEqual(proposal_response.status_code, 200)
        proposal_id = proposal_response.json()["proposal"]["proposal_id"]

        with (
            patch(
                "finharness.api.app.complete_identity_mutation",
                side_effect=OSError("simulated terminal receipt loss"),
            ),
            TestClient(self.app, raise_server_exceptions=False) as client,
        ):
            response = client.post(
                f"/proposals/{proposal_id}/attest",
                headers=self.headers,
                json={
                    "decision": "approved",
                    "reason": "Commit Attestation truth before terminal loss.",
                },
            )
        self.assertEqual(response.status_code, 500)

        receipt_path = self._identity_receipts()[0]
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        swapped = _swap_attestation_and_review_event_resolvers(
            self.app.state.keyed_mutation_route_capabilities
        )
        attestation_capability = swapped.by_route(
            "POST", "/proposals/{proposal_id}/attest"
        )
        self.assertIsNotNone(attestation_capability)
        assert attestation_capability is not None
        receipt["route_capability"] = attestation_capability.receipt_binding()
        receipt["content_sha256"] = canonical_json_sha256(
            {
                key: value
                for key, value in receipt.items()
                if key != "content_sha256"
            }
        )
        receipt_path.write_text(json.dumps(receipt), encoding="utf-8")

        with (
            patch(
                "finharness.api.routes_proposals.load_keyed_mutation_route_capabilities",
                return_value=swapped,
            ),
            self.assertRaisesRegex(
                IdentityMutationError,
                "differs from executable resolver contract",
            ),
        ):
            reconcile_identity_mutation_from_domain_truth(
                receipt_path,
                engine=self.engine,
                receipt_root=self.root / "receipts",
                reconciled_by="operator:route-capability",
                reason="Prove registry-owned substitution cannot redirect dispatch.",
            )

    def test_legacy_v1_pending_uses_narrow_adapter_and_remains_v1(self) -> None:
        body = {
            "kind": "allocation",
            "claim": "A historical v1 Proposal receipt remains recoverable.",
            "decision_scaffold": VALID_SCAFFOLD,
            "source_refs": ["test:#387:legacy-v1"],
        }

        def legacy_begin(*args, **kwargs):
            kwargs.pop("route_capability", None)
            return begin_identity_mutation(*args, **kwargs)

        with (
            patch(
                "finharness.api.app.begin_identity_mutation",
                side_effect=legacy_begin,
            ),
            patch(
                "finharness.api.app.complete_identity_mutation",
                side_effect=OSError("simulated legacy terminal receipt loss"),
            ),
            TestClient(self.app, raise_server_exceptions=False) as client,
        ):
            response = client.post("/proposals", headers=self.headers, json=body)

        self.assertEqual(response.status_code, 500)
        receipt_path = self._identity_receipts()[0]
        pending = json.loads(receipt_path.read_text(encoding="utf-8"))
        self.assertEqual(
            pending["schema"],
            "finharness.api_mutation_identity_receipt.v1",
        )
        self.assertNotIn("route_capability", pending)

        reconciled = reconcile_identity_mutation_from_domain_truth(
            receipt_path,
            engine=self.engine,
            receipt_root=self.root / "receipts",
            reconciled_by="operator:route-capability",
            reason="Verified historical v1 Proposal truth through the narrow adapter.",
        )
        self.assertEqual(reconciled["state"], "reconciled_applied")
        self.assertEqual(
            reconciled["schema"],
            "finharness.api_mutation_identity_receipt.v1",
        )
        self.assertNotIn("route_capability", reconciled)

        with TestClient(self.app) as client:
            replay = client.post("/proposals", headers=self.headers, json=body)
        self.assertEqual(replay.status_code, 200, replay.text)
        self.assertEqual(
            json.loads(receipt_path.read_text(encoding="utf-8"))["schema"],
            "finharness.api_mutation_identity_receipt.v1",
        )


class KeyedMutationRouteCapabilityRegistryTest(unittest.TestCase):
    def setUp(self) -> None:
        self.raw = json.loads(
            (
                Path(__file__).parents[1]
                / "config"
                / "keyed-mutation-route-capabilities.json"
            ).read_text(encoding="utf-8")
        )

    def _validate(self, raw: dict) -> KeyedMutationRouteCapabilityRegistry:
        return KeyedMutationRouteCapabilityRegistry.model_validate(raw)

    def test_exact_runtime_inventory_and_dispatcher_contract(self) -> None:
        app = create_app()
        registry = load_keyed_mutation_route_capabilities()
        audit = audit_keyed_mutation_route_capabilities(
            app,
            registry,
            dispatcher_contracts=(
                identity_mutation_reconciliation_dispatcher_contracts()
            ),
        )

        self.assertEqual(audit["non_safe_route_count"], 22)
        self.assertEqual(
            audit["mode_counts"],
            {
                "typed_domain_reconciliation": 5,
                "terminal_replay_only": 2,
                "keyed_mutation_prohibited": 15,
            },
        )
        self.assertEqual(
            audit["typed_resolver_ids"],
            [
                "finharness.api.agent_shell.paper_effect.v1",
                "finharness.api.attestation_create.v1",
                "finharness.api.proposal_create.v1",
                "finharness.api.proposal_scaffold_revision.v1",
                "finharness.api.review_event_create.v1",
            ],
        )

    def test_closed_schema_rejects_parallel_or_invalid_mechanisms(self) -> None:
        mutations = {
            "unknown_registry_field": lambda raw: raw.__setitem__(
                "runtime_classifier", "path_suffix"
            ),
            "unknown_capability_field": lambda raw: raw["capabilities"][0].__setitem__(
                "second_dispatcher", "fallback"
            ),
            "duplicate_capability_id": lambda raw: raw["capabilities"][1].__setitem__(
                "capability_id", raw["capabilities"][0]["capability_id"]
            ),
            "duplicate_route": lambda raw: raw["capabilities"][1].update(
                {
                    "method": raw["capabilities"][0]["method"],
                    "canonical_path_template": raw["capabilities"][0][
                        "canonical_path_template"
                    ],
                }
            ),
            "unknown_mode": lambda raw: raw["capabilities"][0].__setitem__(
                "mode", "guess_from_path"
            ),
            "typed_without_resolver": lambda raw: raw["capabilities"][0].__setitem__(
                "resolver_id", None
            ),
            "prohibited_with_resolver": lambda raw: raw["capabilities"][4].__setitem__(
                "resolver_id", "finharness.api.unsafe_fallback.v1"
            ),
            "terminal_without_proof": lambda raw: raw["capabilities"][4].update(
                {
                    "mode": "terminal_replay_only",
                    "no_ambiguous_effect_contract": None,
                }
            ),
            "invalid_bound": lambda raw: raw["capabilities"][0].__setitem__(
                "max_request_bytes", 0
            ),
            "execution_authority": lambda raw: raw["capabilities"][0].__setitem__(
                "execution_allowed", True
            ),
        }
        for name, mutate in mutations.items():
            with self.subTest(name=name):
                candidate = copy.deepcopy(self.raw)
                mutate(candidate)
                with self.assertRaises(ValueError):
                    self._validate(candidate)

    def test_route_and_dispatcher_drift_fail_exact_audit(self) -> None:
        app = create_app()
        registry = load_keyed_mutation_route_capabilities()
        missing_route = registry.model_copy(
            update={"capabilities": registry.capabilities[1:]}
        )
        with self.assertRaisesRegex(
            KeyedMutationCapabilityError,
            "missing registry entry: POST /proposals",
        ):
            audit_keyed_mutation_route_capabilities(
                app,
                missing_route,
                dispatcher_contracts=(
                    identity_mutation_reconciliation_dispatcher_contracts()
                ),
            )

        with self.assertRaisesRegex(
            KeyedMutationCapabilityError,
            "route/resolver mapping drift",
        ):
            audit_keyed_mutation_route_capabilities(
                app,
                registry,
                dispatcher_contracts=(
                    identity_mutation_reconciliation_dispatcher_contracts()[1:]
                ),
            )

    def test_valid_resolver_swap_fails_exact_route_mapping_audit(self) -> None:
        app = create_app()
        registry = _swap_attestation_and_review_event_resolvers(
            load_keyed_mutation_route_capabilities()
        )
        with self.assertRaisesRegex(
            KeyedMutationCapabilityError,
            (
                "route/resolver mapping drift: "
                "POST /proposals/\\{proposal_id\\}/attest "
                "expected finharness.api.attestation_create.v1 "
                "found finharness.api.review_event_create.v1"
            ),
        ):
            audit_keyed_mutation_route_capabilities(
                app,
                registry,
                dispatcher_contracts=(
                    identity_mutation_reconciliation_dispatcher_contracts()
                ),
            )

    def test_duplicate_runtime_api_route_fails_startup_audit(self) -> None:
        app = create_app()

        async def duplicate_proposal_route() -> dict[str, bool]:
            return {"executed": True}

        app.add_api_route(
            "/proposals",
            duplicate_proposal_route,
            methods=["POST"],
        )
        with self.assertRaisesRegex(
            KeyedMutationCapabilityError,
            "duplicate runtime APIRoute identity: POST /proposals \\(2\\)",
        ):
            audit_keyed_mutation_route_capabilities(
                app,
                load_keyed_mutation_route_capabilities(),
                dispatcher_contracts=(
                    identity_mutation_reconciliation_dispatcher_contracts()
                ),
            )


if __name__ == "__main__":
    unittest.main()
