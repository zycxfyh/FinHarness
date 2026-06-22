"""Narrow contract for research evidence attached to capital-allocation candidates.

RE1 is the **interface + redlines only**: the types a candidate uses to pull graded,
historical-descriptive evidence from the headless research engine, plus the hard
boundaries that keep that engine a passive *evidence provider* — never an advice or
execution surface. No real engine adapter lives here (that is RE2).

North star dependency direction: a candidate pulls evidence; the engine never drives
the candidate or the UI. Research evidence is descriptive and historical — never a
prediction, recommendation, price/size target, or execution instruction. These
redlines are enforced as code (closed enums + validators + a shared recursive scanner
over value/lineage keys and string values), not left to reviewer memory.

Scope of the guarantee: redlines are enforced **at construction**, and the models are
**top-level frozen** (no field reassignment). They are NOT deep-frozen — nested dicts
in ``value``/``lineage`` can still be mutated in place after construction, so callers
must treat a constructed item as read-only rather than rely on Python to prevent
post-init mutation.
"""

from __future__ import annotations

from typing import Any, Literal, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from finharness.redlines import (
    FULL_RESEARCH_REDLINE,
    NARROW_RESEARCH_REDLINE,
    STRUCTURED_ADVICE_KEYS,
    reject_nested,
    reject_text,
    reject_text_sequence,
)

# Closed sets: questions, evidence kinds, grades, and the requested time window are
# enums, not free text, so the contract surface cannot quietly widen over time.
ResearchQuestion = Literal["historical_risk_profile"]

# RE2 amendment: the requested/answered window is a closed set, not free text, so a
# caller cannot smuggle a future-looking or prediction-shaped "window" past the gate.
ResearchTimeWindow = Literal["trailing_1y", "trailing_3y"]

ResearchEvidenceKind = Literal[
    "historical_risk_profile",
    "realized_volatility",
    "max_drawdown",
    "conditional_var",
    "average_volume",
]

ResearchEvidenceGrade = Literal[
    "observed_account_state",
    "historical_market_data",
    "backtest_descriptive",
    "llm_interpretation",
]

# Each grade must carry at least these non-claims; weaker (later) grades require
# stronger disclaimers.
REQUIRED_NON_CLAIMS: dict[str, tuple[str, ...]] = {
    "observed_account_state": ("Descriptive account state, not advice.",),
    "historical_market_data": (
        "Historical market description, not a prediction.",
        "Not investment advice.",
    ),
    "backtest_descriptive": (
        "Backtest is a historical description, not a forecast.",
        "Past results do not indicate future returns.",
        "Not investment advice.",
    ),
    "llm_interpretation": (
        "LLM interpretation of historical data, not a prediction.",
        "May be wrong; verify against source_refs.",
        "Not investment advice.",
    ),
}

ResearchEvidenceFieldPolicy = Literal[
    "closed_literal",
    "execution_false",
    "full_text",
    "narrow_text",
    "nested_evidence",
    "structured_full",
]

# Machine-readable surface inventory. Tests assert these exactly match model fields,
# so a new provider-output field cannot be added without assigning a redline policy.
RESEARCH_EVIDENCE_FIELD_POLICIES: dict[str, ResearchEvidenceFieldPolicy] = {
    "kind": "closed_literal",
    "claim": "full_text",
    "evidence_grade": "closed_literal",
    "value": "structured_full",
    "time_window": "closed_literal",
    "source_refs": "narrow_text",
    "lineage": "structured_full",
    "limitations": "narrow_text",
    "non_claims": "narrow_text",
    "execution_allowed": "execution_false",
}

RESEARCH_EVIDENCE_RESULT_FIELD_POLICIES: dict[str, ResearchEvidenceFieldPolicy] = {
    "items": "nested_evidence",
    "data_gaps": "narrow_text",
    "execution_allowed": "execution_false",
}


class ResearchEvidenceRequest(BaseModel):
    """A candidate's specific, closed-vocabulary question to the research engine."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    detector_kind: str
    subject: str
    question: ResearchQuestion
    time_window: ResearchTimeWindow


class ResearchEvidence(BaseModel):
    """One graded, historical-descriptive evidence item (never advice/prediction)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: ResearchEvidenceKind
    claim: str
    evidence_grade: ResearchEvidenceGrade
    value: dict[str, Any] = Field(default_factory=dict)
    time_window: ResearchTimeWindow
    source_refs: tuple[str, ...] = ()
    lineage: dict[str, Any] = Field(default_factory=dict)
    limitations: tuple[str, ...] = ()
    non_claims: tuple[str, ...] = ()
    execution_allowed: bool = False

    @field_validator("execution_allowed")
    @classmethod
    def _never_executes(cls, value: bool) -> bool:
        if value:
            raise ValueError("research evidence never carries execution authority")
        return False

    @field_validator("claim")
    @classmethod
    def _prose_has_no_advice(cls, text: str) -> str:
        # claim is free-text assertion output, so it gets the full advice/prediction
        # redline. time_window is now a closed literal (cannot carry advice). Disclaimers
        # use a narrower validator below because they MUST be able to say "not a forecast
        # / not advice".
        return reject_text(text, FULL_RESEARCH_REDLINE, surface="research evidence")

    @field_validator("value", "lineage")
    @classmethod
    def _no_forbidden_keys(cls, mapping: dict[str, Any]) -> dict[str, Any]:
        # Both value AND lineage are checked: advice/optimizer output must not be
        # smuggled in under provenance metadata either, whether as keys or strings.
        return reject_nested(
            mapping,
            FULL_RESEARCH_REDLINE,
            forbidden_keys=STRUCTURED_ADVICE_KEYS,
            surface="research evidence structured payload",
        )

    @field_validator("source_refs")
    @classmethod
    def _source_refs_have_no_advice(cls, refs: tuple[str, ...]) -> tuple[str, ...]:
        # source_refs are receipt/path references; they may legitimately name data
        # like "returns"/"forecast" files, so only the advice/execution redline
        # applies (not the prediction one).
        return reject_text_sequence(
            refs,
            NARROW_RESEARCH_REDLINE,
            surface="research evidence source_ref",
        )

    @field_validator("limitations", "non_claims")
    @classmethod
    def _disclaimers_have_no_advice(cls, texts: tuple[str, ...]) -> tuple[str, ...]:
        # Disclaimers must be able to say "not a forecast / not advice", so they use
        # the narrow redline: no buy/sell/recommend/target/execution language.
        return reject_text_sequence(
            texts,
            NARROW_RESEARCH_REDLINE,
            surface="research evidence disclaimer",
        )

    @model_validator(mode="after")
    def _require_grade_non_claims(self) -> ResearchEvidence:
        missing = [
            claim
            for claim in REQUIRED_NON_CLAIMS[self.evidence_grade]
            if claim not in self.non_claims
        ]
        if missing:
            raise ValueError(
                f"evidence_grade {self.evidence_grade!r} requires non_claims: {missing}"
            )
        return self


class ResearchEvidenceResult(BaseModel):
    """Provider output: items plus disclosed gaps, so an empty result is never
    silently read as 'no risk evidence exists'."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    items: tuple[ResearchEvidence, ...] = ()
    data_gaps: tuple[str, ...] = ()
    execution_allowed: bool = False

    @field_validator("execution_allowed")
    @classmethod
    def _never_executes(cls, value: bool) -> bool:
        if value:
            raise ValueError("research evidence result never carries execution authority")
        return False

    @field_validator("data_gaps")
    @classmethod
    def _gaps_have_no_advice(cls, gaps: tuple[str, ...]) -> tuple[str, ...]:
        # data_gaps is provider output too; a gap must disclose missing data, never
        # carry advice/execution language.
        return reject_text_sequence(
            gaps,
            NARROW_RESEARCH_REDLINE,
            surface="research evidence data gap",
        )


@runtime_checkable
class ResearchEvidenceProvider(Protocol):
    """Narrow seam: a candidate asks a specific question; the provider answers with
    graded historical evidence. Real implementations (RE2) adapt the headless engine
    but must honor the redlines above."""

    def provide(self, request: ResearchEvidenceRequest) -> ResearchEvidenceResult: ...


class NullResearchEvidenceProvider:
    """Default provider: no engine wired. Returns no items, with a disclosed gap so
    callers never mistake 'no provider' for 'no risk evidence'."""

    def provide(self, request: ResearchEvidenceRequest) -> ResearchEvidenceResult:
        return ResearchEvidenceResult(
            items=(),
            data_gaps=(
                f"no research evidence provider configured for "
                f"{request.detector_kind}/{request.question}",
            ),
        )
