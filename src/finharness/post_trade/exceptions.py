"""Post-trade exception construction helpers."""

from __future__ import annotations

from finharness.execution import ExecutionSnapshot
from finharness.post_trade._util import exception
from finharness.post_trade.models import (
    PostTradeCostEstimate,
    PostTradeException,
    PostTradeReconciliation,
)


def build_post_trade_exceptions(
    *,
    execution_snapshot: ExecutionSnapshot,
    reconciliations: list[PostTradeReconciliation],
    cost_estimates: list[PostTradeCostEstimate],
) -> list[PostTradeException]:
    exceptions: list[PostTradeException] = []
    refs = [execution_snapshot.payload_ref, execution_snapshot.receipt_ref]
    for reconciliation in reconciliations:
        evidence = [*refs, *reconciliation.execution_event_ids]
        if reconciliation.status == "partial_fill_exception":
            exceptions.append(
                exception(
                    exception_type="partial_fill",
                    severity="warning",
                    reason="Partial fill requires review before portfolio handoff.",
                    evidence_refs=evidence,
                )
            )
        elif reconciliation.status == "reconciled_rejected":
            exceptions.append(
                exception(
                    exception_type="execution_rejected",
                    severity="warning",
                    reason="Execution adapter rejected the order request.",
                    evidence_refs=evidence,
                )
            )
        elif reconciliation.status == "reconciled_canceled":
            exceptions.append(
                exception(
                    exception_type="execution_canceled",
                    severity="info",
                    reason="Execution was canceled; no clean fill handoff.",
                    evidence_refs=evidence,
                )
            )
        elif reconciliation.status == "staged_no_trade":
            exceptions.append(
                exception(
                    exception_type="staged_no_trade",
                    severity="info",
                    reason="Order-shaped request was staged only and is not a trade.",
                    evidence_refs=evidence,
                )
            )
        elif reconciliation.status == "pending_monitoring":
            exceptions.append(
                exception(
                    exception_type="pending_monitoring",
                    severity="info",
                    reason="Execution lifecycle is not terminal yet.",
                    evidence_refs=evidence,
                )
            )
        elif reconciliation.status == "needs_human_review":
            exceptions.append(
                exception(
                    exception_type="blocked_before_submit",
                    severity="critical",
                    reason="Execution was blocked before submit and needs review.",
                    evidence_refs=evidence,
                )
            )
    for estimate in cost_estimates:
        if estimate.filled_quantity > 0 and (
            estimate.reference_price is None or estimate.average_fill_price is None
        ):
            exceptions.append(
                exception(
                    exception_type="missing_tca_price_input",
                    severity="warning",
                    reason="Filled quantity exists but TCA price inputs are incomplete.",
                    evidence_refs=refs,
                )
            )
    if not execution_snapshot.receipt_ref:
        exceptions.append(
            exception(
                exception_type="missing_execution_receipt",
                severity="critical",
                reason="Execution receipt reference is missing.",
                evidence_refs=[execution_snapshot.execution_snapshot_id],
            )
        )
    return exceptions
