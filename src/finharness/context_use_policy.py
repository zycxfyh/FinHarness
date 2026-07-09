"""Context use policy v0.

Agentic-space dimension: Context Space.

Validates that context refs have sufficient trust for their intended use.
Prevents agent_draft / unknown / untrusted context from being used as
evidence or planning basis without review.

Rules:
  receipt_backed_state → read, cite, plan_from, use_as_evidence
  system_computed      → read, cite, plan_from, use_as_evidence
  human_attested       → read, cite, plan_from, use_as_evidence
  agent_draft          → read, explain, draft_review (NOT use_as_evidence)
  user_supplied        → read, explain (NOT plan_from, NOT use_as_evidence)
  external_provider    → read, cite, plan_from (NOT use_as_evidence without attestation)
  unknown / untrusted  → read only
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from finharness.context_trust import ContextTrust

ContextRequiredUse = Literal[
    "read", "explain", "cite", "draft_review", "plan_from", "use_as_evidence"
]


@dataclass(frozen=True)
class ContextUseValidation:
    """Result of validating context refs for a given use."""

    valid: bool
    required_use: str
    refs_checked: int
    blocked_refs: list[str]
    blocked_reasons: list[str]
    passed_refs: list[str]

    @property
    def all_passed(self) -> bool:
        return len(self.blocked_refs) == 0


def validate_context_refs_for_use(
    *,
    refs: list[str],
    trust_by_ref: dict[str, ContextTrust],
    required_use: ContextRequiredUse,
) -> ContextUseValidation:
    """Validate that all context refs have the required trust for the intended use.

    Returns ContextUseValidation with blocked_refs for any ref that
    does not have the required trust level.
    """
    blocked_refs: list[str] = []
    blocked_reasons: list[str] = []
    passed_refs: list[str] = []

    for ref in refs:
        trust = trust_by_ref.get(ref)
        if trust is None:
            blocked_refs.append(ref)
            blocked_reasons.append(f"ref has no trust metadata: {ref}")
            continue

        if required_use not in trust.allowed_uses:
            blocked_refs.append(ref)
            blocked_reasons.append(
                f"ref trust={trust.trust_level} source={trust.source_type} "
                f"allows {trust.allowed_uses}, not {required_use}: {ref}"
            )
            continue

        passed_refs.append(ref)

    return ContextUseValidation(
        valid=len(blocked_refs) == 0,
        required_use=required_use,
        refs_checked=len(refs),
        blocked_refs=blocked_refs,
        blocked_reasons=blocked_reasons,
        passed_refs=passed_refs,
    )
