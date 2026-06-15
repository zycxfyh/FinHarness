"""Allowlist policy for the OKX CLI Venue Adapter."""

from __future__ import annotations

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

# Red-team F8: an exact-match denylist (--live, --demo, ...) was bypassable via
# --live=1, --profile=live, abbreviations, etc. Replaced by a per-action flag
# allowlist: any token that looks like a flag must be explicitly permitted for
# that command, otherwise it is rejected (fail-closed).
COMMON_READ_FLAGS = frozenset(
    {
        "--instType",
        "--instId",
        "--uly",
        "--instFamily",
        "--limit",
        "--after",
        "--before",
        "--bar",
        "--ccy",
        "--ordId",
        "--clOrdId",
        "--state",
        "--category",
    }
)

MUTATION_FLAGS: dict[str, frozenset[str]] = {
    "place": frozenset(
        {
            "--instId",
            "--side",
            "--ordType",
            "--sz",
            "--px",
            "--tdMode",
            "--posSide",
            "--reduceOnly",
            "--clOrdId",
            "--tgtCcy",
            "--ccy",
            "--lever",
            "--mgnMode",
        }
    ),
    "amend": frozenset({"--instId", "--ordId", "--clOrdId", "--newSz", "--newPx"}),
    "cancel": frozenset({"--instId", "--ordId", "--clOrdId"}),
    "batch": frozenset({"--instId", "--ordId", "--clOrdId"}),
    "batch-cancel": frozenset({"--instId", "--ordId", "--clOrdId"}),
    "close": frozenset({"--instId", "--mgnMode", "--posSide", "--ccy"}),
    "leverage": frozenset({"--instId", "--lever", "--mgnMode", "--posSide"}),
    "set-position-mode": frozenset({"--posMode"}),
    "transfer": frozenset({"--ccy", "--amt", "--from", "--to", "--type"}),
}


def action_is_read_only(module: str, action: str) -> bool:
    return action in READ_ONLY_ACTIONS.get(module, frozenset())


def action_is_mutating(module: str, action: str) -> bool:
    return action in MUTATING_ACTIONS.get(module, frozenset())


def allowed_flags(module: str, action: str) -> frozenset[str]:
    """Flags this command may carry. Empty means no flags allowed."""
    if action_is_mutating(module, action):
        return MUTATION_FLAGS.get(action, frozenset())
    if action_is_read_only(module, action):
        return COMMON_READ_FLAGS
    return frozenset()


def looks_like_flag(token: str) -> bool:
    """True for --flag / -f, but not for negative numbers like -1 or -0.5."""
    if not token.startswith("-"):
        return False
    stripped = token.lstrip("-")
    return bool(stripped) and not stripped[0].isdigit()


def disallowed_flag(module: str, action: str, args: list[str]) -> str | None:
    """Return the first flag not permitted for this module/action, if any."""
    allowed = allowed_flags(module, action)
    for token in args:
        if not looks_like_flag(token):
            continue
        name = token.split("=", 1)[0]
        if name not in allowed:
            return name
    return None


def blocked_tokens(module: str, action: str, args: list[str]) -> list[str]:
    """Return blocked OKX command tokens."""
    return [token for token in [module, action, *args] if token in BLOCKED_TOKENS]
