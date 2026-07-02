"""Receipt-backed CapitalMandate policy domain.

Capital mandates sit above the IPS as a human-attested policy domain for future
delegated capital authority. They are policy scaffolding only: no execution
authorization, no authority transition, no broker instruction, and no order
ticket.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from sqlalchemy import Engine
from sqlmodel import Session, col, select

from finharness.ips import DEFAULT_IPS_RECEIPT_ROOT, current_ips
from finharness.market_data import ROOT
from finharness.statecore.models import CapitalMandate, InvestmentPolicyStatement, ReceiptIndex
from finharness.statecore.receipt_io import (
    atomic_write_json,
    remove_file_best_effort,
    resolve_under,
)
from finharness.statecore.store import StateCoreStoreError, upsert_records

DEFAULT_CAPITAL_MANDATE_RECEIPT_ROOT = DEFAULT_IPS_RECEIPT_ROOT

CAPITAL_MANDATE_NON_CLAIMS = (
    "CapitalMandate is a human-attested policy domain, not investment advice.",
    "CapitalMandate does not grant an Agent identity or delegated authority.",
    "CapitalMandate is not an AuthorityContract, order ticket, or broker instruction.",
    "CapitalMandate does not authorize execution or live capital movement.",
)


class CapitalMandateValidationError(ValueError):
    """Raised when a capital mandate write would cross its policy boundary."""


def current_capital_mandate(engine: Engine) -> CapitalMandate | None:
    """Return the latest active CapitalMandate, or ``None`` when none exists."""
    with Session(engine) as session:
        statement = (
            select(CapitalMandate)
            .where(CapitalMandate.status == "active")
            .order_by(col(CapitalMandate.created_at_utc).desc())
            .limit(1)
        )
        return session.exec(statement).first()


def record_capital_mandate(
    *,
    profile_snapshot: Mapping[str, Any],
    investment_objectives: Mapping[str, Any],
    risk_profile: Mapping[str, Any],
    human_attester: str,
    human_reason: str,
    explicit_confirmation: bool,
    engine: Engine,
    receipt_root: str | Path = DEFAULT_CAPITAL_MANDATE_RECEIPT_ROOT,
    allowed_asset_classes: Sequence[str] | None = None,
    restricted_asset_classes: Sequence[str] | None = None,
    allowed_action_types: Sequence[str] | None = None,
    restricted_action_types: Sequence[str] | None = None,
    autonomy_level: str = "L1_candidate_only",
    limit_book: Mapping[str, Any] | None = None,
    kill_switch_rules: Sequence[Mapping[str, Any]] | None = None,
    review_cadence: Mapping[str, Any] | None = None,
    source_ips_id: str | None = None,
    source_refs: Sequence[str] | None = None,
    receipt_refs: Sequence[str] | None = None,
    capital_mandate_id: str | None = None,
    created_at_utc: str | None = None,
) -> CapitalMandate:
    """Write a receipt-backed active CapitalMandate.

    Previously active mandates are marked ``superseded``. The receipt file is the
    source of truth; the SQLite row is the queryable mirror.
    """
    _require_attestation(
        human_attester=human_attester,
        human_reason=human_reason,
        explicit_confirmation=explicit_confirmation,
    )
    created_at = created_at_utc or _now_utc()
    resolved_id = (
        _safe_id(capital_mandate_id)
        if capital_mandate_id
        else f"capital_mandate_{_stamp()}_{uuid4().hex[:8]}"
    )
    source_ips = _resolve_source_ips(engine, source_ips_id=source_ips_id)
    resolved_receipt_refs = list(receipt_refs or [])
    if (
        source_ips
        and source_ips.receipt_ref
        and source_ips.receipt_ref not in resolved_receipt_refs
    ):
        resolved_receipt_refs.append(source_ips.receipt_ref)

    receipt_id = f"receipt_capital_mandate_{_stamp()}_{uuid4().hex[:8]}"
    receipt_path = resolve_under(receipt_root, "capital-mandates", f"{receipt_id}.json")
    mandate = CapitalMandate(
        capital_mandate_id=resolved_id,
        status="active",
        source_ips_id=source_ips.ips_id if source_ips else None,
        profile_snapshot=dict(profile_snapshot),
        investment_objectives=dict(investment_objectives),
        risk_profile=dict(risk_profile),
        allowed_asset_classes=list(allowed_asset_classes or []),
        restricted_asset_classes=list(restricted_asset_classes or []),
        allowed_action_types=list(allowed_action_types or []),
        restricted_action_types=list(restricted_action_types or []),
        autonomy_level=autonomy_level,
        limit_book=dict(limit_book or {}),
        kill_switch_rules=[dict(rule) for rule in (kill_switch_rules or [])],
        review_cadence=dict(review_cadence or {}),
        human_attester=human_attester.strip(),
        human_reason=human_reason.strip(),
        explicit_confirmation=True,
        source_refs=list(source_refs or []),
        receipt_refs=resolved_receipt_refs,
        non_claims=list(CAPITAL_MANDATE_NON_CLAIMS),
        receipt_ref=_display_path(receipt_path),
        execution_allowed=False,
        authority_transition=False,
        created_at_utc=created_at,
        as_of_utc=created_at,
    )
    receipt_existed = receipt_path.exists()
    atomic_write_json(
        receipt_path,
        _capital_mandate_receipt_payload(
            mandate=mandate,
            receipt_id=receipt_id,
            source_ips=source_ips,
        ),
    )
    display = _display_path(receipt_path)
    index = ReceiptIndex(
        receipt_id=receipt_id,
        kind="state_core_capital_mandate",
        path=display,
        created_at_utc=created_at,
        source_refs=[display, *mandate.source_refs],
        refs=[resolved_id, *_source_ips_refs(mandate), *mandate.receipt_refs],
    )
    superseded = _supersede_active_mandates(engine, keep=resolved_id)
    try:
        upsert_records([*superseded, mandate, index], engine=engine)
    except StateCoreStoreError:
        if not receipt_existed:
            remove_file_best_effort(receipt_path)
        raise
    return mandate


def _resolve_source_ips(
    engine: Engine,
    *,
    source_ips_id: str | None,
) -> InvestmentPolicyStatement | None:
    if source_ips_id is None:
        return current_ips(engine)
    with Session(engine) as session:
        ips = session.get(InvestmentPolicyStatement, source_ips_id)
    if ips is None:
        raise KeyError(source_ips_id)
    return ips


def _require_attestation(
    *,
    human_attester: str,
    human_reason: str,
    explicit_confirmation: bool,
) -> None:
    if not human_attester.strip():
        raise CapitalMandateValidationError("human_attester is required")
    if not human_reason.strip():
        raise CapitalMandateValidationError("human_reason is required")
    if not explicit_confirmation:
        raise CapitalMandateValidationError("explicit_confirmation must be true")


def _capital_mandate_receipt_payload(
    *,
    mandate: CapitalMandate,
    receipt_id: str,
    source_ips: InvestmentPolicyStatement | None,
) -> dict[str, Any]:
    return {
        "receipt_id": receipt_id,
        "kind": "state_core_capital_mandate",
        "created_at_utc": mandate.created_at_utc,
        "capital_mandate": mandate.model_dump(mode="json"),
        "source_ips": source_ips.model_dump(mode="json") if source_ips else None,
        "governance_boundary": {
            "execution_allowed": False,
            "authority_transition": False,
            "explicit_confirmation": True,
            "human_attested_policy_domain": True,
            "future_authority_basis": True,
            "not_execution_authorization": True,
            "not_agent_identity_grant": True,
            "not_authority_contract": True,
            "not_order_ticket": True,
        },
        "non_claims": list(CAPITAL_MANDATE_NON_CLAIMS),
    }


def _source_ips_refs(mandate: CapitalMandate) -> list[str]:
    return [mandate.source_ips_id] if mandate.source_ips_id else []


def _supersede_active_mandates(engine: Engine, *, keep: str) -> list[CapitalMandate]:
    with Session(engine) as session:
        rows = session.exec(
            select(CapitalMandate).where(CapitalMandate.status == "active")
        ).all()
    superseded: list[CapitalMandate] = []
    for row in rows:
        if row.capital_mandate_id == keep:
            continue
        row.status = "superseded"
        superseded.append(row)
    return superseded


def _now_utc() -> str:
    return datetime.now(UTC).isoformat()


def _stamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def _safe_id(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in {"_", "-"} else "_" for ch in value)


def _display_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(ROOT).as_posix()
    except ValueError:
        return str(resolved)
