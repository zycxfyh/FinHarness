"""Deterministic current and historical Capital World resolution."""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal, TypeVar

from pydantic import BaseModel
from sqlalchemy import Engine
from sqlmodel import Session, col, select

from finharness.capital_import_contract import canonical_utc
from finharness.capital_projection import projection_sha256
from finharness.statecore.models import (
    Account,
    AccountIdentity,
    CashflowEvent,
    DocumentRef,
    FinancialGoal,
    IdentityAlias,
    ImportBatch,
    InstrumentIdentity,
    InsurancePolicy,
    Liability,
    Position,
    ReceiptManifest,
    Snapshot,
    TaxEvent,
)

CapitalWorldUseCase = Literal[
    "capital_review",
    "exposure",
    "daily_brief",
    "decision_scan",
    "agent_context",
    "scenario",
    "action_preflight",
]


class CapitalWorldResolutionError(RuntimeError):
    """Raised when a query itself is invalid; unsafe worlds return blockers."""


@dataclass(frozen=True)
class CapitalWorldQuery:
    as_of_utc: str
    known_at_utc: str
    base_currency: str
    use_case: CapitalWorldUseCase


@dataclass(frozen=True)
class CapitalWorldSourceSelection:
    stable_source_id: str
    source_kind: str
    batch_id: str
    projection_artifact_id: str
    projection_sha256: str
    covered_domains: tuple[str, ...]
    observed_at_utc: str
    recorded_at_utc: str


@dataclass(frozen=True)
class CapitalWorldTrust:
    status: Literal["admitted", "partial", "blocked"]
    evidence_integrity: Literal["intact", "unverified", "failed"]
    completeness: Literal["complete", "partial", "blocked", "unavailable"]
    valuation_status: Literal["admitted", "blocked", "unavailable"]
    blockers: tuple[str, ...]


_ModelT = TypeVar("_ModelT", bound=BaseModel)


@dataclass(frozen=True)
class CapitalWorld:
    world_id: str
    basis_digest: str
    query: CapitalWorldQuery
    selected_sources: tuple[CapitalWorldSourceSelection, ...]
    records: tuple[dict[str, Any], ...]
    trust: CapitalWorldTrust
    recovery_refs: tuple[str, ...]

    def models(self, record_type: str, model: type[_ModelT]) -> tuple[_ModelT, ...]:
        return tuple(
            model.model_validate(item["payload"])
            for item in self.records
            if item.get("record_type") == record_type
        )

    @property
    def snapshots(self) -> tuple[Snapshot, ...]:
        return self.models("Snapshot", Snapshot)

    @property
    def positions(self) -> tuple[Position, ...]:
        return self.models("Position", Position)

    @property
    def liabilities(self) -> tuple[Liability, ...]:
        return self.models("Liability", Liability)

    @property
    def cashflows(self) -> tuple[CashflowEvent, ...]:
        return self.models("CashflowEvent", CashflowEvent)

    @property
    def taxes(self) -> tuple[TaxEvent, ...]:
        return self.models("TaxEvent", TaxEvent)

    @property
    def insurance(self) -> tuple[InsurancePolicy, ...]:
        return self.models("InsurancePolicy", InsurancePolicy)


_WORLD_RECORD_MODELS: dict[str, type[BaseModel]] = {
    model.__name__: model
    for model in (
        Account,
        AccountIdentity,
        Snapshot,
        Position,
        InstrumentIdentity,
        IdentityAlias,
        Liability,
        FinancialGoal,
        CashflowEvent,
        TaxEvent,
        InsurancePolicy,
        DocumentRef,
    )
}


def _clock(value: str | None, *, field: str) -> str | None:
    if not value:
        return None
    return canonical_utc(value, field=field)


def _batch_observed(batch: ImportBatch) -> str | None:
    return _clock(
        batch.observed_at_utc or str((batch.time_semantics or {}).get("observed_at_utc") or ""),
        field="observed_at_utc",
    )


def _batch_recorded(batch: ImportBatch) -> str | None:
    return _clock(
        batch.recorded_at_utc or str((batch.time_semantics or {}).get("recorded_at_utc") or ""),
        field="recorded_at_utc",
    )


def _select_source_domain_head(
    source_id: str,
    domain: str,
    batches: list[ImportBatch],
    blockers: list[str],
) -> ImportBatch | None:
    domain_batches = [batch for batch in batches if domain in batch.covered_domains]
    observed = [(batch, _batch_observed(batch)) for batch in domain_batches]
    usable = [(batch, clock) for batch, clock in observed if clock is not None]
    if not usable:
        blockers.append(f"source_time_unavailable:{source_id}:{domain}")
        return None
    max_observed = max(clock for _batch, clock in usable)
    candidates = [batch for batch, clock in usable if clock == max_observed]
    candidate_ids = {batch.batch_id for batch in candidates}
    superseded_ids = {
        batch.supersedes_batch_id
        for batch in candidates
        if batch.supersedes_batch_id in candidate_ids
    }
    heads = [batch for batch in candidates if batch.batch_id not in superseded_ids]
    if len(heads) != 1:
        blockers.append(
            f"ambiguous_source_head:{source_id}:{domain}:{max_observed}"
        )
        return None
    return heads[0]


_RECORD_DOMAINS: dict[str, str] = {
    "Position": "position",
    "Liability": "liability",
    "FinancialGoal": "goal",
    "CashflowEvent": "cashflow",
    "TaxEvent": "tax_event",
    "InsurancePolicy": "insurance",
    "DocumentRef": "document",
}


def _record_domain(item: dict[str, Any]) -> str | None:
    record_type = str(item.get("record_type") or "")
    if record_type == "Snapshot":
        payload = item.get("payload")
        if isinstance(payload, dict) and payload.get("kind") == "portfolio":
            return "position"
        return ""
    return _RECORD_DOMAINS.get(record_type)


def _batch_rank(batch: ImportBatch) -> tuple[str, str, str]:
    return (
        _batch_observed(batch) or "",
        _batch_recorded(batch) or "",
        batch.batch_id,
    )


def _record_identity(item: dict[str, Any]) -> tuple[str, str] | None:
    record_type = str(item.get("record_type") or "")
    payload = item.get("payload")
    if not isinstance(payload, dict):
        return None
    if record_type == "Position":
        account = str(payload.get("account_id") or "")
        instrument = str(payload.get("instrument_id") or payload.get("symbol") or "")
        return (record_type, f"{account}:{instrument}") if account and instrument else None
    fields = {
        "Account": "canonical_account_id",
        "AccountIdentity": "canonical_account_id",
        "InstrumentIdentity": "instrument_id",
        "IdentityAlias": "alias_id",
        "Snapshot": "snapshot_id",
        "Liability": "liability_id",
        "FinancialGoal": "goal_id",
        "CashflowEvent": "cashflow_id",
        "TaxEvent": "tax_event_id",
        "InsurancePolicy": "policy_id",
        "DocumentRef": "document_id",
    }
    field = fields.get(record_type)
    if field is None:
        return None
    value = payload.get(field) or (payload.get("account_id") if record_type == "Account" else None)
    return (record_type, str(value)) if value else None



@dataclass(frozen=True)
class _ResolutionInputs:
    batches: tuple[ImportBatch, ...]
    legacy_snapshot: Snapshot | None
    legacy_snapshot_time_invalid: bool
    legacy_models: tuple[BaseModel, ...]


@dataclass(frozen=True)
class _ProjectedComposition:
    selections: tuple[CapitalWorldSourceSelection, ...]
    records: tuple[dict[str, Any], ...]
    recovery_refs: tuple[str, ...]
    completeness_values: tuple[str, ...]
    evidence_failed: bool


def _load_resolution_inputs(engine: Engine, resolved_as_of: str) -> _ResolutionInputs:
    with Session(engine) as session:
        batches = tuple(
            session.exec(
                select(ImportBatch)
                .join(
                    ReceiptManifest,
                    col(ReceiptManifest.batch_id) == ImportBatch.batch_id,
                )
                .where(ReceiptManifest.materialization_status == "materialized")
            ).all()
        )
        portfolio_snapshots = tuple(
            session.exec(
                select(Snapshot).where(Snapshot.kind == "portfolio")
            ).all()
        )
        valid_legacy_snapshots: list[tuple[str, Snapshot]] = []
        invalid_legacy_snapshots: list[Snapshot] = []
        for candidate in portfolio_snapshots:
            try:
                candidate_clock = canonical_utc(
                    candidate.as_of_utc,
                    field="snapshot_as_of_utc",
                )
            except ValueError:
                invalid_legacy_snapshots.append(candidate)
            else:
                if candidate_clock <= resolved_as_of:
                    valid_legacy_snapshots.append((candidate_clock, candidate))
        if invalid_legacy_snapshots:
            legacy_snapshot = max(
                invalid_legacy_snapshots,
                key=lambda item: item.snapshot_id,
            )
        elif valid_legacy_snapshots:
            legacy_snapshot = max(
                valid_legacy_snapshots,
                key=lambda item: (item[0], item[1].snapshot_id),
            )[1]
        else:
            legacy_snapshot = None
        legacy_models: list[BaseModel] = [
            *session.exec(select(AccountIdentity)).all(),
            *session.exec(select(InstrumentIdentity)).all(),
            *session.exec(select(IdentityAlias)).all(),
            *session.exec(select(Account)).all(),
            *session.exec(select(Liability)).all(),
            *session.exec(select(FinancialGoal)).all(),
            *session.exec(select(CashflowEvent)).all(),
            *session.exec(select(TaxEvent)).all(),
            *session.exec(select(InsurancePolicy)).all(),
            *session.exec(select(DocumentRef)).all(),
        ]
        if legacy_snapshot is not None:
            legacy_models.extend(
                [
                    legacy_snapshot,
                    *session.exec(
                        select(Position).where(
                            Position.snapshot_id == legacy_snapshot.snapshot_id
                        )
                    ).all(),
                ]
            )
    return _ResolutionInputs(
        batches=batches,
        legacy_snapshot=legacy_snapshot,
        legacy_snapshot_time_invalid=bool(invalid_legacy_snapshots),
        legacy_models=tuple(legacy_models),
    )


def _eligible_batches(
    batches: tuple[ImportBatch, ...],
    *,
    resolved_as_of: str,
    resolved_known_at: str,
    blockers: list[str],
) -> dict[str, list[ImportBatch]]:
    eligible: dict[str, list[ImportBatch]] = defaultdict(list)
    legacy_count = 0
    for batch in batches:
        if not batch.stable_source_id or not batch.projection_payload:
            legacy_count += 1
            continue
        observed = _batch_observed(batch)
        recorded = _batch_recorded(batch)
        if observed is None or recorded is None:
            blockers.append(f"source_time_unavailable:{batch.stable_source_id}")
            continue
        if observed <= resolved_as_of and recorded <= resolved_known_at:
            eligible[batch.stable_source_id].append(batch)
    if legacy_count and not eligible:
        blockers.append("legacy_projection_missing")
    return eligible


def _select_domain_heads(
    eligible: dict[str, list[ImportBatch]],
    blockers: list[str],
) -> list[tuple[ImportBatch, tuple[str, ...]]]:
    selected_by_batch: dict[str, tuple[ImportBatch, set[str]]] = {}
    for source_id in sorted(eligible):
        domains = sorted(
            {
                domain
                for batch in eligible[source_id]
                for domain in batch.covered_domains
            }
        )
        for domain in domains:
            head = _select_source_domain_head(
                source_id,
                domain,
                eligible[source_id],
                blockers,
            )
            if head is None:
                continue
            entry = selected_by_batch.setdefault(head.batch_id, (head, set()))
            entry[1].add(domain)
    return sorted(
        (
            (batch, tuple(sorted(domains)))
            for batch, domains in selected_by_batch.values()
        ),
        key=lambda item: (
            item[0].stable_source_id or "",
            _batch_rank(item[0]),
            item[0].batch_id,
        ),
    )


def _validated_projection_records(
    batch: ImportBatch,
    selected_domains: tuple[str, ...],
    blockers: list[str],
) -> tuple[list[dict[str, Any]], bool, bool]:
    payload = dict(batch.projection_payload or {})
    expected = batch.projection_sha256 or ""
    actual = projection_sha256(payload) if payload else ""
    if not expected or actual != expected:
        blockers.append(f"projection_digest_mismatch:{batch.batch_id}")
        return [], True, True
    if payload.get("batch_id") != batch.batch_id:
        blockers.append(f"projection_batch_mismatch:{batch.batch_id}")
        return [], True, True
    if payload.get("stable_source_id") != batch.stable_source_id:
        blockers.append(f"projection_source_mismatch:{batch.batch_id}")
        return [], True, True
    batch_records = payload.get("records")
    if not isinstance(batch_records, list):
        blockers.append(f"projection_records_invalid:{batch.batch_id}")
        return [], True, True
    valid: list[dict[str, Any]] = []
    evidence_failed = False
    for item in batch_records:
        if not isinstance(item, dict) or item.get("record_type") not in _WORLD_RECORD_MODELS:
            blockers.append(f"projection_record_unsupported:{batch.batch_id}")
            evidence_failed = True
            continue
        record_domain = _record_domain(item)
        if record_domain == "" or (
            record_domain is not None and record_domain not in selected_domains
        ):
            continue
        record_type = str(item["record_type"])
        try:
            _WORLD_RECORD_MODELS[record_type].model_validate(item.get("payload"))
        except Exception:
            blockers.append(f"projection_record_invalid:{batch.batch_id}:{record_type}")
            evidence_failed = True
            continue
        valid.append(item)
    return valid, evidence_failed, False


def _deduplicate_projected_records(
    candidates: list[tuple[str, tuple[str, str, str], dict[str, Any]]],
    blockers: list[str],
) -> list[dict[str, Any]]:
    deduplicated: dict[
        tuple[str, str, str],
        tuple[tuple[str, str, str], dict[str, Any]],
    ] = {}
    anonymous: list[tuple[str, dict[str, Any]]] = []
    for source_id, rank, item in candidates:
        identity = _record_identity(item)
        if identity is None:
            anonymous.append((source_id, item))
            continue
        key = (source_id, identity[0], identity[1])
        prior = deduplicated.get(key)
        if prior is None or rank > prior[0]:
            deduplicated[key] = (rank, item)
    source_by_identity: dict[tuple[str, str], str] = {}
    records: list[dict[str, Any]] = []
    final_candidates = [
        (key[0], value[1]) for key, value in deduplicated.items()
    ] + anonymous
    for source_id, item in final_candidates:
        identity = _record_identity(item)
        if identity is not None:
            prior_source = source_by_identity.get(identity)
            if prior_source is not None and prior_source != source_id:
                blockers.append(
                    f"source_ownership_conflict:{identity[0]}:{identity[1]}"
                )
            else:
                source_by_identity[identity] = source_id
        records.append(item)
    return records


def _compose_projected_world(
    selected_entries: list[tuple[ImportBatch, tuple[str, ...]]],
    inputs: _ResolutionInputs,
    blockers: list[str],
) -> _ProjectedComposition:
    records: list[dict[str, Any]] = []
    if not selected_entries and inputs.legacy_models:
        blockers.append("legacy_projection_missing")
        if inputs.legacy_snapshot_time_invalid:
            blockers.append("legacy_snapshot_time_invalid")
        records.extend(
            {
                "record_type": type(record).__name__,
                "payload": record.model_dump(mode="python"),
            }
            for record in inputs.legacy_models
        )
    selections: list[CapitalWorldSourceSelection] = []
    recovery_refs: set[str] = set()
    completeness_values: list[str] = []
    evidence_failed = False
    candidates: list[tuple[str, tuple[str, str, str], dict[str, Any]]] = []
    for batch, selected_domains in selected_entries:
        batch_records, invalid, fatal = _validated_projection_records(
            batch,
            selected_domains,
            blockers,
        )
        evidence_failed = evidence_failed or invalid
        candidates.extend(
            (str(batch.stable_source_id), _batch_rank(batch), item)
            for item in batch_records
        )
        if fatal:
            continue
        expected = batch.projection_sha256 or ""
        selections.append(
            CapitalWorldSourceSelection(
                stable_source_id=str(batch.stable_source_id),
                source_kind=batch.source_kind,
                batch_id=batch.batch_id,
                projection_artifact_id=str(batch.projection_artifact_id or ""),
                projection_sha256=expected,
                covered_domains=selected_domains,
                observed_at_utc=_batch_observed(batch) or "",
                recorded_at_utc=_batch_recorded(batch) or "",
            )
        )
        completeness_values.append(batch.completeness_status)
        recovery_refs.update(
            ref
            for ref in (batch.source_artifact_id, batch.projection_artifact_id)
            if ref
        )
    records.extend(_deduplicate_projected_records(candidates, blockers))
    records.sort(
        key=lambda item: (
            str(item.get("record_type") or ""),
            str(item.get("payload") or ""),
        )
    )
    return _ProjectedComposition(
        selections=tuple(selections),
        records=tuple(records),
        recovery_refs=tuple(sorted(recovery_refs)),
        completeness_values=tuple(completeness_values),
        evidence_failed=evidence_failed,
    )


def _derive_world_trust(
    composition: _ProjectedComposition,
    blockers: list[str],
) -> CapitalWorldTrust:
    positions = [
        Position.model_validate(item["payload"])
        for item in composition.records
        if item.get("record_type") == "Position"
    ]
    valuation_blocked = any(
        position.valuation_status not in {"valued", "valued_converted"}
        for position in positions
    )
    if not positions:
        blockers.append("portfolio_world_unavailable")
    if valuation_blocked:
        blockers.append("capital_valuation_blocked")
    unique_blockers = tuple(dict.fromkeys(blockers))
    if "blocked" in composition.completeness_values:
        completeness: Literal["complete", "partial", "blocked", "unavailable"] = "blocked"
    elif "partial" in composition.completeness_values:
        completeness = "partial"
    elif composition.completeness_values:
        completeness = "complete"
    else:
        completeness = "unavailable"
    status: Literal["admitted", "partial", "blocked"]
    if unique_blockers or completeness in {"blocked", "unavailable"}:
        status = "blocked"
    elif completeness == "partial":
        status = "partial"
    else:
        status = "admitted"
    evidence_integrity: Literal["intact", "unverified", "failed"] = (
        "failed"
        if composition.evidence_failed
        else "intact"
        if composition.selections
        else "unverified"
    )
    valuation_status: Literal["admitted", "blocked", "unavailable"] = (
        "unavailable" if not positions else "blocked" if valuation_blocked else "admitted"
    )
    return CapitalWorldTrust(
        status=status,
        evidence_integrity=evidence_integrity,
        completeness=completeness,
        valuation_status=valuation_status,
        blockers=unique_blockers,
    )


def _world_basis_digest(
    *,
    base_currency: str,
    legacy_snapshot: Snapshot | None,
    selections: tuple[CapitalWorldSourceSelection, ...],
) -> str:
    basis_material = {
        "schema": "finharness.capital_world_basis.v1",
        "base_currency": base_currency,
        "legacy_snapshot_id": (
            legacy_snapshot.snapshot_id if not selections and legacy_snapshot is not None else None
        ),
        "sources": [
            {
                "stable_source_id": item.stable_source_id,
                "batch_id": item.batch_id,
                "projection_sha256": item.projection_sha256,
                "covered_domains": list(item.covered_domains),
            }
            for item in selections
        ],
    }
    encoded = json.dumps(
        basis_material,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()

def resolve_capital_world(
    *,
    engine: Engine,
    as_of_utc: str | None = None,
    known_at_utc: str | None = None,
    base_currency: str = "USD",
    use_case: CapitalWorldUseCase = "capital_review",
) -> CapitalWorld:
    """Resolve one deterministic, read-only Capital World from manifested imports."""
    now = datetime.now(UTC).isoformat()
    resolved_as_of = canonical_utc(as_of_utc or now, field="as_of_utc")
    resolved_known_at = canonical_utc(known_at_utc or now, field="known_at_utc")
    clean_currency = base_currency.strip().upper()
    if len(clean_currency) != 3 or not clean_currency.isalpha():
        raise CapitalWorldResolutionError("base_currency must be a three-letter code")

    inputs = _load_resolution_inputs(engine, resolved_as_of)
    blockers: list[str] = []
    eligible = _eligible_batches(
        inputs.batches,
        resolved_as_of=resolved_as_of,
        resolved_known_at=resolved_known_at,
        blockers=blockers,
    )
    selected_entries = _select_domain_heads(eligible, blockers)
    composition = _compose_projected_world(selected_entries, inputs, blockers)
    trust = _derive_world_trust(composition, blockers)
    basis_digest = _world_basis_digest(
        base_currency=clean_currency,
        legacy_snapshot=inputs.legacy_snapshot,
        selections=composition.selections,
    )
    return CapitalWorld(
        world_id=f"capital_world_{basis_digest[:24]}",
        basis_digest=basis_digest,
        query=CapitalWorldQuery(
            as_of_utc=resolved_as_of,
            known_at_utc=resolved_known_at,
            base_currency=clean_currency,
            use_case=use_case,
        ),
        selected_sources=composition.selections,
        records=composition.records,
        trust=trust,
        recovery_refs=composition.recovery_refs,
    )


def resolve_previous_capital_world(
    *,
    engine: Engine,
    current_world: CapitalWorld,
) -> CapitalWorld | None:
    """Resolve the immediately preceding legal observation basis."""
    if current_world.selected_sources:
        current_observed = max(
            item.observed_at_utc for item in current_world.selected_sources
        )
        with Session(engine) as session:
            batches = list(session.exec(select(ImportBatch)).all())
        prior_clocks = sorted(
            {
                observed
                for batch in batches
                if batch.stable_source_id
                and batch.projection_payload
                and (observed := _batch_observed(batch)) is not None
                and (recorded := _batch_recorded(batch)) is not None
                and observed < current_observed
                and recorded <= current_world.query.known_at_utc
            }
        )
    else:
        snapshots = current_world.snapshots
        if not snapshots:
            return None
        current_observed = max(item.as_of_utc for item in snapshots)
        with Session(engine) as session:
            prior_clocks = sorted(
                item.as_of_utc
                for item in session.exec(
                    select(Snapshot).where(
                        Snapshot.kind == "portfolio",
                        Snapshot.as_of_utc < current_observed,
                    )
                ).all()
            )
    if not prior_clocks:
        return None
    return resolve_capital_world(
        engine=engine,
        as_of_utc=prior_clocks[-1],
        known_at_utc=current_world.query.known_at_utc,
        base_currency=current_world.query.base_currency,
        use_case=current_world.query.use_case,
    )
