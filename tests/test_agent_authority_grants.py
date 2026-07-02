from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from sqlmodel import Session

from finharness.api.app import create_app
from finharness.statecore.agent_authority_grants import (
    AGENT_AUTHORITY_GRANT_DENY_REASONS,
    AGENT_AUTHORITY_GRANT_NON_CLAIMS,
    AgentAuthorityGrantValidationError,
    record_agent_authority_grant,
    validate_agent_authority_grant,
)
from finharness.statecore.capital_mandates import record_capital_mandate
from finharness.statecore.models import AgentAuthorityGrant, ReceiptIndex
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
            now_utc="2026-07-03T00:00:00+00:00",
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

    def test_validate_grant_denies_when_mandate_superseded_after_creation(self) -> None:
        grant = self._record_grant()
        self._record_mandate(mandate_id="mandate_replacement")

        result = validate_agent_authority_grant(
            grant.agent_authority_grant_id,
            engine=self.engine,
            requested_scope=self._scope(),
        )

        self.assertFalse(result.allowed)
        self.assertIn("capital_mandate_not_active", result.deny_reasons)

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
        )
        self.client = AsgiTestClient(self.app)
        self.addCleanup(self.client.close)
        self.addCleanup(self.engine.dispose)
        self.addCleanup(self.tmp.cleanup)
        self.mandate_id = self._record_mandate()

    def _record_mandate(self) -> str:
        mandate = record_capital_mandate(
            capital_mandate_id="mandate_api",
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
