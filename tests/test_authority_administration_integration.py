from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from finharness.api.app import create_app
from finharness.authority_administration import AuthorityAdministrationDeniedError
from finharness.identity import IDEMPOTENCY_HEADER, TestIdentityProvider
from finharness.local_operator import LocalOperatorContext
from finharness.statecore.agent_authority_grants import (
    AgentAuthorityGrantValidationError,
    consume_agent_authority_grant,
    record_agent_authority_grant,
    revoke_agent_authority_grant,
)
from finharness.statecore.capital_mandates import (
    record_capital_mandate,
    resume_capital_mandate,
    revoke_capital_mandate,
    suspend_capital_mandate,
)
from finharness.statecore.models import (
    AgentAuthorityGrant,
    AgentAuthorityGrantConsumption,
    CapitalMandate,
    CapitalMandateLifecycleEvent,
    CapitalMandateVersion,
    ReceiptIndex,
)
from finharness.statecore.store import init_state_core, read_all
from tests.asgi_test_client import AsgiTestClient
from tests.authority_test_helpers import authority_admin_context


class AuthorityAdministrationIntegrationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.receipts = self.root / "receipts"
        self.engine = init_state_core(self.root / "state.sqlite")
        self.addCleanup(self.engine.dispose)
        self.addCleanup(self.tmp.cleanup)
        self.admin = authority_admin_context("principal:alice")

    def _mandate_body(self, mandate_id: str = "mandate:admin") -> dict[str, object]:
        return {
            "capital_mandate_id": mandate_id,
            "profile_snapshot": {},
            "investment_objectives": {},
            "risk_profile": {},
            "allowed_asset_classes": ["cash"],
            "allowed_action_types": ["rebalance"],
            "typed_limits": {
                "action_types": ["rebalance"],
                "max_notional": {"amount": "1000", "currency": "USD"},
            },
            "human_reason": "Human administrator confirms this bounded policy.",
            "explicit_confirmation": True,
        }

    def _record_mandate(self, mandate_id: str = "mandate:admin") -> CapitalMandate:
        body = self._mandate_body(mandate_id)
        return record_capital_mandate(
            operator_context=self.admin,
            engine=self.engine,
            receipt_root=self.receipts,
            **body,
        )

    def _record_grant(
        self,
        mandate_id: str,
        grant_id: str = "grant:admin",
    ) -> AgentAuthorityGrant:
        return record_agent_authority_grant(
            operator_context=self.admin,
            agent_authority_grant_id=grant_id,
            capital_mandate_id=mandate_id,
            agent_id="agent:research",
            agent_runtime_id="runtime:research",
            grant_scope={
                "allowed_asset_classes": ["cash"],
                "allowed_action_types": ["rebalance"],
                "autonomy_level": "L1_candidate_only",
            },
            issued_reason="Allow bounded candidate research.",
            engine=self.engine,
            receipt_root=self.receipts,
        )

    def _domain_snapshot(self) -> dict[str, object]:
        return {
            "mandates": [row.model_dump() for row in read_all(CapitalMandate, engine=self.engine)],
            "versions": [
                row.model_dump() for row in read_all(CapitalMandateVersion, engine=self.engine)
            ],
            "events": [
                row.model_dump()
                for row in read_all(CapitalMandateLifecycleEvent, engine=self.engine)
            ],
            "grants": [
                row.model_dump() for row in read_all(AgentAuthorityGrant, engine=self.engine)
            ],
            "indexes": [row.model_dump() for row in read_all(ReceiptIndex, engine=self.engine)],
            "domain_receipts": sorted(
                str(path.relative_to(self.receipts))
                for path in self.receipts.rglob("*.json")
                if "identity" not in path.parts
            ),
        }

    def _client(
        self,
        identities: dict[str, object],
    ) -> tuple[AsgiTestClient, dict[str, object]]:
        provider_mapping = dict(identities)
        app = create_app(
            state_core_engine=self.engine,
            receipt_root=str(self.receipts),
            identity_provider=TestIdentityProvider(provider_mapping),  # type: ignore[arg-type]
        )
        client = AsgiTestClient(app)
        self.addCleanup(client.close)
        return client, provider_mapping

    def test_direct_domain_calls_cannot_bypass_administration_guard(self) -> None:
        mandate = self._record_mandate()
        grant = self._record_grant(mandate.capital_mandate_id)
        before = self._domain_snapshot()
        denied_contexts = {
            "ordinary": authority_admin_context(
                "principal:alice",
                with_assertion=False,
            ),
            "service": authority_admin_context(
                "principal:alice",
                principal_kind="service",
            ),
            "agent": authority_admin_context(
                "principal:alice",
                agent_runtime_id="runtime:alice-agent",
            ),
        }
        for context_name, context in denied_contexts.items():
            calls = (
                lambda context=context, context_name=context_name: record_capital_mandate(
                    operator_context=context,
                    engine=self.engine,
                    receipt_root=self.receipts,
                    **self._mandate_body(f"mandate:denied:{context_name}"),
                ),
                lambda context=context: suspend_capital_mandate(
                    mandate.capital_mandate_id,
                    operator_context=context,
                    reason="Denied.",
                    engine=self.engine,
                    receipt_root=self.receipts,
                ),
                lambda context=context: resume_capital_mandate(
                    mandate.capital_mandate_id,
                    operator_context=context,
                    reason="Denied.",
                    engine=self.engine,
                    receipt_root=self.receipts,
                ),
                lambda context=context: revoke_capital_mandate(
                    mandate.capital_mandate_id,
                    operator_context=context,
                    reason="Denied.",
                    engine=self.engine,
                    receipt_root=self.receipts,
                ),
                lambda context=context: record_agent_authority_grant(
                    operator_context=context,
                    capital_mandate_id=mandate.capital_mandate_id,
                    agent_id="agent:other",
                    issued_reason="Denied.",
                    engine=self.engine,
                    receipt_root=self.receipts,
                ),
                lambda context=context: revoke_agent_authority_grant(
                    grant.agent_authority_grant_id,
                    operator_context=context,
                    reason="Denied.",
                    engine=self.engine,
                    receipt_root=self.receipts,
                ),
            )
            for call in calls:
                with (
                    self.subTest(
                        context=context_name,
                        call=call,
                    ),
                    self.assertRaises(AuthorityAdministrationDeniedError),
                ):
                    call()
                self.assertEqual(self._domain_snapshot(), before)

    def test_api_denials_are_typed_and_have_no_domain_side_effect(self) -> None:
        contexts = {
            "ordinary": authority_admin_context("principal:alice", with_assertion=False),
            "service": authority_admin_context(
                "principal:service",
                principal_kind="service",
            ),
            "agent": authority_admin_context(
                "principal:alice",
                agent_runtime_id="runtime:alice-agent",
            ),
        }
        client, _mapping = self._client(contexts)
        before = self._domain_snapshot()
        expected = {
            "ordinary": "authority_administrator_required",
            "service": "human_principal_required",
            "agent": "agent_runtime_forbidden",
        }
        for token, reason in expected.items():
            with self.subTest(token=token):
                response = client.post(
                    "/capital-mandates",
                    headers={"Authorization": f"Bearer {token}"},
                    json=self._mandate_body(f"mandate:{token}"),
                )
                self.assertEqual(response.status_code, 403, response.text)
                self.assertEqual(
                    response.json()["detail"],
                    {
                        "code": "authority_administration_denied",
                        "reason": reason,
                        "operation": "mandate_create_or_replace",
                        "policy_version": "finharness.authority-administration.v1",
                        "execution_allowed": False,
                        "authority_transition": False,
                    },
                )
                self.assertEqual(self._domain_snapshot(), before)

    def test_request_fields_and_headers_cannot_mint_administration(self) -> None:
        ordinary = authority_admin_context("principal:alice", with_assertion=False)
        client, _mapping = self._client({"ordinary": ordinary})
        hostile = {
            **self._mandate_body(),
            "operation": "mandate_suspend",
            "is_admin": True,
            "authentication_assurance": "elevated",
        }
        structurally_rejected = client.post(
            "/capital-mandates",
            headers={"Authorization": "Bearer ordinary"},
            json=hostile,
        )
        self.assertEqual(structurally_rejected.status_code, 422)

        denied = client.post(
            "/capital-mandates",
            headers={
                "Authorization": "Bearer ordinary",
                "X-FinHarness-Admin": "true",
                "X-FinHarness-Assurance": "elevated",
                "X-FinHarness-Policy-Version": "finharness.authority-administration.v1",
            },
            json=self._mandate_body(),
        )
        self.assertEqual(denied.status_code, 403)
        self.assertEqual(
            denied.json()["detail"]["reason"],
            "authority_administrator_required",
        )

        mandate = self._record_mandate()
        mislabeled_resume = client.post(
            f"/capital-mandates/{mandate.capital_mandate_id}/resume",
            headers={"Authorization": "Bearer ordinary"},
            json={"reason": "Caller mislabels expansion.", "operation": "mandate_suspend"},
        )
        self.assertEqual(mislabeled_resume.status_code, 422)
        hostile_grant = {
            "capital_mandate_id": mandate.capital_mandate_id,
            "agent_id": "agent:research",
            "issued_by": "principal:alice",
            "issued_reason": "Caller tries to supply authority.",
            "operation": "grant_revoke",
        }
        grant_structurally_rejected = client.post(
            "/agent-authority-grants",
            headers={"Authorization": "Bearer ordinary"},
            json=hostile_grant,
        )
        self.assertEqual(grant_structurally_rejected.status_code, 422)
        grant_denied = client.post(
            "/agent-authority-grants",
            headers={
                "Authorization": "Bearer ordinary",
                "X-FinHarness-Admin": "true",
                "X-FinHarness-Assurance": "elevated",
            },
            json={
                "capital_mandate_id": mandate.capital_mandate_id,
                "agent_id": "agent:research",
                "issued_reason": "Header must not grant authority.",
            },
        )
        self.assertEqual(grant_denied.status_code, 403)
        self.assertEqual(
            grant_denied.json()["detail"]["reason"],
            "authority_administrator_required",
        )

    def test_legacy_local_operator_is_not_an_implicit_administrator(self) -> None:
        app = create_app(
            state_core_engine=self.engine,
            receipt_root=str(self.receipts),
            local_operator_context=LocalOperatorContext("legacy-admin-label"),
        )
        client = AsgiTestClient(app)
        self.addCleanup(client.close)
        response = client.post("/capital-mandates", json=self._mandate_body())
        self.assertEqual(response.status_code, 403, response.text)
        self.assertEqual(
            response.json()["detail"]["reason"],
            "human_principal_required",
        )

    def test_standard_admin_can_reduce_but_cannot_expand_authority(self) -> None:
        mandate = self._record_mandate()
        grant = self._record_grant(mandate.capital_mandate_id)
        standard = authority_admin_context("principal:alice", assurance="standard")
        client, _mapping = self._client({"standard": standard})
        headers = {"Authorization": "Bearer standard"}

        create = client.post(
            "/capital-mandates",
            headers=headers,
            json=self._mandate_body("mandate:replacement"),
        )
        self.assertEqual(create.status_code, 403)
        self.assertEqual(
            create.json()["detail"]["reason"],
            "elevated_authentication_required",
        )
        create_grant = client.post(
            "/agent-authority-grants",
            headers=headers,
            json={
                "capital_mandate_id": mandate.capital_mandate_id,
                "agent_id": "agent:other",
                "issued_reason": "Attempt expansion.",
            },
        )
        self.assertEqual(create_grant.status_code, 403)
        self.assertEqual(
            create_grant.json()["detail"]["reason"],
            "elevated_authentication_required",
        )

        suspend = client.post(
            f"/capital-mandates/{mandate.capital_mandate_id}/suspend",
            headers=headers,
            json={"reason": "Emergency pause."},
        )
        self.assertEqual(suspend.status_code, 200, suspend.text)
        resume = client.post(
            f"/capital-mandates/{mandate.capital_mandate_id}/resume",
            headers=headers,
            json={"reason": "Attempt restore."},
        )
        self.assertEqual(resume.status_code, 403)
        self.assertEqual(
            resume.json()["detail"]["reason"],
            "elevated_authentication_required",
        )
        revoke_grant = client.post(
            f"/agent-authority-grants/{grant.agent_authority_grant_id}/revoke",
            headers=headers,
            json={"reason": "Emergency revoke."},
        )
        self.assertEqual(revoke_grant.status_code, 200, revoke_grant.text)
        revoke_mandate = client.post(
            f"/capital-mandates/{mandate.capital_mandate_id}/revoke",
            headers=headers,
            json={"reason": "Emergency revoke."},
        )
        self.assertEqual(revoke_mandate.status_code, 200, revoke_mandate.text)

    def test_reduction_requests_cannot_supply_future_or_backdated_authority_time(
        self,
    ) -> None:
        mandate = self._record_mandate()
        grant = self._record_grant(mandate.capital_mandate_id)
        client, _mapping = self._client({"admin": self.admin})
        headers = {"Authorization": "Bearer admin"}
        cases = (
            (
                f"/capital-mandates/{mandate.capital_mandate_id}/suspend",
                "effective_at_utc",
            ),
            (
                f"/capital-mandates/{mandate.capital_mandate_id}/revoke",
                "effective_at_utc",
            ),
            (
                f"/agent-authority-grants/{grant.agent_authority_grant_id}/revoke",
                "revoked_at_utc",
            ),
        )
        for path, field in cases:
            for hostile_time in (
                "2020-01-01T00:00:00+00:00",
                "2035-01-01T00:00:00+00:00",
            ):
                with self.subTest(path=path, field=field, hostile_time=hostile_time):
                    before = self._domain_snapshot()
                    response = client.post(
                        path,
                        headers=headers,
                        json={
                            "reason": "Caller must not own reduction time.",
                            field: hostile_time,
                        },
                    )
                    self.assertEqual(response.status_code, 422, response.text)
                    self.assertEqual(self._domain_snapshot(), before)

    def test_reduction_mutation_receipt_response_and_decision_share_server_time(
        self,
    ) -> None:
        mandate = self._record_mandate()
        grant = self._record_grant(mandate.capital_mandate_id)
        client, _mapping = self._client(
            {
                "standard": authority_admin_context(
                    "principal:alice",
                    assurance="standard",
                )
            }
        )
        headers = {"Authorization": "Bearer standard"}

        mandate_time = "2026-07-17T08:30:00+00:00"
        with patch(
            "finharness.statecore.capital_mandates._now_utc",
            return_value=mandate_time,
        ):
            suspended = client.post(
                f"/capital-mandates/{mandate.capital_mandate_id}/suspend",
                headers=headers,
                json={"reason": "Immediate server-timed pause."},
            )
        self.assertEqual(suspended.status_code, 200, suspended.text)
        suspended_body = suspended.json()
        event = suspended_body["resolution"]["lifecycle_event"]
        self.assertEqual(suspended_body["resolution"]["at_utc"], mandate_time)
        self.assertEqual(event["effective_at_utc"], mandate_time)
        self.assertEqual(event["created_at_utc"], mandate_time)
        mandate_receipt = json.loads(
            Path(suspended_body["receipt_ref"]).read_text(encoding="utf-8")
        )
        self.assertEqual(mandate_receipt["created_at_utc"], mandate_time)
        self.assertEqual(
            mandate_receipt["authority_administration"]["checked_at_utc"],
            mandate_time,
        )
        self.assertEqual(
            mandate_receipt["lifecycle_event"]["effective_at_utc"],
            mandate_time,
        )
        mandate_index = next(
            row
            for row in read_all(ReceiptIndex, engine=self.engine)
            if row.path == suspended_body["receipt_ref"]
        )
        self.assertEqual(mandate_index.created_at_utc, mandate_time)

        grant_time = "2026-07-17T08:31:00+00:00"
        with patch(
            "finharness.statecore.agent_authority_grants._now_utc",
            return_value=grant_time,
        ):
            revoked = client.post(
                f"/agent-authority-grants/{grant.agent_authority_grant_id}/revoke",
                headers=headers,
                json={"reason": "Immediate server-timed revoke."},
            )
        self.assertEqual(revoked.status_code, 200, revoked.text)
        revoked_body = revoked.json()
        self.assertEqual(
            revoked_body["agent_authority_grant"]["revoked_at_utc"],
            grant_time,
        )
        grant_receipt = json.loads(Path(revoked_body["receipt_ref"]).read_text(encoding="utf-8"))
        self.assertEqual(grant_receipt["created_at_utc"], grant_time)
        self.assertEqual(
            grant_receipt["authority_administration"]["checked_at_utc"],
            grant_time,
        )
        self.assertEqual(grant_receipt["grant_after"]["revoked_at_utc"], grant_time)
        grant_index = next(
            row
            for row in read_all(ReceiptIndex, engine=self.engine)
            if row.path == revoked_body["receipt_ref"]
        )
        self.assertEqual(grant_index.created_at_utc, grant_time)

        with self.assertRaisesRegex(
            AgentAuthorityGrantValidationError,
            "grant_not_active",
        ):
            consume_agent_authority_grant(
                grant.agent_authority_grant_id,
                principal_id="principal:alice",
                agent_runtime_id="runtime:research",
                nonce="after-revoke",
                requested_scope={
                    "allowed_asset_classes": ["cash"],
                    "allowed_action_types": ["rebalance"],
                    "autonomy_level": "L1_candidate_only",
                },
                requested_notional={"amount": "0", "currency": "USD"},
                engine=self.engine,
                receipt_root=self.receipts,
            )

    def test_reduction_idempotent_replay_keeps_original_authoritative_time(
        self,
    ) -> None:
        mandate = self._record_mandate()
        client, mapping = self._client({"admin": self.admin})
        headers = {
            "Authorization": "Bearer admin",
            IDEMPOTENCY_HEADER: "authority-reduction-replay-0001",
        }
        body = {"reason": "Replay must preserve the committed reduction."}
        first_time = "2026-07-17T08:32:00+00:00"
        with patch(
            "finharness.statecore.capital_mandates._now_utc",
            return_value=first_time,
        ):
            first = client.post(
                f"/capital-mandates/{mandate.capital_mandate_id}/suspend",
                headers=headers,
                json=body,
            )
        self.assertEqual(first.status_code, 200, first.text)
        after_first = self._domain_snapshot()
        self.assertEqual(first.json()["resolution"]["at_utc"], first_time)

        mapping["admin"] = authority_admin_context(
            "principal:alice",
            with_assertion=False,
        )
        with patch(
            "finharness.statecore.capital_mandates._now_utc",
            return_value="2026-07-17T09:32:00+00:00",
        ):
            replay = client.post(
                f"/capital-mandates/{mandate.capital_mandate_id}/suspend",
                headers=headers,
                json=body,
            )
        self.assertEqual(replay.status_code, 200, replay.text)
        self.assertEqual(replay.headers["X-FinHarness-Idempotent-Replay"], "true")
        self.assertEqual(replay.json(), first.json())
        self.assertEqual(self._domain_snapshot(), after_first)

    def test_committed_mandate_reduction_blocks_grant_consumption(self) -> None:
        mandate = self._record_mandate()
        grant = self._record_grant(mandate.capital_mandate_id)
        suspend_capital_mandate(
            mandate.capital_mandate_id,
            operator_context=authority_admin_context(
                "principal:alice",
                assurance="standard",
            ),
            reason="Immediate mandate kill switch.",
            engine=self.engine,
            receipt_root=self.receipts,
        )

        with self.assertRaisesRegex(
            AgentAuthorityGrantValidationError,
            "capital_mandate_not_active",
        ):
            consume_agent_authority_grant(
                grant.agent_authority_grant_id,
                principal_id="principal:alice",
                agent_runtime_id="runtime:research",
                nonce="after-mandate-suspend",
                requested_scope={
                    "allowed_asset_classes": ["cash"],
                    "allowed_action_types": ["rebalance"],
                    "autonomy_level": "L1_candidate_only",
                },
                requested_notional={"amount": "0", "currency": "USD"},
                engine=self.engine,
                receipt_root=self.receipts,
            )
        self.assertEqual(
            read_all(AgentAuthorityGrantConsumption, engine=self.engine),
            [],
        )

    def test_receipts_bind_decision_to_exact_domain_targets(self) -> None:
        mandate = self._record_mandate()
        mandate_receipt = json.loads(Path(mandate.receipt_ref or "").read_text())
        mandate_decision = mandate_receipt["authority_administration"]
        self.assertEqual(mandate_decision["operation"], "mandate_create_or_replace")
        self.assertEqual(
            mandate_decision["administrator_principal_id"],
            mandate_receipt["mandate_version"]["principal_id"],
        )
        self.assertEqual(
            mandate_receipt["capital_mandate"]["capital_mandate_id"],
            mandate_receipt["mandate_version"]["capital_mandate_id"],
        )

        grant = self._record_grant(mandate.capital_mandate_id)
        grant_receipt = json.loads(Path(grant.receipt_ref or "").read_text())
        grant_decision = grant_receipt["authority_administration"]
        self.assertEqual(grant_decision["operation"], "grant_create")
        self.assertEqual(
            grant_decision["administrator_principal_id"],
            grant_receipt["agent_authority_grant"]["principal_id"],
        )
        self.assertEqual(
            grant_receipt["agent_authority_grant"]["mandate_version_id"],
            grant_receipt["source_capital_mandate_version"]["mandate_version_id"],
        )

        event = suspend_capital_mandate(
            mandate.capital_mandate_id,
            operator_context=authority_admin_context(
                "principal:alice",
                assurance="standard",
            ),
            reason="Pause.",
            engine=self.engine,
            receipt_root=self.receipts,
        )
        lifecycle_receipt = json.loads(Path(event.receipt_ref).read_text())
        self.assertEqual(
            lifecycle_receipt["authority_administration"]["operation"],
            "mandate_suspend",
        )
        self.assertEqual(
            lifecycle_receipt["mandate_version"]["mandate_version_id"],
            lifecycle_receipt["lifecycle_event"]["mandate_version_id"],
        )

    def test_historical_replay_is_not_current_authorization(self) -> None:
        elevated = authority_admin_context("principal:alice")
        client, _mapping = self._client({"alice": elevated})
        body = self._mandate_body("mandate:replay")
        headers = {
            "Authorization": "Bearer alice",
            IDEMPOTENCY_HEADER: "authority-admin-replay-0001",
        }
        first = client.post("/capital-mandates", headers=headers, json=body)
        self.assertEqual(first.status_code, 200, first.text)
        after_first = self._domain_snapshot()

        client.close()
        self.engine.dispose()
        self.engine = init_state_core(self.root / "state.sqlite")
        self.addCleanup(self.engine.dispose)
        restarted, _mapping = self._client(
            {
                "alice": authority_admin_context(
                    "principal:alice",
                    with_assertion=False,
                )
            }
        )
        replay = restarted.post("/capital-mandates", headers=headers, json=body)
        self.assertEqual(replay.status_code, 200, replay.text)
        self.assertEqual(replay.headers["X-FinHarness-Idempotent-Replay"], "true")
        self.assertEqual(replay.json(), first.json())
        self.assertEqual(self._domain_snapshot(), after_first)

        old_receipt_ref = first.json()["receipt_ref"]
        new_command_body = {**body, "receipt_refs": [old_receipt_ref]}
        denied = restarted.post(
            "/capital-mandates",
            headers={
                "Authorization": "Bearer alice",
                IDEMPOTENCY_HEADER: "authority-admin-new-command-0002",
            },
            json=new_command_body,
        )
        self.assertEqual(denied.status_code, 403, denied.text)
        self.assertEqual(
            denied.json()["detail"]["reason"],
            "authority_administrator_required",
        )
        self.assertEqual(self._domain_snapshot(), after_first)

        _mapping["alice"] = authority_admin_context(
            "principal:alice",
            policy_version="finharness.authority-administration.v0",
        )
        wrong_policy = restarted.post(
            "/capital-mandates",
            headers={
                "Authorization": "Bearer alice",
                IDEMPOTENCY_HEADER: "authority-admin-new-command-0003",
            },
            json=new_command_body,
        )
        self.assertEqual(wrong_policy.status_code, 403, wrong_policy.text)
        self.assertEqual(
            wrong_policy.json()["detail"]["reason"],
            "authority_policy_version_mismatch",
        )
        self.assertEqual(self._domain_snapshot(), after_first)


if __name__ == "__main__":
    unittest.main()
