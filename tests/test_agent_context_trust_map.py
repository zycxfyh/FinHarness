"""Tests for context trust map extraction.

Agentic-space dimension: Context Space.
Operating surface: Track C — Context / Memory / Search.

v0.1 (PR #210): Adds findings for malformed trust/pack data.
"""

from __future__ import annotations

from finharness.agent_context_trust_map import (
    extract_context_trust_by_ref,
    extract_context_trust_map,
)
from finharness.context_trust import (
    trust_for_human_attested,
    trust_for_receipt_backed_state,
    trust_for_system_computed,
)


class TestExtractContextTrustByRef:
    """Existing backward-compat tests."""

    def test_empty_payload_returns_empty_map(self) -> None:
        result = extract_context_trust_by_ref({})
        assert result == {}

    def test_no_packs_returns_empty_map(self) -> None:
        result = extract_context_trust_by_ref({"bundle": {}})
        assert result == {}

    def test_pack_level_trust_extracted(self) -> None:
        trust = trust_for_system_computed(source_refs=["ref://1"])
        payload = {
            "packs": [{
                "name": "capital_summary",
                "summary": {"open_count": 3, "trust": trust.model_dump()},
                "source_refs": ["ref://1"],
            }]
        }
        result = extract_context_trust_by_ref(payload)
        assert "ref://1" in result
        assert result["ref://1"].source_type == "system_computed"

    def test_item_level_trust_overrides_pack_level(self) -> None:
        pack_trust = trust_for_system_computed(source_refs=["ref://1"])
        item_trust = trust_for_human_attested(source_refs=["ref://2"])
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
        assert "ref://1" in result
        assert result["ref://1"].source_type == "system_computed"
        assert "ref://2" in result
        assert result["ref://2"].source_type == "human_attested"

    def test_receipt_backed_refs_retain_trust(self) -> None:
        trust = trust_for_receipt_backed_state(
            source_refs=["receipt://abc123"], receipt_refs=["r1"],
        )
        payload = {
            "packs": [{
                "name": "proposal_timeline",
                "summary": {"trust": trust.model_dump()},
                "source_refs": ["receipt://abc123"],
                "receipt_refs": ["r1"],
            }]
        }
        result = extract_context_trust_by_ref(payload)
        assert "receipt://abc123" in result
        assert result["receipt://abc123"].source_type == "receipt_backed_state"
        assert "r1" in result

    def test_missing_trust_not_auto_upgraded(self) -> None:
        payload = {
            "packs": [{
                "name": "some_pack", "summary": {},
                "source_refs": ["unknown://ref"],
            }]
        }
        result = extract_context_trust_by_ref(payload)
        assert "unknown://ref" not in result

    def test_item_receipt_ref_is_mapped(self) -> None:
        trust = trust_for_receipt_backed_state(source_refs=[], receipt_refs=["r_item"])
        payload = {
            "packs": [{
                "name": "proposals",
                "summary": {"items": [{
                    "proposal_id": "p1", "receipt_ref": "r_item",
                    "trust": trust.model_dump(),
                }]},
            }]
        }
        result = extract_context_trust_by_ref(payload)
        assert "r_item" in result
        assert result["r_item"].source_type == "receipt_backed_state"


class TestExtractContextTrustMapFindings:
    """Tests for findings in trust map extraction (new in v0.1)."""

    def test_extraction_result_has_trust_by_ref(self) -> None:
        trust = trust_for_system_computed(source_refs=["ref://1"])
        payload = {
            "packs": [{
                "name": "p", "summary": {"trust": trust.model_dump()},
                "source_refs": ["ref://1"],
            }]
        }
        result = extract_context_trust_map(payload)
        assert "ref://1" in result.trust_by_ref
        assert isinstance(result.findings, list)

    def test_malformed_pack_produces_finding(self) -> None:
        payload: dict[str, object] = {"packs": ["not_a_dict"]}
        result = extract_context_trust_map(payload)
        codes = {f.code for f in result.findings}
        assert "malformed_pack" in codes

    def test_malformed_trust_produces_finding(self) -> None:
        payload: dict[str, object] = {
            "packs": [{
                "name": "p",
                "summary": {"trust": {"source_type": 999}},  # invalid
                "source_refs": ["ref://1"],
            }]
        }
        result = extract_context_trust_map(payload)
        codes = {f.code for f in result.findings}
        assert "malformed_trust" in codes

    def test_pack_trust_without_refs_produces_finding(self) -> None:
        trust = trust_for_system_computed(source_refs=[])
        payload: dict[str, object] = {
            "packs": [{
                "name": "orphan_trust",
                "summary": {"trust": trust.model_dump()},
            }]
        }
        result = extract_context_trust_map(payload)
        codes = {f.code for f in result.findings}
        assert "pack_trust_without_refs" in codes

    def test_item_trust_without_ref_produces_finding(self) -> None:
        trust = trust_for_human_attested(source_refs=[])
        payload: dict[str, object] = {
            "packs": [{
                "name": "proposals",
                "summary": {"items": [{
                    "trust": trust.model_dump(),
                }]},
            }]
        }
        result = extract_context_trust_map(payload)
        codes = {f.code for f in result.findings}
        assert "item_trust_without_ref" in codes

    def test_backward_compat_helper_works(self) -> None:
        trust = trust_for_system_computed(source_refs=["ref://x"])
        payload: dict[str, object] = {
            "packs": [{"summary": {"trust": trust.model_dump()}, "source_refs": ["ref://x"]}]
        }
        result = extract_context_trust_by_ref(payload)
        assert "ref://x" in result
