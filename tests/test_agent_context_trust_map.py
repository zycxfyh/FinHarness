"""Tests for context trust map extraction.

Agentic-space dimension: Context Space.
Operating surface: Track C — Context / Memory / Search.
"""

from __future__ import annotations

from finharness.agent_context_trust_map import extract_context_trust_by_ref
from finharness.context_trust import (
    trust_for_human_attested,
    trust_for_receipt_backed_state,
    trust_for_system_computed,
)


class TestExtractContextTrustByRef:
    """Unit tests for context trust map extraction."""

    def test_empty_payload_returns_empty_map(self) -> None:
        """Empty payload → empty trust map."""
        result = extract_context_trust_by_ref({})
        assert result == {}

    def test_no_packs_returns_empty_map(self) -> None:
        """Payload without packs → empty trust map."""
        result = extract_context_trust_by_ref({"bundle": {}})
        assert result == {}

    def test_pack_level_trust_extracted(self) -> None:
        """Pack-level summary.trust → mapped to pack's source_refs."""
        trust = trust_for_system_computed(source_refs=["ref://1"])
        payload = {
            "packs": [{
                "name": "capital_summary",
                "summary": {
                    "open_count": 3,
                    "trust": trust.model_dump(),
                },
                "source_refs": ["ref://1"],
            }]
        }
        result = extract_context_trust_by_ref(payload)
        assert "ref://1" in result
        assert result["ref://1"].source_type == "system_computed"

    def test_item_level_trust_overrides_pack_level(self) -> None:
        """Item-level trust takes priority over pack-level trust."""
        pack_trust = trust_for_system_computed(source_refs=["ref://1"])
        item_trust = trust_for_human_attested(
            source_refs=["ref://2"],
        )
        payload = {
            "packs": [{
                "name": "open_proposals",
                "summary": {
                    "trust": pack_trust.model_dump(),
                    "items": [{
                        "proposal_id": "p1",
                        "source_refs": ["ref://2"],
                        "trust": item_trust.model_dump(),
                    }],
                },
                "source_refs": ["ref://1"],
            }]
        }
        result = extract_context_trust_by_ref(payload)
        # Pack-level still applied to pack's own refs
        assert "ref://1" in result
        assert result["ref://1"].source_type == "system_computed"
        # Item-level applied to item's refs
        assert "ref://2" in result
        assert result["ref://2"].source_type == "human_attested"

    def test_receipt_backed_refs_retain_trust(self) -> None:
        """Receipt-backed state refs map correctly."""
        trust = trust_for_receipt_backed_state(
            source_refs=["receipt://abc123"],
            receipt_refs=["r1"],
        )
        payload = {
            "packs": [{
                "name": "proposal_timeline",
                "summary": {
                    "trust": trust.model_dump(),
                },
                "source_refs": ["receipt://abc123"],
                "receipt_refs": ["r1"],
            }]
        }
        result = extract_context_trust_by_ref(payload)
        assert "receipt://abc123" in result
        assert result["receipt://abc123"].source_type == "receipt_backed_state"
        assert "r1" in result

    def test_missing_trust_not_auto_upgraded(self) -> None:
        """Refs without trust metadata are NOT added to the map."""
        payload = {
            "packs": [{
                "name": "some_pack",
                "summary": {},
                "source_refs": ["unknown://ref"],
            }]
        }
        result = extract_context_trust_by_ref(payload)
        assert "unknown://ref" not in result

    def test_item_receipt_ref_is_mapped(self) -> None:
        """An item's receipt_ref is mapped with item-level trust."""
        trust = trust_for_receipt_backed_state(
            source_refs=[],
            receipt_refs=["r_item"],
        )
        payload = {
            "packs": [{
                "name": "proposals",
                "summary": {
                    "items": [{
                        "proposal_id": "p1",
                        "receipt_ref": "r_item",
                        "trust": trust.model_dump(),
                    }],
                },
            }]
        }
        result = extract_context_trust_by_ref(payload)
        assert "r_item" in result
        assert result["r_item"].source_type == "receipt_backed_state"
