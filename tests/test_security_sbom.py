from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from scripts.generate_security_sbom import (
    build_provenance_baseline,
    build_sbom,
    write_json,
)


class SecuritySbomTest(unittest.TestCase):
    def test_sbom_baseline_contains_all_project_ecosystems(self) -> None:
        sbom = build_sbom()
        ecosystems = sbom["component_counts_by_ecosystem"]

        self.assertEqual(sbom["schema"], "finharness.local_sbom.v1")
        self.assertFalse(sbom["execution_allowed"])
        self.assertGreater(ecosystems["pypi"], 0)
        self.assertGreater(ecosystems["npm"], 0)
        self.assertGreater(ecosystems["cargo"], 0)
        self.assertGreaterEqual(ecosystems["local"], 2)
        self.assertIn("uv.lock", sbom["source_files"])
        self.assertIn("pnpm-lock.yaml", sbom["source_files"])
        self.assertIn("Cargo.lock", sbom["source_files"])
        self.assertIn("local:finharness@0.1.0", {item["bom_ref"] for item in sbom["components"]})

    def test_provenance_baseline_is_not_formal_attestation(self) -> None:
        sbom = build_sbom()
        provenance = build_provenance_baseline(sbom)

        self.assertEqual(provenance["schema"], "finharness.provenance_baseline.v1")
        self.assertFalse(provenance["execution_allowed"])
        self.assertEqual(provenance["slsa_status"], "planning_baseline_not_attestation")
        self.assertIn("Not a signed SLSA provenance statement.", provenance["non_claims"])
        self.assertTrue(all(item["sha256"] for item in provenance["materials"]))

    def test_sbom_outputs_are_json_serializable(self) -> None:
        sbom = build_sbom()
        provenance = build_provenance_baseline(sbom)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sbom_path = root / "sbom.json"
            provenance_path = root / "provenance.json"

            write_json(sbom_path, sbom)
            write_json(provenance_path, provenance)

            self.assertTrue(sbom_path.exists())
            self.assertTrue(provenance_path.exists())


if __name__ == "__main__":
    unittest.main()
