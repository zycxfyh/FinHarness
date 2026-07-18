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

# Compatibility bridge for the pre-registry store module. Importing any
# ``finharness.statecore.*`` module initializes this package first, so the generic
# store helpers use the code-owned production-import inventory rather than an
# adapter-local list. A later cleanup may move the import into store.py directly;
# the canonical owner remains capital_import_registry.py.
from finharness.capital_import_registry import (  # noqa: E402
    PRODUCTION_CAPITAL_IMPORT_SOURCE_KINDS,
)
from finharness.statecore import store as _store  # noqa: E402

_store._PRODUCTION_IMPORT_KINDS = set(PRODUCTION_CAPITAL_IMPORT_SOURCE_KINDS)

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
