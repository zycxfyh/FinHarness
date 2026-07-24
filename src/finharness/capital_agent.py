"""Thin, durable personal-capital Agent core.

Owns the smallest useful path: Constitution -> Mission/Belief -> Delegation
-> simulated Effect -> Consequence. Capital facts stay in Capital World and
execution facts stay in the Execution Kernel. Durable Agent state is hashed
JSON; no new database schema, scheduler, or workflow platform is introduced.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import Engine

from finharness.execution.commands import submit_order
from finharness.execution.services import (
    create_order_draft,
    record_approval,
    record_position_delta,
    record_reconciliation,
    run_pretrade_check,
    stage_execution_order,
)
from finharness.statecore.capital_world import CapitalWorld
from finharness.statecore.receipt_io import (
    ReceiptIntegrityError,
    canonical_json_sha256,
    durable_compare_and_swap_json,
    durable_create_json_exclusive,
)

MissionState = Literal["active", "paused", "closed"]
DelegationState = Literal["active", "revoked"]
ExecutionState = Literal["claimed", "completed", "failed"]


class CapitalAgentError(RuntimeError):
    pass


class CapitalAgentConflictError(CapitalAgentError):
    pass


class CapitalAgentNotFoundError(CapitalAgentError):
    pass


class EffectAdmissionDenied(CapitalAgentError):
    pass


class EffectRecoveryRequired(CapitalAgentError):
    def __init__(self, execution_ref: str, detail: str) -> None:
        self.execution_ref = execution_ref
        super().__init__(f"{detail}; reconcile {execution_ref}")


class _Artifact(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    content_sha256: str = ""


class PrincipalConstitution(_Artifact):
    schema_version: Literal["finharness.principal_constitution.v1"] = (
        "finharness.principal_constitution.v1"
    )
    constitution_id: str
    principal_id: str
    goals: tuple[str, ...]
    liquidity_floor: Decimal = Field(ge=0)
    max_simulated_notional: Decimal = Field(gt=0)
    prohibited_effects: tuple[str, ...] = ()
    supersedes: str | None = None
    created_at_utc: str


class AgentMission(_Artifact):
    schema_version: Literal["finharness.agent_mission.v1"] = "finharness.agent_mission.v1"
    mission_id: str
    principal_id: str
    agent_id: str
    objective: str
    success_conditions: tuple[str, ...]
    constitution_ref: str
    current_world_id: str
    current_world_basis_digest: str
    state: MissionState = "active"
    checkpoint_ref: str | None = None
    stop_reason: str | None = None
    created_at_utc: str
    updated_at_utc: str
    closed_at_utc: str | None = None


class BeliefArtifact(_Artifact):
    schema_version: Literal["finharness.agent_belief.v1"] = "finharness.agent_belief.v1"
    belief_id: str
    mission_id: str
    claim: str
    confidence: Decimal = Field(ge=0, le=1)
    evidence_refs: tuple[str, ...] = ()
    counter_evidence_refs: tuple[str, ...] = ()
    review_condition: str
    created_at_utc: str


class MissionCheckpoint(_Artifact):
    schema_version: Literal["finharness.agent_mission_checkpoint.v1"] = (
        "finharness.agent_mission_checkpoint.v1"
    )
    checkpoint_id: str
    mission_id: str
    world_id: str
    world_basis_digest: str
    belief_refs: tuple[str, ...] = ()
    effect_refs: tuple[str, ...] = ()
    note: str
    created_at_utc: str


class DelegationEnvelope(_Artifact):
    schema_version: Literal["finharness.delegation_envelope.v1"] = (
        "finharness.delegation_envelope.v1"
    )
    delegation_id: str
    constitution_ref: str
    principal_id: str
    agent_id: str
    allowed_effects: tuple[Literal["simulated_order"], ...] = ("simulated_order",)
    max_notional: Decimal = Field(gt=0)
    max_uses: int = Field(gt=0)
    expires_at_utc: str
    state: DelegationState = "active"
    created_at_utc: str
    updated_at_utc: str
    revoked_at_utc: str | None = None
    revoked_reason: str | None = None

    @field_validator("expires_at_utc")
    @classmethod
    def utc_expiry(cls, value: str) -> str:
        return _parse_utc(value, "expires_at_utc").isoformat()


class EffectIntent(_Artifact):
    schema_version: Literal["finharness.effect_intent.v1"] = "finharness.effect_intent.v1"
    effect_intent_id: str
    idempotency_key: str
    effect_type: Literal["simulated_order"] = "simulated_order"
    mission_id: str
    delegation_id: str
    principal_id: str
    agent_id: str
    world_id: str
    world_basis_digest: str
    execution_account_id: str
    broker_connection_id: str
    instrument_ref: str
    symbol: str
    side: Literal["buy", "sell"]
    order_type: Literal["market", "limit"]
    quantity: Decimal = Field(gt=0)
    reference_price: Decimal = Field(gt=0)
    currency: str = "USD"
    rationale: str
    created_at_utc: str

    @property
    def notional(self) -> Decimal:
        return self.quantity * self.reference_price


class EffectAdmission(_Artifact):
    schema_version: Literal["finharness.effect_admission.v1"] = "finharness.effect_admission.v1"
    admission_id: str
    effect_intent_ref: str
    effect_intent_id: str
    mission_id: str
    delegation_id: str
    constitution_ref: str
    world_id: str
    world_basis_digest: str
    verified_reference_price: Decimal = Field(gt=0)
    admitted_notional: Decimal
    created_at_utc: str


class EffectExecutionRecord(_Artifact):
    schema_version: Literal["finharness.effect_execution.v1"] = "finharness.effect_execution.v1"
    execution_id: str
    effect_intent_ref: str
    admission_ref: str
    state: ExecutionState
    runtime_job_id: str | None = None
    runtime_attempt_id: str | None = None
    order_draft_id: str | None = None
    execution_order_id: str | None = None
    execution_report_id: str | None = None
    position_delta_id: str | None = None
    reconciliation_id: str | None = None
    failure_reason: str | None = None
    recovery_evidence_refs: tuple[str, ...] = ()
    created_at_utc: str
    updated_at_utc: str


class ConsequenceRecord(_Artifact):
    schema_version: Literal["finharness.consequence_record.v1"] = "finharness.consequence_record.v1"
    consequence_id: str
    mission_id: str
    execution_ref: str
    world_before_id: str
    world_before_basis_digest: str
    world_after_id: str
    world_after_basis_digest: str
    expected_change: dict[str, Any]
    observed_change: dict[str, Any]
    discrepancies: tuple[dict[str, Any], ...] = ()
    created_at_utc: str


_DIR = {
    PrincipalConstitution: "constitutions",
    AgentMission: "missions",
    BeliefArtifact: "beliefs",
    MissionCheckpoint: "checkpoints",
    DelegationEnvelope: "delegations",
    EffectIntent: "effect-intents",
    EffectAdmission: "effect-admissions",
    EffectExecutionRecord: "effect-executions",
    ConsequenceRecord: "consequences",
}


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _parse_utc(value: str, name: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be ISO-8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != UTC.utcoffset(parsed):
        raise ValueError(f"{name} must be UTC")
    return parsed.astimezone(UTC)


def _text(value: str, name: str) -> str:
    if not (clean := value.strip()):
        raise ValueError(f"{name} must not be blank")
    return clean


def _id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


def _stable_id(prefix: str, material: dict[str, Any]) -> str:
    return f"{prefix}_{canonical_json_sha256(material)[:32]}"


def _verified_position_basis(intent: EffectIntent, world: CapitalWorld) -> tuple[Decimal, Decimal]:
    matching = [
        position
        for position in world.positions
        if position.symbol.strip().upper() == intent.symbol.strip().upper()
    ]
    if len(matching) != 1:
        raise EffectAdmissionDenied("world_position_not_uniquely_resolved")
    position = matching[0]
    if position.valuation_status not in {"valued", "valued_converted"}:
        raise EffectAdmissionDenied("world_position_not_valued")
    price = position.unit_price
    if price is None and position.market_value is not None and position.quantity != 0:
        price = position.market_value / position.quantity
    if price is None or price <= 0:
        raise EffectAdmissionDenied("world_reference_price_unavailable")
    if intent.side == "sell" and position.quantity < intent.quantity:
        raise EffectAdmissionDenied("insufficient_world_position")
    return position.quantity, price


def _seal[T: _Artifact](model: T) -> T:
    payload = model.model_dump(mode="json", exclude={"content_sha256"})
    payload["content_sha256"] = canonical_json_sha256(payload)
    return type(model).model_validate(payload)


def _verify[T: _Artifact](model_type: type[T], payload: dict[str, Any]) -> T:
    claimed = payload.get("content_sha256")
    raw = {key: value for key, value in payload.items() if key != "content_sha256"}
    if not isinstance(claimed, str) or claimed != canonical_json_sha256(raw):
        raise ReceiptIntegrityError(f"{model_type.__name__} content hash mismatch")
    return model_type.model_validate(payload)


class CapitalAgentStore:
    """Durable artifact store and minimal personal-capital Agent operations."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)

    def _path(self, model_type: type[_Artifact], artifact_id: str) -> Path:
        return self.root / _DIR[model_type] / f"{artifact_id}.json"

    def ref(self, model_type: type[_Artifact], artifact_id: str) -> str:
        return f"{_DIR[model_type]}/{artifact_id}.json"

    def _read[T: _Artifact](self, model_type: type[T], artifact_id: str) -> T:
        path = self._path(model_type, artifact_id)
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise CapitalAgentNotFoundError(str(path)) from exc
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ReceiptIntegrityError(f"artifact unreadable: {path}") from exc
        if not isinstance(payload, dict):
            raise ReceiptIntegrityError(f"artifact is not a JSON object: {path}")
        return _verify(model_type, payload)

    def _create[T: _Artifact](self, model: T, artifact_id: str) -> T:
        sealed = _seal(model)
        path = self._path(type(model), artifact_id)
        if durable_create_json_exclusive(path, sealed.model_dump(mode="json")):
            return sealed
        existing = self._read(type(model), artifact_id)
        if existing != sealed:
            raise CapitalAgentConflictError(f"immutable artifact conflict: {path}")
        return existing

    def _transition[T: _Artifact](
        self, current: T, artifact_id: str, expected: str, **updates: Any
    ) -> T:
        if getattr(current, "state", None) != expected:
            raise CapitalAgentConflictError(
                f"expected {expected}, got {getattr(current, 'state', None)}"
            )
        replacement = _seal(current.model_copy(update={**updates, "content_sha256": ""}))
        if not durable_compare_and_swap_json(
            self._path(type(current), artifact_id),
            expected_content_sha256=current.content_sha256,
            expected_state=expected,
            payload=replacement.model_dump(mode="json"),
        ):
            raise CapitalAgentConflictError(f"concurrent transition: {artifact_id}")
        return replacement

    def create_constitution(
        self,
        *,
        principal_id: str,
        goals: tuple[str, ...],
        liquidity_floor: Decimal,
        max_simulated_notional: Decimal,
        prohibited_effects: tuple[str, ...] = (),
        supersedes: str | None = None,
        constitution_id: str | None = None,
        created_at_utc: str | None = None,
    ) -> PrincipalConstitution:
        constitution = PrincipalConstitution(
            constitution_id=_text(constitution_id, "constitution_id")
            if constitution_id
            else _id("constitution"),
            principal_id=_text(principal_id, "principal_id"),
            goals=tuple(_text(item, "goal") for item in goals),
            liquidity_floor=liquidity_floor,
            max_simulated_notional=max_simulated_notional,
            prohibited_effects=tuple(sorted(set(prohibited_effects))),
            supersedes=supersedes,
            created_at_utc=(
                _parse_utc(created_at_utc, "created_at_utc").isoformat()
                if created_at_utc
                else _now()
            ),
        )
        return self._create(constitution, constitution.constitution_id)

    def read_constitution(self, constitution_id: str) -> PrincipalConstitution:
        return self._read(PrincipalConstitution, constitution_id)

    def create_mission(
        self,
        *,
        principal_id: str,
        agent_id: str,
        objective: str,
        success_conditions: tuple[str, ...],
        constitution_id: str,
        world: CapitalWorld,
        mission_id: str | None = None,
        created_at_utc: str | None = None,
    ) -> AgentMission:
        constitution = self.read_constitution(constitution_id)
        if constitution.principal_id != principal_id:
            raise CapitalAgentConflictError("constitution principal mismatch")
        now = _parse_utc(created_at_utc, "created_at_utc").isoformat() if created_at_utc else _now()
        mission = AgentMission(
            mission_id=_text(mission_id, "mission_id") if mission_id else _id("mission"),
            principal_id=_text(principal_id, "principal_id"),
            agent_id=_text(agent_id, "agent_id"),
            objective=_text(objective, "objective"),
            success_conditions=tuple(
                _text(item, "success_condition") for item in success_conditions
            ),
            constitution_ref=self.ref(PrincipalConstitution, constitution_id),
            current_world_id=world.world_id,
            current_world_basis_digest=world.basis_digest,
            created_at_utc=now,
            updated_at_utc=now,
        )
        return self._create(mission, mission.mission_id)

    def read_mission(self, mission_id: str) -> AgentMission:
        return self._read(AgentMission, mission_id)

    def list_missions(self, *, principal_id: str | None = None) -> tuple[AgentMission, ...]:
        directory = self.root / _DIR[AgentMission]
        if not directory.exists():
            return ()
        missions = tuple(
            self._read(AgentMission, path.stem) for path in sorted(directory.glob("*.json"))
        )
        if principal_id is None:
            return missions
        return tuple(item for item in missions if item.principal_id == principal_id)

    def pause_mission(self, mission_id: str, *, reason: str) -> AgentMission:
        mission = self.read_mission(mission_id)
        return self._transition(
            mission,
            mission_id,
            "active",
            state="paused",
            stop_reason=_text(reason, "reason"),
            updated_at_utc=_now(),
        )

    def resume_mission(self, mission_id: str, *, world: CapitalWorld) -> AgentMission:
        mission = self.read_mission(mission_id)
        return self._transition(
            mission,
            mission_id,
            "paused",
            state="active",
            stop_reason=None,
            current_world_id=world.world_id,
            current_world_basis_digest=world.basis_digest,
            updated_at_utc=_now(),
        )

    def close_mission(self, mission_id: str, *, reason: str) -> AgentMission:
        mission = self.read_mission(mission_id)
        if mission.state not in {"active", "paused"}:
            raise CapitalAgentConflictError("mission is already closed")
        now = _now()
        return self._transition(
            mission,
            mission_id,
            mission.state,
            state="closed",
            stop_reason=_text(reason, "reason"),
            updated_at_utc=now,
            closed_at_utc=now,
        )

    def read_belief(self, belief_id: str) -> BeliefArtifact:
        return self._read(BeliefArtifact, belief_id)

    def create_belief(
        self,
        *,
        mission_id: str,
        claim: str,
        confidence: Decimal,
        review_condition: str,
        evidence_refs: tuple[str, ...] = (),
        counter_evidence_refs: tuple[str, ...] = (),
        belief_id: str | None = None,
        created_at_utc: str | None = None,
    ) -> BeliefArtifact:
        self.read_mission(mission_id)
        belief = BeliefArtifact(
            belief_id=_text(belief_id, "belief_id") if belief_id else _id("belief"),
            mission_id=mission_id,
            claim=_text(claim, "claim"),
            confidence=confidence,
            evidence_refs=evidence_refs,
            counter_evidence_refs=counter_evidence_refs,
            review_condition=_text(review_condition, "review_condition"),
            created_at_utc=(
                _parse_utc(created_at_utc, "created_at_utc").isoformat()
                if created_at_utc
                else _now()
            ),
        )
        return self._create(belief, belief.belief_id)

    def checkpoint_mission(
        self,
        mission_id: str,
        *,
        world: CapitalWorld,
        belief_refs: tuple[str, ...] = (),
        effect_refs: tuple[str, ...] = (),
        note: str,
    ) -> tuple[AgentMission, MissionCheckpoint]:
        mission = self.read_mission(mission_id)
        if mission.state == "closed":
            raise CapitalAgentConflictError("closed mission cannot checkpoint")
        checkpoint = MissionCheckpoint(
            checkpoint_id=_id("checkpoint"),
            mission_id=mission_id,
            world_id=world.world_id,
            world_basis_digest=world.basis_digest,
            belief_refs=belief_refs,
            effect_refs=effect_refs,
            note=_text(note, "note"),
            created_at_utc=_now(),
        )
        checkpoint = self._create(checkpoint, checkpoint.checkpoint_id)
        updated = self._transition(
            mission,
            mission_id,
            mission.state,
            checkpoint_ref=self.ref(MissionCheckpoint, checkpoint.checkpoint_id),
            current_world_id=world.world_id,
            current_world_basis_digest=world.basis_digest,
            updated_at_utc=_now(),
        )
        return updated, checkpoint

    def create_delegation(
        self,
        *,
        constitution_id: str,
        principal_id: str,
        agent_id: str,
        max_notional: Decimal,
        max_uses: int,
        expires_at_utc: str,
        delegation_id: str | None = None,
        created_at_utc: str | None = None,
    ) -> DelegationEnvelope:
        constitution = self.read_constitution(constitution_id)
        if constitution.principal_id != principal_id:
            raise CapitalAgentConflictError("constitution principal mismatch")
        if max_notional > constitution.max_simulated_notional:
            raise CapitalAgentConflictError("delegation exceeds constitution notional")
        now = _parse_utc(created_at_utc, "created_at_utc").isoformat() if created_at_utc else _now()
        if _parse_utc(expires_at_utc, "expires_at_utc") <= _parse_utc(now, "created_at_utc"):
            raise ValueError("delegation expiry must be in the future")
        delegation = DelegationEnvelope(
            delegation_id=_text(delegation_id, "delegation_id")
            if delegation_id
            else _id("delegation"),
            constitution_ref=self.ref(PrincipalConstitution, constitution_id),
            principal_id=_text(principal_id, "principal_id"),
            agent_id=_text(agent_id, "agent_id"),
            max_notional=max_notional,
            max_uses=max_uses,
            expires_at_utc=expires_at_utc,
            created_at_utc=now,
            updated_at_utc=now,
        )
        return self._create(delegation, delegation.delegation_id)

    def read_delegation(self, delegation_id: str) -> DelegationEnvelope:
        return self._read(DelegationEnvelope, delegation_id)

    def revoke_delegation(self, delegation_id: str, *, reason: str) -> DelegationEnvelope:
        delegation = self.read_delegation(delegation_id)
        now = _now()
        return self._transition(
            delegation,
            delegation_id,
            "active",
            state="revoked",
            revoked_at_utc=now,
            revoked_reason=_text(reason, "reason"),
            updated_at_utc=now,
        )

    def create_effect_intent(
        self,
        *,
        mission_id: str,
        delegation_id: str,
        idempotency_key: str,
        execution_account_id: str,
        broker_connection_id: str,
        instrument_ref: str,
        symbol: str,
        side: Literal["buy", "sell"],
        order_type: Literal["market", "limit"],
        quantity: Decimal,
        reference_price: Decimal,
        rationale: str,
    ) -> EffectIntent:
        mission = self.read_mission(mission_id)
        delegation = self.read_delegation(delegation_id)
        key = _text(idempotency_key, "idempotency_key")
        intent_id = _stable_id("effect", {"mission_id": mission_id, "idempotency_key": key})
        semantic = {
            "mission_id": mission_id,
            "delegation_id": delegation_id,
            "idempotency_key": key,
            "execution_account_id": execution_account_id,
            "broker_connection_id": broker_connection_id,
            "instrument_ref": instrument_ref,
            "symbol": symbol,
            "side": side,
            "order_type": order_type,
            "quantity": str(quantity),
            "reference_price": str(reference_price),
            "rationale": rationale,
        }
        if self._path(EffectIntent, intent_id).exists():
            existing = self._read(EffectIntent, intent_id)
            actual = {
                name: str(getattr(existing, name))
                if name in {"quantity", "reference_price"}
                else getattr(existing, name)
                for name in semantic
            }
            if actual != semantic:
                raise CapitalAgentConflictError("idempotency key reused with different intent")
            return existing
        if (
            delegation.principal_id != mission.principal_id
            or delegation.agent_id != mission.agent_id
        ):
            raise CapitalAgentConflictError("mission and delegation identity mismatch")
        intent = EffectIntent(
            effect_intent_id=intent_id,
            idempotency_key=key,
            mission_id=mission_id,
            delegation_id=delegation_id,
            principal_id=mission.principal_id,
            agent_id=mission.agent_id,
            world_id=mission.current_world_id,
            world_basis_digest=mission.current_world_basis_digest,
            execution_account_id=_text(execution_account_id, "execution_account_id"),
            broker_connection_id=_text(broker_connection_id, "broker_connection_id"),
            instrument_ref=_text(instrument_ref, "instrument_ref"),
            symbol=_text(symbol, "symbol"),
            side=side,
            order_type=order_type,
            quantity=quantity,
            reference_price=reference_price,
            rationale=_text(rationale, "rationale"),
            created_at_utc=_now(),
        )
        return self._create(intent, intent_id)

    def read_effect_intent(self, effect_intent_id: str) -> EffectIntent:
        return self._read(EffectIntent, effect_intent_id)

    def read_effect_admission(self, admission_id: str) -> EffectAdmission:
        return self._read(EffectAdmission, admission_id)

    def _admission_count(self, delegation_id: str) -> int:
        directory = self.root / _DIR[EffectAdmission]
        if not directory.exists():
            return 0
        return sum(
            self._read(EffectAdmission, path.stem).delegation_id == delegation_id
            for path in directory.glob("*.json")
        )

    def admit_effect(  # noqa: C901
        self, effect_intent_id: str, *, current_world: CapitalWorld
    ) -> EffectAdmission:
        intent = self.read_effect_intent(effect_intent_id)
        admission_id = _stable_id("admission", {"effect_intent_id": effect_intent_id})
        if self._path(EffectAdmission, admission_id).exists():
            return self._read(EffectAdmission, admission_id)
        mission = self.read_mission(intent.mission_id)
        delegation = self.read_delegation(intent.delegation_id)
        constitution_id = Path(delegation.constitution_ref).stem
        constitution = self.read_constitution(constitution_id)
        reasons: list[str] = []
        if mission.state != "active":
            reasons.append("mission_not_active")
        if delegation.state != "active":
            reasons.append("delegation_not_active")
        if _parse_utc(delegation.expires_at_utc, "expires_at_utc") <= datetime.now(UTC):
            reasons.append("delegation_expired")
        if intent.principal_id != delegation.principal_id or intent.agent_id != delegation.agent_id:
            reasons.append("identity_mismatch")
        if (
            intent.world_id != current_world.world_id
            or intent.world_basis_digest != current_world.basis_digest
        ):
            reasons.append("stale_world")
        if current_world.trust.blockers or current_world.trust.valuation_status != "admitted":
            reasons.append("world_not_admitted_for_valuation")
        if intent.effect_type not in delegation.allowed_effects:
            reasons.append("effect_outside_delegation")
        if intent.effect_type in constitution.prohibited_effects:
            reasons.append("effect_prohibited_by_constitution")
        verified_price: Decimal | None = None
        try:
            _position_quantity, verified_price = _verified_position_basis(intent, current_world)
        except EffectAdmissionDenied as exc:
            reasons.append(str(exc))
        admitted_notional = (
            intent.quantity * verified_price if verified_price is not None else intent.notional
        )
        if (
            admitted_notional > delegation.max_notional
            or admitted_notional > constitution.max_simulated_notional
        ):
            reasons.append("notional_exceeds_limit")
        if self._admission_count(delegation.delegation_id) >= delegation.max_uses:
            reasons.append("delegation_use_limit_reached")
        if reasons:
            raise EffectAdmissionDenied(",".join(reasons))
        if verified_price is None:
            raise EffectAdmissionDenied("world_reference_price_unavailable")
        admission = EffectAdmission(
            admission_id=admission_id,
            effect_intent_ref=self.ref(EffectIntent, effect_intent_id),
            effect_intent_id=effect_intent_id,
            mission_id=intent.mission_id,
            delegation_id=delegation.delegation_id,
            constitution_ref=delegation.constitution_ref,
            world_id=current_world.world_id,
            world_basis_digest=current_world.basis_digest,
            verified_reference_price=verified_price,
            admitted_notional=admitted_notional,
            created_at_utc=_now(),
        )
        return self._create(admission, admission_id)

    def execute_simulated_effect(
        self,
        *,
        engine: Engine,
        receipt_root: str | Path,
        effect_intent_id: str,
        admission_id: str,
        current_world: CapitalWorld,
    ) -> EffectExecutionRecord:
        intent = self.read_effect_intent(effect_intent_id)
        admission = self._read(EffectAdmission, admission_id)
        if admission.effect_intent_id != effect_intent_id:
            raise CapitalAgentConflictError("admission does not bind intent")
        if (admission.world_id, admission.world_basis_digest) != (
            current_world.world_id,
            current_world.basis_digest,
        ):
            raise EffectAdmissionDenied("admission_world_is_stale")
        if current_world.trust.blockers or current_world.trust.valuation_status != "admitted":
            raise EffectAdmissionDenied("current_world_not_admitted_for_valuation")
        mission = self.read_mission(intent.mission_id)
        delegation = self.read_delegation(intent.delegation_id)
        if mission.state != "active" or delegation.state != "active":
            raise EffectAdmissionDenied("mission_or_delegation_not_active")
        if _parse_utc(delegation.expires_at_utc, "expires_at_utc") <= datetime.now(UTC):
            raise EffectAdmissionDenied("delegation_expired")
        position_quantity_before, verified_price = _verified_position_basis(intent, current_world)
        if (
            admission.verified_reference_price != verified_price
            or admission.admitted_notional != intent.quantity * verified_price
        ):
            raise EffectAdmissionDenied("admission_price_basis_changed")
        execution_id = _stable_id("effect_execution", {"effect_intent_id": effect_intent_id})
        execution_ref = self.ref(EffectExecutionRecord, execution_id)
        if self._path(EffectExecutionRecord, execution_id).exists():
            existing = self._read(EffectExecutionRecord, execution_id)
            if existing.state == "completed":
                return existing
            raise EffectRecoveryRequired(execution_ref, f"effect execution is {existing.state}")
        now = _now()
        claimed = self._create(
            EffectExecutionRecord(
                execution_id=execution_id,
                effect_intent_ref=self.ref(EffectIntent, effect_intent_id),
                admission_ref=self.ref(EffectAdmission, admission_id),
                state="claimed",
                created_at_utc=now,
                updated_at_utc=now,
            ),
            execution_id,
        )
        try:
            draft = create_order_draft(
                engine=engine,
                receipt_root=receipt_root,
                execution_account_id=intent.execution_account_id,
                instrument_ref=intent.instrument_ref,
                symbol=intent.symbol,
                side=intent.side,
                order_type=intent.order_type,
                quantity=intent.quantity,
                rationale=intent.rationale,
                environment="paper",
                limit_price=intent.reference_price if intent.order_type == "limit" else None,
                source_kind="capital_agent_effect",
                source_ref=admission.effect_intent_ref,
            )
            run_pretrade_check(
                engine=engine,
                receipt_root=receipt_root,
                order_draft_id=draft.order_draft_id,
                findings=[
                    {
                        "rule": "effect_admission",
                        "severity": "info",
                        "result": admission.admission_id,
                    }
                ],
                required_approval_level="delegation",
            )
            record_approval(
                engine=engine,
                receipt_root=receipt_root,
                order_draft_id=draft.order_draft_id,
                decision="approved",
                reviewer_id=f"delegation:{delegation.delegation_id}",
                rationale=f"admitted by {admission.admission_id}",
            )
            order = stage_execution_order(
                engine=engine,
                receipt_root=receipt_root,
                order_draft_id=draft.order_draft_id,
                broker_connection_id=intent.broker_connection_id,
                environment="paper",
            )
            report = submit_order(
                engine=engine,
                receipt_root=receipt_root,
                execution_order_id=order.execution_order_id,
            )
            signed = report.filled_quantity if intent.side == "buy" else -report.filled_quantity
            post_quantity = position_quantity_before + signed
            delta = record_position_delta(
                engine=engine,
                receipt_root=receipt_root,
                execution_report_id=report.execution_report_id,
                execution_account_id=intent.execution_account_id,
                symbol=intent.symbol,
                delta_quantity=signed,
                post_execution_quantity=post_quantity,
            )
            reconciliation = record_reconciliation(
                engine=engine,
                receipt_root=receipt_root,
                execution_account_id=intent.execution_account_id,
                expected_positions=[{"symbol": intent.symbol, "quantity": str(post_quantity)}],
                actual_positions=[{"symbol": intent.symbol, "quantity": str(post_quantity)}],
            )
        except Exception as exc:
            raise EffectRecoveryRequired(execution_ref, str(exc)) from exc
        return self._transition(
            claimed,
            execution_id,
            "claimed",
            state="completed",
            order_draft_id=draft.order_draft_id,
            execution_order_id=order.execution_order_id,
            execution_report_id=report.execution_report_id,
            position_delta_id=delta.position_delta_id,
            reconciliation_id=reconciliation.reconciliation_id,
            updated_at_utc=_now(),
        )

    def effect_execution_id(self, effect_intent_id: str) -> str:
        self.read_effect_intent(effect_intent_id)
        return _stable_id("effect_execution", {"effect_intent_id": effect_intent_id})

    def read_effect_execution(self, execution_id: str) -> EffectExecutionRecord:
        return self._read(EffectExecutionRecord, execution_id)

    def bind_runtime_execution(
        self,
        execution_id: str,
        *,
        runtime_job_id: str,
        runtime_attempt_id: str | None,
    ) -> EffectExecutionRecord:
        execution = self._read(EffectExecutionRecord, execution_id)
        clean_job = _text(runtime_job_id, "runtime_job_id")
        clean_attempt = (
            _text(runtime_attempt_id, "runtime_attempt_id")
            if runtime_attempt_id is not None
            else None
        )
        if execution.runtime_job_id is not None:
            if (
                execution.runtime_job_id != clean_job
                or execution.runtime_attempt_id != clean_attempt
            ):
                raise CapitalAgentConflictError("execution already bound to another Runtime Job")
            return execution
        return self._transition(
            execution,
            execution_id,
            execution.state,
            runtime_job_id=clean_job,
            runtime_attempt_id=clean_attempt,
            updated_at_utc=_now(),
        )

    def reconcile_claimed_execution(
        self,
        execution_id: str,
        *,
        outcome: Literal["completed", "failed"],
        evidence_refs: tuple[str, ...],
        reason: str,
    ) -> EffectExecutionRecord:
        execution = self._read(EffectExecutionRecord, execution_id)
        return self._transition(
            execution,
            execution_id,
            "claimed",
            state=outcome,
            failure_reason=None if outcome == "completed" else _text(reason, "reason"),
            recovery_evidence_refs=evidence_refs,
            updated_at_utc=_now(),
        )

    def record_consequence(
        self,
        *,
        mission_id: str,
        execution_id: str,
        world_before: CapitalWorld,
        world_after: CapitalWorld,
        expected_change: dict[str, Any],
        observed_change: dict[str, Any],
        discrepancies: tuple[dict[str, Any], ...] = (),
    ) -> ConsequenceRecord:
        mission = self.read_mission(mission_id)
        execution = self._read(EffectExecutionRecord, execution_id)
        if execution.state != "completed":
            raise CapitalAgentConflictError("consequence requires completed execution")
        if (mission.current_world_id, mission.current_world_basis_digest) != (
            world_before.world_id,
            world_before.basis_digest,
        ):
            raise CapitalAgentConflictError("mission is not bound to world_before")
        consequence_id = _stable_id(
            "consequence",
            {"execution_id": execution_id, "world_after_basis_digest": world_after.basis_digest},
        )
        if self._path(ConsequenceRecord, consequence_id).exists():
            return self._read(ConsequenceRecord, consequence_id)
        return self._create(
            ConsequenceRecord(
                consequence_id=consequence_id,
                mission_id=mission_id,
                execution_ref=self.ref(EffectExecutionRecord, execution_id),
                world_before_id=world_before.world_id,
                world_before_basis_digest=world_before.basis_digest,
                world_after_id=world_after.world_id,
                world_after_basis_digest=world_after.basis_digest,
                expected_change=expected_change,
                observed_change=observed_change,
                discrepancies=discrepancies,
                created_at_utc=_now(),
            ),
            consequence_id,
        )


__all__ = [
    "AgentMission",
    "BeliefArtifact",
    "CapitalAgentConflictError",
    "CapitalAgentNotFoundError",
    "CapitalAgentStore",
    "ConsequenceRecord",
    "DelegationEnvelope",
    "EffectAdmission",
    "EffectAdmissionDenied",
    "EffectExecutionRecord",
    "EffectIntent",
    "EffectRecoveryRequired",
    "MissionCheckpoint",
    "PrincipalConstitution",
]
