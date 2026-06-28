from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
THREAT_MODEL = ROOT / "docs" / "security" / "finharness-threat-model.md"
SSDF_MAP = ROOT / "docs" / "security" / "ssdf-control-map.md"
SECURITY_RUNBOOK = ROOT / "docs" / "security" / "security-response-runbook.md"
CODEOWNERS = ROOT / ".github" / "CODEOWNERS"
CURRENT_SECURITY_EVIDENCE = (THREAT_MODEL, SSDF_MAP, SECURITY_RUNBOOK, CODEOWNERS)
ARCHIVED_MAINLINE_PATHS = (
    "src/finharness/okx_cli.py",
    "src/finharness/alpaca_client.py",
    "src/finharness/execution.py",
    "src/finharness/risk_gate.py",
    "src/finharness/execution/",
    "src/finharness/risk_gate/",
)


class SecurityMaturityDocsTest(unittest.TestCase):
    def test_threat_model_tracks_core_boundaries(self) -> None:
        text = THREAT_MODEL.read_text(encoding="utf-8")

        required = [
            "Provider credentials",
            "Archived live-trading boundary",
            "Research asset specs",
            "src/finharness/data_entry.py",
            "src/finharness/restricted_symbols.py",
            "src/finharness/research_assets.py",
            "experiments/archive/live_trading_legacy/",
            ".github/workflows/security.yml",
            "docs/security/security-response-runbook.md",
            ".github/CODEOWNERS",
            "TM-001",
            "TM-008",
            "execution_allowed=false",
            "does not authorize live trading",
        ]
        for item in required:
            with self.subTest(item=item):
                self.assertIn(item, text)

    def test_ssdf_map_links_controls_to_existing_evidence(self) -> None:
        text = SSDF_MAP.read_text(encoding="utf-8")

        required = [
            "PO: Prepare the Organization",
            "PS: Protect the Software",
            "PW: Produce Well-Secured Software",
            "RV: Respond to Vulnerabilities",
            "task release:preflight",
            "task hardening:gate",
            "SBOM",
            "SLSA",
            "CODEOWNERS",
            "security response runbook",
            "does not authorize live trading",
        ]
        for item in required:
            with self.subTest(item=item):
                self.assertIn(item, text)

    def test_security_response_runbook_records_triage_and_release_blocks(self) -> None:
        text = SECURITY_RUNBOOK.read_text(encoding="utf-8")

        required = [
            "Critical",
            "High",
            "Rotation Checklist",
            "Release Blocking Rules",
            "task security:scan",
            "task release:preflight",
            "execution_allowed=true",
            "does not authorize autonomous live trading",
        ]
        for item in required:
            with self.subTest(item=item):
                self.assertIn(item, text)

    def test_codeowners_covers_high_risk_paths(self) -> None:
        text = CODEOWNERS.read_text(encoding="utf-8")

        required = [
            ".github/",
            "Taskfile.yml",
            "src/finharness/authorization.py",
            "src/finharness/restricted_symbols.py",
            "src/finharness/data_entry.py",
            "src/finharness/providers/",
            "src/finharness/research_assets.py",
            "src/finharness/release_preflight_graph.py",
            "experiments/archive/live_trading_legacy/",
            "docs/security/",
            "data/security/",
            "@zycxfyh",
        ]
        for item in required:
            with self.subTest(item=item):
                self.assertIn(item, text)

    def test_current_security_evidence_does_not_require_archived_mainline_paths(self) -> None:
        for path in CURRENT_SECURITY_EVIDENCE:
            text = path.read_text(encoding="utf-8")
            for retired_path in ARCHIVED_MAINLINE_PATHS:
                with self.subTest(path=path.name, retired_path=retired_path):
                    self.assertNotIn(retired_path, text)


if __name__ == "__main__":
    unittest.main()
