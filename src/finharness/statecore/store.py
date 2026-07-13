"""SQLite store for the FinHarness state core."""

from __future__ import annotations

import json
import os
from collections.abc import Callable, Iterable, Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from sqlalchemy import Connection, Engine, event, inspect, text
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session, SQLModel, create_engine, select

from finharness.project_paths import ROOT
from finharness.statecore.execution_models import (
    ApprovalRecord,
    BrokerConnection,
    ExecutionAccount,
    ExecutionOrder,
    ExecutionReport,
    OrderDraft,
    PositionDelta,
    PreTradeCheck,
    ReconciliationReport,
)
from finharness.statecore.models import (
    Account,
    ActionIntent,
    ActionIntentAuthorityBinding,
    ActionIntentSimulationReport,
    AgentAuthorityGrant,
    AgentAuthorityGrantConsumption,
    Attestation,
    CapitalMandate,
    CapitalMandateLifecycleEvent,
    CapitalMandateVersion,
    CapitalObjectiveFit,
    CashflowEvent,
    DocumentRef,
    FinancialGoal,
    ImportBatch,
    InsurancePolicy,
    InvestmentPolicyStatement,
    Liability,
    PaperAccount,
    PaperExecutionReceipt,
    PaperOrderTicketCandidate,
    PaperPosition,
    Position,
    Proposal,
    ReceiptIndex,
    ReceiptManifest,
    ReviewEvent,
    Snapshot,
    TaxEvent,
    TradePlanCandidate,
    TradePlanReviewGate,
)

STATE_CORE_DB_ENV_VAR = "FINHARNESS_STATE_CORE_DB_PATH"
DEFAULT_STATE_CORE_DB_PATH = ROOT / "data" / "state" / "state-core" / "state-core.sqlite"

StateCoreRecord = (
    Account
    | ActionIntent
    | ActionIntentAuthorityBinding
    | ActionIntentSimulationReport
    | AgentAuthorityGrant
    | AgentAuthorityGrantConsumption
    | CapitalMandate
    | CapitalMandateLifecycleEvent
    | CapitalMandateVersion
    | CapitalObjectiveFit
    | TradePlanCandidate
    | TradePlanReviewGate
    | Position
    | Liability
    | FinancialGoal
    | CashflowEvent
    | TaxEvent
    | InsurancePolicy
    | DocumentRef
    | PaperAccount
    | PaperExecutionReceipt
    | PaperOrderTicketCandidate
    | PaperPosition
    | Snapshot
    | ReceiptIndex
    | Proposal
    | Attestation
    | ReviewEvent
    | InvestmentPolicyStatement
    | BrokerConnection
    | ExecutionAccount
    | OrderDraft
    | PreTradeCheck
    | ApprovalRecord
    | ExecutionOrder
    | ExecutionReport
    | PositionDelta
    | ReconciliationReport
    | ImportBatch
    | ReceiptManifest
)

if TYPE_CHECKING:
    from finharness.artifact_store import ArtifactStore


class StateCoreStoreError(RuntimeError):
    """Raised when state-core storage cannot be trusted."""


def state_core_db_path(path: str | Path | None = None) -> Path:
    if path is not None:
        return Path(path)
    env_path = os.environ.get(STATE_CORE_DB_ENV_VAR)
    if env_path:
        return Path(env_path)
    return DEFAULT_STATE_CORE_DB_PATH


def _database_url(path: Path) -> str:
    return f"sqlite:///{path}"


def _enable_sqlite_foreign_keys(dbapi_connection: Any, _connection_record: Any) -> None:
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA foreign_keys=ON")
    finally:
        cursor.close()


def _run_integrity_check(engine: Engine) -> None:
    try:
        with engine.connect() as connection:
            check = connection.execute(text("PRAGMA quick_check")).scalar_one()
            if str(check).lower() != "ok":
                raise StateCoreStoreError(f"state-core sqlite integrity check failed: {check}")
    except (SQLAlchemyError, OSError) as exc:
        raise StateCoreStoreError(f"state-core sqlite file unreadable: {exc}") from exc


def _configure_sqlite(engine: Engine) -> None:
    try:
        with engine.begin() as connection:
            connection.execute(text("PRAGMA foreign_keys=ON"))
            journal_mode = connection.execute(text("PRAGMA journal_mode=WAL")).scalar_one()
            if str(journal_mode).lower() != "wal":
                raise StateCoreStoreError(f"state-core sqlite WAL mode unavailable: {journal_mode}")
    except (SQLAlchemyError, OSError) as exc:
        raise StateCoreStoreError(f"state-core sqlite configuration failed: {exc}") from exc


def open_state_core(path: str | Path | None = None, *, create: bool = False) -> Engine:
    """Open the state-core SQLite database.

    Missing state is not treated as a clean state unless ``create`` is explicit.
    Corrupt or unreadable SQLite files fail closed with ``StateCoreStoreError``.
    """
    target = state_core_db_path(path)
    if not target.exists() and not create:
        raise StateCoreStoreError(f"state-core sqlite file missing: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(_database_url(target), connect_args={"check_same_thread": False})
    event.listen(engine, "connect", _enable_sqlite_foreign_keys)
    if target.exists() and target.stat().st_size > 0:
        _run_integrity_check(engine)
    _configure_sqlite(engine)
    return engine


def init_state_core(path: str | Path | None = None) -> Engine:
    """Create tables and return an opened WAL-enabled engine."""
    engine = open_state_core(path, create=True)
    ensure_state_core_schema(engine)
    return engine


def ensure_state_core_schema(engine: Engine) -> None:
    """Bring an already-open state-core database to the current schema.

    First ``create_all`` adds any tables missing from an older database (it only
    emits ``CREATE TABLE`` for absent tables), so cockpit reads do not fail with
    ``no such table``. Then versioned migrations fix column-level changes that
    ``create_all`` cannot, such as money columns left with REAL affinity before
    the Decimal migration. Both steps are idempotent and safe on every open.
    """
    try:
        SQLModel.metadata.create_all(engine)
    except (SQLAlchemyError, OSError) as exc:
        raise StateCoreStoreError(f"state-core schema initialization failed: {exc}") from exc
    migrate_state_core(engine)


CURRENT_STATE_CORE_USER_VERSION = 8

_SOURCE_COLUMN_ALTERS: tuple[tuple[str, str], ...] = (
    ("liabilities", "ALTER TABLE liabilities ADD COLUMN source TEXT NOT NULL DEFAULT ''"),
    ("financial_goals", "ALTER TABLE financial_goals ADD COLUMN source TEXT NOT NULL DEFAULT ''"),
    ("cashflow_events", "ALTER TABLE cashflow_events ADD COLUMN source TEXT NOT NULL DEFAULT ''"),
    ("tax_events", "ALTER TABLE tax_events ADD COLUMN source TEXT NOT NULL DEFAULT ''"),
    (
        "insurance_policies",
        "ALTER TABLE insurance_policies ADD COLUMN source TEXT NOT NULL DEFAULT ''",
    ),
    ("document_refs", "ALTER TABLE document_refs ADD COLUMN source TEXT NOT NULL DEFAULT ''"),
)

_SOURCE_DELETES: tuple[Any, ...] = (
    text("DELETE FROM liabilities WHERE source = :source"),
    text("DELETE FROM financial_goals WHERE source = :source"),
    text("DELETE FROM cashflow_events WHERE source = :source"),
    text("DELETE FROM tax_events WHERE source = :source"),
    text("DELETE FROM insurance_policies WHERE source = :source"),
    text("DELETE FROM document_refs WHERE source = :source"),
)

_POSITION_MONEY_COLUMNS = ("quantity", "market_value", "cost_basis")
_POSITIONS_SELECT = text(
    "SELECT position_id, snapshot_id, account_id, symbol, quantity, market_value, "
    "cost_basis, schema_version, as_of_utc, authority_level, source_refs FROM positions"
)
_POSITIONS_INSERT = text(
    "INSERT INTO positions (position_id, snapshot_id, account_id, symbol, quantity, "
    "market_value, cost_basis, schema_version, as_of_utc, authority_level, source_refs) "
    "VALUES (:position_id, :snapshot_id, :account_id, :symbol, :quantity, :market_value, "
    ":cost_basis, :schema_version, :as_of_utc, :authority_level, :source_refs)"
)


def _positions_money_already_text(connection: Connection) -> bool:
    info = connection.execute(text("PRAGMA table_info(positions)")).all()
    if not info:
        return True  # no positions table yet: nothing to migrate
    declared = {row[1]: (row[2] or "").upper() for row in info}
    return all(
        "CHAR" in declared.get(column, "") or "TEXT" in declared.get(column, "")
        for column in _POSITION_MONEY_COLUMNS
    )


def _migrate_positions_money_to_text(connection: Connection) -> None:
    """Rebuild legacy REAL money columns on ``positions`` as exact TEXT.

    ``positions`` is a leaf table (nothing references it), so it can be dropped
    and recreated from current metadata. Money values are converted with Python
    ``str`` (shortest round-trip repr) rather than SQLite ``CAST``, which would
    truncate to ~15 significant digits.
    """
    if _positions_money_already_text(connection):
        return
    rows = [dict(row) for row in connection.execute(_POSITIONS_SELECT).mappings()]
    for row in rows:
        for column in _POSITION_MONEY_COLUMNS:
            if row[column] is not None:
                row[column] = str(row[column])
    connection.execute(text("DROP TABLE positions"))
    SQLModel.metadata.tables["positions"].create(connection)
    if rows:
        connection.execute(_POSITIONS_INSERT, rows)


def _migrate_add_source_columns(connection: Connection) -> None:
    """Add the ``source`` column to source-owned personal-finance tables.

    SQLite supports ``ALTER TABLE ... ADD COLUMN`` natively (no table rebuild).
    Idempotent: tables that already have ``source`` (fresh ``create_all``) are
    skipped.
    """
    inspector = inspect(connection)
    existing_tables = set(inspector.get_table_names())
    for table, alter_sql in _SOURCE_COLUMN_ALTERS:
        if table not in existing_tables:
            continue
        columns = {column["name"] for column in inspector.get_columns(table)}
        if "source" in columns:
            continue
        connection.exec_driver_sql(alter_sql)


def _migrate_add_decision_scaffold_column(connection: Connection) -> None:
    """Add the ``decision_scaffold`` column to ``proposals`` (P4 forcing gate).

    SQLite ``ALTER TABLE ... ADD COLUMN`` with a constant default backfills existing
    rows, so a legacy database's proposals get ``'{}'``. Idempotent: skipped when
    ``proposals`` is absent (a fresh ``create_all`` already made it with the column)
    or when the column is already present.
    """
    inspector = inspect(connection)
    if "proposals" not in set(inspector.get_table_names()):
        return
    columns = {column["name"] for column in inspector.get_columns("proposals")}
    if "decision_scaffold" in columns:
        return
    connection.exec_driver_sql(
        "ALTER TABLE proposals ADD COLUMN decision_scaffold TEXT NOT NULL DEFAULT '{}'"
    )


def _migrate_add_agent_authority_grant_bindings(connection: Connection) -> None:
    """Add nullable AUTH-03 bindings without inventing identity for legacy grants."""

    inspector = inspect(connection)
    if "agent_authority_grants" not in set(inspector.get_table_names()):
        return
    columns = {
        column["name"] for column in inspector.get_columns("agent_authority_grants")
    }
    additions = {
        "mandate_version_id": "VARCHAR",
        "principal_id": "VARCHAR",
        "agent_runtime_id": "VARCHAR",
        "max_uses": "INTEGER",
        "max_total_notional": "TEXT",
    }
    for name, declaration in additions.items():
        if name not in columns:
            connection.exec_driver_sql(
                f"ALTER TABLE agent_authority_grants ADD COLUMN {name} {declaration}"
            )
    for name in ("mandate_version_id", "principal_id", "agent_runtime_id"):
        connection.exec_driver_sql(
            "CREATE INDEX IF NOT EXISTS "
            f"ix_agent_authority_grants_{name} "
            f"ON agent_authority_grants ({name})"
        )


def _migrate_add_import_provenance_tables(connection: Connection) -> None:
    """Add W0 provenance tables without inventing manifests for legacy receipts."""
    SQLModel.metadata.tables["import_batches"].create(connection, checkfirst=True)
    SQLModel.metadata.tables["receipt_manifests"].create(connection, checkfirst=True)


def _migrate_add_import_semantics(connection: Connection) -> None:
    """Add D0-02 clocks/findings while marking old batches explicitly legacy."""
    inspector = inspect(connection)
    if "import_batches" not in set(inspector.get_table_names()):
        return
    columns = {column["name"] for column in inspector.get_columns("import_batches")}
    additions = {
        "completeness_status": "VARCHAR NOT NULL DEFAULT 'legacy_unknown'",
        "time_semantics": "JSON NOT NULL DEFAULT '{}'",
        "findings": "JSON NOT NULL DEFAULT '[]'",
    }
    for name, declaration in additions.items():
        if name not in columns:
            connection.exec_driver_sql(
                f"ALTER TABLE import_batches ADD COLUMN {name} {declaration}"
            )


def _review_events_kind_constraint_current(connection: Connection) -> bool:
    row = connection.execute(
        text("SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'review_events'")
    ).first()
    sql = str(row[0] if row else "")
    return "'agent_review_note'" in sql and "'agent_scaffold_revision_apply_candidate'" in sql


def _migrate_review_events_kind_constraint(connection: Connection) -> None:
    """Rebuild ``review_events`` so the closed kind set admits current review events."""
    inspector = inspect(connection)
    if "review_events" not in set(inspector.get_table_names()):
        return
    if _review_events_kind_constraint_current(connection):
        return
    rows = [dict(row) for row in connection.execute(text("SELECT * FROM review_events")).mappings()]
    connection.execute(text("ALTER TABLE review_events RENAME TO review_events_legacy_v3"))
    SQLModel.metadata.tables["review_events"].create(connection)
    if rows:
        connection.execute(SQLModel.metadata.tables["review_events"].insert(), rows)
    connection.execute(text("DROP TABLE review_events_legacy_v3"))


def migrate_state_core(engine: Engine) -> None:
    """Apply versioned, idempotent state-core migrations via ``PRAGMA user_version``."""
    migrations: tuple[tuple[int, Callable[[Connection], None]], ...] = (
        (1, _migrate_positions_money_to_text),
        (2, _migrate_add_source_columns),
        (3, _migrate_add_decision_scaffold_column),
        (4, _migrate_review_events_kind_constraint),
        (5, _migrate_review_events_kind_constraint),
        (6, _migrate_add_agent_authority_grant_bindings),
        (7, _migrate_add_import_provenance_tables),
        (8, _migrate_add_import_semantics),
    )
    try:
        with engine.connect() as connection:
            current = int(connection.execute(text("PRAGMA user_version")).scalar_one())
            # Release the transaction SQLAlchemy autobegins on the read above so
            # the per-migration begin() blocks below can start cleanly.
            connection.rollback()
            for version, step in migrations:
                if version <= current:
                    continue
                with connection.begin():
                    step(connection)
                    connection.exec_driver_sql(f"PRAGMA user_version = {version}")
    except (SQLAlchemyError, OSError) as exc:
        raise StateCoreStoreError(f"state-core migration failed: {exc}") from exc


def write_records(
    records: Iterable[StateCoreRecord],
    *,
    path: str | Path | None = None,
    engine: Engine | None = None,
) -> list[StateCoreRecord]:
    """Write records in one SQLite transaction."""
    materialized = list(records)
    _reject_unmanifested_production_import(materialized)
    owned_engine = engine is None
    active_engine = engine or open_state_core(path)
    saved: list[StateCoreRecord] = []
    try:
        with Session(active_engine) as session:
            with session.begin():
                for record in materialized:
                    session.add(record)
                    session.flush()
                    saved.append(record)
            for record in saved:
                session.refresh(record)
    except (SQLAlchemyError, OSError) as exc:
        raise StateCoreStoreError(f"state-core atomic write failed: {exc}") from exc
    finally:
        if owned_engine:
            active_engine.dispose()
    return saved


def upsert_records(
    records: Iterable[StateCoreRecord],
    *,
    path: str | Path | None = None,
    engine: Engine | None = None,
) -> list[StateCoreRecord]:
    """Merge records in one SQLite transaction.

    Use this for idempotent indexing/ingestion paths. ``write_records`` remains
    the stricter insert-only helper for tests and one-shot writes.
    """
    materialized = list(records)
    _reject_unmanifested_production_import(materialized)
    owned_engine = engine is None
    active_engine = engine or open_state_core(path)
    saved: list[StateCoreRecord] = []
    try:
        with Session(active_engine) as session:
            with session.begin():
                for record in materialized:
                    saved.append(session.merge(record))
                    session.flush()
            for record in saved:
                session.refresh(record)
    except (SQLAlchemyError, OSError) as exc:
        raise StateCoreStoreError(f"state-core atomic upsert failed: {exc}") from exc
    finally:
        if owned_engine:
            active_engine.dispose()
    return saved


_PRODUCTION_IMPORT_KINDS = {"personal_finance_export", "beancount_ledger"}


def _reject_unmanifested_production_import(records: Sequence[StateCoreRecord]) -> None:
    """Keep generic store helpers from bypassing W0 for known production adapters."""
    for record in records:
        if isinstance(record, ReceiptIndex) and record.kind in _PRODUCTION_IMPORT_KINDS:
            raise StateCoreStoreError(
                "production import receipts require materialize_import_batch"
            )
        if (
            isinstance(record, Snapshot)
            and record.payload.get("source") in _PRODUCTION_IMPORT_KINDS
        ):
            raise StateCoreStoreError(
                "production import snapshots require materialize_import_batch"
            )
        if (
            isinstance(
                record,
                (
                    Liability,
                    FinancialGoal,
                    CashflowEvent,
                    TaxEvent,
                    InsurancePolicy,
                    DocumentRef,
                ),
            )
            and record.source in _PRODUCTION_IMPORT_KINDS
        ):
            raise StateCoreStoreError(
                "production import state requires materialize_import_batch"
            )


def _validate_import_envelope(
    *,
    source: str,
    batch: ImportBatch,
    manifest: ReceiptManifest,
    records: Sequence[StateCoreRecord],
    artifact_store: ArtifactStore,
) -> None:
    from finharness.artifact_store import ArtifactStoreError

    if batch.source_kind != source:
        raise StateCoreStoreError("import batch source does not match materialization source")
    if batch.completeness_status not in {"complete", "partial", "blocked"}:
        raise StateCoreStoreError("current import completeness status is outside the closed set")
    if manifest.batch_id != batch.batch_id:
        raise StateCoreStoreError("receipt manifest does not bind the import batch")
    if manifest.source_artifact_id != batch.source_artifact_id:
        raise StateCoreStoreError("receipt manifest does not bind the source evidence")
    if manifest.materialization_status != "materialized":
        raise StateCoreStoreError("only a materialized receipt manifest can become current")
    try:
        source_descriptor = artifact_store.descriptor(batch.source_artifact_id)
        receipt_descriptor = artifact_store.descriptor(manifest.receipt_artifact_id)
        artifact_store.read(batch.source_artifact_id)
        receipt_content = artifact_store.read(manifest.receipt_artifact_id)
    except ArtifactStoreError as exc:
        raise StateCoreStoreError(f"import evidence failed integrity validation: {exc}") from exc
    if source_descriptor.content_sha256 != batch.source_sha256:
        raise StateCoreStoreError("source artifact hash does not match the import batch")
    if receipt_descriptor.content_sha256 != manifest.receipt_sha256:
        raise StateCoreStoreError("receipt artifact hash does not match the manifest")
    _validate_receipt_binding(
        receipt_content=receipt_content,
        source_schema=source_descriptor.artifact_schema,
        receipt_schema=receipt_descriptor.artifact_schema,
        batch=batch,
        manifest=manifest,
    )
    receipt_indexes = [record for record in records if isinstance(record, ReceiptIndex)]
    if len(receipt_indexes) != 1:
        raise StateCoreStoreError("production import requires exactly one receipt index")
    receipt_index = receipt_indexes[0]
    if (
        receipt_index.receipt_id != manifest.receipt_id
        or receipt_index.path != manifest.receipt_ref
    ):
        raise StateCoreStoreError("receipt index does not match the receipt manifest")


def _validate_receipt_binding(
    *,
    receipt_content: bytes,
    source_schema: str,
    receipt_schema: str,
    batch: ImportBatch,
    manifest: ReceiptManifest,
) -> None:
    if source_schema != "finharness.import_source_evidence":
        raise StateCoreStoreError("source artifact has the wrong provenance schema")
    if receipt_schema != "finharness.import_receipt":
        raise StateCoreStoreError("receipt artifact has the wrong provenance schema")
    try:
        receipt_payload = json.loads(receipt_content)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise StateCoreStoreError("receipt artifact is not valid JSON") from exc
    expected_receipt_fields = {
        "import_batch_id": batch.batch_id,
        "receipt_manifest_id": manifest.manifest_id,
        "source_artifact_id": batch.source_artifact_id,
        "receipt_id": manifest.receipt_id,
        "source_sha256": batch.source_sha256,
        "adapter_version": batch.adapter_version,
        "coverage_mode": batch.coverage_mode,
        "record_counts": batch.record_counts,
        "completeness_status": batch.completeness_status,
        "time_semantics": batch.time_semantics,
        "findings": batch.findings,
    }
    if any(receipt_payload.get(key) != value for key, value in expected_receipt_fields.items()):
        raise StateCoreStoreError("receipt artifact does not bind the import envelope")
    if manifest.record_counts != batch.record_counts:
        raise StateCoreStoreError("manifest record counts do not match the import batch")


def materialize_import_batch(
    records: Iterable[StateCoreRecord],
    *,
    source: str,
    batch: ImportBatch,
    manifest: ReceiptManifest,
    artifact_store: ArtifactStore,
    engine: Engine,
) -> list[StateCoreRecord]:
    """Atomically commit a provenance-bound production capital import.

    Source-owned tables (liabilities, goals, cashflows, tax events, insurance,
    documents) are deleted for ``source`` first so a re-import drops rows that no
    longer exist upstream. The batch and manifest are committed in the same database
    transaction as the queryable records; callers cannot make an import current by
    supplying only direct state payloads.
    """
    materialized = list(records)
    _validate_import_envelope(
        source=source,
        batch=batch,
        manifest=manifest,
        records=materialized,
        artifact_store=artifact_store,
    )
    saved: list[StateCoreRecord] = []
    try:
        with Session(engine) as session:
            with session.begin():
                existing_batch = session.get(ImportBatch, batch.batch_id)
                if existing_batch is not None and existing_batch.model_dump() != batch.model_dump():
                    raise StateCoreStoreError("import batch identity is immutable")
                existing_manifest = session.get(ReceiptManifest, manifest.manifest_id)
                if (
                    existing_manifest is not None
                    and existing_manifest.model_dump() != manifest.model_dump()
                ):
                    raise StateCoreStoreError("receipt manifest identity is immutable")
                for statement in _SOURCE_DELETES:
                    session.execute(statement, {"source": source})
                for record in [batch, manifest, *materialized]:
                    saved.append(session.merge(record))
                session.flush()
            for record in saved:
                session.refresh(record)
    except (SQLAlchemyError, OSError) as exc:
        raise StateCoreStoreError(f"state-core atomic replace failed: {exc}") from exc
    return saved


def read_all(model: type[StateCoreRecord], *, engine: Engine) -> Sequence[StateCoreRecord]:
    with Session(engine) as session:
        return cast(Sequence[StateCoreRecord], list(session.exec(select(model)).all()))


def get_account(account_id: str, *, engine: Engine) -> Account | None:
    with Session(engine) as session:
        return session.get(Account, account_id)


def get_snapshot(snapshot_id: str, *, engine: Engine) -> Snapshot | None:
    with Session(engine) as session:
        return session.get(Snapshot, snapshot_id)
