"""Context trust map extraction from projection payload.

Agentic-space dimension: Context Space.
Operating surface: Track C — Context / Memory / Search.

v0.1 (PR #210): Returns findings for malformed trust/pack data instead
of silently swallowing errors.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Literal

from pydantic import BaseModel, ConfigDict

from finharness.context_trust import ContextTrust


class ContextTrustMapFinding(BaseModel):
    """Diagnostic finding from trust map extraction."""

    model_config = ConfigDict(frozen=True)

    severity: Literal["warn", "block"]
    code: str
    message: str


class ContextTrustMapExtractionResult(BaseModel):
    """Result of extracting context trust from projection payload."""

    model_config = ConfigDict(frozen=True)

    trust_by_ref: dict[str, ContextTrust] = {}
    findings: list[ContextTrustMapFinding] = []


def extract_context_trust_map(
    projection_payload: Mapping[str, object],
) -> ContextTrustMapExtractionResult:
    """Extract context_trust_by_ref map with diagnostic findings.

    Scans packs[].summary.trust (pack-level) and
    packs[].summary.items[].trust (item-level, higher priority)
    to build a ref -> ContextTrust mapping.

    Returns both the trust map and any findings about malformed
    trust data that was silently swallowed in v0.
    """
    trust_map: dict[str, ContextTrust] = {}
    findings: list[ContextTrustMapFinding] = []
    packs = projection_payload.get("packs")
    if not isinstance(packs, list):
        return ContextTrustMapExtractionResult(
            trust_by_ref=trust_map, findings=findings,
        )

    for i, pack in enumerate(packs):
        if isinstance(pack, dict):
            _extract_pack_trust(pack, trust_map, findings, i)
        else:
            findings.append(ContextTrustMapFinding(
                severity="warn",
                code="malformed_pack",
                message=f"Pack at index {i} is not a dict: {type(pack).__name__}",
            ))

    return ContextTrustMapExtractionResult(
        trust_by_ref=trust_map, findings=findings,
    )


def extract_context_trust_by_ref(
    projection_payload: Mapping[str, object],
) -> dict[str, ContextTrust]:
    """Return just the trust map (backward-compat wrapper)."""
    return extract_context_trust_map(projection_payload).trust_by_ref


def _extract_pack_trust(
    pack: dict[str, object],
    trust_map: dict[str, ContextTrust],
    findings: list[ContextTrustMapFinding],
    pack_idx: int,
) -> None:
    """Extract trust from one pack and populate the trust map."""
    pack_summary = pack.get("summary")
    pack_trust = _extract_trust_entry(
        pack_summary, findings, f"pack[{pack_idx}].summary"
    )

    refs = [
        *_extract_string_list(pack, "source_refs"),
        *_extract_string_list(pack, "receipt_refs"),
        *_extract_string_list(pack, "context_pack_refs"),
    ]

    if not refs and pack_trust is not None:
        findings.append(ContextTrustMapFinding(
            severity="warn",
            code="pack_trust_without_refs",
            message=(
                f"Pack at index {pack_idx} has trust metadata but no "
                "source_refs, receipt_refs, or context_pack_refs"
            ),
        ))

    # Pack-level trust: only for refs not already covered
    if pack_trust is not None:
        for ref in refs:
            if ref not in trust_map:
                trust_map[ref] = pack_trust

    # Item-level trust: higher priority, always overrides
    if isinstance(pack_summary, dict):
        _extract_items_trust(pack_summary, trust_map, findings)


def _extract_items_trust(
    pack_summary: dict[str, object],
    trust_map: dict[str, ContextTrust],
    findings: list[ContextTrustMapFinding],
) -> None:
    """Extract item-level trust from summary items."""
    items = pack_summary.get("items")
    if not isinstance(items, list):
        return
    for i, item in enumerate(items):
        if not isinstance(item, dict):
            findings.append(ContextTrustMapFinding(
                severity="warn",
                code="malformed_pack",
                message=f"Item at index {i} is not a dict: {type(item).__name__}",
            ))
            continue
        item_trust = _extract_trust_entry(
            item, findings, f"items[{i}]"
        )
        if item_trust is None:
            continue
        item_refs = _extract_string_list(item, "source_refs")
        item_receipt = item.get("receipt_ref")
        if isinstance(item_receipt, str) and item_receipt.strip():
            item_refs.append(item_receipt.strip())
        if not item_refs:
            findings.append(ContextTrustMapFinding(
                severity="warn",
                code="item_trust_without_ref",
                message=f"Item at index {i} has trust but no source_refs or receipt_ref",
            ))
        for ref in item_refs:
            trust_map[ref] = item_trust


def _extract_trust_entry(
    data: object,
    findings: list[ContextTrustMapFinding],
    location: str,
) -> ContextTrust | None:
    """Extract a ContextTrust from a dict's 'trust' key."""
    if not isinstance(data, dict):
        return None
    trust_data = data.get("trust")
    if not isinstance(trust_data, dict):
        return None
    try:
        return ContextTrust(**trust_data)
    except (TypeError, ValueError) as exc:
        findings.append(ContextTrustMapFinding(
            severity="warn",
            code="malformed_trust",
            message=(
                f"Malformed trust at {location}: {exc}"
            ),
        ))
        return None


def _extract_string_list(data: dict[str, object], key: str) -> list[str]:
    """Extract a list of strings from a dict key."""
    value = data.get(key)
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, (list, tuple)):
        return [str(v) for v in value if str(v).strip()]
    return []
