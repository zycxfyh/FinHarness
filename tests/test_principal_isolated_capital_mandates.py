"""ASSURE-AUTH-02 principal-isolated CapitalMandate executable contract."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import Engine

from finharness.agent_autonomy_adapter import resolve_runtime_autonomy_mandate
from finharness.api.app import create_app
from finharness.identity import OperatorContext, TestIdentityProvider
from finharness.statecore.agent_authority_grants import (
    record_agent_authority_grant,
    validate_agent_authority_grant,
)
from finharness.statecore.capital_mandates import (
    CAPITAL_MANDATE_LIFECYCLE_ORDER,
    CAPITAL_MANDATE_RESOLUTION_ORDER,
    CapitalMandateValidationError,
    current_capital_mandate,
    record_capital_mandate,
    resolve_capital_mandate,
    resume_capital_mandate,
    revoke_capital_mandate,
    suspend_capital_mandate,
)
from finharness.statecore.models import (
    AgentAuthorityGrant,
    CapitalMandate,
    CapitalMandateLifecycleEvent,
    CapitalMandateVersion,
    ReceiptIndex,
)
from finharness.statecore.store import init_state_core, read_all, upsert_records, write_records
from tests.asgi_test_client import AsgiTestClient
from tests.authority_test_helpers import authority_admin_context

ALICE = "principal:alice"
BOB = "principal:bob"
BASE_TIME = "2026-01-10T00:00:00+00:00"
GRANT_TIME = "2026-01-10T12:00:00+00:00"
LATER_TIME = "2026-01-11T00:00:00+00:00"
VALIDATION_TIME = "2026-01-12T00:00:00+00:00"
ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "docs" / "governance" / "receipt-backed-write-registry.json"

EXPECTED_PRINCIPAL_CONTRACT = {
    "schema": "finharness.capital_mandate_principal_contract.v1",
    "http_principal": "OperatorContext.principal.principal_id",
    "durable_series_owner": "CapitalMandateVersion.principal_id",
    "current_truth": "resolve_capital_mandate(principal_id, at_utc)",
    "compatibility_mirror": "CapitalMandate.status is non-authoritative",
    "series_owner_transition": "forbidden",
    "historical_owner_conflict_policy": (
        "resolver, grant creation and validation, and lifecycle commands fail closed"
    ),
    "ownership_conflict_timing": (
        "before receipt, version, lifecycle event, ReceiptIndex, or mirror mutation"
    ),
    "resolution_total_order_desc": [
        "effective_at_utc",
        "created_at_utc",
        "version_number",
        "capital_mandate_id",
        "mandate_version_id",
    ],
    "lifecycle_total_order_desc": [
        "effective_at_utc",
        "created_at_utc",
        "mandate_lifecycle_event_id",
    ],
    "lifecycle_authority": ("principal == version owner == event principal == actor principal"),
    "grant_currentness": "principal-bound exact mandate_version_id equality",
    "legacy_owner_policy": (
        "unowned rows remain readable but unverified labels cannot claim ownership"
    ),
    "non_claims": [
        "Authentication identity is not capital authority.",
        "An active CapitalMandate is not execution authorization.",
        "A valid AgentAuthorityGrant is not approval or broker submission.",
    ],
}


def _context(principal_id: str) -> OperatorContext:
    return authority_admin_context(principal_id, provider_id="test-provider")


def _inject_preexisting_shared_id_owner_conflict(*, engine: Engine) -> None:
    alice_version = next(
        version
        for version in read_all(CapitalMandateVersion, engine=engine)
        if version.capital_mandate_id == "shared-id" and version.principal_id == ALICE
    )
    alice_activation = next(
        event
        for event in read_all(CapitalMandateLifecycleEvent, engine=engine)
        if event.mandate_version_id == alice_version.mandate_version_id
    )
    bob_version = CapitalMandateVersion(
        **{
            **alice_version.model_dump(),
            "mandate_version_id": "shared-id:v1:legacy-bob",
            "principal_id": BOB,
            "mandate_content_hash": "legacy-bob-content-hash",
            "receipt_ref": "legacy:receipt:bob-version",
        }
    )
    bob_activation = CapitalMandateLifecycleEvent(
        **{
            **alice_activation.model_dump(),
            "mandate_lifecycle_event_id": "mandate-event-legacy-bob-activation",
            "mandate_version_id": bob_version.mandate_version_id,
            "principal_id": BOB,
            "authenticated_actor_principal_id": BOB,
            "receipt_ref": "legacy:receipt:bob-activation",
        }
    )
    write_records([bob_version, bob_activation], engine=engine)


class PrincipalIsolatedCapitalMandateTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.database = self.root / "state.sqlite"
        self.receipts = self.root / "receipts"
        self.engine = init_state_core(self.database)
        self.addCleanup(self.tmp.cleanup)
        self.addCleanup(self._dispose_engine)

    def _dispose_engine(self) -> None:
        self.engine.dispose()

    def _record(
        self,
        mandate_id: str,
        principal_id: str,
        *,
        effective_at: str = BASE_TIME,
        created_at: str | None = None,
        expires_at: str | None = None,
        max_notional: str = "1000",
    ) -> CapitalMandate:
        return record_capital_mandate(
            operator_context=_context(principal_id),
            capital_mandate_id=mandate_id,
            profile_snapshot={"profile": "balanced"},
            investment_objectives={"primary": "preserve"},
            risk_profile={"max_loss": "500"},
            allowed_asset_classes=["cash", "equity"],
            allowed_action_types=["rebalance"],
            typed_limits={
                "product_ids": ["portfolio:main"],
                "instrument_ids": ["instrument:SPY"],
                "action_types": ["rebalance"],
                "max_notional": {"amount": max_notional, "currency": "USD"},
            },
            human_reason="Principal confirms the bounded policy.",
            explicit_confirmation=True,
            effective_at_utc=effective_at,
            expires_at_utc=expires_at,
            created_at_utc=created_at or effective_at,
            engine=self.engine,
            receipt_root=self.receipts,
        )

    def _grant(
        self,
        mandate_id: str,
        principal_id: str = ALICE,
    ) -> AgentAuthorityGrant:
        return record_agent_authority_grant(
            operator_context=_context(principal_id),
            capital_mandate_id=mandate_id,
            agent_id="agent:research",
            agent_runtime_id="runtime:research",
            issued_reason="Bounded research authority.",
            grant_scope={
                "allowed_asset_classes": ["cash"],
                "allowed_action_types": ["rebalance"],
                "autonomy_level": "L1_candidate_only",
            },
            created_at_utc=GRANT_TIME,
            engine=self.engine,
            receipt_root=self.receipts,
        )

    def _validate(self, grant: AgentAuthorityGrant, *, now: str = VALIDATION_TIME):
        return validate_agent_authority_grant(
            grant.agent_authority_grant_id,
            principal_id=grant.principal_id,
            agent_runtime_id=grant.agent_runtime_id,
            requested_scope=grant.grant_scope,
            now_utc=now,
            engine=self.engine,
        )

    def _side_effect_counts(self) -> tuple[int, int, int, int, int]:
        return (
            len(read_all(CapitalMandate, engine=self.engine)),
            len(read_all(CapitalMandateVersion, engine=self.engine)),
            len(read_all(CapitalMandateLifecycleEvent, engine=self.engine)),
            len(read_all(ReceiptIndex, engine=self.engine)),
            len(list(self.receipts.rglob("*.json"))) if self.receipts.exists() else 0,
        )

    def _inject_preexisting_shared_id_owner_conflict(self) -> None:
        _inject_preexisting_shared_id_owner_conflict(engine=self.engine)

    def test_machine_contract_and_canonical_order_are_exact(self) -> None:
        registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
        self.assertEqual(
            registry["capital_mandate_principal_contract"],
            EXPECTED_PRINCIPAL_CONTRACT,
        )
        self.assertEqual(
            CAPITAL_MANDATE_RESOLUTION_ORDER,
            tuple(EXPECTED_PRINCIPAL_CONTRACT["resolution_total_order_desc"]),
        )
        self.assertEqual(
            CAPITAL_MANDATE_LIFECYCLE_ORDER,
            tuple(EXPECTED_PRINCIPAL_CONTRACT["lifecycle_total_order_desc"]),
        )

    def test_bob_creation_cannot_supersede_alice_or_invalidate_grant(self) -> None:
        alice = self._record("mandate-alice", ALICE)
        grant = self._grant(alice.capital_mandate_id)
        bob = self._record("mandate-bob", BOB)

        rows = {
            row.capital_mandate_id: row.status
            for row in read_all(CapitalMandate, engine=self.engine)
        }
        alice_resolution = resolve_capital_mandate(
            principal_id=ALICE,
            at_utc=VALIDATION_TIME,
            engine=self.engine,
        )
        bob_resolution = resolve_capital_mandate(
            principal_id=BOB,
            at_utc=VALIDATION_TIME,
            engine=self.engine,
        )
        validation = self._validate(grant)
        runtime = resolve_runtime_autonomy_mandate(
            grant.agent_authority_grant_id,
            engine=self.engine,
            now_utc=VALIDATION_TIME,
        )

        self.assertEqual(
            rows, {alice.capital_mandate_id: "active", bob.capital_mandate_id: "active"}
        )
        self.assertEqual(alice_resolution.version.capital_mandate_id, alice.capital_mandate_id)
        self.assertEqual(alice_resolution.version.principal_id, ALICE)
        self.assertEqual(bob_resolution.version.capital_mandate_id, bob.capital_mandate_id)
        self.assertEqual(bob_resolution.version.principal_id, BOB)
        self.assertTrue(validation.allowed, validation.deny_reasons)
        self.assertNotIn("capital_mandate_not_active", validation.deny_reasons)
        self.assertNotIn("mandate_version_changed", validation.deny_reasons)
        self.assertTrue(runtime.resolved, runtime.deny_reasons)
        self.assertEqual(runtime.mandate.principal_id, ALICE)
        self.assertEqual(runtime.mandate.mandate_id, alice.capital_mandate_id)
        for row in (
            *read_all(CapitalMandate, engine=self.engine),
            *read_all(CapitalMandateVersion, engine=self.engine),
            *read_all(CapitalMandateLifecycleEvent, engine=self.engine),
            grant,
        ):
            self.assertFalse(row.execution_allowed)
            self.assertFalse(getattr(row, "authority_transition", False))

    def test_compatibility_row_status_cannot_override_version_truth(self) -> None:
        mandate = self._record("mandate-alice", ALICE)
        grant = self._grant(mandate.capital_mandate_id)
        mirror = read_all(CapitalMandate, engine=self.engine)[0]
        mirror.status = "superseded"
        upsert_records([mirror], engine=self.engine)

        resolution = resolve_capital_mandate(
            principal_id=ALICE,
            at_utc=VALIDATION_TIME,
            engine=self.engine,
        )
        validation = self._validate(grant)
        self.assertEqual(resolution.status, "active")
        self.assertTrue(validation.allowed, validation.deny_reasons)

    def test_shared_id_takeover_fails_before_any_domain_or_receipt_mutation(self) -> None:
        self._record("shared-id", ALICE)
        before = self._side_effect_counts()

        with self.assertRaisesRegex(CapitalMandateValidationError, "owned by another principal"):
            self._record("shared-id", BOB)

        self.assertEqual(self._side_effect_counts(), before)
        versions = read_all(CapitalMandateVersion, engine=self.engine)
        self.assertEqual({version.principal_id for version in versions}, {ALICE})
        mirror = read_all(CapitalMandate, engine=self.engine)[0]
        self.assertEqual(mirror.human_attester, ALICE)

    def test_preexisting_shared_id_multi_owner_fails_resolution_closed(self) -> None:
        self._record(
            "mandate-safe",
            ALICE,
            effective_at="2026-01-01T00:00:00+00:00",
            created_at="2026-01-01T00:00:00+00:00",
        )
        self._record("shared-id", ALICE)
        self._inject_preexisting_shared_id_owner_conflict()

        for principal_id in (ALICE, BOB):
            with self.subTest(principal_id=principal_id):
                resolution = resolve_capital_mandate(
                    principal_id=principal_id,
                    at_utc=VALIDATION_TIME,
                    engine=self.engine,
                )
                self.assertEqual(resolution.status, "invalid")
                self.assertIsNone(resolution.version)
                self.assertEqual(
                    resolution.deny_reasons,
                    ("mandate_series_owner_conflict",),
                )

    def test_preexisting_shared_id_multi_owner_invalidates_existing_grant(self) -> None:
        self._record("shared-id", ALICE)
        grant = self._grant("shared-id")
        self._inject_preexisting_shared_id_owner_conflict()

        validation = self._validate(grant)

        self.assertFalse(validation.allowed)
        self.assertEqual(validation.deny_reasons, ["mandate_series_owner_conflict"])

    def test_preexisting_shared_id_multi_owner_rejects_lifecycle_without_side_effects(
        self,
    ) -> None:
        self._record("shared-id", ALICE)
        self._inject_preexisting_shared_id_owner_conflict()
        mirror_before = [row.model_dump() for row in read_all(CapitalMandate, engine=self.engine)]
        before = self._side_effect_counts()
        commands = {
            "suspend": suspend_capital_mandate,
            "resume": resume_capital_mandate,
            "revoke": revoke_capital_mandate,
        }

        for principal_id in (ALICE, BOB):
            for command_name, command in commands.items():
                with self.subTest(principal_id=principal_id, command=command_name):
                    command_kwargs = (
                        {"effective_at_utc": LATER_TIME} if command_name == "resume" else {}
                    )
                    with self.assertRaisesRegex(
                        CapitalMandateValidationError,
                        "mandate_series_owner_conflict",
                    ):
                        command(
                            "shared-id",
                            operator_context=_context(principal_id),
                            reason="Historical owner conflict must fail closed.",
                            engine=self.engine,
                            receipt_root=self.receipts,
                            **command_kwargs,
                        )
                    self.assertEqual(self._side_effect_counts(), before)
                    self.assertEqual(
                        [row.model_dump() for row in read_all(CapitalMandate, engine=self.engine)],
                        mirror_before,
                    )

    def test_owner_conflict_remains_failed_after_restart(self) -> None:
        self._record("shared-id", ALICE)
        self._inject_preexisting_shared_id_owner_conflict()
        self.engine.dispose()
        self.engine = init_state_core(self.database)

        for principal_id in (ALICE, BOB):
            resolution = resolve_capital_mandate(
                principal_id=principal_id,
                at_utc=VALIDATION_TIME,
                engine=self.engine,
            )
            self.assertEqual(resolution.status, "invalid")
            self.assertIsNone(resolution.version)
            self.assertEqual(
                resolution.deny_reasons,
                ("mandate_series_owner_conflict",),
            )

    def test_unrelated_mandate_creation_preflights_historical_owner_conflict(self) -> None:
        self._record("shared-id", ALICE)
        self._inject_preexisting_shared_id_owner_conflict()
        before = self._side_effect_counts()
        mirror_before = [row.model_dump() for row in read_all(CapitalMandate, engine=self.engine)]

        with self.assertRaisesRegex(
            CapitalMandateValidationError,
            "multiple durable principal owners",
        ):
            self._record("mandate-clean", ALICE)

        self.assertEqual(self._side_effect_counts(), before)
        self.assertEqual(
            [row.model_dump() for row in read_all(CapitalMandate, engine=self.engine)],
            mirror_before,
        )

    def test_resolution_total_order_is_insertion_and_restart_independent(self) -> None:
        def resolve_for(order: tuple[str, str]) -> tuple[str, str]:
            with tempfile.TemporaryDirectory() as tmp:
                database = Path(tmp) / "state.sqlite"
                receipts = Path(tmp) / "receipts"
                engine = init_state_core(database)
                try:
                    for mandate_id in order:
                        record_capital_mandate(
                            operator_context=_context(ALICE),
                            capital_mandate_id=mandate_id,
                            profile_snapshot={},
                            investment_objectives={},
                            risk_profile={},
                            human_reason="Deterministic tie fixture.",
                            explicit_confirmation=True,
                            effective_at_utc=BASE_TIME,
                            created_at_utc=BASE_TIME,
                            engine=engine,
                            receipt_root=receipts,
                        )
                    first = resolve_capital_mandate(
                        principal_id=ALICE,
                        at_utc=VALIDATION_TIME,
                        engine=engine,
                    )
                    repeated = resolve_capital_mandate(
                        principal_id=ALICE,
                        at_utc=VALIDATION_TIME,
                        engine=engine,
                    )
                    self.assertEqual(
                        first.version.mandate_version_id, repeated.version.mandate_version_id
                    )
                finally:
                    engine.dispose()
                restarted = init_state_core(database)
                try:
                    replay = resolve_capital_mandate(
                        principal_id=ALICE,
                        at_utc=VALIDATION_TIME,
                        engine=restarted,
                    )
                    return replay.version.capital_mandate_id, replay.version.mandate_version_id
                finally:
                    restarted.dispose()

        forward = resolve_for(("mandate-alpha", "mandate-zeta"))
        reverse = resolve_for(("mandate-zeta", "mandate-alpha"))
        self.assertEqual(forward, reverse)
        self.assertEqual(forward[0], "mandate-zeta")

    def test_created_time_and_version_number_refine_equal_effective_time(self) -> None:
        self._record(
            "mandate-alpha",
            ALICE,
            effective_at=BASE_TIME,
            created_at=LATER_TIME,
        )
        self._record(
            "mandate-zeta",
            ALICE,
            effective_at=BASE_TIME,
            created_at=BASE_TIME,
        )
        created_winner = resolve_capital_mandate(
            principal_id=ALICE,
            at_utc=VALIDATION_TIME,
            engine=self.engine,
        )
        self.assertEqual(created_winner.version.capital_mandate_id, "mandate-alpha")

        self._record(
            "mandate-alpha",
            ALICE,
            effective_at=BASE_TIME,
            created_at=LATER_TIME,
            max_notional="900",
        )
        version_winner = resolve_capital_mandate(
            principal_id=ALICE,
            at_utc=VALIDATION_TIME,
            engine=self.engine,
        )
        self.assertEqual(version_winner.version.capital_mandate_id, "mandate-alpha")
        self.assertEqual(version_winner.version.version_number, 2)

    def test_same_time_lifecycle_events_have_stable_recorded_order(self) -> None:
        self._record("mandate-alice", ALICE)
        with patch(
            "finharness.statecore.capital_mandates._now_utc",
            return_value=LATER_TIME,
        ):
            suspend_capital_mandate(
                "mandate-alice",
                operator_context=authority_admin_context(ALICE, assurance="standard"),
                reason="Pause.",
                engine=self.engine,
                receipt_root=self.receipts,
            )
        resume_capital_mandate(
            "mandate-alice",
            operator_context=_context(ALICE),
            reason="Resume at the same domain time.",
            effective_at_utc=LATER_TIME,
            engine=self.engine,
            receipt_root=self.receipts,
        )
        before = resolve_capital_mandate(
            principal_id=ALICE,
            at_utc=LATER_TIME,
            engine=self.engine,
        )
        self.assertEqual(before.status, "active")
        self.engine.dispose()
        self.engine = init_state_core(self.database)
        after = resolve_capital_mandate(
            principal_id=ALICE,
            at_utc=LATER_TIME,
            engine=self.engine,
        )
        self.assertEqual(after.status, "active")
        self.assertEqual(
            after.lifecycle_event.mandate_lifecycle_event_id,
            before.lifecycle_event.mandate_lifecycle_event_id,
        )

    def test_lifecycle_final_tie_breaker_is_restart_stable(self) -> None:
        self._record("mandate-alice", ALICE)
        version = read_all(CapitalMandateVersion, engine=self.engine)[0]
        events = [
            CapitalMandateLifecycleEvent(
                mandate_lifecycle_event_id=event_id,
                capital_mandate_id=version.capital_mandate_id,
                mandate_version_id=version.mandate_version_id,
                principal_id=ALICE,
                event_type=event_type,
                effective_at_utc=LATER_TIME,
                authenticated_actor_principal_id=ALICE,
                reason="Exact total-order fixture.",
                receipt_ref=f"fixture:{event_id}",
                created_at_utc=LATER_TIME,
            )
            for event_id, event_type in (
                ("mandate-event-zeta", "resumed"),
                ("mandate-event-alpha", "suspended"),
            )
        ]
        write_records(events, engine=self.engine)

        before = resolve_capital_mandate(
            principal_id=ALICE,
            at_utc=LATER_TIME,
            engine=self.engine,
        )
        self.assertEqual(before.status, "active")
        self.assertEqual(
            before.lifecycle_event.mandate_lifecycle_event_id,
            "mandate-event-zeta",
        )
        self.engine.dispose()
        self.engine = init_state_core(self.database)
        after = resolve_capital_mandate(
            principal_id=ALICE,
            at_utc=LATER_TIME,
            engine=self.engine,
        )
        self.assertEqual(after.lifecycle_event.mandate_lifecycle_event_id, "mandate-event-zeta")

    def test_same_series_version_drift_invalidates_old_grant(self) -> None:
        self._record("mandate-a", ALICE)
        same_series_grant = self._grant("mandate-a")
        self._record(
            "mandate-a", ALICE, effective_at=LATER_TIME, created_at=LATER_TIME, max_notional="900"
        )
        same_series = self._validate(same_series_grant)
        self.assertIn("mandate_version_changed", same_series.deny_reasons)

    def test_different_series_version_drift_invalidates_old_grant(self) -> None:
        self._record("mandate-basis", ALICE, effective_at=BASE_TIME, created_at=BASE_TIME)
        different_series_grant = self._grant("mandate-basis")
        self._record("mandate-next", ALICE, effective_at=LATER_TIME, created_at=LATER_TIME)
        different_series = self._validate(different_series_grant)
        self.assertIn("mandate_version_changed", different_series.deny_reasons)
        historical = resolve_capital_mandate(
            principal_id=ALICE,
            at_utc=GRANT_TIME,
            engine=self.engine,
        )
        self.assertEqual(historical.version.capital_mandate_id, "mandate-basis")

    def _assert_non_active_grant(self, state: str) -> None:
        mandate_id = f"mandate-{state}"
        expires = LATER_TIME if state == "expired" else None
        self._record(mandate_id, ALICE, expires_at=expires)
        grant = self._grant(mandate_id)
        if state == "suspended":
            with patch(
                "finharness.statecore.capital_mandates._now_utc",
                return_value=LATER_TIME,
            ):
                suspend_capital_mandate(
                    mandate_id,
                    operator_context=authority_admin_context(ALICE, assurance="standard"),
                    reason="Pause.",
                    engine=self.engine,
                    receipt_root=self.receipts,
                )
        elif state == "revoked":
            with patch(
                "finharness.statecore.capital_mandates._now_utc",
                return_value=LATER_TIME,
            ):
                revoke_capital_mandate(
                    mandate_id,
                    operator_context=authority_admin_context(ALICE, assurance="standard"),
                    reason="Revoke.",
                    engine=self.engine,
                    receipt_root=self.receipts,
                )
        result = self._validate(grant, now=VALIDATION_TIME)
        self.assertFalse(result.allowed)
        self.assertIn("capital_mandate_not_active", result.deny_reasons)

    def test_suspended_current_mandate_fails_grant_closed(self) -> None:
        self._assert_non_active_grant("suspended")

    def test_revoked_current_mandate_fails_grant_closed(self) -> None:
        self._assert_non_active_grant("revoked")

    def test_expired_current_mandate_fails_grant_closed(self) -> None:
        self._assert_non_active_grant("expired")

    def test_legacy_unowned_row_remains_readable_but_cannot_be_claimed(self) -> None:
        legacy = CapitalMandate(
            capital_mandate_id="legacy-only",
            status="active",
            profile_snapshot={},
            investment_objectives={},
            risk_profile={},
            human_attester="alice@example.com",
            human_reason="Historical unverified row.",
            explicit_confirmation=True,
            execution_allowed=False,
            authority_transition=False,
        )
        write_records([legacy], engine=self.engine)
        self.assertEqual(current_capital_mandate(self.engine).capital_mandate_id, "legacy-only")
        before = self._side_effect_counts()
        with self.assertRaisesRegex(CapitalMandateValidationError, "durable owner unavailable"):
            self._record("legacy-only", ALICE)
        self.assertEqual(self._side_effect_counts(), before)
        self.assertEqual(read_all(CapitalMandateVersion, engine=self.engine), [])


class PrincipalIsolatedCapitalMandateApiTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.receipts = self.root / "receipts"
        self.engine = init_state_core(self.root / "state.sqlite")
        provider = TestIdentityProvider({"alice": _context(ALICE), "bob": _context(BOB)})
        self.app = create_app(
            state_core_engine=self.engine,
            receipt_root=str(self.receipts),
            identity_provider=provider,
        )
        self.client = AsgiTestClient(self.app)
        self.addCleanup(self.client.close)
        self.addCleanup(self.engine.dispose)
        self.addCleanup(self.tmp.cleanup)

    @staticmethod
    def _headers(actor: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {actor}"}

    @staticmethod
    def _body(mandate_id: str) -> dict[str, object]:
        return {
            "capital_mandate_id": mandate_id,
            "profile_snapshot": {},
            "investment_objectives": {},
            "risk_profile": {},
            "allowed_asset_classes": ["cash"],
            "allowed_action_types": ["rebalance"],
            "human_reason": "Authenticated owner confirms policy.",
            "explicit_confirmation": True,
            "effective_at_utc": BASE_TIME,
        }

    def _counts(self) -> tuple[int, int, int, int]:
        return (
            len(read_all(CapitalMandateVersion, engine=self.engine)),
            len(read_all(CapitalMandateLifecycleEvent, engine=self.engine)),
            len(read_all(ReceiptIndex, engine=self.engine)),
            len(list(self.receipts.rglob("*.json"))) if self.receipts.exists() else 0,
        )

    def test_bob_cannot_take_alice_id_or_operate_alice_lifecycle(self) -> None:
        created = self.client.post(
            "/capital-mandates",
            json=self._body("mandate-alice"),
            headers=self._headers("alice"),
        )
        self.assertEqual(created.status_code, 200, created.text)

        before_takeover = self._counts()
        takeover = self.client.post(
            "/capital-mandates",
            json=self._body("mandate-alice"),
            headers=self._headers("bob"),
        )
        self.assertEqual(takeover.status_code, 422, takeover.text)
        self.assertEqual(self._counts(), before_takeover)

        for command in ("suspend", "revoke"):
            for effective_at in (
                "2025-12-01T00:00:00+00:00",
                LATER_TIME,
                "2030-01-01T00:00:00+00:00",
            ):
                with self.subTest(command=command, effective_at=effective_at):
                    before = self._counts()
                    response = self.client.post(
                        f"/capital-mandates/mandate-alice/{command}",
                        json={
                            "reason": "Hostile lifecycle command.",
                            "effective_at_utc": effective_at,
                        },
                        headers=self._headers("bob"),
                    )
                    self.assertEqual(response.status_code, 422, response.text)
                    self.assertEqual(self._counts(), before)
                    alice = self.client.get(
                        "/capital-mandates/current",
                        headers=self._headers("alice"),
                    ).json()["resolution"]
                    self.assertEqual(alice["status"], "active")
                    self.assertEqual(alice["version"]["principal_id"], ALICE)

        for effective_at in (
            "2025-12-01T00:00:00+00:00",
            LATER_TIME,
            "2030-01-01T00:00:00+00:00",
        ):
            with self.subTest(command="resume", effective_at=effective_at):
                before = self._counts()
                response = self.client.post(
                    "/capital-mandates/mandate-alice/resume",
                    json={
                        "reason": "Hostile lifecycle command.",
                        "effective_at_utc": effective_at,
                    },
                    headers=self._headers("bob"),
                )
                self.assertEqual(response.status_code, 409, response.text)
                self.assertEqual(self._counts(), before)

    def test_request_principal_override_is_rejected(self) -> None:
        body = self._body("mandate-hostile")
        body["principal_id"] = BOB
        response = self.client.post(
            "/capital-mandates",
            json=body,
            headers=self._headers("alice"),
        )
        self.assertEqual(response.status_code, 422)
        self.assertEqual(self._counts(), (0, 0, 0, 0))

    def test_grant_creation_translates_historical_owner_conflict_to_422(self) -> None:
        created = self.client.post(
            "/capital-mandates",
            json=self._body("shared-id"),
            headers=self._headers("alice"),
        )
        self.assertEqual(created.status_code, 200, created.text)
        _inject_preexisting_shared_id_owner_conflict(engine=self.engine)
        receipt_paths_before = set(self.receipts.rglob("*.json"))
        receipt_indexes_before = len(read_all(ReceiptIndex, engine=self.engine))

        response = self.client.post(
            "/agent-authority-grants",
            headers=self._headers("alice"),
            json={
                "agent_authority_grant_id": "grant-owner-conflict",
                "capital_mandate_id": "shared-id",
                "agent_id": "agent:research",
                "agent_runtime_id": "runtime:research",
                "grant_scope": {
                    "allowed_asset_classes": ["cash"],
                    "allowed_action_types": ["rebalance"],
                    "autonomy_level": "L1_candidate_only",
                },
                "issued_reason": "Conflict must be a typed domain rejection.",
            },
        )

        self.assertEqual(response.status_code, 422, response.text)
        self.assertEqual(response.json()["detail"], "mandate_series_owner_conflict")
        self.assertEqual(read_all(AgentAuthorityGrant, engine=self.engine), [])
        self.assertEqual(
            len(read_all(ReceiptIndex, engine=self.engine)),
            receipt_indexes_before,
        )
        self.assertEqual(set(self.receipts.rglob("*.json")), receipt_paths_before)


if __name__ == "__main__":
    unittest.main()
