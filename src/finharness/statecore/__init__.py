"""State-core storage package for the FinHarness cockpit foundation."""

from finharness.statecore.diff import SnapshotDiff, diff_snapshots
from finharness.statecore.models import (
    Account,
    ActionIntentSimulationReport,
    Attestation,
    CapitalMandate,
    CapitalObjectiveFit,
    PaperAccount,
    PaperExecutionReceipt,
    PaperOrderTicketCandidate,
    PaperPosition,
    Position,
    Proposal,
    ReceiptIndex,
    Snapshot,
    TradePlanCandidate,
    TradePlanReviewGate,
)
from finharness.statecore.observations import (
    Observation,
    ObservationThresholds,
    build_observations,
)
from finharness.statecore.snapshots import latest_portfolio_snapshot, portfolio_positions
from finharness.statecore.store import (
    StateCoreStoreError,
    init_state_core,
    open_state_core,
    state_core_db_path,
    upsert_records,
    write_records,
)

__all__ = [
    "Account",
    "ActionIntentSimulationReport",
    "Attestation",
    "CapitalMandate",
    "CapitalObjectiveFit",
    "Observation",
    "ObservationThresholds",
    "PaperAccount",
    "PaperExecutionReceipt",
    "PaperOrderTicketCandidate",
    "PaperPosition",
    "Position",
    "Proposal",
    "ReceiptIndex",
    "Snapshot",
    "SnapshotDiff",
    "StateCoreStoreError",
    "TradePlanCandidate",
    "TradePlanReviewGate",
    "build_observations",
    "diff_snapshots",
    "init_state_core",
    "latest_portfolio_snapshot",
    "open_state_core",
    "portfolio_positions",
    "state_core_db_path",
    "upsert_records",
    "write_records",
]


def _bind_production_import_materialization_kinds() -> None:
    from finharness.capital_import_registry import (
        PRODUCTION_CAPITAL_IMPORT_MATERIALIZED_SOURCES,
    )
    from finharness.statecore import store

    store._PRODUCTION_IMPORT_KINDS = set(
        PRODUCTION_CAPITAL_IMPORT_MATERIALIZED_SOURCES
    )


_bind_production_import_materialization_kinds()
del _bind_production_import_materialization_kinds
