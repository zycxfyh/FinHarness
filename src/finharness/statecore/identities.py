"""Deterministic canonical identity construction and duplicate readiness checks."""

from __future__ import annotations

import hashlib
from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass
from typing import Literal

from finharness.statecore.models import (
    Account,
    AccountIdentity,
    IdentityAlias,
    InstrumentIdentity,
    Position,
)

IdentityKind = Literal["account", "instrument"]


class IdentityContractError(ValueError):
    """Raised when identity input would be ambiguous or non-deterministic."""


@dataclass(frozen=True)
class IdentityReadinessFinding:
    code: str
    severity: Literal["partial", "blocking"]
    message: str
    record_type: str = "position"
    record_id: str | None = None
    field: str = "instrument_id"

    def as_dict(self) -> dict[str, str | None]:
        return asdict(self)


def _required(value: str, field: str, *, upper: bool = False) -> str:
    normalized = value.strip()
    if not normalized:
        raise IdentityContractError(f"{field} must be explicit")
    return normalized.upper() if upper else normalized.lower()


def _id(prefix: str, *parts: str) -> str:
    payload = "\x1f".join(parts).encode("utf-8")
    return f"{prefix}_{hashlib.sha256(payload).hexdigest()[:24]}"


def account_identity(
    *,
    source_namespace: str,
    source_native_id: str,
    source_refs: Sequence[str] = (),
    canonical_account_id: str | None = None,
) -> tuple[AccountIdentity, IdentityAlias]:
    namespace = _required(source_namespace, "source_namespace")
    native_id = source_native_id.strip()
    if not native_id:
        raise IdentityContractError("source_native_id must be explicit")
    canonical_id = canonical_account_id or _id("acct", namespace, native_id)
    identity = AccountIdentity(
        canonical_account_id=canonical_id,
        source_namespace=namespace,
        source_native_id=native_id,
        source_refs=sorted(set(source_refs)),
    )
    alias = identity_alias(
        identity_kind="account",
        provider_namespace=namespace,
        provider_alias=native_id,
        canonical_id=canonical_id,
        source_refs=source_refs,
    )
    return identity, alias


def instrument_identity(
    *,
    symbol: str,
    instrument_type: str,
    venue: str,
    quote_currency: str,
    provider_namespace: str,
    provider_alias: str | None = None,
    source_refs: Sequence[str] = (),
) -> tuple[InstrumentIdentity, IdentityAlias]:
    normalized_symbol = _required(symbol, "symbol", upper=True)
    normalized_type = _required(instrument_type, "instrument_type")
    normalized_venue = _required(venue, "venue")
    normalized_currency = _required(quote_currency, "quote_currency", upper=True)
    if len(normalized_currency) != 3 or not normalized_currency.isalpha():
        raise IdentityContractError("quote_currency must be an explicit three-letter code")
    instrument_id = _id(
        "instr",
        normalized_symbol,
        normalized_type,
        normalized_venue,
        normalized_currency,
    )
    identity = InstrumentIdentity(
        instrument_id=instrument_id,
        symbol=normalized_symbol,
        instrument_type=normalized_type,
        venue=normalized_venue,
        quote_currency=normalized_currency,
        source_refs=sorted(set(source_refs)),
    )
    alias = identity_alias(
        identity_kind="instrument",
        provider_namespace=provider_namespace,
        provider_alias=provider_alias or symbol,
        canonical_id=instrument_id,
        source_refs=source_refs,
    )
    return identity, alias


def identity_alias(
    *,
    identity_kind: IdentityKind,
    provider_namespace: str,
    provider_alias: str,
    canonical_id: str,
    source_refs: Sequence[str] = (),
    mapping_version: str = "finharness.identity_alias.v0",
) -> IdentityAlias:
    namespace = _required(provider_namespace, "provider_namespace")
    alias = provider_alias.strip()
    target = canonical_id.strip()
    version = mapping_version.strip()
    if not alias or not target or not version:
        raise IdentityContractError("alias, canonical_id, and mapping_version must be explicit")
    return IdentityAlias(
        alias_id=_id("alias", identity_kind, namespace, alias, version),
        identity_kind=identity_kind,
        provider_namespace=namespace,
        provider_alias=alias,
        canonical_id=target,
        mapping_version=version,
        source_refs=sorted(set(source_refs)),
    )


def unresolved_instrument_finding(
    *, record_id: str | None, missing_fields: Iterable[str]
) -> IdentityReadinessFinding:
    missing = sorted({field for field in missing_fields if field})
    return IdentityReadinessFinding(
        code="instrument_identity_unresolved",
        severity="blocking",
        message=f"instrument identity is unresolved; missing: {', '.join(missing)}",
        record_id=record_id,
    )


def cross_account_duplicate_findings(
    *, accounts: Sequence[Account], positions: Sequence[Position]
) -> tuple[IdentityReadinessFinding, ...]:
    """Detect the same canonical account/instrument projected through multiple rows."""
    canonical_by_legacy = {account.account_id: account.canonical_account_id for account in accounts}
    groups: dict[tuple[str, str, str], list[Position]] = defaultdict(list)
    findings: list[IdentityReadinessFinding] = []
    for position in positions:
        canonical_account = canonical_by_legacy.get(position.account_id)
        if canonical_account is None or position.instrument_id is None:
            findings.append(
                unresolved_instrument_finding(
                    record_id=position.position_id,
                    missing_fields=(
                        "canonical_account_id" if canonical_account is None else "",
                        "instrument_id" if position.instrument_id is None else "",
                    ),
                )
            )
            continue
        groups[(position.snapshot_id, canonical_account, position.instrument_id)].append(position)
    for (_snapshot, canonical_account, instrument_id), rows in sorted(groups.items()):
        source_accounts = sorted({row.account_id for row in rows})
        if len(source_accounts) < 2:
            continue
        findings.append(
            IdentityReadinessFinding(
                code="cross_account_duplicate",
                severity="blocking",
                message=(
                    f"canonical account {canonical_account} and instrument {instrument_id} "
                    f"appear through source accounts: {', '.join(source_accounts)}"
                ),
                record_id=rows[0].position_id,
            )
        )
    return tuple(findings)
