"""OKX CLI adapter with explicit read/write safety gates."""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from typing import Any

ALLOWED_MARKET_ACTIONS = frozenset(
    {
        "ticker",
        "tickers",
        "orderbook",
        "candles",
        "instruments",
        "funding-rate",
        "mark-price",
        "trades",
        "index-ticker",
        "index-candles",
        "price-limit",
        "open-interest",
        "stock-tokens",
        "instruments-by-category",
        "filter",
        "oi-history",
        "oi-change",
        "pair-spread",
    }
)

READ_ONLY_ACTIONS: dict[str, frozenset[str]] = {
    "market": ALLOWED_MARKET_ACTIONS,
    "account": frozenset(
        {
            "balance",
            "asset-balance",
            "positions",
            "positions-history",
            "bills",
            "fees",
            "config",
            "max-size",
            "max-avail-size",
            "max-withdrawal",
            "audit",
        }
    ),
    "spot": frozenset({"orders", "get", "fills"}),
    "swap": frozenset({"positions", "orders", "get", "fills", "get-leverage"}),
    "futures": frozenset({"positions", "orders", "get", "fills", "get-leverage"}),
    "option": frozenset({"orders", "get", "positions", "fills", "instruments", "greeks"}),
}

MUTATING_ACTIONS: dict[str, frozenset[str]] = {
    "account": frozenset({"set-position-mode", "transfer"}),
    "spot": frozenset({"place", "amend", "cancel", "batch", "leverage"}),
    "swap": frozenset({"place", "amend", "cancel", "batch", "close", "leverage"}),
    "futures": frozenset({"place", "amend", "cancel", "batch", "close", "leverage"}),
    "option": frozenset({"place", "amend", "cancel", "batch-cancel"}),
}

BLOCKED_TOKENS = frozenset(
    {
        "earn",
        "bot",
        "event",
        "smartmoney",
        "setup",
        "pilot",
        "skill",
        "upgrade",
    }
)

BLOCKED_ARG_TOKENS = frozenset({"--live", "--demo", "--json", "--env", "--profile"})


class OkxCliError(RuntimeError):
    """Raised when the OKX CLI command cannot be run safely or successfully."""


@dataclass(frozen=True)
class OkxCliResult:
    module: str
    action: str
    command: list[str]
    data: Any


def normalize_usdt_symbol(symbol: str) -> str:
    """Normalize compact OKX app-style symbols such as BTCUSDT into BTC-USDT."""
    clean = symbol.strip().upper()
    if "-" in clean:
        return clean
    if clean.endswith("USDT") and len(clean) > 4:
        return f"{clean[:-4]}-USDT"
    return clean


def candidate_inst_ids(symbol: str) -> list[str]:
    """Return likely OKX instrument IDs for app-style symbols."""
    normalized = normalize_usdt_symbol(symbol)
    candidates = [normalized]
    if normalized.endswith("-USDT") and not normalized.endswith("-USDT-SWAP"):
        candidates.append(f"{normalized}-SWAP")
    return candidates


def action_is_read_only(module: str, action: str) -> bool:
    return action in READ_ONLY_ACTIONS.get(module, frozenset())


def action_is_mutating(module: str, action: str) -> bool:
    return action in MUTATING_ACTIONS.get(module, frozenset())


def live_mutations_enabled() -> bool:
    return os.environ.get("FINHARNESS_OKX_ENABLE_LIVE_MUTATIONS") == "1"


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
    if mutating and live and not live_mutations_enabled():
        raise OkxCliError("live mutation requires FINHARNESS_OKX_ENABLE_LIVE_MUTATIONS=1")

    safe_args = args or []
    blocked = [token for token in [module, action, *safe_args] if token in BLOCKED_TOKENS]
    blocked.extend(token for token in safe_args if token in BLOCKED_ARG_TOKENS)
    if blocked:
        raise OkxCliError(f"blocked OKX token(s): {blocked}")

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
        stderr = completed.stderr.strip()
        raise OkxCliError(f"okx command failed with exit {completed.returncode}: {stderr}")

    try:
        data = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise OkxCliError("okx command did not return JSON") from exc

    return OkxCliResult(module=module, action=action, command=command, data=data)


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
