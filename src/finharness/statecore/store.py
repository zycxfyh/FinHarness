"""SQLite store for the FinHarness state core."""

from __future__ import annotations

import os
from collections.abc import Callable, Iterable, Sequence
from pathlib import Path
from typing import Any, cast

from sqlalchemy import Connection, Engine, event, inspect, text
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session, SQLModel, create_engine, select

from finharness.market_data import ROOT
from finharness.statecore.models import (
    Account,
    Attestation,
    CashflowEvent,
    DocumentRef,
    FinancialGoal,
    InsurancePolicy,
    Liability,
    Position,
    Proposal,
    ReceiptIndex,
    Snapshot,
    TaxEvent,
)

STATE_CORE_DB_ENV_VAR = "FINHARNESS_STATE_CORE_DB_PATH"
DEFAULT_STATE_CORE_DB_PATH = ROOT / "data" / "state" / "state-core" / "state-core.sqlite"

StateCoreRecord = (
    Account
    | Position
    | Liability
    | FinancialGoal
    | CashflowEvent
    | TaxEvent
    | InsurancePolicy
    | DocumentRef
    | Snapshot
    | ReceiptIndex
    | Proposal
    | Attestation
)


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
                raise StateCoreStoreError(
                    f"state-core sqlite WAL mode unavailable: {journal_mode}"
                )
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


CURRENT_STATE_CORE_USER_VERSION = 2

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


def migrate_state_core(engine: Engine) -> None:
    """Apply versioned, idempotent state-core migrations via ``PRAGMA user_version``."""
    migrations: tuple[tuple[int, Callable[[Connection], None]], ...] = (
        (1, _migrate_positions_money_to_text),
        (2, _migrate_add_source_columns),
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
    owned_engine = engine is None
    active_engine = engine or open_state_core(path)
    saved: list[StateCoreRecord] = []
    try:
        with Session(active_engine) as session:
            with session.begin():
                for record in records:
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
    owned_engine = engine is None
    active_engine = engine or open_state_core(path)
    saved: list[StateCoreRecord] = []
    try:
        with Session(active_engine) as session:
            with session.begin():
                for record in records:
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


def replace_source_records(
    records: Iterable[StateCoreRecord],
    *,
    source: str,
    engine: Engine,
) -> list[StateCoreRecord]:
    """Reconcile a personal-finance import: replace ``source``-owned rows, then upsert.

    Source-owned tables (liabilities, goals, cashflows, tax events, insurance,
    documents) are deleted for ``source`` first so a re-import drops rows that no
    longer exist upstream, instead of accumulating them. Other records (snapshot,
    accounts, positions, receipt index) are merged as usual. All in one transaction.
    """
    materialized = list(records)
    saved: list[StateCoreRecord] = []
    try:
        with Session(engine) as session:
            with session.begin():
                for statement in _SOURCE_DELETES:
                    session.execute(statement, {"source": source})
                for record in materialized:
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
