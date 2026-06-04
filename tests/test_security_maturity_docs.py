from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
THREAT_MODEL = ROOT / "docs" / "security" / "finharness-threat-model.md"
SSDF_MAP = ROOT / "docs" / "security" / "ssdf-control-map.md"


class SecurityMaturityDocsTest(unittest.TestCase):
    def test_threat_model_tracks_core_boundaries(self) -> None:
        text = THREAT_MODEL.read_text(encoding="utf-8")

        required = [
            "Provider credentials",
            "Live mutation gates",
            "Research asset specs",
            "src/finharness/okx_cli.py",
            "src/finharness/execution.py",
            "src/finharness/research_assets.py",
            ".github/workflows/security.yml",
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
            "does not authorize live trading",
        ]
        for item in required:
            with self.subTest(item=item):
                self.assertIn(item, text)


if __name__ == "__main__":
    unittest.main()
