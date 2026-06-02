from __future__ import annotations

import unittest

from finharness.providers.ccxt_provider import build_ccxt_source_spec, require_ccxt


class CcxtProviderBoundaryTest(unittest.TestCase):
    def test_source_spec_does_not_require_installed_ccxt(self) -> None:
        source = build_ccxt_source_spec("okx", "markets")

        self.assertEqual(source.provider, "ccxt:okx")
        self.assertEqual(source.asset_class, "crypto")
        self.assertEqual(source.wheel, "ccxt")

    def test_runtime_loader_reports_missing_dependency_cleanly(self) -> None:
        try:
            require_ccxt()
        except RuntimeError as exc:
            self.assertIn("ccxt is not installed", str(exc))


if __name__ == "__main__":
    unittest.main()
