from __future__ import annotations

import json
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from sqlmodel import Session

from finharness.api.app import create_app
from finharness.identity import (
    AgentRuntimeIdentity,
    OperatorContext,
    PrincipalIdentity,
)
from finharness.identity import (
    TestIdentityProvider as DeterministicIdentityProvider,
)
from finharness.local_operator import LocalOperatorContext
from finharness.statecore.agent_authority_grants import (
    AGENT_AUTHORITY_GRANT_DENY_REASONS,
    AGENT_AUTHORITY_GRANT_NON_CLAIMS,
    AgentAuthorityGrantValidationError,
    consume_agent_authority_grant,
    record_agent_authority_grant,
    revoke_agent_authority_grant,
    validate_agent_authority_grant,
)
from finharness.statecore.capital_mandates import record_capital_mandate
from finharness.statecore.models import (
    AgentAuthorityGrant,
    AgentAuthorityGrantConsumption,
    ReceiptIndex,
)
from finharness.statecore.store import init_state_core, read_all
from tests.asgi_test_client import AsgiTestClient


class AgentAuthorityGrantSliceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.receipt_root = self.root / "receipts"
        self.engine = init_state_core(self.root / "state-core.sqlite")
        self.addCleanup(self.engine.dispose)
        self.addCleanup(self.tmp.cleanup)

    def _record_mandate(
        self,
        *,
        mandate_id: str = "mandate_v1",
        allowed_asset_classes: list[str] | None = None,
        allowed_action_types: list[str] | None = None,
        autonomy_level: str = "L1_candidate_only",
    ) -> str:
        mandate = record_capital_mandate(
            capital_mandate_id=mandate_id,
            profile_snapshot={"profile": "balanced"},
            investment_objectives={"primary": "capital_preservation"},
            risk_profile={"max_drawdown_pct": 0.10},
            allowed_asset_classes=allowed_asset_classes or ["cash", "equity"],
            restricted_asset_classes=["crypto_leverage"],
            allowed_action_types=allowed_action_types or ["rebalance", "raise_cash"],
            restricted_action_types=["open_margin"],
            autonomy_level=autonomy_level,
            typed_limits={
                "product_ids": ["portfolio:main"],
                "instrument_ids": ["instrument:SPY"],
                "action_types": ["rebalance", "raise_cash"],
                "max_notional": {"amount": "1000", "currency": "USD"},
            },
            human_attester="owner@example.com",
            human_reason="Attest mandate scope for authority grant tests.",
            explicit_confirmation=True,
            engine=self.engine,
            receipt_root=self.receipt_root,
        )
        return mandate.capital_mandate_id

    def _scope(self) -> dict[str, object]:
        return {
            "allowed_asset_classes": ["cash"],
            "allowed_action_types": ["rebalance"],
            "autonomy_level": "L1_candidate_only",
        }

    def _record_grant(
        self,
        *,
        grant_id: str = "grant_research",
        mandate_id: str | None = None,
        grant_scope: dict[str, object] | None = None,
        expires_at_utc: str | None = None,
        principal_id: str | None = None,
        agent_runtime_id: str | None = None,
        max_uses: int | None = None,
        max_total_notional: str | None = None,
    ) -> AgentAuthorityGrant:
        resolved_mandate_id = mandate_id or self._record_mandate()
        return record_agent_authority_grant(
            agent_authority_grant_id=grant_id,
            capital_mandate_id=resolved_mandate_id,
            agent_id="agent:research",
            agent_profile_name="review-note",
            grant_scope=grant_scope or self._scope(),
            issued_by="owner@example.com",
            issued_reason="Allow the agent to operate inside this mandate scope.",
            expires_at_utc=expires_at_utc,
            principal_id=principal_id,
            agent_runtime_id=agent_runtime_id,
            max_uses=max_uses,
            max_total_notional=max_total_notional,
            source_refs=["docs/product-north-star.md"],
            engine=self.engine,
            receipt_root=self.receipt_root,
        )

    def _set_grant_status(self, grant_id: str, status: str) -> None:
        with Session(self.engine) as session:
            grant = session.get(AgentAuthorityGrant, grant_id)
            assert grant is not None
            grant.status = status
            session.add(grant)
            session.commit()

    def test_create_grant_requires_active_capital_mandate(self) -> None:
        mandate_id = self._record_mandate()
        grant = self._record_grant(mandate_id=mandate_id)

        self.assertEqual(grant.capital_mandate_id, mandate_id)
        self.assertEqual(grant.status, "active")
        self.assertFalse(grant.execution_allowed)
        self.assertFalse(grant.authority_transition)
        self.assertEqual(tuple(grant.non_claims), AGENT_AUTHORITY_GRANT_NON_CLAIMS)

    def test_create_grant_rejects_missing_capital_mandate(self) -> None:
        with self.assertRaises(KeyError):
            self._record_grant(mandate_id="missing_mandate")

    def test_create_grant_rejects_superseded_capital_mandate(self) -> None:
        first = self._record_mandate(mandate_id="mandate_first")
        self._record_mandate(mandate_id="mandate_second")

        with self.assertRaises(AgentAuthorityGrantValidationError):
            self._record_grant(mandate_id=first)

    def test_create_grant_rejects_scope_outside_mandate(self) -> None:
        mandate_id = self._record_mandate()

        with self.assertRaises(AgentAuthorityGrantValidationError):
            self._record_grant(
                mandate_id=mandate_id,
                grant_scope={
                    "allowed_asset_classes": ["crypto"],
                    "allowed_action_types": ["rebalance"],
                    "autonomy_level": "L1_candidate_only",
                },
            )
        with self.assertRaises(AgentAuthorityGrantValidationError):
            self._record_grant(
                mandate_id=mandate_id,
                grant_scope={
                    "allowed_asset_classes": ["cash"],
                    "allowed_action_types": ["open_margin"],
                    "autonomy_level": "L1_candidate_only",
                },
            )
        with self.assertRaises(AgentAuthorityGrantValidationError):
            self._record_grant(
                mandate_id=mandate_id,
                grant_scope={
                    "allowed_asset_classes": ["cash"],
                    "allowed_action_types": ["rebalance"],
                    "autonomy_level": "L2_human_confirmed_apply",
                },
            )

    def test_create_grant_rejects_execution_semantics(self) -> None:
        mandate_id = self._record_mandate()

        with self.assertRaises(AgentAuthorityGrantValidationError):
            self._record_grant(
                mandate_id=mandate_id,
                grant_scope={
                    "allowed_asset_classes": ["cash"],
                    "allowed_action_types": ["rebalance", "submit_order"],
                    "autonomy_level": "L1_candidate_only",
                },
            )

    def test_validate_grant_allows_active_grant_under_active_mandate(self) -> None:
        grant = self._record_grant()

        result = validate_agent_authority_grant(
            grant.agent_authority_grant_id,
            engine=self.engine,
            requested_scope=self._scope(),
        )

        self.assertTrue(result.allowed)
        self.assertEqual(result.deny_reasons, [])
        self.assertTrue(result.scope_result["grant_scope_within_mandate"])
        self.assertTrue(result.scope_result["requested_scope_within_grant"])
        self.assertFalse(result.execution_allowed)
        self.assertFalse(result.authority_transition)

    def test_validate_grant_denies_revoked_and_suspended_grant(self) -> None:
        grant = self._record_grant()

        self._set_grant_status(grant.agent_authority_grant_id, "revoked")
        revoked = validate_agent_authority_grant(
            grant.agent_authority_grant_id,
            engine=self.engine,
            requested_scope=self._scope(),
        )
        self.assertFalse(revoked.allowed)
        self.assertIn("grant_not_active", revoked.deny_reasons)

        self._set_grant_status(grant.agent_authority_grant_id, "suspended")
        suspended = validate_agent_authority_grant(
            grant.agent_authority_grant_id,
            engine=self.engine,
            requested_scope=self._scope(),
        )
        self.assertFalse(suspended.allowed)
        self.assertIn("grant_not_active", suspended.deny_reasons)

    def test_validate_grant_denies_expired_grant(self) -> None:
        grant = self._record_grant(expires_at_utc="2099-07-04T00:00:00+00:00")

        result = validate_agent_authority_grant(
            grant.agent_authority_grant_id,
            engine=self.engine,
            requested_scope=self._scope(),
            now_utc="2100-07-05T00:00:00+00:00",
        )

        self.assertFalse(result.allowed)
        self.assertIn("grant_expired", result.deny_reasons)

    def test_validate_grant_denies_when_current_mandate_series_changes(self) -> None:
        grant = self._record_grant()
        self._record_mandate(mandate_id="mandate_replacement")

        result = validate_agent_authority_grant(
            grant.agent_authority_grant_id,
            engine=self.engine,
            requested_scope=self._scope(),
        )

        self.assertFalse(result.allowed)
        self.assertIn("mandate_version_changed", result.deny_reasons)

    def test_validate_grant_denies_requested_scope_outside_grant(self) -> None:
        grant = self._record_grant()

        result = validate_agent_authority_grant(
            grant.agent_authority_grant_id,
            engine=self.engine,
            requested_scope={
                "allowed_asset_classes": ["equity"],
                "allowed_action_types": ["rebalance"],
                "autonomy_level": "L1_candidate_only",
            },
        )

        self.assertFalse(result.allowed)
        self.assertIn("requested_scope_exceeds_grant", result.deny_reasons)

    def test_validate_grant_denies_forbidden_requested_scope_semantics(self) -> None:
        grant = self._record_grant()

        result = validate_agent_authority_grant(
            grant.agent_authority_grant_id,
            engine=self.engine,
            requested_scope={
                "allowed_asset_classes": ["cash"],
                "allowed_action_types": ["rebalance", "bypass_preflight"],
                "autonomy_level": "L1_candidate_only",
            },
        )

        self.assertFalse(result.allowed)
        self.assertIn("forbidden_preflight_bypass_semantics", result.deny_reasons)
        self.assertIn("requested_scope_exceeds_grant", result.deny_reasons)

    def test_validation_result_is_structured_and_execution_allowed_false(self) -> None:
        result = validate_agent_authority_grant(
            "missing",
            engine=self.engine,
            requested_scope={"allowed_action_types": ["bypass_preflight"]},
        )

        self.assertFalse(result.allowed)
        self.assertEqual(result.deny_reasons, ["grant_not_found"])
        self.assertFalse(result.execution_allowed)
        self.assertFalse(result.authority_transition)
        self.assertIn("grant_not_found", AGENT_AUTHORITY_GRANT_DENY_REASONS)

    def test_grant_binds_principal_runtime_and_exact_mandate_version(self) -> None:
        grant = self._record_grant(
            principal_id="legacy-unverified:owner@example.com",
            agent_runtime_id="runtime:research:1",
        )

        self.assertEqual(grant.principal_id, "legacy-unverified:owner@example.com")
        self.assertEqual(grant.agent_runtime_id, "runtime:research:1")
        self.assertIsNotNone(grant.mandate_version_id)
        wrong_principal = validate_agent_authority_grant(
            grant.agent_authority_grant_id,
            principal_id="principal:bob",
            agent_runtime_id="runtime:research:1",
            requested_scope=self._scope(),
            engine=self.engine,
        )
        wrong_runtime = validate_agent_authority_grant(
            grant.agent_authority_grant_id,
            principal_id="legacy-unverified:owner@example.com",
            agent_runtime_id="runtime:research:2",
            requested_scope=self._scope(),
            engine=self.engine,
        )
        self.assertIn("principal_mismatch", wrong_principal.deny_reasons)
        self.assertIn("agent_runtime_mismatch", wrong_runtime.deny_reasons)

    def test_structured_scope_is_narrower_than_mandate_and_grant(self) -> None:
        mandate_id = self._record_mandate()
        structured_scope = {
            "product_ids": ["portfolio:main"],
            "instrument_ids": ["instrument:SPY"],
            "action_types": ["rebalance"],
            "directions": ["reduce"],
            "broker_ids": ["paper:primary"],
            "max_notional": {"amount": "50", "currency": "USD"},
        }
        grant = self._record_grant(
            mandate_id=mandate_id,
            grant_scope=structured_scope,
            max_total_notional="500",
        )
        allowed = validate_agent_authority_grant(
            grant.agent_authority_grant_id,
            requested_scope={**structured_scope, "max_notional": "25"},
            engine=self.engine,
        )
        denied = validate_agent_authority_grant(
            grant.agent_authority_grant_id,
            requested_scope={**structured_scope, "directions": ["increase"]},
            engine=self.engine,
        )
        self.assertTrue(allowed.allowed)
        self.assertIn("requested_scope_exceeds_grant", denied.deny_reasons)
        with self.assertRaisesRegex(
            AgentAuthorityGrantValidationError,
            "max_total_notional exceeds",
        ):
            self._record_grant(
                grant_id="grant_over_limit",
                mandate_id=mandate_id,
                grant_scope=structured_scope,
                max_total_notional="1001",
            )

    def test_new_version_of_same_mandate_invalidates_old_grant(self) -> None:
        mandate_id = self._record_mandate()
        grant = self._record_grant(mandate_id=mandate_id)
        self._record_mandate(mandate_id=mandate_id)

        result = validate_agent_authority_grant(
            grant.agent_authority_grant_id,
            requested_scope=self._scope(),
            engine=self.engine,
        )
        self.assertIn("mandate_version_changed", result.deny_reasons)

    def test_consumption_is_nonce_unique_bounded_and_receipt_backed(self) -> None:
        principal_id = "legacy-unverified:owner@example.com"
        runtime_id = "runtime:research:1"
        grant = self._record_grant(
            principal_id=principal_id,
            agent_runtime_id=runtime_id,
            max_uses=2,
            max_total_notional="100",
        )

        first = consume_agent_authority_grant(
            grant.agent_authority_grant_id,
            principal_id=principal_id,
            agent_runtime_id=runtime_id,
            nonce="nonce-1",
            requested_scope=self._scope(),
            requested_notional="40",
            engine=self.engine,
            receipt_root=self.receipt_root,
        )
        self.assertEqual(first.usage_count, 1)
        self.assertEqual(str(first.remaining_notional), "60")
        with self.assertRaisesRegex(AgentAuthorityGrantValidationError, "nonce_replayed"):
            consume_agent_authority_grant(
                grant.agent_authority_grant_id,
                principal_id=principal_id,
                agent_runtime_id=runtime_id,
                nonce="nonce-1",
                requested_scope=self._scope(),
                requested_notional="1",
                engine=self.engine,
                receipt_root=self.receipt_root,
            )
        with self.assertRaisesRegex(
            AgentAuthorityGrantValidationError,
            "grant_notional_exhausted",
        ):
            consume_agent_authority_grant(
                grant.agent_authority_grant_id,
                principal_id=principal_id,
                agent_runtime_id=runtime_id,
                nonce="nonce-too-large",
                requested_scope=self._scope(),
                requested_notional="61",
                engine=self.engine,
                receipt_root=self.receipt_root,
            )
        consume_agent_authority_grant(
            grant.agent_authority_grant_id,
            principal_id=principal_id,
            agent_runtime_id=runtime_id,
            nonce="nonce-2",
            requested_scope=self._scope(),
            requested_notional="60",
            engine=self.engine,
            receipt_root=self.receipt_root,
        )
        with self.assertRaisesRegex(AgentAuthorityGrantValidationError, "grant_exhausted"):
            consume_agent_authority_grant(
                grant.agent_authority_grant_id,
                principal_id=principal_id,
                agent_runtime_id=runtime_id,
                nonce="nonce-3",
                requested_scope=self._scope(),
                requested_notional="0",
                engine=self.engine,
                receipt_root=self.receipt_root,
            )
        consumptions = read_all(AgentAuthorityGrantConsumption, engine=self.engine)
        self.assertEqual([item.nonce for item in consumptions], ["nonce-1", "nonce-2"])
        receipt_kinds = {item.kind for item in read_all(ReceiptIndex, engine=self.engine)}
        self.assertIn("state_core_agent_authority_grant_consumption", receipt_kinds)

    def test_cross_principal_or_runtime_cannot_consume_grant(self) -> None:
        grant = self._record_grant(
            principal_id="legacy-unverified:owner@example.com",
            agent_runtime_id="runtime:alice",
        )
        for principal_id, runtime_id, reason in (
            ("principal:bob", "runtime:alice", "principal_mismatch"),
            (
                "legacy-unverified:owner@example.com",
                "runtime:bob",
                "agent_runtime_mismatch",
            ),
        ):
            with self.assertRaisesRegex(AgentAuthorityGrantValidationError, reason):
                consume_agent_authority_grant(
                    grant.agent_authority_grant_id,
                    principal_id=principal_id,
                    agent_runtime_id=runtime_id,
                    nonce=f"nonce-{reason}",
                    requested_scope=self._scope(),
                    requested_notional="0",
                    engine=self.engine,
                    receipt_root=self.receipt_root,
                )
        self.assertEqual(read_all(AgentAuthorityGrantConsumption, engine=self.engine), [])

    def test_revoke_is_owner_only_audited_and_immediately_fail_closed(self) -> None:
        principal_id = "legacy-unverified:owner@example.com"
        grant = self._record_grant(principal_id=principal_id)
        with self.assertRaisesRegex(AgentAuthorityGrantValidationError, "principal mismatch"):
            revoke_agent_authority_grant(
                grant.agent_authority_grant_id,
                principal_id="principal:bob",
                reason="Attempt cross-owner revoke.",
                engine=self.engine,
                receipt_root=self.receipt_root,
            )
        revoked = revoke_agent_authority_grant(
            grant.agent_authority_grant_id,
            principal_id=principal_id,
            reason="Stop delegated review.",
            engine=self.engine,
            receipt_root=self.receipt_root,
        )
        self.assertEqual(revoked.status, "revoked")
        validation = validate_agent_authority_grant(
            grant.agent_authority_grant_id,
            principal_id=principal_id,
            agent_runtime_id="agent:research",
            requested_scope=self._scope(),
            engine=self.engine,
        )
        self.assertIn("grant_not_active", validation.deny_reasons)
        receipt_kinds = {item.kind for item in read_all(ReceiptIndex, engine=self.engine)}
        self.assertIn("state_core_agent_authority_grant_revoked", receipt_kinds)

    def test_consume_revalidates_lifecycle_after_acquiring_write_lock(self) -> None:
        principal_id = "legacy-unverified:owner@example.com"
        grant = self._record_grant(principal_id=principal_id)
        original_validate = validate_agent_authority_grant
        calls = 0

        def validate_then_revoke(*args, **kwargs):
            nonlocal calls
            result = original_validate(*args, **kwargs)
            calls += 1
            if calls == 1:
                revoke_agent_authority_grant(
                    grant.agent_authority_grant_id,
                    principal_id=principal_id,
                    reason="Race fixture revokes after optimistic validation.",
                    engine=self.engine,
                    receipt_root=self.receipt_root,
                )
            return result

        with patch(
            "finharness.statecore.agent_authority_grants.validate_agent_authority_grant",
            side_effect=validate_then_revoke,
        ), self.assertRaisesRegex(
            AgentAuthorityGrantValidationError,
            "denied under lock: grant_not_active",
        ):
            consume_agent_authority_grant(
                grant.agent_authority_grant_id,
                principal_id=principal_id,
                agent_runtime_id="agent:research",
                nonce="race-nonce",
                requested_scope=self._scope(),
                requested_notional="0",
                engine=self.engine,
                receipt_root=self.receipt_root,
            )
        self.assertEqual(read_all(AgentAuthorityGrantConsumption, engine=self.engine), [])

    def test_grant_receipt_records_mandate_ref_and_scope(self) -> None:
        grant = self._record_grant()

        receipt_path = Path(grant.receipt_ref or "")
        payload = json.loads(receipt_path.read_text(encoding="utf-8"))
        self.assertEqual(payload["kind"], "state_core_agent_authority_grant")
        self.assertEqual(
            payload["agent_authority_grant"]["capital_mandate_id"],
            grant.capital_mandate_id,
        )
        self.assertEqual(payload["agent_authority_grant"]["grant_scope"], self._scope())
        self.assertTrue(payload["governance_boundary"]["mandate_bound_authority_credential"])
        self.assertTrue(payload["governance_boundary"]["dynamic_validation_required"])
        self.assertFalse(payload["governance_boundary"]["execution_allowed"])
        self.assertTrue(payload["governance_boundary"]["not_preflight_bypass"])

        receipts = read_all(ReceiptIndex, engine=self.engine)
        self.assertIn("state_core_agent_authority_grant", {row.kind for row in receipts})


class AgentAuthorityGrantApiTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.receipt_root = self.root / "receipts"
        self.engine = init_state_core(self.root / "state-core.sqlite")
        self.app = create_app(
            state_core_engine=self.engine,
            receipt_root=str(self.receipt_root),
            local_operator_context=LocalOperatorContext("test_harness"),
        )
        self.client = AsgiTestClient(self.app)
        self.addCleanup(self.client.close)
        self.addCleanup(self.engine.dispose)
        self.addCleanup(self.tmp.cleanup)
        self.mandate_id = self._record_mandate()

    def _record_mandate(self) -> str:
        mandate = record_capital_mandate(
            capital_mandate_id="mandate_api",
            principal_id="legacy-local:test_harness",
            profile_snapshot={"profile": "balanced"},
            investment_objectives={"primary": "preserve_capital"},
            risk_profile={"loss_tolerance": "low"},
            allowed_asset_classes=["cash", "equity"],
            allowed_action_types=["rebalance", "raise_cash"],
            autonomy_level="L1_candidate_only",
            human_attester="owner@example.com",
            human_reason="Human owner attests this policy boundary.",
            explicit_confirmation=True,
            engine=self.engine,
            receipt_root=self.receipt_root,
        )
        return mandate.capital_mandate_id

    def _body(self) -> dict[str, object]:
        return {
            "agent_authority_grant_id": "grant_api",
            "capital_mandate_id": self.mandate_id,
            "agent_id": "agent:research",
            "agent_profile_name": "review-note",
            "grant_scope": {
                "allowed_asset_classes": ["cash"],
                "allowed_action_types": ["rebalance"],
                "autonomy_level": "L1_candidate_only",
            },
            "issued_by": "owner@example.com",
            "issued_reason": "Allow bounded mandate-scoped review.",
        }

    def test_create_get_list_validate_and_openapi(self) -> None:
        created = self.client.post("/agent-authority-grants", json=self._body())
        self.assertEqual(created.status_code, 200, created.text)
        payload = created.json()
        self.assertEqual(
            payload["agent_authority_grant"]["agent_authority_grant_id"],
            "grant_api",
        )
        self.assertFalse(payload["execution_allowed"])
        self.assertFalse(payload["authority_transition"])

        fetched = self.client.get("/agent-authority-grants/grant_api")
        self.assertEqual(fetched.status_code, 200)
        self.assertEqual(fetched.json()["agent_id"], "agent:research")

        listed = self.client.get("/agent-authority-grants?agent_id=agent:research")
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(len(listed.json()["agent_authority_grants"]), 1)

        validated = self.client.post(
            "/agent-authority-grants/grant_api/validate",
            json={
                "requested_scope": {
                    "allowed_asset_classes": ["cash"],
                    "allowed_action_types": ["rebalance"],
                    "autonomy_level": "L1_candidate_only",
                }
            },
        )
        self.assertEqual(validated.status_code, 200, validated.text)
        self.assertTrue(validated.json()["allowed"])
        self.assertFalse(validated.json()["execution_allowed"])

        openapi = self.client.get("/openapi.json")
        self.assertEqual(openapi.status_code, 200)
        self.assertIn("/agent-authority-grants", openapi.text)

    def test_validate_api_returns_structured_default_deny(self) -> None:
        response = self.client.post(
            "/agent-authority-grants/missing/validate",
            json={"requested_scope": {"allowed_action_types": ["rebalance"]}},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertFalse(payload["allowed"])
        self.assertEqual(payload["deny_reasons"], ["grant_not_found"])
        self.assertFalse(payload["execution_allowed"])

    def test_authenticated_agent_consumes_and_owner_revokes_via_api(self) -> None:
        principal = PrincipalIdentity(
            principal_id="principal:alice",
            provider_id="test",
        )
        human = OperatorContext(
            principal=principal,
            authentication_method="test_bearer",
            authenticated_at_utc=datetime.now(UTC).isoformat(),
        )
        agent = OperatorContext(
            principal=principal,
            agent_runtime=AgentRuntimeIdentity(
                agent_runtime_id="runtime:alice:research",
                principal_id=principal.principal_id,
                provider_id="test",
            ),
            authentication_method="test_bearer",
            authenticated_at_utc=datetime.now(UTC).isoformat(),
        )
        mandate = record_capital_mandate(
            capital_mandate_id="mandate_authenticated_api",
            principal_id=principal.principal_id,
            profile_snapshot={"profile": "balanced"},
            investment_objectives={"primary": "preserve_capital"},
            risk_profile={"loss_tolerance": "low"},
            allowed_asset_classes=["cash"],
            allowed_action_types=["rebalance"],
            typed_limits={
                "action_types": ["rebalance"],
                "max_notional": {"amount": "100", "currency": "USD"},
            },
            human_attester=principal.principal_id,
            human_reason="Authenticated owner mandate.",
            explicit_confirmation=True,
            engine=self.engine,
            receipt_root=self.receipt_root,
        )
        app = create_app(
            state_core_engine=self.engine,
            receipt_root=str(self.receipt_root),
            identity_provider=DeterministicIdentityProvider(
                {"human": human, "agent": agent}
            ),
        )
        client = AsgiTestClient(app)
        self.addCleanup(client.close)
        body = self._body()
        body.update(
            {
                "agent_authority_grant_id": "grant_authenticated_api",
                "capital_mandate_id": mandate.capital_mandate_id,
                "agent_runtime_id": "runtime:alice:research",
                "max_uses": 1,
                "max_total_notional": "100",
            }
        )
        created = client.post(
            "/agent-authority-grants",
            headers={"Authorization": "Bearer human"},
            json=body,
        )
        self.assertEqual(created.status_code, 200, created.text)
        consumed = client.post(
            "/agent-authority-grants/grant_authenticated_api/consume",
            headers={"Authorization": "Bearer agent"},
            json={
                "nonce": "api-nonce-1",
                "requested_scope": self._body()["grant_scope"],
                "requested_notional": "25",
            },
        )
        self.assertEqual(consumed.status_code, 200, consumed.text)
        replay = client.post(
            "/agent-authority-grants/grant_authenticated_api/consume",
            headers={"Authorization": "Bearer agent"},
            json={
                "nonce": "api-nonce-1",
                "requested_scope": self._body()["grant_scope"],
                "requested_notional": "25",
            },
        )
        self.assertEqual(replay.status_code, 409)
        revoked = client.post(
            "/agent-authority-grants/grant_authenticated_api/revoke",
            headers={"Authorization": "Bearer human"},
            json={"reason": "Stop delegated agent work."},
        )
        self.assertEqual(revoked.status_code, 200, revoked.text)
        self.assertEqual(
            revoked.json()["agent_authority_grant"]["status"],
            "revoked",
        )
