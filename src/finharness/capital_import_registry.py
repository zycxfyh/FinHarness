"""Code-owned inventory for production capital-import adapters and exposures."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal

SOURCE_ARTIFACT_SCHEMA = "finharness.import_source_evidence"
RECEIPT_ARTIFACT_SCHEMA = "finharness.import_receipt"


@dataclass(frozen=True)
class CapitalImportAdapterSpec:
    adapter_id: str
    source_kind: str
    materialized_source: str
    module: str
    symbol: str
    result_type: str
    materializer_symbol: str = "materialize_import_batch"
    source_artifact_schema: str = SOURCE_ARTIFACT_SCHEMA
    receipt_artifact_schema: str = RECEIPT_ARTIFACT_SCHEMA

    def as_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass(frozen=True)
class CapitalImportExposureSpec:
    exposure_id: str
    exposure_kind: Literal["task", "script", "function", "api", "agent"]
    exposure_ref: str
    adapter_id: str
    production: bool = True

    def as_dict(self) -> dict[str, str | bool]:
        return asdict(self)


PRODUCTION_CAPITAL_IMPORT_ADAPTERS: tuple[CapitalImportAdapterSpec, ...] = (
    CapitalImportAdapterSpec(
        adapter_id="personal-finance-export",
        source_kind="personal_finance_export",
        materialized_source="personal_finance_export",
        module="finharness.personal_finance",
        symbol="ingest_personal_finance_export",
        result_type="PersonalFinanceImportResult",
    ),
    CapitalImportAdapterSpec(
        adapter_id="beancount-ledger",
        source_kind="beancount_ledger",
        materialized_source="beancount_ledger",
        module="finharness.beancount_adapter",
        symbol="ingest_beancount_ledger",
        result_type="BeancountImportResult",
    ),
    CapitalImportAdapterSpec(
        adapter_id="broker-read-receipt",
        source_kind="broker_read",
        materialized_source="broker_read_import",
        module="finharness.statecore.snapshot_ingest",
        symbol="ingest_broker_read_receipt",
        result_type="BrokerReadImportResult",
    ),
)

PRODUCTION_CAPITAL_IMPORT_EXPOSURES: tuple[CapitalImportExposureSpec, ...] = (
    CapitalImportExposureSpec(
        exposure_id="task-personal-finance-import",
        exposure_kind="task",
        exposure_ref="personal-finance:import",
        adapter_id="personal-finance-export",
    ),
    CapitalImportExposureSpec(
        exposure_id="script-personal-finance-import",
        exposure_kind="script",
        exposure_ref="scripts/import_personal_finance_export.py",
        adapter_id="personal-finance-export",
    ),
    CapitalImportExposureSpec(
        exposure_id="task-beancount-import",
        exposure_kind="task",
        exposure_ref="beancount:import",
        adapter_id="beancount-ledger",
    ),
    CapitalImportExposureSpec(
        exposure_id="script-beancount-import",
        exposure_kind="script",
        exposure_ref="scripts/import_beancount_ledger.py",
        adapter_id="beancount-ledger",
    ),
    CapitalImportExposureSpec(
        exposure_id="task-cockpit-daily",
        exposure_kind="task",
        exposure_ref="cockpit:daily",
        adapter_id="broker-read-receipt",
    ),
    CapitalImportExposureSpec(
        exposure_id="script-daily-change-brief",
        exposure_kind="script",
        exposure_ref="scripts/run_daily_change_brief.py",
        adapter_id="broker-read-receipt",
    ),
    CapitalImportExposureSpec(
        exposure_id="function-daily-change-brief",
        exposure_kind="function",
        exposure_ref="finharness.daily_change_brief.run_daily_change_brief",
        adapter_id="broker-read-receipt",
    ),
    CapitalImportExposureSpec(
        exposure_id="function-broker-receipt-compat",
        exposure_kind="function",
        exposure_ref=(
            "finharness.statecore.snapshot_ingest."
            "ingest_portfolio_snapshot_from_receipt"
        ),
        adapter_id="broker-read-receipt",
    ),
)

PRODUCTION_CAPITAL_IMPORT_SOURCE_KINDS = frozenset(
    spec.source_kind for spec in PRODUCTION_CAPITAL_IMPORT_ADAPTERS
)
PRODUCTION_CAPITAL_IMPORT_MATERIALIZED_SOURCES = frozenset(
    spec.materialized_source for spec in PRODUCTION_CAPITAL_IMPORT_ADAPTERS
)


def registry_projection() -> dict[str, object]:
    """Return the deterministic governance projection checked into docs."""
    return {
        "schema": "finharness.capital_import_entrypoints.v1",
        "status": "current",
        "generated_from": "src/finharness/capital_import_registry.py",
        "adapters": [spec.as_dict() for spec in PRODUCTION_CAPITAL_IMPORT_ADAPTERS],
        "exposures": [spec.as_dict() for spec in PRODUCTION_CAPITAL_IMPORT_EXPOSURES],
        "empty_surface_claims": {"api": [], "agent": []},
        "non_claims": [
            "Registration does not make an import current CapitalState.",
            "Complete materialization does not prove valuation admission.",
            "No import adapter grants execution authority.",
        ],
    }
