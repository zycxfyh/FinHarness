"""Shared SQLModel primitives for StateCore bounded-context modules.

This module deliberately contains no table models.  Bounded-context model
modules may depend on it without importing the historical ``models``
compatibility surface and creating a circular dependency.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import JSON, Column, String
from sqlalchemy.engine.interfaces import Dialect
from sqlalchemy.types import TypeDecorator
from sqlmodel import Field, SQLModel

STATE_CORE_SCHEMA_VERSION = "finharness.state_core.v1"
AuthorityLevel = str


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def json_list_column() -> Any:
    return Column(JSON, nullable=False)


def json_dict_column() -> Any:
    return Column(JSON, nullable=False)


class DecimalText(TypeDecorator[Decimal]):
    """Store ``Decimal`` exactly as TEXT."""

    impl = String
    cache_ok = True

    def process_bind_param(self, value: Decimal | None, dialect: Dialect) -> str | None:
        if value is None:
            return None
        return str(value)

    def process_result_value(self, value: object, dialect: Dialect) -> Decimal | None:
        if value is None:
            return None
        if isinstance(value, Decimal):
            return value
        # Pre-existing SQLite databases may still return REAL/NUMERIC values.
        # Normalise through str() instead of Decimal(float) to avoid binary noise.
        return Decimal(str(value))


def money_column(*, nullable: bool = False) -> Any:
    """Column for an exact monetary/decimal amount."""

    return Column(DecimalText, nullable=nullable)


class StateCoreBase(SQLModel):
    """Common governance columns shared by StateCore tables."""

    schema_version: str = STATE_CORE_SCHEMA_VERSION
    as_of_utc: str = Field(default_factory=utc_now_iso)
    authority_level: AuthorityLevel = "read_only"


class SourcedStateCoreBase(StateCoreBase):
    """StateCore tables fully owned by the import source that produced them."""

    source: str = Field(default="")
