"""RE3: Research Enrichment Subsystem — the stable seam between allocation candidates
and the RE2 research provider.

This module is the one place that knows *how* a capital-allocation candidate pulls
historical research evidence. ``allocation.py`` consumes a single typed attachment and
never learns provider details, so RE4/RE5 can wire a different evidence source by
swapping the injected enricher rather than re-touching the candidate pipeline.

North-star invariants enforced here:

* **Dependency direction is one-way.** A candidate *pulls* evidence; the research
  engine never drives the candidate. This module reads ``detector_kind``/``evidence``
  off a candidate through a narrow structural ``EnrichableCandidate`` view and never
  imports the candidate pipeline at all (not even for typing).
* **Evidence is additive context, not a gate.** Enrichment never decides whether a
  candidate is produced or recorded. A failed/empty provider yields an attachment with
  disclosed gaps; the candidate stands on its own.
* **Default path is "not enabled", not "enabled but empty".** ``NoopResearchEnricher``
  (the default) returns an empty attachment and the wiring keeps today's evidence shape
  byte-for-byte. The distinct ``NullResearchEvidenceProvider`` (RE1) means "enabled but
  no provider" and *does* disclose a gap — the two must not be conflated.
* **Capability routing decides before calling.** Only ``concentration_high`` with a
  ``top_symbol`` is routed to the provider; unrelated candidates are never enriched and
  never carry research noise. RE2's own scope-guard remains as defense in depth.
* **Failures are sanitized.** A provider exception becomes a safe, templated gap — the
  raw exception text never reaches the Proposal or the cockpit.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from finharness.research_evidence import (
    ResearchEvidence,
    ResearchEvidenceProvider,
    ResearchEvidenceRequest,
    ResearchEvidenceResult,
    ResearchTimeWindow,
)


@runtime_checkable
class EnrichableCandidate(Protocol):
    """Narrow structural view the subsystem needs off a candidate.

    Depending on this (not the concrete ``AllocationCandidate``) keeps RE3 decoupled
    from the candidate pipeline: any object exposing these two attributes can be
    enriched, and the subsystem never imports allocation (even for typing).
    """

    detector_kind: str
    evidence: dict[str, Any]


# Capability routing: RE3 only enriches this detector. Routing decides *before* calling
# the provider, so unrelated candidates never reach it (RE2's scope-guard is a backstop).
SUPPORTED_DETECTOR_KIND = "concentration_high"

# The window RE3 asks for. Closed literal (RE1/RE2); descriptive, not forward-looking.
RESEARCH_TIME_WINDOW: ResearchTimeWindow = "trailing_3y"


@dataclass(frozen=True)
class ResearchEvidenceAttachment:
    """Typed carrier between the enricher and ``record_allocation_candidates``.

    Owns serialization, source_ref dedup, and the empty/Noop case so the allocation
    wiring never hand-assembles research payload details.
    """

    items: tuple[ResearchEvidence, ...] = ()
    data_gaps: tuple[str, ...] = ()
    source_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        # The attachment owns the redline at construction, so even a rogue or buggy
        # enricher cannot smuggle advice/execution text into proposal evidence:
        # 1. Reuse the RE1 contract as the single source of truth — this re-validates
        #    items are ResearchEvidence and runs the data_gaps narrow redline.
        ResearchEvidenceResult(items=self.items, data_gaps=self.data_gaps)
        # 2. source_refs must be *derived* from item source_refs (already redline-checked
        #    at item construction), never free-form — so they cannot smuggle advice.
        allowed = {ref for item in self.items for ref in item.source_refs}
        stray = [ref for ref in self.source_refs if ref not in allowed]
        if stray:
            raise ValueError(
                f"attachment source_refs must derive from item source_refs: {stray}"
            )

    @classmethod
    def from_result(cls, result: ResearchEvidenceResult) -> ResearchEvidenceAttachment:
        """Build an attachment from a provider result, deduping source_refs in order."""
        seen: set[str] = set()
        refs: list[str] = []
        for item in result.items:
            for ref in item.source_refs:
                if ref not in seen:
                    seen.add(ref)
                    refs.append(ref)
        return cls(
            items=tuple(result.items),
            data_gaps=tuple(result.data_gaps),
            source_refs=tuple(refs),
        )

    def to_evidence_payload(self) -> list[dict[str, Any]]:
        """JSON-safe evidence list. Empty items -> ``[]`` (matches today's shape)."""
        return [item.model_dump() for item in self.items]


@runtime_checkable
class ResearchEnricher(Protocol):
    """Seam: turn a candidate into a research attachment (possibly empty)."""

    def enrich(self, candidate: EnrichableCandidate) -> ResearchEvidenceAttachment: ...


@dataclass(frozen=True)
class NoopResearchEnricher:
    """Default enricher: enrichment is **not enabled**.

    Returns an empty attachment — no provider call, no candidate change, no gap. The
    wiring keeps today's evidence shape, so the default path is byte-for-byte unchanged.
    """

    def enrich(self, candidate: EnrichableCandidate) -> ResearchEvidenceAttachment:
        return ResearchEvidenceAttachment()


def build_research_request(
    candidate: EnrichableCandidate,
) -> ResearchEvidenceRequest | None:
    """Capability routing: build a request only for a supported, well-formed candidate.

    Returns ``None`` (do not call the provider, add no gap) for any other detector or a
    candidate missing a usable ``top_symbol``.
    """
    if candidate.detector_kind != SUPPORTED_DETECTOR_KIND:
        return None
    symbol = candidate.evidence.get("top_symbol")
    if not isinstance(symbol, str) or not symbol.strip():
        return None
    return ResearchEvidenceRequest(
        detector_kind=candidate.detector_kind,
        subject=symbol,
        question="historical_risk_profile",
        time_window=RESEARCH_TIME_WINDOW,
    )


def sanitize_gap(_exc: BaseException) -> str:
    """Safe, templated gap for a provider failure — never leaks exception text/paths."""
    return "research enrichment unavailable for this candidate."


@dataclass(frozen=True)
class ProviderResearchEnricher:
    """Opt-in enricher: routes a candidate to an injected RE2 provider.

    Only ``concentration_high`` (with a ``top_symbol``) is routed; everything else gets
    an empty attachment without touching the provider. A provider exception is caught
    and disclosed as a sanitized gap so a candidate is always recorded.
    """

    provider: ResearchEvidenceProvider

    def enrich(self, candidate: EnrichableCandidate) -> ResearchEvidenceAttachment:
        request = build_research_request(candidate)
        if request is None:
            return ResearchEvidenceAttachment()
        # A provider should not raise, but enrichment must never break the scan: any
        # failure collapses to one sanitized, disclosed gap.
        try:
            result = self.provider.provide(request)
        except Exception as exc:
            return ResearchEvidenceAttachment(data_gaps=(sanitize_gap(exc),))
        return ResearchEvidenceAttachment.from_result(result)
