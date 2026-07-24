from __future__ import annotations

import unittest

from finharness.agent_shell_provider_redline_eval import evaluate_provider_redline


class AgentShellProviderRedlineCorpusTest(unittest.TestCase):
    def test_multilingual_corpus_is_classified_exactly(self) -> None:
        report = evaluate_provider_redline()
        self.assertTrue(report["ok"], report)
        self.assertEqual(report["case_count"], 12)
        self.assertEqual(report["blocked_count"], 9)
        self.assertEqual(report["allowed_count"], 3)
        self.assertEqual(report["failures"], [])


if __name__ == "__main__":
    unittest.main()
