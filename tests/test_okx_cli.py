from __future__ import annotations

import json
import os
import subprocess
import unittest
from unittest.mock import patch

from finharness.okx_cli import (
    OkxCliError,
    action_is_mutating,
    action_is_read_only,
    candidate_inst_ids,
    normalize_usdt_symbol,
    okx_ticker,
    run_okx_live_mutation_command,
    run_okx_live_read_command,
    run_okx_market_command,
)


class OkxCliTest(unittest.TestCase):
    def test_normalize_compact_usdt_symbol(self) -> None:
        self.assertEqual(normalize_usdt_symbol("btcusdt"), "BTC-USDT")
        self.assertEqual(normalize_usdt_symbol("BTC-USDT"), "BTC-USDT")

    def test_candidate_inst_ids_include_swap_for_app_symbols(self) -> None:
        self.assertEqual(candidate_inst_ids("NVDAUSDT"), ["NVDA-USDT", "NVDA-USDT-SWAP"])

    def test_blocks_non_market_action(self) -> None:
        with self.assertRaises(OkxCliError):
            run_okx_market_command("account", [])

    def test_blocks_live_token(self) -> None:
        with self.assertRaises(OkxCliError):
            run_okx_market_command("ticker", ["BTC-USDT", "--live"])

    @patch("finharness.okx_cli.subprocess.run")
    def test_runs_whitelisted_market_command(self, mock_run) -> None:
        mock_run.return_value = subprocess.CompletedProcess(
            args=["okx"],
            returncode=0,
            stdout=json.dumps([{"instId": "BTC-USDT", "last": "75000"}]),
            stderr="",
        )

        result = okx_ticker("BTCUSDT")

        self.assertEqual(result["last"], "75000")
        mock_run.assert_called_once()
        self.assertEqual(
            mock_run.call_args.args[0],
            ["okx", "--json", "market", "ticker", "BTC-USDT"],
        )

    @patch("finharness.okx_cli.subprocess.run")
    def test_ticker_falls_back_to_swap_instrument(self, mock_run) -> None:
        mock_run.side_effect = [
            subprocess.CompletedProcess(args=["okx"], returncode=1, stdout="", stderr="missing"),
            subprocess.CompletedProcess(
                args=["okx"],
                returncode=0,
                stdout=json.dumps([{"instId": "NVDA-USDT-SWAP", "last": "215"}]),
                stderr="",
            ),
        ]

        result = okx_ticker("NVDAUSDT")

        self.assertEqual(result["instId"], "NVDA-USDT-SWAP")
        self.assertEqual(mock_run.call_args_list[1].args[0][-1], "NVDA-USDT-SWAP")

    def test_classifies_live_read_and_mutating_actions(self) -> None:
        self.assertTrue(action_is_read_only("account", "balance"))
        self.assertTrue(action_is_read_only("swap", "positions"))
        self.assertTrue(action_is_mutating("swap", "place"))
        self.assertTrue(action_is_mutating("account", "transfer"))

    @patch("finharness.okx_cli.subprocess.run")
    def test_runs_live_read_command(self, mock_run) -> None:
        mock_run.return_value = subprocess.CompletedProcess(
            args=["okx"],
            returncode=0,
            stdout=json.dumps({"acctLv": "2"}),
            stderr="",
        )

        result = run_okx_live_read_command("account", "config")

        self.assertEqual(result.data["acctLv"], "2")
        self.assertEqual(
            mock_run.call_args.args[0], ["okx", "--json", "--live", "account", "config"]
        )

    def test_live_mutation_requires_environment_gate(self) -> None:
        with self.assertRaises(OkxCliError):
            run_okx_live_mutation_command(
                "swap",
                "place",
                ["--instId", "BTC-USDT-SWAP", "--side", "buy", "--ordType", "limit", "--sz", "1"],
            )

    # --- kill-switch: compensating control for a missing IP allowlist ----

    @patch("finharness.okx_cli.subprocess.run")
    def test_live_write_blocked_by_kill_switch_even_with_env_gate(self, mock_run) -> None:
        # Env gate open but the kill-switch disarmed (default): the write must be
        # refused before okx is ever invoked.
        env = {"FINHARNESS_OKX_ENABLE_LIVE_MUTATIONS": "1"}
        env.pop("FINHARNESS_OKX_LIVE_WRITE_ARMED", None)
        with patch.dict(os.environ, env, clear=False):
            os.environ.pop("FINHARNESS_OKX_LIVE_WRITE_ARMED", None)
            with self.assertRaises(OkxCliError) as ctx:
                run_okx_live_mutation_command(
                    "swap",
                    "place",
                    [
                        "--instId",
                        "BTC-USDT-SWAP",
                        "--side",
                        "buy",
                        "--ordType",
                        "limit",
                        "--sz",
                        "1",
                    ],
                )
        self.assertIn("kill-switch", str(ctx.exception))
        mock_run.assert_not_called()

    @patch("finharness.okx_cli.subprocess.run")
    def test_live_write_runs_when_armed_and_env_enabled(self, mock_run) -> None:
        # Both deliberate opt-ins present: the write path is allowed to proceed.
        mock_run.return_value = subprocess.CompletedProcess(
            args=["okx"],
            returncode=0,
            stdout=json.dumps({"ordId": "1"}),
            stderr="",
        )
        env = {
            "FINHARNESS_OKX_ENABLE_LIVE_MUTATIONS": "1",
            "FINHARNESS_OKX_LIVE_WRITE_ARMED": "1",
        }
        with patch.dict(os.environ, env, clear=False):
            result = run_okx_live_mutation_command(
                "swap",
                "place",
                [
                    "--instId",
                    "BTC-USDT-SWAP",
                    "--side",
                    "buy",
                    "--ordType",
                    "limit",
                    "--sz",
                    "1",
                ],
            )
        self.assertEqual(result.data["ordId"], "1")
        mock_run.assert_called_once()
        self.assertIn("--live", mock_run.call_args.args[0])

    # --- F8: per-action flag allowlist ----------------------------------

    def test_arg_allowlist_rejects_equals_form_live(self) -> None:
        with self.assertRaises(OkxCliError):
            run_okx_market_command("ticker", ["BTC-USDT", "--live=1"])

    def test_arg_allowlist_rejects_profile_flag(self) -> None:
        with self.assertRaises(OkxCliError):
            run_okx_live_read_command("account", "config", ["--profile=live"])

    def test_arg_allowlist_allows_negative_number_value(self) -> None:
        from finharness.okx_cli import validate_command_args

        # -1 is a price value, not a flag; it must not be rejected.
        validate_command_args("swap", "place", ["--px", "-1", "--sz", "0.01"])

    def test_arg_allowlist_allows_known_place_flags(self) -> None:
        from finharness.okx_cli import validate_command_args

        validate_command_args(
            "swap",
            "place",
            [
                "--instId",
                "BTC-USDT-SWAP",
                "--side",
                "buy",
                "--ordType",
                "limit",
                "--sz",
                "1",
            ],
        )

    # --- F9: redaction ---------------------------------------------------

    def test_redacts_sensitive_response_fields(self) -> None:
        from finharness.okx_cli import redact_okx_output

        out = redact_okx_output(
            {"apiKey": "abc", "data": [{"secretKey": "x", "ccy": "USDT"}]}
        )
        self.assertEqual(out["apiKey"], "***REDACTED***")
        self.assertEqual(out["data"][0]["secretKey"], "***REDACTED***")
        self.assertEqual(out["data"][0]["ccy"], "USDT")

    def test_redacts_secrets_in_stderr_text(self) -> None:
        from finharness.okx_cli import redact_text

        masked = redact_text('error apiKey="LIVEKEY123" passphrase=hunter2')
        self.assertNotIn("LIVEKEY123", masked)
        self.assertNotIn("hunter2", masked)


if __name__ == "__main__":
    unittest.main()
