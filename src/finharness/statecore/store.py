"""SQLite store for the FinHarness state core."""

from __future__ import annotations

import os
from collections.abc import Iterable, Sequence
from pathlib import Path

from sqlalchemy import Engine, event, text
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import Session, SQLModel, create_engine, select

from finharness.market_data import ROOT
from finharness.statecore.models import (
    Account,
    Attestation,
    Position,
    Proposal,
    ReceiptIndex,
    Snapshot,
)

STATE_CORE_DB_ENV_VAR = "FINHARNESS_STATE_CORE_DB_PATH"
DEFAULT_STATE_CORE_DB_PATH = ROOT / "data" / "state" / "state-core" / "state-core.sqlite"

StateCoreRecord = Account | Position | Snapshot | ReceiptIndex | Proposal | Attestation


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


def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record) -> None:
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
    try:
        SQLModel.metadata.create_all(engine)
    except (SQLAlchemyError, OSError) as exc:
        raise StateCoreStoreError(f"state-core schema initialization failed: {exc}") from exc
    return engine


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


def read_all(model: type[StateCoreRecord], *, engine: Engine) -> Sequence[StateCoreRecord]:
    with Session(engine) as session:
        return list(session.exec(select(model)).all())


def get_account(account_id: str, *, engine: Engine) -> Account | None:
    with Session(engine) as session:
        return session.get(Account, account_id)


def get_snapshot(snapshot_id: str, *, engine: Engine) -> Snapshot | None:
    with Session(engine) as session:
        return session.get(Snapshot, snapshot_id)
