"""SQLite store for the FinHarness state core."""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Callable, Iterable, Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from sqlalchemy import Connection, Engine, delete, event, inspect, text
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session, SQLModel, col, create_engine, select

from finharness.capital_import_registry import (
    PRODUCTION_CAPITAL_IMPORT_MATERIALIZED_SOURCES as _REGISTRY_MATERIALIZED_SOURCES,
)
from finharness.capital_import_registry import (
    PRODUCTION_CAPITAL_IMPORT_SOURCE_KINDS as _REGISTRY_SOURCE_KINDS,
)
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
from finharness.statecore.model_base import SourcedStateCoreBase
from finharness.statecore.models import (
    Account,
    AccountIdentity,
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
    IdentityAlias,
    ImportBatch,
    ImportTombstone,
    InstrumentIdentity,
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
    | AccountIdentity
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
    | IdentityAlias
    | InstrumentIdentity
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
    | ImportTombstone
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


CURRENT_STATE_CORE_USER_VERSION = 13

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

_SOURCE_OWNED_MODELS: tuple[tuple[type[SourcedStateCoreBase], str, str, str], ...] = (
    (Liability, "liability_id", "liabilities", "liability"),
    (FinancialGoal, "goal_id", "financial_goals", "goal"),
    (CashflowEvent, "cashflow_id", "cashflow_events", "cashflow"),
    (TaxEvent, "tax_event_id", "tax_events", "tax_event"),
    (InsurancePolicy, "policy_id", "insurance_policies", "insurance"),
    (DocumentRef, "document_id", "document_refs", "document"),
)

_POSITION_MONEY_COLUMNS = ("quantity", "market_value", "cost_basis")
_POSITIONS_SELECT = text(
    "SELECT position_id, snapshot_id, account_id, symbol, quantity, market_value, "
    "cost_basis, schema_version, as_of_utc, authority_level, source_refs FROM positions"
)
_POSITIONS_INSERT = text(
    "INSERT INTO positions (position_id, snapshot_id, account_id, symbol, quantity, "
    "market_value, cost_basis, schema_version, as_of_utc, authority_level, source_refs, "
    "valuation_status) "
    "VALUES (:position_id, :snapshot_id, :account_id, :symbol, :quantity, :market_value, "
    ":cost_basis, :schema_version, :as_of_utc, :authority_level, :source_refs, "
    ":valuation_status)"
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
        row["valuation_status"] = "unknown_legacy"
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
    columns = {column["name"] for column in inspector.get_columns("agent_authority_grants")}
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


def _migrate_add_agent_authority_currency_bindings(connection: Connection) -> None:
    """Add nullable currency bindings without guessing currency for legacy authority."""

    inspector = inspect(connection)
    tables = set(inspector.get_table_names())
    additions = {
        "agent_authority_grants": {"notional_currency": "VARCHAR"},
        "agent_authority_grant_consumptions": {"requested_notional_currency": "VARCHAR"},
    }
    for table, table_additions in additions.items():
        if table not in tables:
            continue
        columns = {column["name"] for column in inspector.get_columns(table)}
        for name, declaration in table_additions.items():
            if name not in columns:
                connection.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN {name} {declaration}")


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


def _migrate_add_import_correction_semantics(connection: Connection) -> None:
    """Add typed coverage/correction fields and the append-only tombstone table."""
    SQLModel.metadata.tables["import_tombstones"].create(connection, checkfirst=True)
    inspector = inspect(connection)
    if "import_batches" not in set(inspector.get_table_names()):
        return
    columns = {column["name"] for column in inspector.get_columns("import_batches")}
    additions = {
        "covered_domains": "JSON NOT NULL DEFAULT '[]'",
        "supersedes_batch_id": "VARCHAR",
        "correction_reason": "VARCHAR",
        "corporate_action_status": "VARCHAR NOT NULL DEFAULT 'unsupported_gap'",
        "corporate_action_gaps": (
            "JSON NOT NULL DEFAULT '[\"corporate_action_semantics_not_supported\"]'"
        ),
    }
    for name, declaration in additions.items():
        if name not in columns:
            connection.exec_driver_sql(
                f"ALTER TABLE import_batches ADD COLUMN {name} {declaration}"
            )
    connection.exec_driver_sql(
        "CREATE INDEX IF NOT EXISTS ix_import_batches_supersedes_batch_id "
        "ON import_batches (supersedes_batch_id)"
    )


def _migrate_add_canonical_identities(connection: Connection) -> None:
    """Add nullable identity bindings without inventing identity for legacy rows."""
    for table in ("account_identities", "instrument_identities", "identity_aliases"):
        SQLModel.metadata.tables[table].create(connection, checkfirst=True)
    inspector = inspect(connection)
    tables = set(inspector.get_table_names())
    additions = {
        "accounts": ("canonical_account_id", "VARCHAR"),
        "positions": ("instrument_id", "VARCHAR"),
    }
    for table, (column, declaration) in additions.items():
        if table not in tables:
            continue
        columns = {item["name"] for item in inspector.get_columns(table)}
        if column not in columns:
            connection.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN {column} {declaration}")
        connection.exec_driver_sql(
            f"CREATE INDEX IF NOT EXISTS ix_{table}_{column} ON {table} ({column})"
        )


def _migrate_position_valuation_contract(connection: Connection) -> None:
    """Rebuild positions without fabricating valuation evidence for legacy rows."""
    inspector = inspect(connection)
    if "positions" not in set(inspector.get_table_names()):
        return
    columns = {item["name"]: item for item in inspector.get_columns("positions")}
    required = {
        "valuation_currency",
        "unit_price",
        "price_currency",
        "valued_at_utc",
        "price_source_ref",
        "fx_rate",
        "fx_as_of_utc",
        "fx_source_ref",
        "valuation_status",
    }
    if required <= set(columns) and columns["market_value"].get("nullable", False):
        return
    rows = [dict(row) for row in connection.execute(text("SELECT * FROM positions")).mappings()]
    connection.execute(text("DROP TABLE positions"))
    SQLModel.metadata.tables["positions"].create(connection)
    current_columns = set(SQLModel.metadata.tables["positions"].columns.keys())
    migrated: list[dict[str, Any]] = []
    for row in rows:
        projected = {key: value for key, value in row.items() if key in current_columns}
        projected.update(
            {
                "valuation_currency": None,
                "unit_price": None,
                "price_currency": None,
                "valued_at_utc": None,
                "price_source_ref": None,
                "fx_rate": None,
                "fx_as_of_utc": None,
                "fx_source_ref": None,
                "valuation_status": "unknown_legacy",
            }
        )
        migrated.append(projected)
    if migrated:
        connection.execute(SQLModel.metadata.tables["positions"].insert(), migrated)


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


def _migrate_add_version_binding_columns(connection: Connection) -> None:
    """Add bound_proposal_version_id / bound_proposal_receipt_ref to attestations
    and review_events. Legacy rows stay NULL; new writes set them non-null."""
    for table_name in ("attestations", "review_events"):
        inspector = inspect(connection)
        if table_name not in set(inspector.get_table_names()):
            continue
        existing = {col["name"] for col in inspector.get_columns(table_name)}
        for col_name in ("bound_proposal_version_id", "bound_proposal_receipt_ref"):
            if col_name not in existing:
                connection.exec_driver_sql(
                    f"ALTER TABLE {table_name} ADD COLUMN {col_name} TEXT"
                )


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
        (9, _migrate_add_canonical_identities),
        (10, _migrate_position_valuation_contract),
        (11, _migrate_add_import_correction_semantics),
        (12, _migrate_add_agent_authority_currency_bindings),
        (13, _migrate_add_version_binding_columns),
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
                if version == 10:
                    connection.exec_driver_sql("PRAGMA foreign_keys = OFF")
                    connection.commit()
                with connection.begin():
                    step(connection)
                    connection.exec_driver_sql(f"PRAGMA user_version = {version}")
                if version == 10:
                    connection.exec_driver_sql("PRAGMA foreign_keys = ON")
                    connection.commit()
    except (SQLAlchemyError, OSError) as exc:
        raise StateCoreStoreError(f"state-core migration failed: {exc}") from exc


@contextmanager
def immediate_state_core_session(engine: Engine) -> Iterator[Session]:
    """Yield a Session on a ``BEGIN IMMEDIATE`` SQLite connection.

    The connection is created, ``BEGIN IMMEDIATE`` is executed, then a Session
    is bound to it with ``expire_on_commit=False``.  The caller does the
    application-level writes inside the ``with`` block, then:

    * ``session.flush()``
    * ``connection.commit()``

    On any exception the connection is rolled back.  The session and
    connection are always closed before leaving the context manager.

    Only the context manager owns commit/rollback — callers must never call
    ``session.commit()`` or ``connection.commit()`` inside the block.
    """
    connection = engine.connect()
    session: Session | None = None
    try:
        connection.exec_driver_sql("BEGIN IMMEDIATE")
        session = Session(bind=connection, expire_on_commit=False)
        yield session
        session.flush()
        connection.commit()
    except (SQLAlchemyError, OSError) as exc:
        connection.rollback()
        raise StateCoreStoreError(
            f"state-core immediate transaction failed: {exc}"
        ) from exc
    except Exception:
        connection.rollback()
        raise
    finally:
        if session is not None:
            session.close()
        connection.close()


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
                    _reject_alias_retarget(session, record)
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


_PRODUCTION_SOURCE_KINDS = set(_REGISTRY_SOURCE_KINDS)
_PRODUCTION_MATERIALIZED_SOURCES = set(_REGISTRY_MATERIALIZED_SOURCES)
_PRODUCTION_IMPORT_KINDS = _PRODUCTION_SOURCE_KINDS | _PRODUCTION_MATERIALIZED_SOURCES


def _reject_unmanifested_production_import(records: Sequence[StateCoreRecord]) -> None:
    """Keep generic store helpers from bypassing W0 for known production adapters."""
    for record in records:
        if isinstance(record, ReceiptIndex) and record.kind in _PRODUCTION_IMPORT_KINDS:
            raise StateCoreStoreError("production import receipts require materialize_import_batch")
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
            raise StateCoreStoreError("production import state requires materialize_import_batch")


def _reject_alias_retarget(session: Session, record: StateCoreRecord) -> None:
    if not isinstance(record, IdentityAlias):
        return
    existing = session.get(IdentityAlias, record.alias_id)
    if existing is None:
        return
    identity_fields = (
        "identity_kind",
        "provider_namespace",
        "provider_alias",
        "canonical_id",
        "mapping_version",
    )
    if any(getattr(existing, field) != getattr(record, field) for field in identity_fields):
        raise StateCoreStoreError("identity alias mapping is immutable")


def _validate_import_envelope(  # noqa: C901
    *,
    source: str,
    batch: ImportBatch,
    manifest: ReceiptManifest,
    records: Sequence[StateCoreRecord],
    artifact_store: ArtifactStore,
) -> None:
    from finharness.artifact_store import ArtifactStoreError

    _validate_import_contract_fields(source=source, batch=batch, manifest=manifest)
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
    from finharness.capital_import_registry import materialized_source_for

    expected_kind = materialized_source_for(source) if source in _PRODUCTION_SOURCE_KINDS else None
    if expected_kind is not None and receipt_index.kind != expected_kind:
        raise StateCoreStoreError(
            f"receipt index kind {receipt_index.kind!r} != canonical {expected_kind!r}"
        )
    if (
        receipt_index.receipt_id != manifest.receipt_id
        or receipt_index.path != manifest.receipt_ref
    ):
        raise StateCoreStoreError("receipt index does not match the receipt manifest")
    if source in _PRODUCTION_SOURCE_KINDS:
        expected_source_refs = [manifest.receipt_ref, batch.source_id]
        if receipt_index.source_refs != expected_source_refs:
            raise StateCoreStoreError("receipt index source_refs contract mismatch")
    if manifest.snapshot_id and source == "broker_read":
        all_snapshots = [
            record for record in records if isinstance(record, Snapshot)
        ]
        if len(all_snapshots) != 1:
            raise StateCoreStoreError(
                f"manifest declares snapshot_id but found {len(all_snapshots)} snapshots"
            )
        if all_snapshots[0].snapshot_id != manifest.snapshot_id:
            raise StateCoreStoreError(
                f"snapshot id {all_snapshots[0].snapshot_id!r} != manifest {manifest.snapshot_id!r}"
            )
        active_snapshot = all_snapshots[0]
        snapshot_payload = active_snapshot.payload
        required_bindings = {
            "import_batch_id": batch.batch_id,
            "receipt_manifest_id": manifest.manifest_id,
            "import_receipt_id": manifest.receipt_id,
            "import_receipt_ref": manifest.receipt_ref,
            "source_artifact_id": batch.source_artifact_id,
            "record_counts": batch.record_counts,
            "completeness_status": batch.completeness_status,
            "findings": batch.findings,
        }
        for key, expected in required_bindings.items():
            if key not in snapshot_payload:
                raise StateCoreStoreError(
                    f"snapshot payload missing required import binding: {key}"
                )
            if snapshot_payload[key] != expected:
                raise StateCoreStoreError(
                    f"snapshot payload {key!r} binding mismatch: "
                    f"{snapshot_payload[key]!r} != {expected!r}"
                )
    if source == "broker_read":
        from finharness.capital_import_registry import receipt_index_contract_fields

        try:
            receipt_payload = json.loads(receipt_content)
        except (UnicodeDecodeError, json.JSONDecodeError):
            receipt_payload = {}
        contract = receipt_index_contract_fields(
            source_kind=source,
            receipt_ref=manifest.receipt_ref,
            created_at_utc=receipt_descriptor.created_at_utc,
            source_ref=str(receipt_payload.get("source_ref") or batch.source_id),
            upstream_receipt_id=receipt_payload.get("upstream_receipt_id"),
            source_artifact_id=batch.source_artifact_id,
        )
        if receipt_index.kind != contract["kind"]:
            raise StateCoreStoreError("receipt index kind contract mismatch")
        if receipt_index.path != contract["path"]:
            raise StateCoreStoreError("receipt index path contract mismatch")
        if receipt_index.created_at_utc != contract["created_at_utc"]:
            raise StateCoreStoreError("receipt index created_at_utc contract mismatch")
        if receipt_index.source_refs != contract["source_refs"]:
            raise StateCoreStoreError("receipt index source_refs contract mismatch")
        if receipt_index.refs != contract["refs"]:
            raise StateCoreStoreError("receipt index refs contract mismatch")


def _validate_import_contract_fields(
    *, source: str, batch: ImportBatch, manifest: ReceiptManifest
) -> None:
    if batch.source_kind != source:
        raise StateCoreStoreError("import batch source does not match materialization source")
    if batch.coverage_mode not in {"full", "delta"}:
        raise StateCoreStoreError("import batch coverage mode is outside the closed set")
    if (batch.supersedes_batch_id is None) != (batch.correction_reason is None):
        raise StateCoreStoreError(
            "import correction requires both supersedes_batch_id and correction_reason"
        )
    if batch.correction_reason is not None and not batch.correction_reason.strip():
        raise StateCoreStoreError("import correction reason must be non-empty")
    if batch.completeness_status not in {"complete", "partial", "blocked"}:
        raise StateCoreStoreError("current import completeness status is outside the closed set")
    if manifest.batch_id != batch.batch_id:
        raise StateCoreStoreError("receipt manifest does not bind the import batch")
    if manifest.source_artifact_id != batch.source_artifact_id:
        raise StateCoreStoreError("receipt manifest does not bind the source evidence")
    if manifest.materialization_status != "materialized":
        raise StateCoreStoreError("only a materialized receipt manifest can become current")



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
        "covered_domains": batch.covered_domains,
        "supersedes_batch_id": batch.supersedes_batch_id,
        "correction_reason": batch.correction_reason,
        "corporate_action_status": batch.corporate_action_status,
        "corporate_action_gaps": batch.corporate_action_gaps,
    }
    if any(receipt_payload.get(key) != value for key, value in expected_receipt_fields.items()):
        raise StateCoreStoreError("receipt artifact does not bind the import envelope")
    if manifest.record_counts != batch.record_counts:
        raise StateCoreStoreError("manifest record counts do not match the import batch")


def _tombstone_id(batch_id: str, record_type: str, record_id: str) -> str:
    digest = hashlib.sha256(
        "\x00".join((batch_id, record_type, record_id)).encode("utf-8")
    ).hexdigest()[:24]
    return f"import_tombstone_{digest}"


def _tombstone(
    *, batch: ImportBatch, record_type: str, record_id: str, reason: str
) -> ImportTombstone:
    return ImportTombstone(
        tombstone_id=_tombstone_id(batch.batch_id, record_type, record_id),
        batch_id=batch.batch_id,
        source_kind=batch.source_kind,
        record_type=record_type,
        record_id=record_id,
        reason=reason,
        source_refs=[batch.source_artifact_id],
        as_of_utc=batch.as_of_utc,
        authority_level="read_only",
    )


def _position_identity(position: Position) -> tuple[str, str]:
    return (
        position.account_id,
        position.instrument_id or f"legacy-symbol:{position.symbol.upper()}",
    )


def _previous_source_snapshot(session: Session, *, batch: ImportBatch) -> Snapshot | None:
    statement = (
        select(Snapshot)
        .join(ReceiptManifest, col(ReceiptManifest.snapshot_id) == Snapshot.snapshot_id)
        .join(ImportBatch, col(ImportBatch.batch_id) == ReceiptManifest.batch_id)
        .where(
            ImportBatch.source_kind == batch.source_kind,
            ImportBatch.source_id == batch.source_id,
            ImportBatch.batch_id != batch.batch_id,
        )
        .order_by(
            col(ReceiptManifest.materialized_at_utc).desc(),
            col(ReceiptManifest.manifest_id).desc(),
        )
    )
    return session.exec(statement).first()


def _automatic_full_tombstones(
    session: Session,
    *,
    batch: ImportBatch,
    records: Sequence[StateCoreRecord],
) -> list[ImportTombstone]:
    tombstones: list[ImportTombstone] = []
    for model, id_field, _table, domain in _SOURCE_OWNED_MODELS:
        if domain not in batch.covered_domains:
            continue
        incoming_ids = {
            str(getattr(record, id_field)) for record in records if isinstance(record, model)
        }
        existing = session.exec(select(model).where(model.source == batch.source_kind)).all()
        for record in existing:
            record_id = str(getattr(record, id_field))
            if record_id not in incoming_ids:
                tombstones.append(
                    _tombstone(
                        batch=batch,
                        record_type=model.__name__,
                        record_id=record_id,
                        reason="absent_from_full_import",
                    )
                )
    previous_snapshot = _previous_source_snapshot(session, batch=batch)
    incoming_positions = [record for record in records if isinstance(record, Position)]
    if previous_snapshot is not None and "position" in batch.covered_domains:
        incoming_keys = {_position_identity(position) for position in incoming_positions}
        previous_positions = session.exec(
            select(Position).where(Position.snapshot_id == previous_snapshot.snapshot_id)
        ).all()
        for position in previous_positions:
            if _position_identity(position) not in incoming_keys:
                tombstones.append(
                    _tombstone(
                        batch=batch,
                        record_type="Position",
                        record_id=position.position_id,
                        reason="absent_from_full_import",
                    )
                )
    return tombstones


def _apply_explicit_tombstones(
    session: Session, *, source: str, tombstones: Sequence[ImportTombstone]
) -> None:
    by_type = {
        model.__name__: (model, id_field)
        for model, id_field, _table, _domain in _SOURCE_OWNED_MODELS
    }
    for tombstone in tombstones:
        target = by_type.get(tombstone.record_type)
        if target is None:
            # Position tombstones are applied by snapshot construction; immutable
            # historical Position rows are deliberately retained.
            if tombstone.record_type == "Position":
                continue
            raise StateCoreStoreError(
                f"unsupported import tombstone record type: {tombstone.record_type}"
            )
        model, id_field = target
        session.execute(
            delete(model).where(
                col(getattr(model, id_field)) == tombstone.record_id,
                col(model.source) == source,
            )
        )


def _validate_existing_import_lineage(
    session: Session,
    *,
    source: str,
    batch: ImportBatch,
    manifest: ReceiptManifest,
    tombstones: Sequence[ImportTombstone],
) -> None:
    if any(
        tombstone.batch_id != batch.batch_id or tombstone.source_kind != source
        for tombstone in tombstones
    ):
        raise StateCoreStoreError("import tombstone does not bind the import batch")
    existing_batch = session.get(ImportBatch, batch.batch_id)
    if existing_batch is not None and existing_batch.model_dump() != batch.model_dump():
        raise StateCoreStoreError("import batch identity is immutable")
    existing_manifest = session.get(ReceiptManifest, manifest.manifest_id)
    if existing_manifest is not None and existing_manifest.model_dump() != manifest.model_dump():
        raise StateCoreStoreError("receipt manifest identity is immutable")
    if batch.supersedes_batch_id is None:
        return
    superseded = session.get(ImportBatch, batch.supersedes_batch_id)
    if superseded is None:
        raise StateCoreStoreError("superseded import batch does not exist")
    if superseded.source_kind != batch.source_kind or superseded.source_id != batch.source_id:
        raise StateCoreStoreError("superseded import batch belongs to a different source")


def _delete_covered_source_records(
    session: Session, *, source: str, covered_domains: Sequence[str]
) -> None:
    for model, _id_field, _table, domain in _SOURCE_OWNED_MODELS:
        if domain in covered_domains:
            session.execute(delete(model).where(col(model.source) == source))


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

    Full imports replace only their declared source-owned domains and retain
    tombstones for disappeared rows. Delta imports preserve omitted rows and apply
    only explicit tombstones. The batch and manifest are committed in the same
    database transaction as the queryable records; callers cannot make an import
    current by supplying only direct state payloads.
    """
    materialized = list(records)
    _validate_import_envelope(
        source=source,
        batch=batch,
        manifest=manifest,
        records=materialized,
        artifact_store=artifact_store,
    )
    from finharness.capital_import_valuation import validate_import_valuation_contract
    from finharness.position_valuation import PositionValuationError

    try:
        validate_import_valuation_contract(
            source=source,
            batch=batch,
            manifest=manifest,
            records=materialized,
            artifact_store=artifact_store,
        )
    except PositionValuationError as exc:
        raise StateCoreStoreError(str(exc)) from exc
    saved: list[StateCoreRecord] = []
    try:
        with Session(engine) as session:
            with session.begin():
                explicit_tombstones = [
                    record for record in materialized if isinstance(record, ImportTombstone)
                ]
                _validate_existing_import_lineage(
                    session,
                    source=source,
                    batch=batch,
                    manifest=manifest,
                    tombstones=explicit_tombstones,
                )
                automatic_tombstones = (
                    _automatic_full_tombstones(session, batch=batch, records=materialized)
                    if batch.coverage_mode == "full"
                    else []
                )
                tombstones_by_id = {
                    tombstone.tombstone_id: tombstone
                    for tombstone in [*automatic_tombstones, *explicit_tombstones]
                }
                if batch.coverage_mode == "full":
                    _delete_covered_source_records(
                        session, source=source, covered_domains=batch.covered_domains
                    )
                _apply_explicit_tombstones(
                    session, source=source, tombstones=list(tombstones_by_id.values())
                )
                non_tombstone_records = [
                    record for record in materialized if not isinstance(record, ImportTombstone)
                ]
                for record in [
                    batch,
                    manifest,
                    *non_tombstone_records,
                    *tombstones_by_id.values(),
                ]:
                    _reject_alias_retarget(session, record)
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
