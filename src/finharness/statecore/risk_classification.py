"""P5 high-risk classification and the approval-time counter-evidence gate.

P4 forces the four minimal decision-scaffold fields *when a governed proposal is
created*. P5 adds a stricter, life-cycle-later brake: a **high-risk** proposal may
be recorded and reviewed, but it must not be **approved** without stating what would
prove the thesis wrong (``counter_evidence``).

The two gates live at different life-cycle stages and so raise different errors:

- ``DecisionScaffoldError`` — proposal *creation*: the minimal written structure is
  missing.
- ``HighRiskConfirmationError`` — human *approval / attestation*: a high-risk
  proposal cannot be confirmed without counter-evidence.

This module deliberately classifies risk narrowly over signals that already exist in
the personal-finance governed-proposal line — no new detector kinds are invented, no
network, no market data. Cool-down, liquidation estimates, and historical-volatility
comparisons are explicitly out of scope for this brick.
"""

from __future__ import annotations

from typing import Any

# Proposal kinds that are high-risk in the personal-finance governed-proposal line.
# Kept narrow on purpose: only kinds that actually exist today. Do not pre-invent
# future kinds (leverage_high / margin_high) — add them when the detectors exist.
HIGH_RISK_KINDS: frozenset[str] = frozenset(
    {
        "concentration_high",
        "rate_exposure_high",
    }
)


class HighRiskConfirmationError(ValueError):
    """A high-risk governed proposal is being approved without counter-evidence."""


def _evidence_signals_leverage(evidence: dict[str, Any] | None) -> bool:
    """True when the evidence itself shows leverage/margin/liquidation exposure."""
    if not evidence:
        return False
    leverage = evidence.get("leverage")
    if isinstance(leverage, (int, float)) and not isinstance(leverage, bool) and leverage > 1:
        return True
    return bool(evidence.get("margin_used") or evidence.get("liquidation_risk"))


def is_high_risk(kind: str, evidence: dict[str, Any] | None) -> bool:
    """Classify a governed proposal as high-risk; pure and offline.

    High-risk when the proposal kind is a known high-risk detector, or the evidence
    directly shows leverage/margin/liquidation exposure.
    """
    return kind in HIGH_RISK_KINDS or _evidence_signals_leverage(evidence)


def _has_counter_evidence(scaffold: dict[str, Any] | None) -> bool:
    """True when the scaffold carries a non-blank counter_evidence statement."""
    if not scaffold:
        return False
    value = scaffold.get("counter_evidence")
    if isinstance(value, str):
        return bool(value.strip())
    return value is not None


def ensure_confirmable(
    *,
    kind: str,
    evidence: dict[str, Any] | None,
    decision_scaffold: dict[str, Any] | None,
) -> None:
    """Fail-closed before approving a high-risk proposal that lacks counter-evidence.

    Raises ``HighRiskConfirmationError`` for a high-risk proposal whose scaffold has
    no ``counter_evidence``. Ordinary proposals — and high-risk proposals that do
    state counter-evidence — pass. This gate is for the *approval* path only; it must
    not be wired into proposal creation.
    """
    if is_high_risk(kind, evidence) and not _has_counter_evidence(decision_scaffold):
        raise HighRiskConfirmationError(
            "high-risk proposal cannot be approved without counter_evidence: state "
            "what observable fact would prove the thesis wrong before confirming. A "
            "high-risk action may be recorded and reviewed, but not confirmed blind."
        )
