from __future__ import annotations

import hashlib
import unittest
from pathlib import Path

from scripts.sync_current_docs import current_markdown_paths, document_lifecycle

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE_ROOT = Path("docs/archive/documentation-lifecycle")
MIGRATED_SHA256 = {
    "docs/architecture/documentation-and-onboarding-plan.md": "054a19b26099756f5eb9537f386031c19283058241135a85704eeb0cea9afc96",
    "docs/architecture/evidence-inventory.md": "ec047175c3c867e699647c1827423aada968bf82efb3fb63877702a4a45bf640",
    "docs/architecture/policy-contract.md": "2adcfb48f1247d29a4471bedc7d7517cae8d814d7630b1e17832a9badfed4280",
    "docs/architecture/agent-native-target-space.md": "f33fd90c8a288419f1d9f53cf791b1a729d06a37a592cc9803b379d37f4dfa17",
    "docs/architecture/closure-report.md": "2e0eb76f820de22c2dd4821a4ab8505f681627f8d1e209a1f27743f2e22954e2",
    "docs/architecture/data-quality-interface-plan.md": "c7e22d00b90575662fb6075e6490f73f2b05841c43d734969fa0fbc9de5ba41e",
    "docs/architecture/market-access-ledger-spec.md": "2b7b4cf4bd9661d946f8b1da2c2b72862438b2c933f8d0a473d069038d9779d3",
    "docs/architecture/policy-evidence-interface-plan.md": "811c61ea01f0b00aff30f074efbcb2ec57f4f3b21bb6d4ca5a6ba73b8afb2299",
    "docs/architecture/post-mvp-maturity-roadmap.md": "d30114d341a0fa10813fd120cb0fd5397fbe4667f81ebb279f85e41203a5f999",
    "docs/architecture/research-interface-vectorbt-spec.md": "f4f75d94e18361d09ea7a2922e12160ce0f7290597c460f178ade6e748041479",
    "docs/engineering/execution-spine-debt-paydown.md": "3261bce0a890f747bd2ffd22a6bfcc40eb825dc721b31732bbc7745a75b1070f",
    "docs/operations/governance-dashboard-latest.md": "50e1b3f994576178256418222a4e9b27dccf1507b32ace4ccee0f4ea432181e3",
    "docs/operations/repository-governance.md": "85aea459d6c13b60e06ca977e43787c3d48b3036a67be80672756faf4e59e9ec",
    "docs/reports/trading-validation-report-v1.md": "0e7c678eef4fba4f851643a7547b34bc9a14d7cd01d4f3abd67119b7082e07e3",
    "docs/security/sbom-and-provenance.md": "224c0e387e1a4515ff673f68063ccfd60f8d9e72e13ad5d0f254dcf858a1f088",
    "docs/architecture/agent-work-loop-plan.md": "972953b96c5ec537436b628211c7db8a3365043690b599400f4da6a0aa3de748",
    "docs/architecture/data-quality-interface-pandera-spec.md": "bda6e230f6016c0659220f1f7609247ca01b58f0d9cf58a6b260a65a753b8306",
    "docs/architecture/data-validity-spec.md": "63ca93ec5b9e39f56ee65099f16cfb8738709fa5cc13525078fdc69a9ba351f5",
    "docs/architecture/graph-rationalization-audit.md": "8a6794f0b08ae062371dc5f3d82e66a3f672f475801b8ce13f6547ef83162c5a",
}


def _archive_path(previous: str) -> Path:
    return ARCHIVE_ROOT / Path(previous).relative_to("docs")


class DocumentationLifecycleMigrationFamilyTest(unittest.TestCase):
    def test_reviewed_family_is_exactly_nineteen_paths(self) -> None:
        self.assertEqual(19, len(MIGRATED_SHA256))

    def test_previous_paths_are_bounded_superseded_stubs(self) -> None:
        current = {
            path.relative_to(ROOT).as_posix() for path in current_markdown_paths()
        }
        for previous in MIGRATED_SHA256:
            path = ROOT / previous
            self.assertEqual("superseded", document_lifecycle(path).state, previous)
            self.assertNotIn(previous, current)
            text = path.read_text(encoding="utf-8")
            self.assertIn("**Current authority:**", text, previous)
            self.assertIn("**Redirect stub:**", text, previous)
            nonblank = [line for line in text.splitlines() if line]
            self.assertLessEqual(len(nonblank), 16)

    def test_archived_bodies_are_exact_and_single_owner(self) -> None:
        for previous, expected in MIGRATED_SHA256.items():
            archived = ROOT / _archive_path(previous)
            self.assertEqual("archived", document_lifecycle(archived).state, previous)
            digest = hashlib.sha256(archived.read_bytes()).hexdigest()
            self.assertEqual(expected, digest, previous)
            text = archived.read_text(encoding="utf-8")
            self.assertNotIn("**Redirect stub:**", text, previous)


if __name__ == "__main__":
    unittest.main()
