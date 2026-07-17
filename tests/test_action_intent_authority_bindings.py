from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from sqlmodel import Session

from finharness.api.app import create_app
from finharness.local_operator import LocalOperatorContext
from finharness.statecore.action_intent_authority_bindings import (
    ACTION_INTENT_AUTHORITY_BINDING_NON_CLAIMS,
    create_action_intent_authority_binding,
    latest_action_intent_authority_binding,
)
from finharness.statecore.action_intents import create_governed_action_intent
from finharness.statecore.agent_authority_grants import record_agent_authority_grant
from finharness.statecore.capital_mandates import record_capital_mandate
from finharness.statecore.models import (
    ActionIntentAuthorityBinding,
    AgentAuthorityGrant,
    ReceiptIndex,
)
from finharness.statecore.proposals import create_governed_proposal
from finharness.statecore.store import init_state_core, read_all
from tests._scaffold import VALID_SCAFFOLD
from tests.asgi_test_client import AsgiTestClient
from tests.authority_test_helpers import authority_admin_context


class ActionIntentAuthorityBindingTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.receipt_root = self.root / "receipts" / "state-core"
        self.engine = init_state_core(self.root / "state-core.sqlite")
        self.app = create_app(
            state_core_engine=self.engine,
            receipt_root=str(self.receipt_root),
            local_operator_context=LocalOperatorContext("test_harness"),
        )
        self.client = AsgiTestClient(self.app)
        self.proposal_write = create_governed_proposal(
            kind="rebalance_review",
            claim="Review whether a capital action should be considered.",
            evidence={"snapshot_id": "snap_after"},
            assumptions={"human_review": "required"},
            limitations={"execution": "none"},
            source_refs=["context://proposal"],
            decision_scaffold=VALID_SCAFFOLD,
            engine=self.engine,
            receipt_root=self.receipt_root,
            proposal_id="prop_authority_binding",
        )
        self.addCleanup(self.client.close)
        self.addCleanup(self.engine.dispose)
        self.addCleanup(self.tmp.cleanup)

    def _record_mandate(self, *, mandate_id: str = "mandate_binding") -> str:
        mandate = record_capital_mandate(
            operator_context=authority_admin_context("owner@example.com"),
            capital_mandate_id=mandate_id,
            profile_snapshot={"profile": "balanced"},
            investment_objectives={"primary": "risk_control"},
            risk_profile={"max_drawdown_pct": 0.10},
            allowed_asset_classes=["cash", "equity"],
            restricted_asset_classes=["crypto_leverage"],
            allowed_action_types=["rebalance", "raise_cash"],
            restricted_action_types=["open_margin"],
            autonomy_level="L1_candidate_only",
            typed_limits={
                "max_notional": {"amount": "1000", "currency": "USD"},
            },
            human_reason="Attest mandate scope for authority binding tests.",
            explicit_confirmation=True,
            engine=self.engine,
            receipt_root=self.receipt_root,
        )
        return mandate.capital_mandate_id

    def _scope(self, *, action: str = "rebalance") -> dict[str, object]:
        return {
            "allowed_asset_classes": ["cash"],
            "allowed_action_types": [action],
            "autonomy_level": "L1_candidate_only",
        }

    def _record_grant(
        self,
        *,
        grant_id: str = "grant_binding",
        mandate_id: str | None = None,
        agent_id: str = "agent:research",
        grant_scope: dict[str, object] | None = None,
    ) -> AgentAuthorityGrant:
        return record_agent_authority_grant(
            operator_context=authority_admin_context("owner@example.com"),
            agent_authority_grant_id=grant_id,
            capital_mandate_id=mandate_id or self._record_mandate(),
            agent_id=agent_id,
            agent_profile_name="review-note",
            grant_scope=grant_scope or self._scope(),
            issued_reason="Allow the agent to prepare candidate-only capital intents.",
            source_refs=["docs/product-north-star.md"],
            engine=self.engine,
            receipt_root=self.receipt_root,
        )

    def _create_intent(
        self,
        *,
        created_by: str = "agent",
        action_type: str = "rebalance",
    ):
        return create_governed_action_intent(
            proposal_id=self.proposal_write.proposal.proposal_id,
            expected_proposal_receipt_ref=self.proposal_write.receipt_ref,
            action_type=action_type,  # type: ignore[arg-type]
            intent_summary="Consider a candidate-only rebalance.",
            rationale="Reviewed proposal indicates a rebalance should be considered.",
            target_scope={
                "scope_type": "portfolio",
                "asset_class": "cash",
            },
            constraints={"execution_mode": "none"},
            trigger_context={"source": "authority_binding_test"},
            required_preconditions=["authority_binding", "action_preflight"],
            expected_next_step="action_preflight",
            created_by=created_by,  # type: ignore[arg-type]
            active_profile="review-note" if created_by == "agent" else None,
            source_refs=["context://reviewed_proposal"],
            engine=self.engine,
            receipt_root=self.receipt_root,
        ).action_intent

    def _bind(
        self,
        action_intent_id: str,
        *,
        author_type: str = "agent",
        author_id: str = "agent:research",
        grant_id: str | None = None,
        requested_scope: dict[str, object] | None = None,
        source_rule_ref: str | None = None,
    ):
        return create_action_intent_authority_binding(
            action_intent_id=action_intent_id,
            author_type=author_type,  # type: ignore[arg-type]
            author_id=author_id,
            agent_authority_grant_id=grant_id,
            requested_scope=requested_scope or self._scope(),
            source_rule_ref=source_rule_ref,
            source_refs=["context://authority_binding"],
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

    def test_agent_authored_action_intent_requires_grant(self) -> None:
        intent = self._create_intent(created_by="agent")

        write = self._bind(intent.action_intent_id, grant_id=None)

        self.assertFalse(write.result.allowed)
        self.assertIn("agent_intent_missing_grant", write.result.deny_reasons)
        self.assertIn("binding_result_denied", write.result.deny_reasons)
        self.assertFalse(write.binding.allowed)
        self.assertFalse(write.binding.execution_allowed)
        self.assertFalse(write.binding.authority_transition)
        self.assertEqual(
            read_all(ActionIntentAuthorityBinding, engine=self.engine),
            [write.binding],
        )

    def test_authority_binding_allows_active_agent_grant_under_active_mandate(self) -> None:
        intent = self._create_intent(created_by="agent")
        grant = self._record_grant()

        write = self._bind(intent.action_intent_id, grant_id=grant.agent_authority_grant_id)

        self.assertTrue(write.result.allowed)
        self.assertEqual(write.result.deny_reasons, [])
        self.assertEqual(write.result.capital_mandate_id, grant.capital_mandate_id)
        self.assertEqual(write.binding.agent_authority_grant_id, grant.agent_authority_grant_id)
        self.assertEqual(write.binding.capital_mandate_id, grant.capital_mandate_id)
        self.assertEqual(write.binding.source_action_intent_receipt_ref, intent.receipt_ref)
        self.assertIn(intent.receipt_ref, write.binding.receipt_refs)
        self.assertIn(grant.receipt_ref, write.binding.receipt_refs)
        self.assertEqual(
            tuple(write.binding.non_claims),
            ACTION_INTENT_AUTHORITY_BINDING_NON_CLAIMS,
        )
        self.assertFalse(write.result.execution_allowed)
        self.assertFalse(write.result.authority_transition)

    def test_authority_binding_validates_grant_at_use_time(self) -> None:
        intent = self._create_intent(created_by="agent")
        grant = self._record_grant()
        self._set_grant_status(grant.agent_authority_grant_id, "revoked")

        write = self._bind(intent.action_intent_id, grant_id=grant.agent_authority_grant_id)

        self.assertFalse(write.result.allowed)
        self.assertIn("grant_not_active", write.result.deny_reasons)
        self.assertIn("grant_not_active", write.binding.grant_deny_reasons)

    def test_authority_binding_persists_denial_for_missing_grant(self) -> None:
        intent = self._create_intent(created_by="agent")

        write = self._bind(intent.action_intent_id, grant_id="missing_grant")

        self.assertFalse(write.result.allowed)
        self.assertIn("agent_grant_not_found", write.result.deny_reasons)
        self.assertEqual(write.result.agent_authority_grant_id, "missing_grant")
        self.assertIsNone(write.binding.agent_authority_grant_id)
        self.assertEqual(
            read_all(ActionIntentAuthorityBinding, engine=self.engine),
            [write.binding],
        )

    def test_authority_binding_denies_when_current_mandate_version_changes(self) -> None:
        intent = self._create_intent(created_by="agent")
        grant = self._record_grant()
        self._record_mandate(mandate_id="mandate_replacement")

        write = self._bind(intent.action_intent_id, grant_id=grant.agent_authority_grant_id)

        self.assertFalse(write.result.allowed)
        self.assertIn("mandate_version_changed", write.result.deny_reasons)
        self.assertEqual(
            write.result.source["grant_validation"],
            ["mandate_version_changed"],
        )

    def test_authority_binding_preserves_grant_deny_reasons(self) -> None:
        intent = self._create_intent(created_by="agent")
        grant = self._record_grant()

        write = self._bind(
            intent.action_intent_id,
            grant_id=grant.agent_authority_grant_id,
            requested_scope=self._scope(action="raise_cash"),
        )

        self.assertFalse(write.result.allowed)
        self.assertIn("requested_scope_exceeds_grant", write.result.deny_reasons)
        self.assertEqual(
            write.result.source["grant_validation"],
            ["requested_scope_exceeds_grant"],
        )
        self.assertIn("binding_result_denied", write.result.deny_reasons)

    def test_authority_binding_denies_grant_agent_mismatch(self) -> None:
        intent = self._create_intent(created_by="agent")
        grant = self._record_grant(agent_id="agent:other")

        write = self._bind(intent.action_intent_id, grant_id=grant.agent_authority_grant_id)

        self.assertFalse(write.result.allowed)
        self.assertIn("grant_agent_mismatch", write.result.deny_reasons)
        self.assertEqual(write.result.source["binding"], ["grant_agent_mismatch"])

    def test_human_authored_action_intent_may_omit_grant(self) -> None:
        intent = self._create_intent(created_by="human")

        write = self._bind(
            intent.action_intent_id,
            author_type="human",
            author_id="owner@example.com",
            grant_id=None,
        )

        self.assertTrue(write.result.allowed)
        self.assertEqual(write.result.deny_reasons, [])
        self.assertIn("non_agent_binding_has_no_grant_validation", write.result.warnings)
        self.assertIsNone(write.binding.agent_authority_grant_id)
        self.assertFalse(write.binding.execution_allowed)

    def test_human_authored_action_intent_rejects_unexpected_grant(self) -> None:
        intent = self._create_intent(created_by="human")
        grant = self._record_grant()

        write = self._bind(
            intent.action_intent_id,
            author_type="human",
            author_id="owner@example.com",
            grant_id=grant.agent_authority_grant_id,
        )

        self.assertFalse(write.result.allowed)
        self.assertIn("human_intent_unexpected_grant", write.result.deny_reasons)

    def test_system_authored_action_intent_records_source_rule(self) -> None:
        intent = self._create_intent(created_by="system")

        denied = self._bind(
            intent.action_intent_id,
            author_type="system",
            author_id="system:policy",
            requested_scope=self._scope(),
        )
        allowed = self._bind(
            intent.action_intent_id,
            author_type="system",
            author_id="system:policy",
            requested_scope=self._scope(),
            source_rule_ref="policy://capital-action-admission/system-rule",
        )

        self.assertFalse(denied.result.allowed)
        self.assertIn("system_intent_missing_source_rule", denied.result.deny_reasons)
        self.assertTrue(allowed.result.allowed)
        self.assertEqual(
            allowed.binding.source_rule_ref,
            "policy://capital-action-admission/system-rule",
        )

    def test_authority_binding_denies_author_type_mismatch(self) -> None:
        intent = self._create_intent(created_by="human")
        grant = self._record_grant()

        write = self._bind(
            intent.action_intent_id,
            author_type="agent",
            author_id="agent:research",
            grant_id=grant.agent_authority_grant_id,
        )

        self.assertFalse(write.result.allowed)
        self.assertIn("action_intent_author_type_mismatch", write.result.deny_reasons)

    def test_authority_binding_receipt_links_action_intent_grant_and_mandate(self) -> None:
        intent = self._create_intent(created_by="agent")
        grant = self._record_grant()

        write = self._bind(intent.action_intent_id, grant_id=grant.agent_authority_grant_id)

        receipt_payload = json.loads(Path(write.receipt_ref).read_text(encoding="utf-8"))
        self.assertEqual(receipt_payload["kind"], "state_core_action_intent_authority_binding")
        self.assertEqual(receipt_payload["action_intent_id"], intent.action_intent_id)
        self.assertTrue(receipt_payload["binding_result"]["allowed"])
        self.assertTrue(receipt_payload["governance_boundary"]["authority_admission_only"])
        self.assertTrue(receipt_payload["governance_boundary"]["not_action_preflight"])
        self.assertFalse(receipt_payload["governance_boundary"]["execution_allowed"])
        self.assertFalse(receipt_payload["governance_boundary"]["authority_transition"])

        receipts = read_all(ReceiptIndex, engine=self.engine)
        receipt_index = next(
            row
            for row in receipts
            if row.kind == "state_core_action_intent_authority_binding"
        )
        self.assertIn(intent.action_intent_id, receipt_index.refs)
        self.assertIn(grant.agent_authority_grant_id, receipt_index.refs)
        self.assertIn(grant.capital_mandate_id, receipt_index.refs)

    def test_latest_binding_can_be_read_without_revalidating_grant_semantics(self) -> None:
        intent = self._create_intent(created_by="agent")
        grant = self._record_grant()
        write = self._bind(intent.action_intent_id, grant_id=grant.agent_authority_grant_id)

        latest = latest_action_intent_authority_binding(
            intent.action_intent_id,
            engine=self.engine,
        )

        assert latest is not None
        self.assertEqual(latest.binding_id, write.binding.binding_id)
        self.assertTrue(latest.allowed)
        self.assertEqual(latest.deny_reasons, [])
        self.assertEqual(latest.receipt_ref, write.receipt_ref)

    def test_authority_binding_api_create_fetch_and_openapi(self) -> None:
        intent = self._create_intent(created_by="agent")
        grant = self._record_grant()

        response = self.client.post(
            f"/action-intents/{intent.action_intent_id}/authority-bindings",
            json={
                "author_type": "agent",
                "author_id": "agent:research",
                "agent_authority_grant_id": grant.agent_authority_grant_id,
                "requested_scope": self._scope(),
                "source_refs": ["context://api-binding"],
            },
        )

        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertTrue(body["binding_result"]["allowed"])
        self.assertFalse(body["execution_allowed"])
        self.assertFalse(body["authority_transition"])
        binding_id = body["authority_binding"]["binding_id"]

        fetched = self.client.get(f"/action-intent-authority-bindings/{binding_id}")
        self.assertEqual(fetched.status_code, 200, fetched.text)
        self.assertEqual(fetched.json()["authority_binding"]["receipt_ref"], body["receipt_ref"])
        self.assertFalse(fetched.json()["execution_allowed"])

        missing = self.client.post(
            "/action-intents/missing/authority-bindings",
            json={
                "author_type": "agent",
                "author_id": "agent:research",
                "agent_authority_grant_id": grant.agent_authority_grant_id,
                "requested_scope": self._scope(),
            },
        )
        self.assertEqual(missing.status_code, 404)

        openapi = self.client.get("/openapi.json").json()
        self.assertIn(
            "/action-intents/{action_intent_id}/authority-bindings",
            openapi["paths"],
        )
        self.assertIn(
            "/action-intent-authority-bindings/{binding_id}",
            openapi["paths"],
        )
        self.assertIn("ActionIntentAuthorityBinding", openapi["components"]["schemas"])
        self.assertIn(
            "ActionIntentAuthorityBindingResult",
            openapi["components"]["schemas"],
        )
