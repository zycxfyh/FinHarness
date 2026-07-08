"""Execution capability model — canonical vocabulary for the control plane.

Defines what the execution system CAN do on a given deployment, without
prescribing HOW enforcement should work. This is a vocabulary, not a
permission platform.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ExecutionCapabilities:
    """Capability flags for the execution subsystem.

    These describe the canonical surface area — not individual permissions.
    Enforcement is deferred to services that consume this model.
    """

    create_order_draft: bool
    run_pretrade_check: bool
    record_approval: bool
    stage_execution_order: bool
    submit_simulated_order: bool
    submit_live_order: bool
    manage_broker_credentials: bool


DEFAULT_EXECUTION_CAPABILITIES = ExecutionCapabilities(
    create_order_draft=True,
    run_pretrade_check=True,
    record_approval=True,
    stage_execution_order=True,
    submit_simulated_order=True,
    submit_live_order=False,
    manage_broker_credentials=False,
)
