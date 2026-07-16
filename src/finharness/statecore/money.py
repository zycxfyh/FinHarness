"""Closed, exact money values for authority and policy boundaries."""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator


def normalize_currency_code(value: str) -> str:
    """Normalize one closed three-letter alphabetic currency code."""

    normalized = value.strip().upper()
    if len(normalized) != 3 or not normalized.isalpha() or not normalized.isascii():
        raise ValueError("currency must be a three-letter ASCII alphabetic code")
    return normalized


class MonetaryAmount(BaseModel):
    """Exact Decimal amount paired with an ISO 4217-style alphabetic code."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    amount: Decimal = Field(ge=0)
    currency: str

    @field_validator("currency")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        return normalize_currency_code(value)

    def require_positive(self, *, field_name: str) -> None:
        if self.amount <= 0:
            raise ValueError(f"{field_name} amount must be positive")
