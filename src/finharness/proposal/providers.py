"""Draft-provider helpers for proposal generation."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol

from finharness.validation import ValidationCheckResult


class ProposalDraftProvider(Protocol):
    """Optional provider interface for future LLM proposal drafting."""

    provider_name: str

    def draft(self, validation_results: list[ValidationCheckResult]) -> dict[str, Any]:
        """Return optional draft proposal fields."""


class NullProposalDraftProvider:
    """Default provider: deterministic proposal, no LLM call."""

    provider_name = "none"

    def draft(self, validation_results: list[ValidationCheckResult]) -> dict[str, Any]:
        return {}


class HermesProposalDraftProvider:
    """Reserved adapter boundary for /root/projects/hermes-agent."""

    provider_name = "hermes-agent"

    def __init__(self, *, hermes_root: str | Path = "/root/projects/hermes-agent") -> None:
        self.hermes_root = Path(hermes_root)

    def draft(self, validation_results: list[ValidationCheckResult]) -> dict[str, Any]:
        return {
            "provider": self.provider_name,
            "enabled": False,
            "hermes_root": str(self.hermes_root),
            "note": "LLM proposal interface reserved; deterministic template used in MVP.",
            "result_count": len(validation_results),
        }
