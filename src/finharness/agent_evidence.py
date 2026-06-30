"""Agent evidence provider registry and result envelopes.

This module is the narrow L5 evidence-provider waist for Agent runtime output.
It follows the same mature shape as the tool registry: providers are declared
once, tools reference provider ids, and runtime dispatch projects handler
payloads into a small reviewable envelope.
"""

from __future__ import annotations

import shutil
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from finharness.config import load_settings
from finharness.statecore.store import state_core_db_path

AgentEvidenceProviderKind = Literal[
    "market_data",
    "capital_context",
    "local_eval",
    "proposal_receipt",
]


AGENT_EVIDENCE_NON_CLAIMS = (
    "Agent evidence envelopes describe source lineage; they do not approve a proposal.",
    "Evidence provider availability is diagnostic metadata, not execution authority.",
    "Not execution authorization.",
    "Not investment advice.",
)


@dataclass(frozen=True)
class AgentEvidenceProviderAvailability:
    """Cheap runtime availability result for an Agent evidence provider."""

    available: bool
    reason: str | None = None

    def model(self) -> dict[str, object]:
        return {
            "available": self.available,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class AgentEvidenceProviderEntry:
    """Declared evidence provider used by Agent runtime tools."""

    provider_id: str
    kind: AgentEvidenceProviderKind
    description: str
    source_ref_prefixes: tuple[str, ...]
    check_fn: Callable[[], AgentEvidenceProviderAvailability]
    max_source_refs: int = 24
    execution_allowed: bool = False
    authority_transition: bool = False
    non_claims: tuple[str, ...] = AGENT_EVIDENCE_NON_CLAIMS

    def __post_init__(self) -> None:
        if not self.provider_id.strip():
            raise ValueError("agent evidence provider id cannot be blank")
        if self.execution_allowed:
            raise ValueError("agent evidence providers never grant execution authority")
        if self.authority_transition:
            raise ValueError("agent evidence providers never grant authority transitions")

    def metadata(self) -> dict[str, object]:
        availability = self.check_fn()
        return {
            "provider_id": self.provider_id,
            "kind": self.kind,
            "description": self.description,
            "source_ref_prefixes": list(self.source_ref_prefixes),
            "availability": availability.model(),
            "max_source_refs": self.max_source_refs,
            "execution_allowed": False,
            "authority_transition": False,
            "non_claims": list(self.non_claims),
        }


@dataclass(frozen=True)
class AgentEvidenceEnvelope:
    """Reviewable evidence projection attached to one runtime dispatch result."""

    provider_ids: tuple[str, ...]
    provider_kinds: tuple[AgentEvidenceProviderKind, ...]
    source_refs: tuple[str, ...] = ()
    receipt_refs: tuple[str, ...] = ()
    context_pack_refs: tuple[str, ...] = ()
    data_gaps: tuple[str, ...] = ()
    non_claims: tuple[str, ...] = AGENT_EVIDENCE_NON_CLAIMS
    execution_allowed: bool = False
    authority_transition: bool = False

    def __post_init__(self) -> None:
        if self.execution_allowed:
            raise ValueError("agent evidence envelopes never grant execution authority")
        if self.authority_transition:
            raise ValueError("agent evidence envelopes never grant authority transitions")

    def model(self) -> dict[str, object]:
        return {
            "provider_ids": list(self.provider_ids),
            "provider_kinds": list(self.provider_kinds),
            "source_refs": list(self.source_refs),
            "receipt_refs": list(self.receipt_refs),
            "context_pack_refs": list(self.context_pack_refs),
            "data_gaps": list(self.data_gaps),
            "non_claims": list(self.non_claims),
            "execution_allowed": False,
            "authority_transition": False,
        }


def _available() -> AgentEvidenceProviderAvailability:
    return AgentEvidenceProviderAvailability(True)


def _state_core_available() -> AgentEvidenceProviderAvailability:
    path = state_core_db_path(load_settings().state_core_db_path)
    if path.exists():
        return AgentEvidenceProviderAvailability(True)
    return AgentEvidenceProviderAvailability(False, f"state-core sqlite file missing: {path}")


def _promptfoo_available() -> AgentEvidenceProviderAvailability:
    if shutil.which("pnpm") is None:
        return AgentEvidenceProviderAvailability(False, "pnpm is not available on PATH")
    return AgentEvidenceProviderAvailability(True)


AGENT_EVIDENCE_PROVIDERS: dict[str, AgentEvidenceProviderEntry] = {
    entry.provider_id: entry
    for entry in (
        AgentEvidenceProviderEntry(
            provider_id="market_data.yfinance",
            kind="market_data",
            description=(
                "Read-only Yahoo Finance/yfinance market data used as descriptive "
                "historical or quote evidence."
            ),
            source_ref_prefixes=("market_data://",),
            check_fn=_available,
        ),
        AgentEvidenceProviderEntry(
            provider_id="capital_context.state_core",
            kind="capital_context",
            description=(
                "Read-only StateCore-derived Capital OS context packs for Agent "
                "explanation and review."
            ),
            source_ref_prefixes=("statecore://", "receipt://", "context_pack://"),
            check_fn=_state_core_available,
        ),
        AgentEvidenceProviderEntry(
            provider_id="local_eval.promptfoo",
            kind="local_eval",
            description="Local promptfoo evaluation evidence for generated risk notes.",
            source_ref_prefixes=("eval://", "cache://"),
            check_fn=_promptfoo_available,
        ),
        AgentEvidenceProviderEntry(
            provider_id="proposal_receipt.state_core",
            kind="proposal_receipt",
            description=(
                "Append-only StateCore proposal receipt evidence for Agent-created "
                "review drafts."
            ),
            source_ref_prefixes=("receipt://", "proposal://", "context_pack://"),
            check_fn=_state_core_available,
        ),
    )
}


def resolve_evidence_providers(
    provider_ids: Iterable[str],
) -> tuple[AgentEvidenceProviderEntry, ...]:
    """Return provider entries for ids, failing closed on unknown declarations."""
    entries: list[AgentEvidenceProviderEntry] = []
    missing: list[str] = []
    for provider_id in provider_ids:
        entry = AGENT_EVIDENCE_PROVIDERS.get(provider_id)
        if entry is None:
            missing.append(provider_id)
        else:
            entries.append(entry)
    if missing:
        raise ValueError(f"unknown agent evidence providers: {', '.join(sorted(missing))}")
    return tuple(entries)


def evidence_provider_metadata_for_ids(provider_ids: Iterable[str]) -> list[dict[str, object]]:
    """Return reviewable provider metadata for declared provider ids."""
    return [entry.metadata() for entry in resolve_evidence_providers(provider_ids)]


def list_evidence_provider_metadata() -> list[dict[str, object]]:
    """Return metadata for all declared Agent evidence providers."""
    return [
        AGENT_EVIDENCE_PROVIDERS[provider_id].metadata()
        for provider_id in sorted(AGENT_EVIDENCE_PROVIDERS)
    ]


def build_agent_evidence_envelope(
    *,
    provider_ids: Iterable[str],
    result: dict[str, object],
) -> AgentEvidenceEnvelope:
    """Project one tool handler payload into a bounded evidence envelope."""
    providers = resolve_evidence_providers(provider_ids)
    max_refs = max((provider.max_source_refs for provider in providers), default=0)
    provider_kinds = tuple(provider.kind for provider in providers)
    source_refs = _refs(_field_values(result, "source_refs"))
    receipt_refs = _refs(
        [
            *_field_values(result, "receipt_refs"),
            *_field_values(result, "receipt_ref"),
        ]
    )
    context_pack_refs = _refs(_context_pack_refs(provider_kinds, result))
    data_gaps = _refs(_field_values(result, "data_gaps"))
    non_claims = _refs([*AGENT_EVIDENCE_NON_CLAIMS, *_field_values(result, "non_claims")])
    if max_refs and len(source_refs) > max_refs:
        source_refs = source_refs[:max_refs]
        data_gaps = (*data_gaps, f"source refs truncated to {max_refs} items")
    return AgentEvidenceEnvelope(
        provider_ids=tuple(provider.provider_id for provider in providers),
        provider_kinds=provider_kinds,
        source_refs=source_refs,
        receipt_refs=receipt_refs,
        context_pack_refs=context_pack_refs,
        data_gaps=data_gaps,
        non_claims=non_claims,
        execution_allowed=False,
        authority_transition=False,
    )


def market_data_source_ref(
    *,
    provider: str,
    dataset: str,
    symbol: str,
    qualifier: str | None = None,
) -> str:
    """Build a stable source ref for read-only market data evidence."""
    normalized = symbol.strip().upper()
    path = f"market_data://{provider}/{dataset}/{normalized}"
    if qualifier:
        return f"{path}?{qualifier.strip()}"
    return path


def local_eval_source_ref(path: str | Path) -> str:
    """Build a stable source ref for local evaluation inputs."""
    value = Path(path).as_posix()
    if value.startswith("/"):
        value = value.lstrip("/")
    return f"eval://{value}"


def _field_values(result: dict[str, object], key: str) -> list[str]:
    value = result.get(key)
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, (list, tuple, set)):
        return [str(item) for item in value if str(item).strip()]
    return [str(value)]


def _context_pack_refs(
    provider_kinds: tuple[AgentEvidenceProviderKind, ...],
    result: dict[str, object],
) -> list[str]:
    refs = _field_values(result, "context_pack_refs")
    name = result.get("name")
    if "capital_context" in provider_kinds and isinstance(name, str) and name.strip():
        refs.append(f"context_pack://{name.strip()}")
    return refs


def _refs(values: Iterable[str]) -> tuple[str, ...]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        out.append(text)
    return tuple(out)
