"""Fifth-layer falsifiable hypothesis governance.

Hypotheses convert source-backed interpretations into testable research
statements. They do not validate, recommend, or authorize execution.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, Protocol
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from finharness.interpretation import InterpretationRecord, InterpretationSnapshot
from finharness.market_data import ROOT, display_path, sha256_text

HYPOTHESIS_NORMALIZED_ROOT = ROOT / "data" / "normalized" / "hypotheses"
HYPOTHESIS_RECEIPT_ROOT = ROOT / "data" / "receipts" / "hypotheses"

HypothesisStatus = Literal["draft", "ready_for_validation", "failed_quality"]
ConfidencePrior = Literal["low", "medium", "high", "unknown"]

RECOMMENDATION_PATTERNS = [
    r"\bbuy\b(?!-side)",
    r"\bsell\b(?!-side)",
    r"\bhold\b",
    r"\bshort\b(?!-term|-run|-dated|-horizon)",
    r"\blong\b(?!-term|-run|-dated|-horizon)",
    r"\boverweight\b",
    r"\bunderweight\b",
    r"\btarget price\b",
    r"\bprice target\b",
    r"\btake profit\b",
    r"\bstop loss\b",
    r"\bposition sizing\b",
    r"\bplace order\b",
    r"\bexecute\b",
    r"\btrade recommendation\b",
    "买入",
    "卖出",
    "持有",
    "做多",
    "做空",
    "加仓",
    "减仓",
    "开仓",
    "平仓",
    "目标价",
    "止损",
    "止盈",
    "仓位",
    "下单",
    "执行",
]

VALIDATED_PATTERNS = [
    r"\bvalidated\b",
    r"\bproven\b",
    r"\bconfirmed alpha\b",
    r"\bguaranteed\b",
    "已经验证",
    "已经证明",
    "确定",
    "保证",
]


class HypothesisDraftProvider(Protocol):
    """Optional draft provider interface for future LLM integrations."""

    provider_name: str

    def draft(self, interpretation: InterpretationRecord) -> dict[str, Any]:
        """Return optional draft fields for a hypothesis record."""


class NullHypothesisDraftProvider:
    """Default provider: deterministic layer, no LLM call."""

    provider_name = "none"

    def draft(self, interpretation: InterpretationRecord) -> dict[str, Any]:
        return {}


HERMES_DRAFT_ROOT = ROOT / "data" / "cache" / "hermes-drafts"
HERMES_DRAFT_PROMPT_VERSION = "finharness.hypotheses.hermes_prompt.v1"
ALLOWED_DRAFT_CHECK_TYPES = frozenset(
    {
        "market_reaction",
        "indicator_context",
        "event_follow_up",
        "basket_comparison",
        "human_review",
    }
)


def build_hermes_hypothesis_prompt(interpretation: InterpretationRecord) -> str:
    facts = "\n".join(f"- {item}" for item in interpretation.source_facts[:6])
    counter = "\n".join(f"- {item}" for item in interpretation.counterevidence[:4])
    return (
        "You are a research assistant drafting ONE falsifiable market-research "
        "hypothesis for an evidence-governed harness. This is research drafting "
        "only: no trade recommendations, no buy/sell/hold language, no price "
        "targets, no position sizing, no execution instructions. The draft is "
        "checked by deterministic quality gates and never authorizes any action.\n\n"
        f"Symbol: {interpretation.symbol}\n"
        f"Claim under interpretation: {interpretation.claim}\n"
        f"Inference: {interpretation.inference}\n"
        f"Impact paths: {', '.join(interpretation.impact_paths[:4])}\n"
        f"Horizon: {interpretation.horizon}\n"
        f"Source facts:\n{facts or '- none provided'}\n"
        f"Known counterevidence:\n{counter or '- none provided'}\n\n"
        "Respond with ONLY one JSON object, no prose, with exactly these keys:\n"
        "{\n"
        '  "hypothesis": "one falsifiable if-then statement tied to the claim",\n'
        '  "mechanism": "one sentence on the causal transmission path",\n'
        '  "expected_observations": ["2-4 observations that would support it"],\n'
        '  "disconfirming_observations": ["2-4 observations that would falsify it"],\n'
        '  "assumptions": ["2-3 assumptions; at least one must state how event '
        'timing is separated from market reaction"]\n'
        "}"
    )


def sanitize_hermes_draft(payload: dict[str, Any]) -> dict[str, Any]:
    """Keep only contract keys with the right shapes; drop everything else.

    The downstream quality gates re-check content (blocked language,
    falsifiability fields), so this only enforces structure, not safety.
    """
    draft: dict[str, Any] = {}
    if isinstance(payload.get("hypothesis"), str) and payload["hypothesis"].strip():
        draft["hypothesis"] = payload["hypothesis"].strip()
    if isinstance(payload.get("mechanism"), str) and payload["mechanism"].strip():
        draft["mechanism"] = payload["mechanism"].strip()
    for key in ("expected_observations", "disconfirming_observations", "assumptions"):
        value = payload.get(key)
        if isinstance(value, list):
            items = [str(item).strip() for item in value if str(item).strip()]
            if items:
                draft[key] = items[:6]
    plan = payload.get("validation_plan")
    if isinstance(plan, list):
        valid = [
            item
            for item in plan
            if isinstance(item, dict)
            and item.get("check_type") in ALLOWED_DRAFT_CHECK_TYPES
        ]
        if valid and len(valid) == len(plan):
            draft["validation_plan"] = valid
    return draft


class HermesHypothesisDraftProvider:
    """Generator-seat LLM drafting via the local hermes-agent CLI.

    Fail-closed contract: any bridge, parsing, or sanitization failure returns
    a draft without content keys, so formulate_hypothesis_record falls back to
    the deterministic template field by field. The raw exchange is persisted
    under data/cache/hermes-drafts/ and referenced via draft_ref.
    """

    provider_name = "hermes-agent"

    def __init__(
        self,
        *,
        hermes_root: str | Path = "/root/projects/hermes-agent",
        timeout_seconds: int = 180,
    ) -> None:
        self.hermes_root = Path(hermes_root)
        self.timeout_seconds = timeout_seconds

    def draft(self, interpretation: InterpretationRecord) -> dict[str, Any]:
        from finharness.hermes_bridge import (
            HermesBridgeError,
            extract_json_object,
            run_hermes_single_query,
        )

        prompt = build_hermes_hypothesis_prompt(interpretation)
        base: dict[str, Any] = {
            "provider": self.provider_name,
            "prompt_template_version": HERMES_DRAFT_PROMPT_VERSION,
            "source_interpretation_id": interpretation.interpretation_id,
        }
        raw_output: str | None = None
        try:
            raw_output = run_hermes_single_query(
                prompt, timeout_seconds=self.timeout_seconds
            )
            parsed = extract_json_object(raw_output)
            draft = sanitize_hermes_draft(parsed)
            base.update(draft)
            base["enabled"] = True
        except HermesBridgeError as exc:
            base["enabled"] = False
            base["error"] = str(exc)
        base["draft_ref"] = self._persist_draft(
            interpretation=interpretation, prompt=prompt, raw_output=raw_output, draft=base
        )
        return base

    def _persist_draft(
        self,
        *,
        interpretation: InterpretationRecord,
        prompt: str,
        raw_output: str | None,
        draft: dict[str, Any],
    ) -> str | None:
        try:
            HERMES_DRAFT_ROOT.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
            path = (
                HERMES_DRAFT_ROOT
                / f"{stamp}-{interpretation.interpretation_id}-{uuid4().hex[:8]}.json"
            )
            path.write_text(
                json.dumps(
                    {
                        "prompt_template_version": HERMES_DRAFT_PROMPT_VERSION,
                        "interpretation_id": interpretation.interpretation_id,
                        "prompt": prompt,
                        "raw_output": raw_output,
                        "draft": {k: v for k, v in draft.items() if k != "draft_ref"},
                    },
                    ensure_ascii=False,
                    indent=2,
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )
            return display_path(path)
        except OSError:
            return None


class HypothesisSourceSpec(BaseModel):
    """Source/config layer for hypothesis generation."""

    model_config = ConfigDict(frozen=True)

    provider: str = "FinHarness rule-guided hypotheses"
    method: str = "rule_guided_template"
    input_layer: str = "interpretation"
    template_version: str = "finharness.hypotheses.template.v1"
    llm_provider: str | None = None
    llm_interface: str | None = None
    llm_enabled: bool = False
    hermes_root: str | None = "/root/projects/hermes-agent"
    config: dict[str, Any] = Field(default_factory=dict)


class ValidationCheck(BaseModel):
    """A concrete next-layer validation check."""

    model_config = ConfigDict(frozen=True)

    check_type: Literal[
        "market_reaction",
        "indicator_context",
        "event_follow_up",
        "basket_comparison",
        "human_review",
    ]
    description: str
    required_inputs: list[str]
    expected_support: str
    expected_disconfirm: str


class HypothesisRecord(BaseModel):
    """A falsifiable source-backed research hypothesis."""

    model_config = ConfigDict(frozen=True)

    hypothesis_id: str
    source_interpretation_ids: list[str]
    source_event_ids: list[str]
    symbol: str
    mechanism: str
    hypothesis: str
    horizon: str
    expected_observations: list[str]
    disconfirming_observations: list[str]
    validation_plan: list[ValidationCheck]
    assumptions: list[str]
    confidence_prior: ConfidencePrior
    status: HypothesisStatus
    source_refs: list[str]
    draft_provider: str = "none"
    draft_ref: str | None = None
    created_at_utc: str


class HypothesisQuality(BaseModel):
    """Quality gates for fifth-layer hypotheses."""

    model_config = ConfigDict(frozen=True)

    ok: bool
    record_count: int
    source_backed_hypotheses: bool
    testable_predictions_present: bool
    disconfirming_evidence_present: bool
    horizon_present: bool
    validation_plan_present: bool
    no_execution_language: bool
    no_recommendation_language: bool
    claim_not_marked_validated: bool
    temporal_context_separated: bool
    duplicate_hypothesis_check: bool
    missing_required_fields: dict[str, list[str]] = Field(default_factory=dict)
    blocked_language_hits: dict[str, list[str]] = Field(default_factory=dict)
    duplicate_hypothesis_ids: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class HypothesisLineage(BaseModel):
    """Lineage from InterpretationSnapshot into hypothesis output."""

    model_config = ConfigDict(frozen=True)

    source: HypothesisSourceSpec
    input_interpretation_snapshot_id: str
    input_interpretation_receipt_ref: str
    input_event_snapshot_id: str
    interpretation_record_ids: list[str]
    event_record_ids: list[str]
    market_snapshot_refs: list[str] = Field(default_factory=list)
    indicator_snapshot_refs: list[str] = Field(default_factory=list)
    method: str
    model_provider: str | None = None
    prompt_template_version: str | None = None
    computed_at_utc: str
    transform_version: str = "finharness.hypotheses.v1"
    output_hash: str
    output_ref: str


class HypothesisSnapshot(BaseModel):
    """Stable fifth-layer hypothesis evidence for validation workflows."""

    model_config = ConfigDict(frozen=True)

    hypothesis_snapshot_id: str
    as_of_utc: str
    input_interpretation_snapshot_id: str
    universe: list[str]
    record_count: int
    records: list[HypothesisRecord]
    quality: HypothesisQuality
    lineage: HypothesisLineage
    payload_ref: str
    receipt_ref: str
    execution_allowed: bool = False
    validation_handoff: list[str] = Field(default_factory=list)
    review_questions: list[str] = Field(default_factory=list)


class HypothesisReceipt(BaseModel):
    """Durable evidence root for fifth-layer hypothesis processing."""

    model_config = ConfigDict(frozen=True)

    receipt_id: str
    created_at_utc: str
    kind: str = "hypothesis_processing"
    stage_flow: dict[str, str]
    snapshot: HypothesisSnapshot
    status: Literal["ok", "warning", "failed"] = "ok"


class HypothesisBundle(BaseModel):
    """Compact handoff for scripts and graph nodes."""

    model_config = ConfigDict(frozen=True)

    source: HypothesisSourceSpec
    input_interpretation_snapshot: InterpretationSnapshot
    records: list[HypothesisRecord]
    quality: HypothesisQuality
    lineage: HypothesisLineage
    snapshot: HypothesisSnapshot
    receipt: HypothesisReceipt


def now_utc() -> str:
    return datetime.now(UTC).isoformat()


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str)
        + "\n",
        encoding="utf-8",
    )


def normalize_symbol(symbol: str) -> str:
    return symbol.strip().upper()


def find_blocked_language(value: str) -> list[str]:
    lower = value.lower()
    hits: list[str] = []
    for pattern in [*RECOMMENDATION_PATTERNS, *VALIDATED_PATTERNS]:
        if re.search(pattern, lower):
            hits.append(pattern)
    return hits


def record_text_for_guard(record: HypothesisRecord) -> str:
    validation_text = [
        f"{check.description} {check.expected_support} {check.expected_disconfirm}"
        for check in record.validation_plan
    ]
    return "\n".join(
        [
            record.mechanism,
            record.hypothesis,
            *record.expected_observations,
            *record.disconfirming_observations,
            *record.assumptions,
            *validation_text,
        ]
    )


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


def build_hypothesis_quality(records: list[HypothesisRecord]) -> HypothesisQuality:
    missing_required_fields: dict[str, list[str]] = {}
    blocked_language_hits: dict[str, list[str]] = {}
    seen: dict[str, str] = {}
    duplicate_ids: list[str] = []

    for record in records:
        missing: list[str] = []
        if not record.source_interpretation_ids:
            missing.append("source_interpretation_ids")
        if not record.source_event_ids:
            missing.append("source_event_ids")
        if not record.source_refs:
            missing.append("source_refs")
        if not record.mechanism:
            missing.append("mechanism")
        if not record.hypothesis:
            missing.append("hypothesis")
        if not record.horizon or record.horizon == "unknown":
            missing.append("horizon")
        if not record.expected_observations:
            missing.append("expected_observations")
        if not record.disconfirming_observations:
            missing.append("disconfirming_observations")
        if not record.validation_plan:
            missing.append("validation_plan")
        if not record.assumptions:
            missing.append("assumptions")
        if record.status != "ready_for_validation":
            missing.append("status")
        if missing:
            missing_required_fields[record.hypothesis_id] = missing

        hits = find_blocked_language(record_text_for_guard(record))
        if hits:
            blocked_language_hits[record.hypothesis_id] = hits

        key = record.hypothesis.strip().lower()
        if key in seen:
            duplicate_ids.extend([seen[key], record.hypothesis_id])
        else:
            seen[key] = record.hypothesis_id

    source_backed = all(
        record.source_interpretation_ids and record.source_event_ids and record.source_refs
        for record in records
    )
    testable = all(bool(record.expected_observations) for record in records)
    disconfirming = all(bool(record.disconfirming_observations) for record in records)
    horizon_present = all(record.horizon and record.horizon != "unknown" for record in records)
    validation_plan_present = all(bool(record.validation_plan) for record in records)
    no_blocked_language = not blocked_language_hits
    claim_not_marked_validated = all(
        not re.search("|".join(VALIDATED_PATTERNS), record_text_for_guard(record).lower())
        for record in records
    )
    temporal_context_separated = all(
        any("event" in item.lower() or "timing" in item.lower() for item in record.assumptions)
        for record in records
    )
    duplicate_check = not duplicate_ids
    notes: list[str] = []
    if not records:
        notes.append("no interpretation records were promoted into hypotheses")

    ok = (
        bool(records)
        and source_backed
        and testable
        and disconfirming
        and horizon_present
        and validation_plan_present
        and no_blocked_language
        and claim_not_marked_validated
        and temporal_context_separated
        and duplicate_check
        and not missing_required_fields
    )
    return HypothesisQuality(
        ok=ok,
        record_count=len(records),
        source_backed_hypotheses=source_backed,
        testable_predictions_present=testable,
        disconfirming_evidence_present=disconfirming,
        horizon_present=horizon_present,
        validation_plan_present=validation_plan_present,
        no_execution_language=no_blocked_language,
        no_recommendation_language=no_blocked_language,
        claim_not_marked_validated=claim_not_marked_validated,
        temporal_context_separated=temporal_context_separated,
        duplicate_hypothesis_check=duplicate_check,
        missing_required_fields=missing_required_fields,
        blocked_language_hits=blocked_language_hits,
        duplicate_hypothesis_ids=sorted(set(duplicate_ids)),
        notes=notes,
    )


def validation_handoff(records: list[HypothesisRecord]) -> list[str]:
    return [
        f"{record.hypothesis_id}: validate {record.symbol} through "
        f"{', '.join(check.check_type for check in record.validation_plan)}"
        for record in records
    ]


def snapshot_review_questions(records: list[HypothesisRecord]) -> list[str]:
    questions = [
        "Which hypothesis has the weakest source backing?",
        "Which disconfirming observation should be tested first?",
        "Which validation plan is too vague for layer 6?",
        "Did any hypothesis drift into recommendation language?",
    ]
    if records:
        questions.append("Which hypothesis should be rejected before validation to reduce bias?")
    return questions


def persist_hypothesis_bundle(
    *,
    source: HypothesisSourceSpec,
    input_interpretation_snapshot: InterpretationSnapshot,
    records: list[HypothesisRecord],
) -> HypothesisBundle:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    suffix = uuid4().hex[:8]
    snapshot_id = f"hyps_{stamp}_{suffix}"
    receipt_id = f"receipt_{snapshot_id}"
    output_ref = HYPOTHESIS_NORMALIZED_ROOT / f"{snapshot_id}.json"
    receipt_ref = HYPOTHESIS_RECEIPT_ROOT / f"{receipt_id}.json"
    quality = build_hypothesis_quality(records)
    output_payload = {
        "hypothesis_snapshot_id": snapshot_id,
        "input_interpretation_snapshot_id": (
            input_interpretation_snapshot.interpretation_snapshot_id
        ),
        "universe": input_interpretation_snapshot.universe,
        "records": [record.model_dump(mode="json") for record in records],
    }
    output_hash = sha256_text(
        json.dumps(output_payload, ensure_ascii=False, sort_keys=True, default=str)
    )
    lineage = HypothesisLineage(
        source=source,
        input_interpretation_snapshot_id=(
            input_interpretation_snapshot.interpretation_snapshot_id
        ),
        input_interpretation_receipt_ref=input_interpretation_snapshot.receipt_ref,
        input_event_snapshot_id=input_interpretation_snapshot.input_event_snapshot_id,
        interpretation_record_ids=[
            interpretation_id
            for record in records
            for interpretation_id in record.source_interpretation_ids
        ],
        event_record_ids=[event_id for record in records for event_id in record.source_event_ids],
        market_snapshot_refs=input_interpretation_snapshot.lineage.market_snapshot_refs,
        indicator_snapshot_refs=input_interpretation_snapshot.lineage.indicator_snapshot_refs,
        method=source.method,
        model_provider=source.llm_provider if source.llm_enabled else None,
        prompt_template_version=source.template_version,
        computed_at_utc=now_utc(),
        output_hash=output_hash,
        output_ref=display_path(output_ref),
    )
    snapshot = HypothesisSnapshot(
        hypothesis_snapshot_id=snapshot_id,
        as_of_utc=now_utc(),
        input_interpretation_snapshot_id=(
            input_interpretation_snapshot.interpretation_snapshot_id
        ),
        universe=input_interpretation_snapshot.universe,
        record_count=len(records),
        records=records,
        quality=quality,
        lineage=lineage,
        payload_ref=display_path(output_ref),
        receipt_ref=display_path(receipt_ref),
        execution_allowed=False,
        validation_handoff=validation_handoff(records),
        review_questions=snapshot_review_questions(records),
    )
    receipt = HypothesisReceipt(
        receipt_id=receipt_id,
        created_at_utc=now_utc(),
        stage_flow={
            "source_input": "HypothesisSourceSpec + InterpretationSnapshot",
            "candidate_selection": "source-backed InterpretationRecord selection",
            "formulate": "rule-guided falsifiable hypothesis template",
            "disconfirming_evidence": "explicit failure observations required",
            "validation_plan": "next-layer validation checks only",
            "quality": "source, testability, disconfirmation, no-recommendation gates",
            "lineage": "InterpretationSnapshot refs, ids, output hash/ref",
            "snapshot": "HypothesisSnapshot",
            "receipt": "HypothesisReceipt",
            "consumer_handoff": "validation/review inputs only",
            "review_hook": "human review before validation promotion",
        },
        snapshot=snapshot,
        status="ok" if quality.ok else "warning",
    )
    write_json(output_ref, output_payload)
    write_json(receipt_ref, receipt.model_dump(mode="json"))
    return HypothesisBundle(
        source=source,
        input_interpretation_snapshot=input_interpretation_snapshot,
        records=records,
        quality=quality,
        lineage=lineage,
        snapshot=snapshot,
        receipt=receipt,
    )


def build_hypothesis_bundle_from_interpretation_snapshot(
    interpretation_snapshot: InterpretationSnapshot | dict[str, Any],
    *,
    max_hypotheses: int = 10,
    symbols: list[str] | None = None,
    llm_enabled: bool = False,
    hermes_root: str | Path = "/root/projects/hermes-agent",
) -> HypothesisBundle:
    snapshot = (
        interpretation_snapshot
        if isinstance(interpretation_snapshot, InterpretationSnapshot)
        else InterpretationSnapshot.model_validate(interpretation_snapshot)
    )
    source = HypothesisSourceSpec(
        llm_provider="hermes-agent" if llm_enabled else None,
        llm_interface="HermesHypothesisDraftProvider" if llm_enabled else None,
        llm_enabled=llm_enabled,
        hermes_root=str(hermes_root),
        config={
            "max_hypotheses": max_hypotheses,
            "symbols": symbols or [],
        },
    )
    provider: HypothesisDraftProvider
    if llm_enabled:
        provider = HermesHypothesisDraftProvider(hermes_root=hermes_root)
    else:
        provider = NullHypothesisDraftProvider()
    candidates = select_hypothesis_candidates(
        snapshot,
        max_hypotheses=max_hypotheses,
        symbols=symbols,
    )
    records = [
        formulate_hypothesis_record(record, draft_provider=provider)
        for record in candidates
    ]
    return persist_hypothesis_bundle(
        source=source,
        input_interpretation_snapshot=snapshot,
        records=records,
    )
