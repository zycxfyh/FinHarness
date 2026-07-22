from __future__ import annotations

import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


class LeanGovernanceP0Test(unittest.TestCase):
    def test_scheduled_gitleaks_checkout_fetches_full_history(self) -> None:
        workflow = yaml.safe_load(
            (ROOT / ".github" / "workflows" / "security.yml").read_text(
                encoding="utf-8"
            )
        )
        checkout = workflow["jobs"]["gitleaks"]["steps"][0]
        self.assertEqual(
            checkout["with"]["fetch-depth"],
            "${{ github.event_name == 'schedule' && '0' || '1' }}",
        )


if __name__ == "__main__":
    unittest.main()
