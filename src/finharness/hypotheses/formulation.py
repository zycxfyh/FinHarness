"""Candidate selection and hypothesis formulation."""

from __future__ import annotations

from uuid import uuid4

from finharness.hypotheses._util import normalize_symbol, now_utc
from finharness.hypotheses.models import HypothesisRecord, ValidationCheck
from finharness.hypotheses.providers import (
    HypothesisDraftProvider,
    NullHypothesisDraftProvider,
)
from finharness.interpretation import InterpretationRecord, InterpretationSnapshot


def select_hypothesis_candidates(
    interpretation_snapshot: InterpretationSnapshot,
    *,
    max_hypotheses: int = 10,
    symbols: list[str] | None = None,
) -> list[InterpretationRecord]:
    allowed = {normalize_symbol(symbol) for symbol in symbols} if symbols else None
    candidates = [
        record
        for record in interpretation_snapshot.records
        if record.interpretation_id and record.event_ids and record.evidence_refs
    ]
    if allowed:
        candidates = [record for record in candidates if normalize_symbol(record.symbol) in allowed]
    return candidates[:max_hypotheses]


def build_validation_plan(record: InterpretationRecord) -> list[ValidationCheck]:
    symbol = normalize_symbol(record.symbol)
    return [
        ValidationCheck(
            check_type="event_follow_up",
            description=(
                f"Review later filings, transcripts, or official updates for {symbol} "
                f"that directly mention {', '.join(record.impact_paths[:2])}."
            ),
            required_inputs=["later_filings", "transcripts_or_official_updates"],
            expected_support="Later source evidence reinforces the same mechanism.",
            expected_disconfirm="Later source evidence contradicts or omits the mechanism.",
        ),
        ValidationCheck(
            check_type="market_reaction",
            description=(
                f"Compare {symbol} price and volume reaction after the source event with "
                "pre-event context."
            ),
            required_inputs=["MarketDataSnapshot", "IndicatorSnapshot"],
            expected_support="Reaction persists with liquidity/volume confirmation.",
            expected_disconfirm="Reaction fades or contradicts the stated mechanism.",
        ),
        ValidationCheck(
            check_type="basket_comparison",
            description=f"Compare {symbol} with SPY, QQQ, and affected basket exposures.",
            required_inputs=["MarketDataSnapshot:SPY", "MarketDataSnapshot:QQQ"],
            expected_support="Single-name reaction is not fully explained by index context.",
            expected_disconfirm="Index or basket movement explains most of the reaction.",
        ),
    ]


def expected_observations(record: InterpretationRecord) -> list[str]:
    symbol = normalize_symbol(record.symbol)
    paths = ", ".join(record.impact_paths[:3])
    return [
        f"Source updates for {symbol} continue to mention {paths} as material drivers.",
        f"Market and indicator context for {symbol} shows a reaction consistent with {paths}.",
        "SPY, QQQ, and related basket context do not fully explain the single-name reaction.",
    ]


def disconfirming_observations(record: InterpretationRecord) -> list[str]:
    symbol = normalize_symbol(record.symbol)
    return [
        "The interpretation is mostly backward-looking or already disclosed.",
        f"{symbol} reaction fades while SPY, QQQ, or related baskets explain the move.",
        "Later filings, transcripts, or official updates contradict the proposed mechanism.",
        "Human review finds the source facts too weak or too temporally mixed for validation.",
    ]


def assumptions_for_record(record: InterpretationRecord) -> list[str]:
    return [
        "The InterpretationSnapshot source facts are accurate and not stale.",
        "Market reaction must be interpreted with explicit event timing.",
        "A single event may not isolate the mechanism without basket and index context.",
    ]


def formulate_hypothesis_record(
    interpretation: InterpretationRecord,
    *,
    draft_provider: HypothesisDraftProvider | None = None,
) -> HypothesisRecord:
    provider = draft_provider or NullHypothesisDraftProvider()
    draft = provider.draft(interpretation)
    symbol = normalize_symbol(interpretation.symbol)
    mechanism = (
        f"{symbol} may transmit the source event through "
        f"{', '.join(interpretation.impact_paths[:3])}."
    )
    source_event = interpretation.event_ids[0] if interpretation.event_ids else "unknown-event"
    hypothesis = (
        f"If source event {source_event} supports the interpretation that "
        f"{interpretation.claim} is useful, then source updates, market reaction, "
        "and index/basket context should provide observable support or "
        f"disconfirmation over a {interpretation.horizon} horizon."
    )
    if draft.get("hypothesis"):
        hypothesis = str(draft["hypothesis"])
    return HypothesisRecord(
        hypothesis_id=f"hyp_{uuid4().hex[:12]}",
        source_interpretation_ids=[interpretation.interpretation_id],
        source_event_ids=interpretation.event_ids,
        symbol=symbol,
        mechanism=str(draft.get("mechanism") or mechanism),
        hypothesis=hypothesis,
        horizon=interpretation.horizon,
        expected_observations=list(
            draft.get("expected_observations") or expected_observations(interpretation)
        ),
        disconfirming_observations=list(
            draft.get("disconfirming_observations")
            or disconfirming_observations(interpretation)
        ),
        validation_plan=[
            ValidationCheck.model_validate(check)
            for check in draft.get("validation_plan", build_validation_plan(interpretation))
        ],
        assumptions=list(draft.get("assumptions") or assumptions_for_record(interpretation)),
        confidence_prior=interpretation.confidence,
        status="ready_for_validation",
        source_refs=interpretation.evidence_refs,
        draft_provider=provider.provider_name,
        draft_ref=draft.get("draft_ref"),
        created_at_utc=now_utc(),
    )
