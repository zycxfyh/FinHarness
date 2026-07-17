from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from finharness.api.app import create_app
from finharness.identity import StaticIdentityProvider
from finharness.ips import record_ips
from finharness.statecore.capital_mandates import (
    CAPITAL_MANDATE_NON_CLAIMS,
    CapitalMandateValidationError,
    current_capital_mandate,
    record_capital_mandate,
)
from finharness.statecore.models import CapitalMandate, ReceiptIndex
from finharness.statecore.store import (
    StateCoreStoreError,
    init_state_core,
    read_all,
    write_records,
)
from tests.asgi_test_client import AsgiTestClient
from tests.authority_test_helpers import authority_admin_context


class CapitalMandateSliceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.receipt_root = self.root / "receipts"
        self.engine = init_state_core(self.root / "state-core.sqlite")
        self.addCleanup(self.engine.dispose)
        self.addCleanup(self.tmp.cleanup)

    def _record_ips(self) -> str:
        ips = record_ips(
            liquidity_floor_months=6,
            max_single_holding_pct="0.40",
            allowed_asset_classes=["equity", "cash"],
            engine=self.engine,
            receipt_root=self.receipt_root,
            ips_id="ips_policy_v1",
        )
        return ips.ips_id

    def _record_mandate(self, *, mandate_id: str = "mandate_v1") -> CapitalMandate:
        return record_capital_mandate(
            operator_context=authority_admin_context("owner@example.com"),
            capital_mandate_id=mandate_id,
            profile_snapshot={"profile": "balanced"},
            investment_objectives={"primary": "capital_preservation"},
            risk_profile={"max_drawdown_pct": 0.10},
            allowed_asset_classes=["cash", "equity"],
            restricted_asset_classes=["crypto_leverage"],
            allowed_action_types=["rebalance", "raise_cash"],
            restricted_action_types=["open_margin"],
            autonomy_level="L1_candidate_only",
            limit_book={"single_action_notional_cap": {"amount": 1000, "currency": "USD"}},
            kill_switch_rules=[{"rule": "drawdown_gt_10pct", "action": "freeze"}],
            review_cadence={"cadence": "quarterly"},
            human_reason="This records the policy domain for future authority design.",
            explicit_confirmation=True,
            source_refs=["docs/product-north-star.md"],
            engine=self.engine,
            receipt_root=self.receipt_root,
        )

    def test_record_capital_mandate_references_active_ips_and_receipt(self) -> None:
        ips_id = self._record_ips()
        mandate = self._record_mandate()

        self.assertEqual(mandate.source_ips_id, ips_id)
        self.assertFalse(mandate.execution_allowed)
        self.assertFalse(mandate.authority_transition)
        self.assertTrue(mandate.explicit_confirmation)
        self.assertEqual(tuple(mandate.non_claims), CAPITAL_MANDATE_NON_CLAIMS)
        self.assertTrue(mandate.receipt_ref)

        current = current_capital_mandate(self.engine)
        self.assertIsNotNone(current)
        assert current is not None
        self.assertEqual(current.capital_mandate_id, mandate.capital_mandate_id)

        receipt_path = Path(mandate.receipt_ref or "")
        payload = json.loads(receipt_path.read_text(encoding="utf-8"))
        self.assertEqual(payload["kind"], "state_core_capital_mandate")
        self.assertEqual(payload["capital_mandate"]["source_ips_id"], ips_id)
        self.assertEqual(payload["non_claims"], list(CAPITAL_MANDATE_NON_CLAIMS))
        self.assertFalse(payload["governance_boundary"]["execution_allowed"])
        self.assertFalse(payload["governance_boundary"]["authority_transition"])
        self.assertTrue(payload["governance_boundary"]["not_agent_identity_grant"])

        receipts = read_all(ReceiptIndex, engine=self.engine)
        self.assertIn("state_core_capital_mandate", {receipt.kind for receipt in receipts})

    def test_recording_new_mandate_supersedes_previous_active(self) -> None:
        first = self._record_mandate(mandate_id="mandate_first")
        second = self._record_mandate(mandate_id="mandate_second")

        current = current_capital_mandate(self.engine)
        assert current is not None
        self.assertEqual(current.capital_mandate_id, second.capital_mandate_id)

        mandates = read_all(CapitalMandate, engine=self.engine)
        status_by_id = {row.capital_mandate_id: row.status for row in mandates}
        self.assertEqual(status_by_id[first.capital_mandate_id], "superseded")
        self.assertEqual(status_by_id[second.capital_mandate_id], "active")

    def test_record_capital_mandate_derives_human_attester(self) -> None:
        mandate = self._record_mandate()
        self.assertEqual(mandate.human_attester, "owner@example.com")

    def test_record_capital_mandate_requires_human_reason(self) -> None:
        with self.assertRaises(CapitalMandateValidationError):
            record_capital_mandate(
                operator_context=authority_admin_context(),
                profile_snapshot={},
                investment_objectives={},
                risk_profile={},
                human_reason=" ",
                explicit_confirmation=True,
                engine=self.engine,
                receipt_root=self.receipt_root,
            )

    def test_record_capital_mandate_requires_explicit_confirmation(self) -> None:
        with self.assertRaises(CapitalMandateValidationError):
            record_capital_mandate(
                operator_context=authority_admin_context(),
                profile_snapshot={},
                investment_objectives={},
                risk_profile={},
                human_reason="policy",
                explicit_confirmation=False,
                engine=self.engine,
                receipt_root=self.receipt_root,
            )

    def test_model_rejects_execution_and_authority_transition(self) -> None:
        with self.assertRaises(StateCoreStoreError):
            write_records(
                [
                    CapitalMandate(
                        capital_mandate_id="bad_execution",
                        profile_snapshot={},
                        investment_objectives={},
                        risk_profile={},
                        human_attester="owner",
                        human_reason="policy",
                        explicit_confirmation=True,
                        execution_allowed=True,
                        authority_transition=False,
                    )
                ],
                engine=self.engine,
            )
        with self.assertRaises(StateCoreStoreError):
            write_records(
                [
                    CapitalMandate(
                        capital_mandate_id="bad_authority",
                        profile_snapshot={},
                        investment_objectives={},
                        risk_profile={},
                        human_attester="owner",
                        human_reason="policy",
                        explicit_confirmation=True,
                        execution_allowed=False,
                        authority_transition=True,
                    )
                ],
                engine=self.engine,
            )

    def test_missing_explicit_source_ips_fails_closed(self) -> None:
        with self.assertRaises(KeyError):
            record_capital_mandate(
                operator_context=authority_admin_context(),
                profile_snapshot={},
                investment_objectives={},
                risk_profile={},
                source_ips_id="missing_ips",
                human_reason="policy",
                explicit_confirmation=True,
                engine=self.engine,
                receipt_root=self.receipt_root,
            )


class CapitalMandateApiTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.receipt_root = self.root / "receipts"
        self.engine = init_state_core(self.root / "state-core.sqlite")
        self.app = create_app(
            state_core_engine=self.engine,
            receipt_root=str(self.receipt_root),
            identity_provider=StaticIdentityProvider(authority_admin_context()),
        )
        self.client = AsgiTestClient(self.app)
        self.addCleanup(self.client.close)
        self.addCleanup(self.engine.dispose)
        self.addCleanup(self.tmp.cleanup)

    def _body(self) -> dict[str, object]:
        return {
            "capital_mandate_id": "mandate_api",
            "profile_snapshot": {"profile": "balanced"},
            "investment_objectives": {"primary": "preserve_capital"},
            "risk_profile": {"loss_tolerance": "low"},
            "allowed_asset_classes": ["cash", "equity"],
            "allowed_action_types": ["rebalance"],
            "autonomy_level": "L1_candidate_only",
            "limit_book": {"max_notional_usd": 500},
            "kill_switch_rules": [{"rule": "owner_revokes", "action": "freeze"}],
            "review_cadence": {"cadence": "quarterly"},
            "human_reason": "Human owner attests this policy boundary.",
            "explicit_confirmation": True,
        }

    def test_current_capital_mandate_returns_unavailable_when_empty(self) -> None:
        response = self.client.get("/capital-mandates/current")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["available"], False)
        self.assertFalse(response.json()["execution_allowed"])
        self.assertFalse(response.json()["authority_transition"])

    def test_create_get_current_get_by_id_and_openapi(self) -> None:
        created = self.client.post("/capital-mandates", json=self._body())
        self.assertEqual(created.status_code, 200, created.text)
        payload = created.json()
        self.assertEqual(payload["capital_mandate"]["capital_mandate_id"], "mandate_api")
        self.assertFalse(payload["execution_allowed"])
        self.assertFalse(payload["authority_transition"])
        self.assertIn("does not authorize execution", " ".join(payload["non_claims"]))

        current = self.client.get("/capital-mandates/current")
        self.assertEqual(current.status_code, 200)
        self.assertTrue(current.json()["available"])
        self.assertEqual(
            current.json()["capital_mandate"]["capital_mandate_id"],
            "mandate_api",
        )

        fetched = self.client.get("/capital-mandates/mandate_api")
        self.assertEqual(fetched.status_code, 200)
        self.assertEqual(fetched.json()["capital_mandate_id"], "mandate_api")

        openapi = self.client.get("/openapi.json")
        self.assertEqual(openapi.status_code, 200)
        paths = set(openapi.json()["paths"])
        self.assertIn("/capital-mandates", paths)
        self.assertIn("/capital-mandates/current", paths)
        self.assertIn("/capital-mandates/{capital_mandate_id}", paths)

    def test_create_requires_explicit_confirmation(self) -> None:
        body = self._body()
        body["explicit_confirmation"] = False
        response = self.client.post("/capital-mandates", json=body)
        self.assertEqual(response.status_code, 422)
        self.assertIn("explicit_confirmation", response.text)

    def test_get_missing_capital_mandate_returns_404(self) -> None:
        response = self.client.get("/capital-mandates/missing")
        self.assertEqual(response.status_code, 404)


if __name__ == "__main__":
    unittest.main()
