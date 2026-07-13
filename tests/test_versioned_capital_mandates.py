"""AUTH-02 versioned, principal-bound CapitalMandate lifecycle tests."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from finharness.api.app import create_app
from finharness.local_operator import LocalOperatorContext
from finharness.statecore.capital_mandates import (
    CapitalMandateLimits,
    CapitalMandateValidationError,
    record_capital_mandate,
    resolve_capital_mandate,
    resume_capital_mandate,
    revoke_capital_mandate,
    suspend_capital_mandate,
)
from finharness.statecore.models import (
    CapitalMandateLifecycleEvent,
    CapitalMandateVersion,
)
from finharness.statecore.store import init_state_core, read_all
from tests.asgi_test_client import AsgiTestClient


class VersionedCapitalMandateTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.receipts = self.root / "receipts"
        self.engine = init_state_core(self.root / "state.sqlite")
        self.addCleanup(self.engine.dispose)
        self.addCleanup(self.tmp.cleanup)

    def _record(
        self,
        *,
        effective: str = "2026-07-13T00:00:00+00:00",
        expires: str | None = None,
        max_notional: str = "1000.00",
    ):
        return record_capital_mandate(
            capital_mandate_id="mandate_primary",
            principal_id="principal:alice",
            profile_snapshot={"profile": "balanced"},
            investment_objectives={"primary": "preserve"},
            risk_profile={"max_loss": "500.00"},
            allowed_asset_classes=["equity"],
            allowed_action_types=["rebalance"],
            typed_limits={
                "product_ids": ["portfolio:main"],
                "instrument_ids": ["instrument:SPY"],
                "action_types": ["rebalance"],
                "max_notional": {"amount": max_notional, "currency": "usd"},
                "max_actions_per_period": 2,
                "period_seconds": 86400,
                "max_loss": {"amount": "500", "currency": "USD"},
            },
            kill_switch_scope={
                "product_ids": ["portfolio:main"],
                "action_types": ["rebalance"],
            },
            human_attester="principal:alice",
            human_reason="Owner confirms versioned mandate policy.",
            explicit_confirmation=True,
            effective_at_utc=effective,
            expires_at_utc=expires,
            created_at_utc=effective,
            authenticated_actor_receipt_ref="identity:receipt:1",
            legacy_actor_label="alice@example.com",
            engine=self.engine,
            receipt_root=self.receipts,
        )

    def test_versions_are_immutable_hashed_and_resolved_by_principal_and_time(self) -> None:
        self._record(max_notional="1000")
        self._record(
            effective="2026-07-14T00:00:00+00:00",
            max_notional="2000",
        )
        versions = sorted(
            read_all(CapitalMandateVersion, engine=self.engine),
            key=lambda item: item.version_number,
        )
        self.assertEqual([version.version_number for version in versions], [1, 2])
        self.assertEqual(versions[1].supersedes_version_id, versions[0].mandate_version_id)
        self.assertNotEqual(versions[0].mandate_content_hash, versions[1].mandate_content_hash)
        self.assertEqual(versions[0].typed_limits["max_notional"]["amount"], "1000")
        historical = resolve_capital_mandate(
            principal_id="principal:alice",
            engine=self.engine,
            at_utc="2026-07-13T12:00:00+00:00",
        )
        current = resolve_capital_mandate(
            principal_id="principal:alice",
            engine=self.engine,
            at_utc="2026-07-14T12:00:00+00:00",
        )
        self.assertEqual(historical.version, versions[0])
        self.assertEqual(current.version, versions[1])

    def test_suspend_resume_revoke_are_immediate_append_only_and_receipt_backed(self) -> None:
        self._record()
        suspend = suspend_capital_mandate(
            "mandate_primary",
            principal_id="principal:alice",
            actor_principal_id="principal:alice",
            reason="Pause delegated work.",
            effective_at_utc="2026-07-13T01:00:00+00:00",
            engine=self.engine,
            receipt_root=self.receipts,
        )
        self.assertEqual(
            resolve_capital_mandate(
                principal_id="principal:alice",
                engine=self.engine,
                at_utc=suspend.effective_at_utc,
            ).status,
            "suspended",
        )
        resume = resume_capital_mandate(
            "mandate_primary",
            principal_id="principal:alice",
            actor_principal_id="principal:alice",
            reason="Owner reviewed limits.",
            effective_at_utc="2026-07-13T02:00:00+00:00",
            engine=self.engine,
            receipt_root=self.receipts,
        )
        self.assertEqual(
            resolve_capital_mandate(
                principal_id="principal:alice",
                engine=self.engine,
                at_utc=resume.effective_at_utc,
            ).status,
            "active",
        )
        revoke = revoke_capital_mandate(
            "mandate_primary",
            principal_id="principal:alice",
            actor_principal_id="principal:alice",
            reason="Owner permanently revokes mandate.",
            effective_at_utc="2026-07-13T03:00:00+00:00",
            engine=self.engine,
            receipt_root=self.receipts,
        )
        self.assertEqual(
            resolve_capital_mandate(
                principal_id="principal:alice",
                engine=self.engine,
                at_utc=revoke.effective_at_utc,
            ).status,
            "revoked",
        )
        events = read_all(CapitalMandateLifecycleEvent, engine=self.engine)
        self.assertEqual(
            [event.event_type for event in events], ["activated", "suspended", "resumed", "revoked"]
        )
        for event in events[1:]:
            payload = json.loads(Path(event.receipt_ref).read_text(encoding="utf-8"))
            self.assertEqual(payload["lifecycle_event"]["event_type"], event.event_type)

    def test_expiry_and_cross_principal_substitution_fail_closed(self) -> None:
        self._record(expires="2026-07-13T04:00:00+00:00")
        expired = resolve_capital_mandate(
            principal_id="principal:alice",
            engine=self.engine,
            at_utc="2026-07-13T04:00:00+00:00",
        )
        self.assertEqual(expired.status, "expired")
        self.assertEqual(expired.deny_reasons, ("mandate_expired",))
        with self.assertRaisesRegex(CapitalMandateValidationError, "substitution"):
            suspend_capital_mandate(
                "mandate_primary",
                principal_id="principal:alice",
                actor_principal_id="principal:bob",
                reason="hostile substitution",
                engine=self.engine,
                receipt_root=self.receipts,
            )
        missing = resolve_capital_mandate(
            principal_id="principal:bob",
            engine=self.engine,
            at_utc="2026-07-13T01:00:00+00:00",
        )
        self.assertEqual(missing.status, "unavailable")

    def test_typed_limits_reject_partial_frequency_and_invalid_money(self) -> None:
        with self.assertRaises(ValueError):
            CapitalMandateLimits(max_actions_per_period=2)
        with self.assertRaises(ValueError):
            CapitalMandateLimits.model_validate(
                {"max_notional": {"amount": "-1", "currency": "USD"}}
            )


class VersionedCapitalMandateApiTest(unittest.TestCase):
    def test_payload_cannot_override_principal_and_revoke_is_server_bound(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            engine = init_state_core(root / "state.sqlite")
            app = create_app(
                state_core_engine=engine,
                receipt_root=str(root / "receipts"),
                local_operator_context=LocalOperatorContext("alice"),
            )
            client = AsgiTestClient(app)
            self.addCleanup(client.close)
            self.addCleanup(engine.dispose)
            body = {
                "capital_mandate_id": "mandate_api_v2",
                "profile_snapshot": {},
                "investment_objectives": {},
                "risk_profile": {},
                "human_attester": "historical-alice-label",
                "human_reason": "Confirm server-bound mandate.",
                "explicit_confirmation": True,
                "effective_at_utc": "2026-07-13T00:00:00+00:00",
                "typed_limits": {
                    "action_types": ["rebalance"],
                    "max_notional": {"amount": "100", "currency": "USD"},
                },
            }
            hostile = dict(body, principal_id="principal:bob")
            self.assertEqual(client.post("/capital-mandates", json=hostile).status_code, 422)
            created = client.post("/capital-mandates", json=body)
            self.assertEqual(created.status_code, 200, created.text)
            current = client.get("/capital-mandates/current")
            self.assertEqual(current.status_code, 200)
            resolution = current.json()["resolution"]
            self.assertEqual(resolution["principal_id"], "legacy-local:alice")
            self.assertEqual(
                resolution["version"]["legacy_actor_label"],
                "historical-alice-label",
            )
            self.assertFalse(resolution["version"]["legacy_actor_label_verified"])
            revoked = client.post(
                "/capital-mandates/mandate_api_v2/revoke",
                json={"reason": "Owner revokes immediately."},
            )
            self.assertEqual(revoked.status_code, 200, revoked.text)
            self.assertEqual(revoked.json()["resolution"]["status"], "revoked")


if __name__ == "__main__":
    unittest.main()
