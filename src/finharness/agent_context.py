"""L5 read-only context packs for Agent explanation.

These builders are the Capital OS read-model boundary for agents. They compose
existing deterministic read models into bounded DTOs; they do not call an LLM,
write StateCore, write receipts, or grant execution authority.
"""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, ConfigDict, field_validator
from sqlalchemy import desc
from sqlalchemy.engine import Engine
from sqlmodel import Session, select

from finharness.exposure import compute_exposure
from finharness.ips import IPS_NON_CLAIMS, check_ips_compliance, current_ips
from finharness.review_read import read_proposal_timeline
from finharness.statecore.models import Attestation, Proposal
from finharness.statecore.proposals import archived_proposal_ids

AGENT_CONTEXT_NON_CLAIMS = (
    "Agent context packs are bounded read models, not source-of-truth storage.",
    "Context packs support explanation and review; they are not recommendations.",
    "Not execution authorization.",
    "Not investment advice.",
)

PROPOSAL_CONTEXT_NON_CLAIMS = (
    "Proposal context is review evidence only.",
    "Human review records do not authorize execution.",
    "Not execution authorization.",
    "Not investment advice.",
)


class AgentContextPack(BaseModel):
    """Bounded, audit-friendly context returned to Agent tools."""

    model_config = ConfigDict(extra="forbid")

    name: str
    available: bool
    summary: dict[str, Any]
    source_refs: tuple[str, ...] = ()
    data_gaps: tuple[str, ...] = ()
    non_claims: tuple[str, ...] = AGENT_CONTEXT_NON_CLAIMS
    execution_allowed: bool = False

    @field_validator("execution_allowed")
    @classmethod
    def reject_execution_authority(cls, value: bool) -> bool:
        if value:
            raise ValueError("agent context packs never carry execution authority")
        return False


class AgentContextPackSpec(BaseModel):
    """Small Hermes-inspired spec for each exposed L5 context pack."""

    model_config = ConfigDict(frozen=True)

    name: str
    description: str
    source: str
    max_items: int = 20
    max_chars: int = 6000


CONTEXT_PACK_SPECS: dict[str, AgentContextPackSpec] = {
    "capital_summary": AgentContextPackSpec(
        name="capital_summary",
        description="Bounded summary of current exposure, data gaps, and review signals.",
        source="compute_exposure",
        max_items=10,
        max_chars=6000,
    ),
    "current_ips": AgentContextPackSpec(
        name="current_ips",
        description="Current active Investment Policy Statement, when one exists.",
        source="current_ips",
        max_items=10,
        max_chars=5000,
    ),
    "ips_check": AgentContextPackSpec(
        name="ips_check",
        description="Current IPS compliance check over the exposure read model.",
        source="check_ips_compliance",
        max_items=20,
        max_chars=6000,
    ),
    "open_proposals": AgentContextPackSpec(
        name="open_proposals",
        description="Open, active governed proposals awaiting human review.",
        source="Proposal + Attestation + archived_proposal_ids",
        max_items=10,
        max_chars=9000,
    ),
    "proposal_timeline": AgentContextPackSpec(
        name="proposal_timeline",
        description="Merged read-only review timeline for one governed proposal.",
        source="read_proposal_timeline",
        max_items=20,
        max_chars=9000,
    ),
}


def unavailable_context_pack(name: str, data_gap: str) -> AgentContextPack:
    """Return a standard unavailable pack when a read surface cannot be opened."""
    return AgentContextPack(
        name=name,
        available=False,
        summary={},
        data_gaps=(data_gap,),
        non_claims=AGENT_CONTEXT_NON_CLAIMS,
        execution_allowed=False,
    )


def build_capital_summary_context(engine: Engine) -> AgentContextPack:
    spec = CONTEXT_PACK_SPECS["capital_summary"]
    report = compute_exposure(engine)
    holdings = [
        holding.model_dump(mode="json") for holding in report.holdings[: spec.max_items]
    ]
    obligations = [
        obligation.model_dump(mode="json")
        for obligation in report.upcoming_obligations[: spec.max_items]
    ]
    data_gaps = list(report.data_gaps)
    if len(report.holdings) > len(holdings):
        data_gaps.append(f"holdings truncated to {len(holdings)} items")
    if len(report.upcoming_obligations) > len(obligations):
        data_gaps.append(f"upcoming obligations truncated to {len(obligations)} items")
    top_holding = holdings[0] if holdings else None
    summary = {
        "as_of_date": report.as_of_date,
        "base_currency": report.base_currency,
        "net_worth": report.net_worth,
        "total_assets": report.total_assets,
        "total_liabilities": report.total_liabilities,
        "cash_total": report.cash_total,
        "cash_total_verified": report.cash_total_verified,
        "cash_runway_months": report.cash_runway_months,
        "monthly_net_cashflow": report.monthly_net_cashflow,
        "holding_count": report.holding_count,
        "top_holding": top_holding,
        "top_holding_weight": report.top_holding_weight,
        "top5_weight": report.top5_weight,
        "concentration_flagged": report.concentration_flagged,
        "concentration_threshold": report.concentration_threshold,
        "interest_bearing_debt_total": report.interest_bearing_debt_total,
        "weighted_avg_interest_rate": report.weighted_avg_interest_rate,
        "insurance_active_count": report.insurance_active_count,
        "insurance_review_gaps": list(report.insurance_review_gaps[: spec.max_items]),
        "tax_review_gaps": list(report.tax_review_gaps[: spec.max_items]),
        "holdings": holdings,
        "upcoming_obligations": obligations,
    }
    return _pack(
        name=spec.name,
        available=True,
        summary=summary,
        source_refs=report.source_refs,
        data_gaps=tuple(data_gaps),
        non_claims=tuple(_dedupe([*report.non_claims, *AGENT_CONTEXT_NON_CLAIMS])),
        spec=spec,
    )


def build_current_ips_context(engine: Engine) -> AgentContextPack:
    spec = CONTEXT_PACK_SPECS["current_ips"]
    ips = current_ips(engine)
    if ips is None:
        return AgentContextPack(
            name=spec.name,
            available=False,
            summary={},
            data_gaps=("No active IPS has been recorded.",),
            non_claims=IPS_NON_CLAIMS,
            execution_allowed=False,
        )
    receipt_ref = ips.receipt_ref or ""
    summary = {
        "ips_id": ips.ips_id,
        "status": ips.status,
        "base_currency": ips.base_currency,
        "created_at_utc": ips.created_at_utc,
        "receipt_ref": receipt_ref or None,
        "thresholds": {
            "liquidity_floor_months": str(ips.liquidity_floor_months),
            "max_single_holding_pct": str(ips.max_single_holding_pct),
            "cash_overweight_pct": (
                str(ips.cash_overweight_pct) if ips.cash_overweight_pct is not None else None
            ),
            "high_interest_rate_pct": (
                str(ips.high_interest_rate_pct)
                if ips.high_interest_rate_pct is not None
                else None
            ),
        },
        "allowed_asset_classes": list(ips.allowed_asset_classes),
        "restricted_actions": list(ips.restricted_actions),
        "review_cadence": ips.review_cadence,
    }
    return _pack(
        name=spec.name,
        available=True,
        summary=summary,
        source_refs=_refs([*ips.source_refs, receipt_ref]),
        data_gaps=(),
        non_claims=IPS_NON_CLAIMS,
        spec=spec,
    )


def build_ips_check_context(engine: Engine) -> AgentContextPack:
    spec = CONTEXT_PACK_SPECS["ips_check"]
    ips = current_ips(engine)
    if ips is None:
        return AgentContextPack(
            name=spec.name,
            available=False,
            summary={},
            data_gaps=("No active IPS has been recorded; compliance cannot be checked.",),
            non_claims=IPS_NON_CLAIMS,
            execution_allowed=False,
        )
    report = compute_exposure(engine)
    check = check_ips_compliance(report, ips)
    results = [result.model_dump(mode="json") for result in check.results[: spec.max_items]]
    data_gaps = list(report.data_gaps)
    if len(check.results) > len(results):
        data_gaps.append(f"IPS rule results truncated to {len(results)} items")
    summary = {
        "ips_id": check.ips_id,
        "as_of_date": check.as_of_date,
        "violations": list(check.violations),
        "blocked": list(check.blocked),
        "results": results,
    }
    return _pack(
        name=spec.name,
        available=True,
        summary=summary,
        source_refs=check.source_refs,
        data_gaps=tuple(data_gaps),
        non_claims=check.non_claims,
        spec=spec,
    )


def build_open_proposals_context(engine: Engine, *, limit: int = 10) -> AgentContextPack:
    spec = CONTEXT_PACK_SPECS["open_proposals"]
    item_limit = _clamp_limit(limit, spec.max_items)
    archived = archived_proposal_ids(engine)
    with Session(engine) as session:
        proposals = list(
            session.exec(
                select(Proposal).order_by(
                    desc(Proposal.created_at_utc),
                    desc(Proposal.proposal_id),
                )
            ).all()
        )
        attestations = list(session.exec(select(Attestation)).all())
    attested = {attestation.proposal_id for attestation in attestations}
    open_proposals = [
        proposal
        for proposal in proposals
        if proposal.proposal_id not in attested and proposal.proposal_id not in archived
    ]
    items = [_proposal_summary(proposal) for proposal in open_proposals[:item_limit]]
    source_refs = _refs(
        ref
        for proposal in open_proposals[:item_limit]
        for ref in [proposal.receipt_ref, *proposal.source_refs]
    )
    data_gaps: list[str] = []
    if len(open_proposals) > len(items):
        data_gaps.append(f"open proposals truncated to {len(items)} items")
    summary = {
        "open_count": len(open_proposals),
        "returned_count": len(items),
        "items": items,
    }
    return _pack(
        name=spec.name,
        available=True,
        summary=summary,
        source_refs=source_refs,
        data_gaps=tuple(data_gaps),
        non_claims=PROPOSAL_CONTEXT_NON_CLAIMS,
        spec=spec,
    )


def build_proposal_timeline_context(
    engine: Engine, proposal_id: str, *, limit: int = 20
) -> AgentContextPack:
    spec = CONTEXT_PACK_SPECS["proposal_timeline"]
    item_limit = _clamp_limit(limit, spec.max_items)
    timeline = read_proposal_timeline(engine, proposal_id)
    if timeline is None:
        return AgentContextPack(
            name=spec.name,
            available=False,
            summary={"proposal_id": proposal_id},
            data_gaps=(f"Proposal not found: {proposal_id}",),
            non_claims=PROPOSAL_CONTEXT_NON_CLAIMS,
            execution_allowed=False,
        )
    entries = [_timeline_entry_summary(entry) for entry in timeline.entries[:item_limit]]
    source_refs = _refs(
        ref for entry in entries for ref in entry.get("source_refs", ())
    )
    data_gaps: list[str] = []
    if len(timeline.entries) > len(entries):
        data_gaps.append(f"proposal timeline truncated to {len(entries)} entries")
    summary = {
        "proposal_id": timeline.proposal_id,
        "is_archived": timeline.is_archived,
        "entry_count": len(timeline.entries),
        "returned_count": len(entries),
        "entries": entries,
    }
    return _pack(
        name=spec.name,
        available=True,
        summary=summary,
        source_refs=source_refs,
        data_gaps=tuple(data_gaps),
        non_claims=PROPOSAL_CONTEXT_NON_CLAIMS,
        spec=spec,
    )


def _pack(
    *,
    name: str,
    available: bool,
    summary: dict[str, Any],
    source_refs: tuple[str, ...],
    data_gaps: tuple[str, ...],
    non_claims: tuple[str, ...],
    spec: AgentContextPackSpec,
) -> AgentContextPack:
    bounded_refs = _refs(source_refs)
    bounded_data_gaps = _dedupe(data_gaps)
    if len(bounded_refs) > spec.max_items:
        bounded_data_gaps.append(f"source refs truncated to {spec.max_items} items")
    pack = AgentContextPack(
        name=name,
        available=available,
        summary=_bounded_value(summary, max_items=spec.max_items),
        source_refs=bounded_refs[: spec.max_items],
        data_gaps=tuple(bounded_data_gaps),
        non_claims=tuple(_dedupe(non_claims)),
        execution_allowed=False,
    )
    return _fit_pack_to_budget(pack, spec)


def _fit_pack_to_budget(
    pack: AgentContextPack, spec: AgentContextPackSpec
) -> AgentContextPack:
    if len(pack.model_dump_json()) <= spec.max_chars:
        return pack
    compacted = pack.model_copy(
        update={
            "summary": _bounded_value(
                pack.summary,
                max_items=max(1, spec.max_items // 2),
                max_string_chars=240,
            ),
            "data_gaps": tuple(
                _dedupe(
                    [
                        *pack.data_gaps,
                        f"context pack exceeded {spec.max_chars} chars; summary was compacted",
                    ]
                )
            ),
        }
    )
    if len(compacted.model_dump_json()) <= spec.max_chars:
        return compacted
    marker = compacted.model_copy(
        update={
            "summary": {"compacted": True},
            "data_gaps": tuple(
                _dedupe(
                    [
                        *compacted.data_gaps,
                        (
                            f"context pack exceeded {spec.max_chars} chars; "
                            "summary was replaced by compact marker"
                        ),
                    ]
                )
            ),
        }
    )
    if len(marker.model_dump_json()) <= spec.max_chars:
        return marker
    return marker.model_copy(
        update={
            "source_refs": (),
            "data_gaps": (
                f"context pack exceeded {spec.max_chars} chars; "
                "summary and source refs were replaced by compact markers",
            ),
            "non_claims": ("Not execution authorization.", "Not investment advice."),
        }
    )


def _proposal_summary(proposal: Proposal) -> dict[str, Any]:
    return {
        "proposal_id": proposal.proposal_id,
        "kind": proposal.kind,
        "claim": _truncate_text(proposal.claim),
        "created_at_utc": proposal.created_at_utc,
        "authority_level": proposal.authority_level,
        "receipt_ref": proposal.receipt_ref,
        "decision_scaffold": _bounded_value(proposal.decision_scaffold, max_items=12),
        "evidence": _bounded_value(proposal.evidence, max_items=12),
        "assumption_keys": sorted(proposal.assumptions),
        "limitation_keys": sorted(proposal.limitations),
        "source_refs": list(_refs([proposal.receipt_ref, *proposal.source_refs])),
        "execution_allowed": False,
    }


def _timeline_entry_summary(entry: Any) -> dict[str, Any]:
    detail = entry.detail if isinstance(entry.detail, dict) else {}
    source_refs = _refs(detail.get("source_refs", ()))
    out = {
        "source_type": entry.source_type,
        "id": entry.id,
        "kind": entry.kind,
        "created_at_utc": entry.created_at_utc,
        "attester": entry.attester,
        "reason": _truncate_text(entry.reason),
        "source_refs": list(source_refs),
        "execution_allowed": False,
    }
    for key in ("decision", "text", "attestation_ref", "compare_with"):
        value = detail.get(key)
        if value:
            out[key] = _bounded_value(value, max_items=5)
    note = detail.get("agent_review_note")
    if isinstance(note, dict):
        out["agent_review_note"] = _bounded_value(note, max_items=12)
    return out


def _bounded_value(value: Any, *, max_items: int, max_string_chars: int = 500) -> Any:
    if isinstance(value, dict):
        return {
            str(key): _bounded_value(
                child,
                max_items=max_items,
                max_string_chars=max_string_chars,
            )
            for key, child in list(value.items())[:max_items]
        }
    if isinstance(value, (list, tuple)):
        return [
            _bounded_value(
                child,
                max_items=max_items,
                max_string_chars=max_string_chars,
            )
            for child in list(value)[:max_items]
        ]
    if isinstance(value, str):
        return _truncate_text(value, max_chars=max_string_chars)
    try:
        json.dumps(value)
        return value
    except TypeError:
        return str(value)


def _truncate_text(value: str, *, max_chars: int = 500) -> str:
    if len(value) <= max_chars:
        return value
    return value[: max_chars - 15].rstrip() + "... [truncated]"


def _clamp_limit(limit: int, max_items: int) -> int:
    return max(1, min(int(limit), max_items))


def _refs(values: Any) -> tuple[str, ...]:
    return tuple(sorted({str(value) for value in values if value}))


def _dedupe(values: Any) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        text = str(value)
        if text and text not in seen:
            seen.add(text)
            out.append(text)
    return out
