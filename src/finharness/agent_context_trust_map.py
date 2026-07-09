"""Context trust map extraction from projection payload.

Agentic-space dimension: Context Space.
Operating surface: Track C — Context / Memory / Search.

Extracts a dict[str, ContextTrust] from a context projection payload
so AgentCognitionFlow can validate source_refs against trust metadata.
"""

from __future__ import annotations

from collections.abc import Mapping

from finharness.context_trust import ContextTrust


def extract_context_trust_by_ref(
    projection_payload: Mapping[str, object],
) -> dict[str, ContextTrust]:
    """Extract context_trust_by_ref map from a projection payload.

    Scans packs[].summary.trust (pack-level) and
    packs[].summary.items[].trust (item-level, higher priority)
    to build a ref → ContextTrust mapping.

    Rules:
    - item-level trust overrides pack-level trust
    - receipt-backed refs retain receipt-backed trust
    - system-computed refs retain system-computed trust
    - missing trust is NOT auto-upgraded
    """
    trust_map: dict[str, ContextTrust] = {}
    packs = projection_payload.get("packs")
    if not isinstance(packs, list):
        return trust_map

    for pack in packs:
        if isinstance(pack, dict):
            _extract_pack_trust(pack, trust_map)

    return trust_map


def _extract_pack_trust(
    pack: dict[str, object],
    trust_map: dict[str, ContextTrust],
) -> None:
    """Extract trust from one pack and populate the trust map."""
    pack_summary = pack.get("summary")
    pack_trust = _extract_trust_entry(pack_summary)

    refs = [
        *_extract_string_list(pack, "source_refs"),
        *_extract_string_list(pack, "receipt_refs"),
        *_extract_string_list(pack, "context_pack_refs"),
    ]

    # Pack-level trust: only for refs not already covered
    if pack_trust is not None:
        for ref in refs:
            if ref not in trust_map:
                trust_map[ref] = pack_trust

    # Item-level trust: higher priority, always overrides
    if isinstance(pack_summary, dict):
        _extract_items_trust(pack_summary, trust_map)


def _extract_items_trust(
    pack_summary: dict[str, object],
    trust_map: dict[str, ContextTrust],
) -> None:
    """Extract item-level trust from summary items."""
    items = pack_summary.get("items")
    if not isinstance(items, list):
        return
    for item in items:
        if not isinstance(item, dict):
            continue
        item_trust = _extract_trust_entry(item)
        if item_trust is None:
            continue
        item_refs = _extract_string_list(item, "source_refs")
        item_receipt = item.get("receipt_ref")
        if isinstance(item_receipt, str) and item_receipt.strip():
            item_refs.append(item_receipt.strip())
        for ref in item_refs:
            trust_map[ref] = item_trust


def _extract_trust_entry(data: object) -> ContextTrust | None:
    """Extract a ContextTrust from a dict's 'trust' key."""
    if not isinstance(data, dict):
        return None
    trust_data = data.get("trust")
    if not isinstance(trust_data, dict):
        return None
    try:
        return ContextTrust(**trust_data)
    except (TypeError, ValueError):
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
