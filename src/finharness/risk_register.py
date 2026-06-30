"""Derived review risk register.

The register is a read-only view over review queue triage. It does not persist
risk state, score investments, accept risk, or authorize any action.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from finharness.review_read import ReviewQueueItem, read_review_queue

RiskKind = Literal[
    "evidence_gap",
    "stale_context",
    "duplicate_proposal",
    "policy_mismatch",
    "counter_evidence_needed",
    "agent_reported_risk",
    "open_question",
]
RiskStatus = Literal["open", "reviewed", "archived"]
SeverityHint = Literal["high", "medium", "low"]

RISK_REGISTER_NON_CLAIMS: tuple[str, ...] = (
    "Risk register is a derived review surface, not investment advice.",
    "Risk severity is a triage hint and does not authorize action.",
    "Risk register items are not approval, attestation, rejection, or execution authorization.",
)


@dataclass(frozen=True)
class RiskRegisterItem:
    risk_id: str
    risk_kind: RiskKind
    title: str
    description: str
    severity_hint: SeverityHint
    status: RiskStatus
    source_type: str
    related_proposal_ids: list[str]
    evidence_status: str
    risk_reasons: list[str]
    data_gaps: list[str]
    open_questions: list[str]
    source_refs: list[str]
    receipt_refs: list[str]
    next_actions: list[str]
    non_claims: tuple[str, ...] = RISK_REGISTER_NON_CLAIMS
    execution_allowed: bool = False
    authority_transition: bool = False


@dataclass(frozen=True)
class RiskRegister:
    items: list[RiskRegisterItem]
    non_claims: tuple[str, ...] = RISK_REGISTER_NON_CLAIMS
    execution_allowed: bool = False
    authority_transition: bool = False


def _status(item: ReviewQueueItem) -> RiskStatus:
    if item.status == "archived":
        return "archived"
    if item.status == "reviewed":
        return "reviewed"
    return "open"


def _severity(item: ReviewQueueItem) -> SeverityHint:
    if item.priority == "high":
        return "high"
    if item.priority == "low":
        return "low"
    return "medium"


def _risk_id(item: ReviewQueueItem, risk_kind: RiskKind) -> str:
    return f"risk:{item.proposal_id}:{risk_kind}"


def _reasons_with_needles(item: ReviewQueueItem, needles: tuple[str, ...]) -> list[str]:
    matches: list[str] = []
    for reason in item.triage_reasons:
        normalized = reason.lower()
        if any(needle in normalized for needle in needles):
            matches.append(reason)
    return matches


def _dedupe(values: list[str]) -> list[str]:
    return sorted({value for value in values if value})


def _risk_item(
    item: ReviewQueueItem,
    *,
    risk_kind: RiskKind,
    title: str,
    description: str,
    related_proposal_ids: list[str] | None = None,
    risk_reasons: list[str] | None = None,
    data_gaps: list[str] | None = None,
    open_questions: list[str] | None = None,
    next_actions: list[str] | None = None,
) -> RiskRegisterItem:
    return RiskRegisterItem(
        risk_id=_risk_id(item, risk_kind),
        risk_kind=risk_kind,
        title=title,
        description=description,
        severity_hint=_severity(item),
        status=_status(item),
        source_type="review_queue",
        related_proposal_ids=_dedupe(related_proposal_ids or [item.proposal_id]),
        evidence_status=item.evidence_status,
        risk_reasons=_dedupe(risk_reasons or item.triage_reasons),
        data_gaps=_dedupe(data_gaps or []),
        open_questions=_dedupe(open_questions or []),
        source_refs=_dedupe(item.source_refs),
        receipt_refs=_dedupe(item.receipt_refs),
        next_actions=_dedupe(next_actions or item.next_actions),
        execution_allowed=False,
        authority_transition=False,
    )


def _items_for_queue_item(item: ReviewQueueItem) -> list[RiskRegisterItem]:
    risks: list[RiskRegisterItem] = []

    evidence_reasons = _reasons_with_needles(
        item,
        ("source references", "data gap", "missing evidence"),
    )
    if item.data_gaps or (
        item.evidence_status == "incomplete" and evidence_reasons
    ):
        risks.append(
            _risk_item(
                item,
                risk_kind="evidence_gap",
                title="Proposal has unresolved evidence gaps",
                description=(
                    "Review queue triage reports incomplete or missing evidence "
                    "before this proposal can be reviewed safely."
                ),
                risk_reasons=evidence_reasons
                or ["Review queue reports incomplete evidence."],
                data_gaps=item.data_gaps,
            )
        )

    if item.stale_context_flags:
        risks.append(
            _risk_item(
                item,
                risk_kind="stale_context",
                title="Proposal depends on stale or inconsistent context",
                description=(
                    "Review queue triage found stale, missing, or inconsistent "
                    "context evidence for this proposal."
                ),
                risk_reasons=item.stale_context_flags,
                data_gaps=item.stale_context_flags,
            )
        )

    policy_reasons = _reasons_with_needles(item, ("policy", "ips mismatch"))
    if policy_reasons:
        risks.append(
            _risk_item(
                item,
                risk_kind="policy_mismatch",
                title="Proposal may conflict with IPS or policy facts",
                description=(
                    "Review queue triage reports a policy or IPS mismatch that "
                    "must stay visible before human review progresses."
                ),
                risk_reasons=policy_reasons,
            )
        )

    counter_reasons = _reasons_with_needles(item, ("counter-evidence", "counter evidence"))
    if counter_reasons:
        risks.append(
            _risk_item(
                item,
                risk_kind="counter_evidence_needed",
                title="Proposal needs counter-evidence before review",
                description=(
                    "The decision scaffold lacks required counter-evidence for "
                    "the current proposal risk posture."
                ),
                risk_reasons=counter_reasons,
            )
        )

    if item.duplicate_candidates:
        risks.append(
            _risk_item(
                item,
                risk_kind="duplicate_proposal",
                title="Proposal may duplicate another open proposal",
                description=(
                    "Review queue triage found another open proposal with the "
                    "same kind and claim."
                ),
                related_proposal_ids=[item.proposal_id, *item.duplicate_candidates],
                risk_reasons=[
                    "Another open proposal has the same kind and claim.",
                ],
                next_actions=["compare duplicate candidates before progressing review"],
            )
        )

    if item.risks:
        risks.append(
            _risk_item(
                item,
                risk_kind="agent_reported_risk",
                title="Agent review note reports risks",
                description=(
                    "An append-only AgentReviewNoteDraft surfaced risk language "
                    "for human review."
                ),
                risk_reasons=item.risks,
            )
        )

    if item.open_questions:
        risks.append(
            _risk_item(
                item,
                risk_kind="open_question",
                title="Proposal has unresolved review questions",
                description=(
                    "Open questions remain before the reviewer can compare the "
                    "proposal evidence cleanly."
                ),
                risk_reasons=["Agent review note reports open questions."],
                open_questions=item.open_questions,
                next_actions=["answer Agent open questions"],
            )
        )

    return risks


def read_review_risk_register(
    engine: Any,
    *,
    receipt_root: Path,
    limit: int = 100,
    include_closed: bool = False,
) -> RiskRegister:
    """Build a deterministic, read-only risk register from review queue triage."""

    queue = read_review_queue(
        engine,
        receipt_root=receipt_root,
        limit=max(limit, 200),
        include_closed=include_closed,
    )
    items = [
        risk_item
        for queue_item in queue.items
        for risk_item in _items_for_queue_item(queue_item)
    ]
    status_order = {"open": 0, "reviewed": 1, "archived": 2}
    severity_order = {"high": 0, "medium": 1, "low": 2}
    items.sort(
        key=lambda risk_item: (
            status_order[risk_item.status],
            severity_order[risk_item.severity_hint],
            risk_item.risk_id,
        )
    )
    return RiskRegister(items=items[:limit])
