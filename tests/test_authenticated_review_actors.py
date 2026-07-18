"""Executable contract for server-owned actors on governed review writes."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient
from sqlmodel import Session, select

from finharness.api.app import create_app
from finharness.api.routes_capital_mandates import CapitalMandateRequest
from finharness.api.routes_proposals import (
    AttestationCreateRequest,
    ProposalScaffoldRevisionRequest,
    ReviewEventCreateRequest,
    ScaffoldRevisionCandidateApplyRequest,
)
from finharness.identity import (
    IDEMPOTENCY_HEADER,
    IDEMPOTENT_REPLAY_HEADER,
    IDENTITY_RECEIPT_HEADER,
    IdentityMutationClaim,
    IdentityMutationError,
    OperatorContext,
    TestIdentityProvider,
    authoritative_actor_id_from_binding,
    bind_authenticated_actor_to_mutation,
    identity_mutation_source_ref,
)
from finharness.statecore.models import Attestation
from finharness.statecore.proposal_version import resolve_current_proposal_version
from finharness.statecore.store import init_state_core
from tests._scaffold import VALID_SCAFFOLD
from tests.authority_test_helpers import authority_admin_context

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "docs" / "governance" / "receipt-backed-write-registry.json"

EXPECTED_CONTRACT_KEYS = {
    "schema",
    "authority_source",
    "authoritative_actor_selection",
    "request_actor_fields",
    "identity_receipt_source",
    "unkeyed_identity_reference",
    "historical_actor_labels",
    "non_claims",
    "routes",
}

EXPECTED_ROUTE_CONTRACTS = {
    "POST /proposals/{proposal_id}/attest": (
        "AttestationCreateRequest",
        ("attester",),
        "Attestation.attester",
        "mutation_context",
    ),
    "PATCH /proposals/{proposal_id}/decision-scaffold": (
        "ProposalScaffoldRevisionRequest",
        ("attester",),
        "Proposal receipt revision_context.attester",
        "revision_context",
    ),
    "POST /proposals/{proposal_id}/review-events": (
        "ReviewEventCreateRequest",
        ("attester",),
        "ReviewEvent.attester",
        "mutation_context",
    ),
    "POST /scaffold-revision-candidates/{candidate_id}/apply": (
        "ScaffoldRevisionCandidateApplyRequest",
        ("human_attester",),
        "Proposal receipt revision_context.attester",
        "revision_context",
    ),
    "POST /capital-mandates": (
        "CapitalMandateRequest",
        ("human_attester", "authenticated_actor_receipt_ref"),
        "CapitalMandate.human_attester",
        "authenticated_actor_receipt_ref",
    ),
}

REQUEST_MODELS = {
    "AttestationCreateRequest": AttestationCreateRequest,
    "ProposalScaffoldRevisionRequest": ProposalScaffoldRevisionRequest,
    "ReviewEventCreateRequest": ReviewEventCreateRequest,
    "ScaffoldRevisionCandidateApplyRequest": ScaffoldRevisionCandidateApplyRequest,
    "CapitalMandateRequest": CapitalMandateRequest,
}


def _context(*, agent_runtime_id: str | None = None) -> OperatorContext:
    return authority_admin_context(
        "principal:alice",
        provider_id="test-provider",
        legacy_label="Alice legacy label",
        agent_runtime_id=agent_runtime_id,
    )


class AuthenticatedReviewActorContractTest(unittest.TestCase):
    def test_route_inventory_is_exact_and_request_actor_fields_are_forbidden(self) -> None:
        registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
        contract = registry["authenticated_actor_contract"]
        self.assertEqual(set(contract), EXPECTED_CONTRACT_KEYS)
        self.assertEqual(contract["schema"], "finharness.governed_write_actor_routes.v1")
        self.assertEqual(contract["authority_source"], "WriteCapabilityDependency.OperatorContext")
        self.assertEqual(
            contract["authoritative_actor_selection"],
            "agent_runtime_id_when_present_else_principal_id",
        )
        self.assertEqual(contract["request_actor_fields"], "forbidden")
        self.assertEqual(contract["identity_receipt_source"], "server_identity_mutation_claim_only")
        self.assertEqual(
            contract["unkeyed_identity_reference"],
            "not_backfilled_pending_issue_352_cross_medium_commit",
        )
        self.assertEqual(
            contract["historical_actor_labels"],
            "preserved_unverified_not_authoritative",
        )
        self.assertEqual(
            contract["non_claims"],
            [
                "Authentication identity is not capital authority.",
                "Actor binding does not authorize execution.",
            ],
        )

        actual = {
            route["route_ref"]: (
                route["request_model"],
                tuple(route["forbidden_request_fields"]),
                route["domain_actor_field"],
                route["domain_receipt_context"],
            )
            for route in contract["routes"]
        }
        self.assertEqual(actual, EXPECTED_ROUTE_CONTRACTS)
        self.assertEqual(len(contract["routes"]), len(actual))

        for request_model, forbidden, _, _ in actual.values():
            model = REQUEST_MODELS[request_model]
            with self.subTest(request_model=request_model):
                self.assertEqual(model.model_config.get("extra"), "forbid")
                self.assertTrue(set(forbidden).isdisjoint(model.model_fields))

    def test_authoritative_actor_prefers_authenticated_runtime(self) -> None:
        human = _context()
        agent = _context(agent_runtime_id="agent-runtime:alice:review")
        self.assertEqual(human.authoritative_actor_id, "principal:alice")
        self.assertEqual(agent.authoritative_actor_id, "agent-runtime:alice:review")

    def test_mutation_actor_binding_rejects_parallel_or_substituted_actor(self) -> None:
        context = _context(agent_runtime_id="agent-runtime:alice:review")
        valid = IdentityMutationClaim(
            disposition="execute",
            receipt_id="identity_mutation_0123456789abcdef0123456789abcdef",
            receipt_path=Path("unused.json"),
            payload={"state": "pending", "actor": context.receipt_binding()},
        )
        actor_ref, actor = bind_authenticated_actor_to_mutation(
            valid,
            context=context,
        ) or (None, None)
        self.assertEqual(
            actor_ref,
            "identity-mutation:identity_mutation_0123456789abcdef0123456789abcdef",
        )
        self.assertEqual(authoritative_actor_id_from_binding(actor), context.authoritative_actor_id)

        for mutation in (
            {**context.receipt_binding(), "principal_id": "principal:bob"},
            {**context.receipt_binding(), "agent_runtime_id": "agent-runtime:bob:review"},
            {**context.receipt_binding(), "parallel_actor_source": "caller"},
        ):
            with self.subTest(mutation=mutation):
                hostile = IdentityMutationClaim(
                    disposition="execute",
                    receipt_id=valid.receipt_id,
                    receipt_path=valid.receipt_path,
                    payload={"state": "pending", "actor": mutation},
                )
                with self.assertRaisesRegex(
                    IdentityMutationError,
                    "differs from OperatorContext",
                ):
                    bind_authenticated_actor_to_mutation(hostile, context=context)

    def test_caller_actor_fields_are_rejected_on_all_governed_routes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            engine = init_state_core(root / "state.sqlite")
            self.addCleanup(engine.dispose)
            app = create_app(
                state_core_engine=engine,
                receipt_root=str(root / "receipts"),
                identity_provider=TestIdentityProvider({"alice": _context()}),
            )
            headers = {"Authorization": "Bearer alice"}
            cases = (
                (
                    "POST",
                    "/proposals/not-used/attest",
                    {"decision": "rejected", "reason": "No substitution.", "attester": "Bob"},
                    "attester",
                ),
                (
                    "PATCH",
                    "/proposals/not-used/decision-scaffold",
                    {"reason": "No substitution.", "decision_scaffold": {}, "attester": "Bob"},
                    "attester",
                ),
                (
                    "POST",
                    "/proposals/not-used/review-events",
                    {"kind": "annotation", "reason": "No substitution.", "attester": "Bob"},
                    "attester",
                ),
                (
                    "POST",
                    "/scaffold-revision-candidates/not-used/apply",
                    {
                        "human_reason": "No substitution.",
                        "human_attester": "Bob",
                        "expected_candidate_receipt_ref": "candidate:1",
                        "expected_proposal_receipt_ref": "proposal:1",
                        "expected_preflight_report_hash": "a" * 64,
                        "explicit_confirmation": True,
                        "explicit_preflight_acknowledgement": True,
                    },
                    "human_attester",
                ),
                (
                    "POST",
                    "/capital-mandates",
                    {
                        "human_reason": "No substitution.",
                        "explicit_confirmation": True,
                        "human_attester": "Bob",
                    },
                    "human_attester",
                ),
                (
                    "POST",
                    "/capital-mandates",
                    {
                        "human_reason": "No receipt substitution.",
                        "explicit_confirmation": True,
                        "authenticated_actor_receipt_ref": "identity:principal:bob",
                    },
                    "authenticated_actor_receipt_ref",
                ),
            )
            with TestClient(app) as client:
                for method, path, body, field in cases:
                    with self.subTest(path=path, field=field):
                        response = client.request(method, path, headers=headers, json=body)
                        self.assertEqual(response.status_code, 422, response.text)
                        errors = response.json()["detail"]
                        self.assertTrue(
                            any(
                                error.get("type") == "extra_forbidden"
                                and error.get("loc", [])[-1] == field
                                for error in errors
                            ),
                            errors,
                        )

    def test_agent_actor_agrees_across_row_receipts_and_restart_replay(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            engine = init_state_core(root / "state.sqlite")
            self.addCleanup(engine.dispose)
            context = _context(agent_runtime_id="agent-runtime:alice:review")
            provider = TestIdentityProvider({"alice": context})
            headers = {
                "Authorization": "Bearer alice",
                IDEMPOTENCY_HEADER: "authenticated-agent-attestation-0001",
            }
            app = create_app(
                state_core_engine=engine,
                receipt_root=str(root / "receipts"),
                identity_provider=provider,
            )
            with TestClient(app) as client:
                proposal = client.post(
                    "/proposals",
                    headers={"Authorization": "Bearer alice"},
                    json={
                        "kind": "allocation",
                        "claim": "Server actor owns review identity.",
                        "decision_scaffold": VALID_SCAFFOLD,
                        "source_refs": ["test:authenticated-review-actor"],
                    },
                ).json()["proposal"]
                endpoint = f"/proposals/{proposal['proposal_id']}/attest"
                version = resolve_current_proposal_version(
                    proposal["proposal_id"],
                    engine=engine,
                    receipt_root=root / "receipts",
                )
                body = {
                    "decision": "rejected",
                    "reason": "Bind the authenticated runtime, not request prose.",
                    "expected_proposal_version_id": version.proposal_version_id,
                    "expected_proposal_receipt_ref": version.receipt_ref,
                }
                first = client.post(endpoint, headers=headers, json=body)
            self.assertEqual(first.status_code, 200, first.text)
            receipt_id = first.headers[IDENTITY_RECEIPT_HEADER]
            domain = first.json()["attestation"]
            self.assertEqual(domain["attester"], context.authoritative_actor_id)
            receipt = json.loads(Path(first.json()["receipt_ref"]).read_text(encoding="utf-8"))
            self.assertEqual(receipt["attestation"]["attester"], context.authoritative_actor_id)
            self.assertEqual(
                receipt["mutation_context"]["authenticated_actor"],
                context.receipt_binding(),
            )
            self.assertEqual(
                receipt["mutation_context"]["authenticated_actor_receipt_ref"],
                identity_mutation_source_ref(receipt_id),
            )

            restarted = create_app(
                state_core_engine=engine,
                receipt_root=str(root / "receipts"),
                identity_provider=provider,
            )
            with TestClient(restarted) as client:
                replay = client.post(endpoint, headers=headers, json=body)
            self.assertEqual(replay.status_code, 200, replay.text)
            self.assertEqual(replay.headers[IDEMPOTENT_REPLAY_HEADER], "true")
            self.assertEqual(replay.headers[IDENTITY_RECEIPT_HEADER], receipt_id)
            self.assertEqual(replay.json(), first.json())
            with Session(engine) as session:
                rows = list(session.exec(select(Attestation)).all())
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0].attester, context.authoritative_actor_id)

    def test_capital_mandate_keyed_write_is_prohibited_before_actor_binding(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            engine = init_state_core(root / "state.sqlite")
            self.addCleanup(engine.dispose)
            context = _context()
            app = create_app(
                state_core_engine=engine,
                receipt_root=str(root / "receipts"),
                identity_provider=TestIdentityProvider({"alice": context}),
            )
            headers = {
                "Authorization": "Bearer alice",
                IDEMPOTENCY_HEADER: "authenticated-capital-mandate-0001",
            }
            with TestClient(app) as client:
                keyed = client.post(
                    "/capital-mandates",
                    headers=headers,
                    json={
                        "human_reason": "Record policy with server-owned actor provenance.",
                        "explicit_confirmation": True,
                    },
                )
                response = client.post(
                    "/capital-mandates",
                    headers={"Authorization": "Bearer alice"},
                    json={
                        "human_reason": "Record policy with server-owned actor provenance.",
                        "explicit_confirmation": True,
                    },
                )
                current = client.get(
                    "/capital-mandates/current",
                    headers={"Authorization": "Bearer alice"},
                )
            self.assertEqual(keyed.status_code, 409, keyed.text)
            self.assertEqual(
                keyed.json()["detail"]["code"],
                "keyed_mutation_prohibited",
            )
            self.assertNotIn(IDENTITY_RECEIPT_HEADER, keyed.headers)
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(
                response.json()["capital_mandate"]["human_attester"],
                context.authoritative_actor_id,
            )
            resolution = current.json()["resolution"]
            self.assertIsNone(
                resolution["version"]["authenticated_actor_receipt_ref"],
            )
            self.assertEqual(
                resolution["version"]["legacy_actor_label"],
                "Alice legacy label",
            )
            self.assertFalse(resolution["version"]["legacy_actor_label_verified"])


if __name__ == "__main__":
    unittest.main()
