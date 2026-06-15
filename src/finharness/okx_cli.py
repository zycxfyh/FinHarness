"""OKX CLI adapter with explicit read/write safety gates."""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from typing import Any

from finharness.okx_policy import (
    action_is_mutating,
    action_is_read_only,
    blocked_tokens,
    disallowed_flag,
)
from finharness.okx_redaction import redact_okx_output, redact_text
from finharness.okx_symbols import candidate_inst_ids, normalize_usdt_symbol

__all__ = [
    "OkxCliError",
    "OkxCliResult",
    "action_is_mutating",
    "action_is_read_only",
    "candidate_inst_ids",
    "normalize_usdt_symbol",
    "okx_ticker",
    "redact_okx_output",
    "redact_text",
    "run_okx_command",
    "run_okx_live_mutation_command",
    "run_okx_live_read_command",
    "run_okx_market_command",
    "validate_command_args",
]


class OkxCliError(RuntimeError):
    """Raised when the OKX CLI command cannot be run safely or successfully."""


@dataclass(frozen=True)
class OkxCliResult:
    module: str
    action: str
    command: list[str]
    data: Any


def live_mutations_enabled() -> bool:
    return os.environ.get("FINHARNESS_OKX_ENABLE_LIVE_MUTATIONS") == "1"


# Compensating control for deployments without an OKX IP allowlist (e.g. a
# rotating-IP VPN). The IP allowlist normally bounds a leaked key to known IPs;
# without it, this hard kill-switch keeps live writes impossible through the
# harness unless an operator deliberately arms it. It defaults to DISARMED
# (fail-closed) and is independent of FINHARNESS_OKX_ENABLE_LIVE_MUTATIONS, so a
# live write now requires two separate, deliberate opt-ins. Reads are never
# affected.
OKX_LIVE_WRITE_ARM_ENV = "FINHARNESS_OKX_LIVE_WRITE_ARMED"


def live_writes_armed() -> bool:
    return os.environ.get(OKX_LIVE_WRITE_ARM_ENV) == "1"


def validate_command_args(module: str, action: str, args: list[str]) -> None:
    """Reject any flag not on the per-action allowlist (red-team F8).

    Catches --live=1, --profile=live, --env=prod, and short/abbreviated forms by
    construction: a flag-looking token outside the allowlist is refused. Non-flag
    tokens (instrument ids, sizes, prices) pass through for okx to validate.
    """
    name = disallowed_flag(module, action, args)
    if name is not None:
        raise OkxCliError(f"argument flag not allowed for {module} {action}: {name}")


def run_okx_command(
    module: str,
    action: str,
    args: list[str] | None = None,
    *,
    live: bool = False,
    demo: bool = False,
    allow_mutation: bool = False,
    timeout_seconds: int = 20,
) -> OkxCliResult:
    """Run an OKX CLI command through explicit module/action allowlists."""
    if live and demo:
        raise OkxCliError("--live and --demo are mutually exclusive")

    read_only = action_is_read_only(module, action)
    mutating = action_is_mutating(module, action)
    if not read_only and not mutating:
        raise OkxCliError(f"blocked OKX command: {module} {action}")

    if mutating and not allow_mutation:
        raise OkxCliError(f"mutation requires explicit approval: {module} {action}")
    # Hard kill-switch (compensating control for a missing IP allowlist). Checked
    # before the env gate so a live write needs both this and the env opt-in.
    if mutating and live and not live_writes_armed():
        raise OkxCliError(
            f"live OKX writes are disabled by kill-switch ({OKX_LIVE_WRITE_ARM_ENV}!=1); "
            "compensating control for no IP allowlist"
        )
    if mutating and live and not live_mutations_enabled():
        raise OkxCliError("live mutation requires FINHARNESS_OKX_ENABLE_LIVE_MUTATIONS=1")

    safe_args = args or []
    blocked = blocked_tokens(module, action, safe_args)
    if blocked:
        raise OkxCliError(f"blocked OKX token(s): {blocked}")
    # F8: per-action flag allowlist (replaces the bypassable arg denylist).
    validate_command_args(module, action, safe_args)

    command = ["okx", "--json"]
    if live:
        command.append("--live")
    if demo:
        command.append("--demo")
    command.extend([module, action, *safe_args])
    completed = subprocess.run(
        command,
        text=True,
        capture_output=True,
        timeout=timeout_seconds,
        check=False,
    )
    if completed.returncode != 0:
        # F9: never surface raw stderr; secrets can appear in error payloads.
        stderr = redact_text(completed.stderr.strip())
        raise OkxCliError(f"okx command failed with exit {completed.returncode}: {stderr}")

    try:
        data = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise OkxCliError("okx command did not return JSON") from exc

    # F9: mask sensitive fields before any caller can log/store the response.
    return OkxCliResult(
        module=module, action=action, command=command, data=redact_okx_output(data)
    )


def run_okx_market_command(
    action: str,
    args: list[str] | None = None,
    timeout_seconds: int = 20,
) -> OkxCliResult:
    """Run a whitelisted public OKX market command through the official CLI."""
    return run_okx_command("market", action, args, timeout_seconds=timeout_seconds)


def run_okx_live_read_command(
    module: str,
    action: str,
    args: list[str] | None = None,
    timeout_seconds: int = 20,
) -> OkxCliResult:
    """Run a read-only command against the live OKX profile."""
    if not action_is_read_only(module, action):
        raise OkxCliError(f"not a live read-only command: {module} {action}")
    return run_okx_command(
        module,
        action,
        args,
        live=True,
        timeout_seconds=timeout_seconds,
    )


def run_okx_live_mutation_command(
    module: str,
    action: str,
    args: list[str] | None = None,
    timeout_seconds: int = 20,
) -> OkxCliResult:
    """Run a live mutating command after both code and env gates are opened."""
    return run_okx_command(
        module,
        action,
        args,
        live=True,
        allow_mutation=True,
        timeout_seconds=timeout_seconds,
    )


def okx_ticker(symbol: str) -> dict[str, Any]:
    """Fetch one public ticker snapshot."""
    errors: list[str] = []
    for inst_id in candidate_inst_ids(symbol):
        try:
            result = run_okx_market_command("ticker", [inst_id])
        except OkxCliError as exc:
            errors.append(str(exc))
            continue

        if not isinstance(result.data, list) or not result.data:
            errors.append(f"empty ticker response for {inst_id}")
            continue

        first = result.data[0]
        if not isinstance(first, dict):
            errors.append(f"unexpected ticker response for {inst_id}")
            continue
        return first

    raise OkxCliError(f"no ticker found for {symbol}; tried {candidate_inst_ids(symbol)}: {errors}")
