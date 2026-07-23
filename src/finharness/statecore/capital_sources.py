"""Stable logical identities for external capital-import sources."""

from __future__ import annotations

import hashlib
from pathlib import Path

from sqlalchemy import Engine
from sqlmodel import Session, select
from uuid6 import uuid7

from finharness.statecore.import_models import (
    CapitalImportSource,
    CapitalImportSourceAlias,
)


class CapitalImportSourceError(RuntimeError):
    """Raised when one discovery alias conflicts with canonical source identity."""


def canonical_path_alias(path: str | Path) -> str:
    """Return a diagnostic path alias; the value never owns source identity."""
    return str(Path(path).resolve())


def _alias_id(alias_kind: str, alias_value: str) -> str:
    digest = hashlib.sha256(f"{alias_kind}\x00{alias_value}".encode()).hexdigest()[:24]
    return f"source_alias_{digest}"


def resolve_or_register_import_source(
    *,
    engine: Engine,
    source_kind: str,
    alias_kind: str,
    alias_value: str,
    source_id: str | None = None,
    display_name: str | None = None,
) -> CapitalImportSource:
    """Resolve a stable source by alias or register a new UUIDv7-backed identity.

    A moved file can be rebound by supplying the previously returned ``source_id``
    once. Future imports from the new path then resolve through the new alias.
    """
    clean_kind = source_kind.strip()
    clean_alias_kind = alias_kind.strip()
    clean_alias_value = alias_value.strip()
    if not clean_kind or not clean_alias_kind or not clean_alias_value:
        raise CapitalImportSourceError("source kind and alias must be non-empty")

    with Session(engine) as session:
        existing_alias = session.exec(
            select(CapitalImportSourceAlias).where(
                CapitalImportSourceAlias.alias_kind == clean_alias_kind,
                CapitalImportSourceAlias.alias_value == clean_alias_value,
            )
        ).one_or_none()
        if source_id is None and existing_alias is not None:
            source = session.get(CapitalImportSource, existing_alias.source_id)
            if source is None:
                raise CapitalImportSourceError("source alias points to a missing source")
            if source.source_kind != clean_kind:
                raise CapitalImportSourceError("source alias belongs to another source kind")
            return source

        active_source_id = source_id or f"source_{uuid7()}"
        source = session.get(CapitalImportSource, active_source_id)
        if source is None:
            source = CapitalImportSource(
                source_id=active_source_id,
                source_kind=clean_kind,
                display_name=(display_name or clean_alias_value).strip(),
                source_refs=[f"{clean_alias_kind}:{clean_alias_value}"],
                authority_level="read_only",
            )
            session.add(source)
        elif source.source_kind != clean_kind:
            raise CapitalImportSourceError("source_id belongs to another source kind")

        if existing_alias is not None and existing_alias.source_id != active_source_id:
            raise CapitalImportSourceError("source alias is already bound to another source")
        if existing_alias is None:
            session.add(
                CapitalImportSourceAlias(
                    alias_id=_alias_id(clean_alias_kind, clean_alias_value),
                    source_id=active_source_id,
                    alias_kind=clean_alias_kind,
                    alias_value=clean_alias_value,
                    authority_level="read_only",
                )
            )
        session.commit()
        persisted = session.get(CapitalImportSource, active_source_id)
        if persisted is None:
            raise CapitalImportSourceError("source registration did not persist")
        return persisted
